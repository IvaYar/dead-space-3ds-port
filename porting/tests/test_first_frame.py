"""ARM tests for the directory ABI, matrices and actual triangle/texture pixels."""
import hashlib,json,struct,sys,time,unittest,uuid
from pathlib import Path
import test_gles_state as gl
PORTING=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PORTING/'tools'))
from run_engine_experiment import Experiment,CTX,OUT
DATA=0x06008000;RESULT=0x06009800
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.e=Experiment(PORTING/'3ds/build-emulator/core-test.elf');self.arm=self.e.arm;self.handles=[]
    def tearDown(self):
        for h in self.handles:self.arm.call('ds20_closedir',h)
        self.assertEqual(self.arm.call('ds20_active'),0)
    def path(self,s):self.arm.uc.mem_write(DATA,s.encode()+b'\0');return DATA
    def error(self):return self.e.words(self.arm.call('ds_io_errno'))[0]
    def opendir(self,s='published/data'):
        h=self.arm.call('ds20_opendir',self.path(s))
        if h:self.handles.append(h)
        return h
    def entry(self,h):
        self.arm.uc.mem_write(RESULT,b'Z'*296);self.e.write(OUT,0x12345678)
        result=self.arm.call('ds20_readdir_r',h,RESULT,OUT);pointer=self.e.words(OUT)[0]
        self.assertEqual(bytes(self.arm.uc.mem_read(RESULT+280,16)),b'Z'*16)
        return result,pointer,bytes(self.arm.uc.mem_read(RESULT,280))
    def test_appdata_roots_and_generated_double_separator(self):
        for p,tail in [('appdata:/',''),('appdata://',''),('appdata://var/','var'),('appdata:/var/settings.sb','var/settings.sb')]:
            self.assertEqual(self.arm.call('ds6_map_path',self.path(p),OUT,1),0);self.assertEqual(self.e.string(OUT),'sdmc:/3ds/deadspace/test-output/'+tail)
    def test_paths_reject_traversal_unknown_mounts_and_readonly_writes(self):
        for p in ('appdata:/../x','appdata://a/../../x','appdata:///x','appdata:/a//b','appdata:/x:y','appdata:/x\\y'):
            self.assertEqual(self.arm.call('ds6_map_path',self.path(p),OUT,1),0xffffffff,p)
        for p in ('published/data','/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/published/data'):
            self.assertEqual(self.arm.call('ds6_mkdir',self.path(p),0o755),0xffffffff);self.assertEqual(self.error(),30)
    def test_real_private_directory_creation_and_stat_roundtrip(self):
        name='ds20-unit-'+uuid.uuid4().hex;logical='appdata://'+name;actual=PORTING/'analysis/unicorn-userdata'/name
        try:
            self.assertEqual(self.arm.call('ds6_mkdir',self.path(logical),0o755),0);self.assertTrue(actual.is_dir())
            self.assertEqual(self.arm.call('ds6_stat',self.path(logical),RESULT),0);self.assertEqual(self.e.words(RESULT+16)[0]&0o170000,0o40000)
            self.assertEqual(self.arm.call('ds6_mkdir',self.path(logical),0o755),0xffffffff);self.assertEqual(self.error(),17)
        finally:
            if actual.exists():actual.rmdir()
    def test_root_and_external_cache_metadata_come_from_real_backend(self):
        for p in ('/','appdata:/','/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/published'):
            self.assertEqual(self.arm.call('ds6_stat',self.path(p),RESULT),0);self.assertEqual(self.e.words(RESULT+16)[0]&0o170000,0o40000)
        p='/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/Downloaded.indicate'
        self.assertEqual(self.arm.call('ds6_stat',self.path(p),RESULT),0);self.assertEqual(struct.unpack('<Q',self.arm.uc.mem_read(RESULT+48,8))[0],58)
    def test_bionic_dirent_layout_names_types_and_eof(self):
        h=self.opendir();self.assertTrue(h);names=[]
        for _ in range(100):
            result,pointer,entry=self.entry(h);self.assertEqual(result,0)
            if not pointer:break
            self.assertEqual(pointer,RESULT);name=entry[19:].split(b'\0',1)[0].decode();names.append(name)
            ino,offset,reclen,type_=struct.unpack_from('<QqHB',entry);self.assertEqual(offset,len(names));self.assertEqual(reclen%8,0);self.assertGreaterEqual(reclen,20+len(name.encode()));self.assertEqual(type_,8)
        expected=sorted(p.name for p in (PORTING/'analysis/candidate-sd/assets/published/data').iterdir());self.assertEqual(sorted(names),expected)
        self.assertEqual(self.entry(h)[:2],(0,0))
    def test_missing_file_and_invalid_directory_are_errors(self):
        self.assertEqual(self.opendir('published/not-present'),0);self.assertEqual(self.error(),2)
        self.assertEqual(self.opendir('published/data/achievements.sb'),0)
    def test_directory_capacity_close_and_stale_handle(self):
        handles=[self.opendir() for _ in range(8)];self.assertNotIn(0,handles);self.assertEqual(self.opendir(),0);self.assertEqual(self.error(),24)
        old=self.handles.pop();self.assertEqual(self.arm.call('ds20_closedir',old),0);new=self.opendir();self.assertTrue(new);self.assertNotEqual(old,new)
        result,pointer,entry=self.entry(old);self.assertEqual((result,pointer),(9,0));self.assertEqual(entry,b'Z'*280)
    def test_bad_result_and_entry_arguments_do_not_call_backend(self):
        h=self.opendir();self.assertEqual(self.arm.call('ds20_readdir_r',h,0,OUT),22);self.assertEqual(self.arm.call('ds20_readdir_r',h,RESULT,0),22)
        self.assertEqual(self.entry(h)[0],0)
    def test_backend_error_preserves_caller_entry_and_returns_errno(self):
        h=self.opendir();original=self.e.host_directory_call
        def fail_next(op):
            if op==1:
                from run_engine_experiment import REGS
                p=self.arm.uc.reg_read(REGS[2]);self.e.write(p,5);return -1
            return original(op)
        self.e.host_directory_call=fail_next
        result,pointer,entry=self.entry(h);self.assertEqual((result,pointer),(5,0));self.assertEqual(entry,b'Z'*280)
    def test_backend_reset_refuses_live_directory(self):
        self.opendir();self.assertEqual(self.arm.call('ds20_init',CTX+0x180),16)
class DrawTests(gl.GlesTests):
    def setUp(self):
        super().setUp();self.arm.call('ds22_client_range',gl.CTX,DATA,4096)
        self.color(0,0,0);self.call('glClear',0x4000)
    def floats(self,p,values):self.arm.uc.mem_write(p,struct.pack('<'+'f'*len(values),*values));return p
    def quad(self,coords=None):
        vertices=coords or (-1,-1,0,1,-1,0,-1,1,0,1,1,0)
        self.floats(DATA,vertices);self.call('glVertexPointer',3,0x1406,0,DATA);self.call('glEnableClientState',0x8074)
    def rgba(self,*v):self.call('glColor4f',*(bits(x) for x in v))
    def stats(self):self.arm.call('ds22_stats',gl.CTX,RESULT);return self.base.words(RESULT,4)
    def mat(self,name=0xba6):self.call('glGetFloatv',name,RESULT);return struct.unpack('<16f',self.arm.uc.mem_read(RESULT,64))
    def transform(self,v,mode=0x1700,unit=0):
        self.floats(DATA+700,v);self.arm.call('ds21_transform',gl.CTX,mode,unit,DATA+700,RESULT);return struct.unpack('<4f',self.arm.uc.mem_read(RESULT,16))
    def texture(self,linear=False,format=0x1908,pixels=None):
        self.call('glGenTextures',1,RESULT);name=self.base.words(RESULT)[0];self.call('glBindTexture',0xde1,name)
        f=0x2601 if linear else 0x2600
        self.call('glTexParameteri',0xde1,0x2801,f);self.call('glTexParameteri',0xde1,0x2800,f)
        self.call('glTexParameteri',0xde1,0x2802,0x812f);self.call('glTexParameteri',0xde1,0x2803,0x812f)
        raw=pixels if pixels is not None else bytes((255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255))
        self.arm.uc.mem_write(DATA+300,raw);self.call('glPixelStorei',0xcf5,1);self.call('glTexImage2D',0xde1,0,format,2,2,0,format,0x1401,DATA+300)
        self.floats(DATA+128,(0,0,1,0,0,1,1,1));self.call('glTexCoordPointer',2,0x1406,0,DATA+128);self.call('glEnableClientState',0x8078);self.call('glEnable',0xde1);return name
    def test_identity_queries_and_default_framebuffer_validation(self):
        self.assertEqual(self.mat(),tuple(float(i%5==0) for i in range(16)));self.call('glBindFramebufferOES',0x8d40,0);self.assertEqual(self.query(0x8ca6,1),(0,))
        self.call('glBindFramebufferOES',0xdead,0);self.assertEqual(self.call('glGetError'),0x500)
        self.call('glBindFramebufferOES',0x8d40,17);self.assertEqual(self.call('glGetError'),0x500)
    def test_postmultiply_translation_scale_and_fixed_variants(self):
        self.call('glTranslatef',bits(1),bits(2),bits(3));self.call('glScalex',2*65536,3*65536,4*65536)
        self.assertEqual(self.transform((1,1,1,1)),(3,5,7,1));self.call('glLoadIdentity');self.assertEqual(self.transform((1,2,3,1)),(1,2,3,1))
    def test_axis_rotation_and_zero_axis(self):
        self.call('glRotatef',bits(90),0,0,bits(1));v=self.transform((1,0,0,1));self.assertAlmostEqual(v[0],0,places=5);self.assertAlmostEqual(v[1],1,places=5)
        old=self.mat();self.call('glRotatef',bits(30),0,0,0);self.assertEqual(self.mat(),old)
    def test_projection_and_texture_stacks_are_independent(self):
        self.call('glMatrixMode',0x1701);self.call('glOrthof',bits(0),bits(4),bits(0),bits(3),bits(-1),bits(1));self.assertEqual(self.transform((4,3,0,1),0x1701),(1,1,0,1))
        self.call('glMatrixMode',0x1702);self.call('glTranslatex',65536,0,0);self.call('glActiveTexture',0x84c1)
        self.assertEqual(self.transform((0,0,0,1),0x1702,0),(1,0,0,1));self.assertEqual(self.transform((0,0,0,1),0x1702,1),(0,0,0,1))
    def test_stack_bounds_restore_and_no_partial_matrix_query(self):
        self.call('glMatrixMode',0x1701);self.call('glPushMatrix');self.call('glTranslatex',65536,0,0);self.call('glPushMatrix');self.assertEqual(self.call('glGetError'),0x503)
        self.call('glPopMatrix');self.assertEqual(self.mat(0xba7)[12],0);self.call('glPopMatrix');self.assertEqual(self.call('glGetError'),0x504)
        self.arm.uc.mem_write(RESULT,b'Z'*80);self.call('glGetFloatv',0xba7,RESULT);self.assertEqual(bytes(self.arm.uc.mem_read(RESULT+64,16)),b'Z'*16)
    def test_invalid_matrix_projection_keeps_previous_state(self):
        before=self.mat();self.call('glFrustumf',bits(-1),bits(1),bits(-1),bits(1),bits(0),bits(10));self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.mat(),before)
        self.floats(DATA,(float('nan'),)*16);self.call('glLoadMatrixf',DATA);self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.mat(),before)
    def test_solid_quad_covers_target_once(self):
        self.quad();self.rgba(1,0,0,1);self.call('glDrawArrays',5,0,4);self.assertEqual(self.pixels(),b'\xff\0\0'*12);self.assertEqual(self.stats(),(1,2,12,0))
    def test_indexed_triangle_list_and_bound_element_buffer(self):
        self.quad();self.rgba(0,1,0,1);self.arm.uc.mem_write(DATA+512,struct.pack('<6H',0,1,2,2,1,3))
        self.call('glGenBuffers',1,RESULT);buffer=self.base.words(RESULT)[0];self.call('glBindBuffer',0x8893,buffer);self.call('glBufferData',0x8893,12,DATA+512,0x88e4)
        self.call('glDrawElements',4,6,0x1403,0);self.assertEqual(self.pixels(),b'\0\xff\0'*12);self.assertEqual(self.stats(),(1,2,12,0))
    def test_homogeneous_clipping_and_scissor(self):
        self.quad();self.rgba(1,0,0,1);self.call('glTranslatex',65536,0,0);self.call('glEnable',0xc11);self.call('glScissor',2,1,1,1);self.call('glDrawArrays',5,0,4)
        expected=bytearray(36);expected[(1*4+2)*3]=255;self.assertEqual(self.pixels(),bytes(expected));self.assertEqual(self.stats()[2],1)
    def test_blending_alpha_and_shared_edges(self):
        self.quad();self.rgba(1,0,0,.5);self.call('glEnable',0xbe2);self.call('glBlendFunc',0x302,0x303);self.call('glDrawArrays',5,0,4)
        self.assertEqual(self.pixels(),bytes((128,0,0))*12);self.assertEqual(self.stats()[2],12)
    def test_alpha_test_cull_and_color_mask(self):
        self.quad();self.rgba(1,1,1,.25);self.call('glEnable',0xbc0);self.call('glAlphaFunc',0x204,bits(.5));self.call('glDrawArrays',5,0,4);self.assertEqual(self.stats()[2],0)
        self.call('glDisable',0xbc0);self.call('glEnable',0xb44);self.call('glCullFace',0x404);self.call('glDrawArrays',5,0,4);self.assertEqual(self.stats()[2],0)
        self.call('glDisable',0xb44);self.call('glColorMask',0,1,0,0);self.call('glDrawArrays',5,0,4);self.assertEqual(self.pixels(),b'\0\xff\0'*12)
    def test_nearest_textured_quad_uses_actual_rgba_store(self):
        self.quad();self.texture();self.call('glDrawArrays',5,0,4)
        want=bytes((255,0,0))*2+bytes((0,255,0))*2+(bytes((0,0,255))*2+bytes((255,255,255))*2)*2
        self.assertEqual(self.pixels(),want);self.assertEqual(self.stats(),(1,2,12,12))
    def test_bilinear_sampling_interpolates_texels(self):
        self.quad();self.texture(True);self.call('glDrawArrays',5,0,4);self.assertEqual(self.pixels()[(1*4+1)*3:(1*4+1)*3+3],bytes((128,64,128)))
    def test_repeat_and_clamp_of_outside_coordinates(self):
        self.quad();self.texture();self.floats(DATA+128,(-.25,-.25)*4);self.call('glTexParameteri',0xde1,0x2802,0x2901);self.call('glTexParameteri',0xde1,0x2803,0x2901)
        self.call('glDrawArrays',5,0,4);self.assertEqual(self.pixels(),b'\xff\xff\xff'*12)
    def test_replace_alpha_texture_preserves_primary_rgb(self):
        self.quad();self.texture(format=0x1906,pixels=b'\x80'*4);self.rgba(1,0,0,.25);self.call('glTexEnvi',0x2300,0x2200,0x1e01)
        self.call('glDrawArrays',5,0,4);self.assertEqual(self.pixels(),b'\xff\0\0'*12)
    def test_alpha_only_glyph_texture_keeps_rgb_and_modulates_coverage(self):
        self.quad();self.texture(format=0x1906,pixels=b'\x80'*4);self.rgba(1,.5,0,1)
        self.call('glEnable',0xbe2);self.call('glBlendFunc',0x302,0x303)
        for mode in (0x2100,0x104,0xbe2,0x1e01):
            with self.subTest(mode=mode):
                self.arm.uc.mem_write(gl.PIX,b'\0'*36)
                self.call('glTexEnvi',0x2300,0x2200,mode);self.call('glDrawArrays',5,0,4)
                self.assertEqual(self.pixels(),bytes((128,64,0))*12)
    def test_texture_environment_color_fixed_and_integer_queries(self):
        self.arm.uc.mem_write(DATA,struct.pack('<4i',65536,32768,0,65536));self.call('glTexEnvxv',0x2300,0x2201,DATA)
        self.call('glGetTexEnvfv',0x2300,0x2201,RESULT);self.assertEqual(struct.unpack('<4f',self.arm.uc.mem_read(RESULT,16)),(1,.5,0,1))
        self.call('glGetTexEnviv',0x2300,0x2201,RESULT);self.assertEqual(self.base.words(RESULT,4),(0x7fffffff,0x3fffffff,0,0x7fffffff))
    def test_invalid_client_pointer_or_index_changes_no_pixels(self):
        self.quad();before=self.pixels();self.call('glVertexPointer',3,0x1406,0,0x4000);self.call('glDrawArrays',5,0,4);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.pixels(),before)
        self.quad();self.arm.uc.mem_write(DATA+512,b'\0\0\xff\xff\2\0');self.call('glDrawElements',4,3,0x1403,DATA+512);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.pixels(),before)
    def test_unsupported_lighting_mipmap_and_combiner_are_explicit(self):
        self.quad();self.call('glEnable',0xb50);self.call('glDrawArrays',5,0,4);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.stats()[2],0)
        self.call('glDisable',0xb50);self.texture();self.call('glTexParameteri',0xde1,0x2801,0x2702);self.call('glDrawArrays',5,0,4);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.stats()[2],0)
        self.call('glTexEnvi',0x2300,0x2200,0x8570);self.assertEqual(self.call('glGetError'),0x500)
    def test_large_viewport_offset_is_bounded_without_writes(self):
        self.quad();self.call('glViewport',0x7fffffff,0x7fffffff,4,3);self.call('glDrawArrays',5,0,4);self.assertEqual(self.stats()[2],0);self.assertEqual(self.pixels(),b'\0'*36)
    def test_new_matrix_and_draw_storage_is_released_on_close(self):
        self.call('glLoadIdentity');self.rgba(.5,.5,.5,1);self.arm.call('ds13_close',gl.CTX);self.arm.call('ds_runtime_stats',RESULT);self.assertEqual(self.base.words(RESULT,9)[4:6],(0,0))
if __name__=='__main__':
    started=time.monotonic();suite=unittest.TestSuite()
    for cls in (FilesystemTests,DrawTests):suite.addTests(cls(n) for n in cls.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((PORTING/'3ds/build-emulator/core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (PORTING/'analysis/first-frame-tests.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
