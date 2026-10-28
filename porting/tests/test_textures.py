"""Actual ARM texture stores, row unpacking, conversion and lifetime."""
import hashlib,json,struct,time,unittest
import test_gles_state as gl
from test_arm_loader import FILE_ADDR,INFO_ADDR,IMAGE_ADDR
DATA=0x16000400;RESULT=0x16000600;T=0xde1;RGBA=0x1908;RGB=0x1907;UB=0x1401
class TextureTests(gl.GlesTests):
    def names(self,n=1):
        self.call('glGenTextures',n,gl.OUT);return self.base.words(gl.OUT,n)
    def bind(self,name=None):
        if name is None:name=self.names()[0]
        self.call('glBindTexture',T,name);return name
    def stats(self):self.arm.call('ds15_test_stats',gl.OUT);return self.base.words(gl.OUT,4)
    def image(self,w=2,h=2,data=bytes(range(16)),fmt=RGBA,typ=UB,level=0):
        if data is not None:self.arm.uc.mem_write(DATA,data)
        self.call('glTexImage2D',T,level,fmt,w,h,0,fmt,typ,DATA if data is not None else 0)
    def texel(self,name,x=0,y=0,level=0):
        self.arm.uc.mem_write(RESULT,b'ZZZZ');code=self.arm.call('ds15_test_read',name,level,x,y,RESULT)
        return code,bytes(self.arm.uc.mem_read(RESULT,4))
    def param(self,name):
        self.call('glGetTexParameteriv',T,name,gl.OUT);return self.base.words(gl.OUT)[0]
    def test_names_reserved_then_created_and_arbitrary_binding(self):
        a,b=self.names(2);self.assertNotEqual(a,b);self.assertEqual(self.call('glIsTexture',a),0)
        self.bind(a);self.assertEqual(self.call('glIsTexture',a),1);self.assertEqual(self.call('glIsTexture',0),0)
        self.bind(0xffffffff);self.assertEqual(self.call('glIsTexture',0xffffffff),1)
    def test_two_server_units_share_objects_and_have_separate_enable(self):
        a=self.bind();self.image();self.call('glEnable',T);self.call('glActiveTexture',0x84c1)
        self.assertEqual(self.query(0x8069,1),(0,));self.assertEqual(self.call('glIsEnabled',T),0)
        self.bind(a);self.assertEqual(self.texel(a,1,1),(0,bytes(range(12,16))))
        self.call('glClientActiveTexture',0x84c0);self.assertEqual(self.query(0x8069,1),(a,))
    def test_default_texture_zero_is_real_shared_storage(self):
        self.image();self.assertEqual(self.texel(0),(0,bytes(range(4))))
        self.call('glActiveTexture',0x84c1);self.assertEqual(self.query(0x8069,1),(0,));self.assertEqual(self.texel(0,1,1)[0],0)
    def test_upload_copies_pixels_and_subimage_patches_selected_rectangle(self):
        a=self.bind();self.image();self.arm.uc.mem_write(DATA,b'abcd')
        self.call('glTexSubImage2D',T,0,1,0,1,1,RGBA,UB,DATA)
        self.assertEqual(self.texel(a,1,0),(0,b'abcd'));self.assertEqual(self.texel(a,1,1),(0,bytes(range(12,16))))
        self.assertEqual(self.stats(),(1,16,1,1))
    def test_unpack_alignment_skips_row_padding_and_no_final_padding_read(self):
        a=self.bind();self.image(1,2,b'abcZdef',RGB)
        self.assertEqual(self.texel(a,0,0),(0,b'abc\xff'));self.assertEqual(self.texel(a,0,1),(0,b'def\xff'))
        self.call('glPixelStorei',0xcf5,1);self.image(1,2,b'ghijkl',RGB)
        self.assertEqual(self.texel(a,0,1),(0,b'jkl\xff'))
    def test_alpha_luminance_and_luminance_alpha_conversion(self):
        a=self.bind()
        for fmt,data,want in ((0x1906,b'\x36',b'\0\0\0\x36'),(0x1909,b'\x52',b'\x52\x52\x52\xff'),(0x190a,b'\x63\x27',b'\x63\x63\x63\x27')):
            self.image(1,1,data,fmt);self.assertEqual(self.texel(a),(0,want))
    def test_packed_565_4444_5551_conversion_and_subimage_type_change(self):
        a=self.bind()
        for fmt,typ,value,want in ((RGB,0x8363,0xf81f,b'\xff\0\xff\xff'),(RGBA,0x8033,0x1234,bytes((17,34,51,68))),(RGBA,0x8034,0x07c1,b'\0\xff\0\xff')):
            self.image(1,1,struct.pack('<H',value),fmt,typ);self.assertEqual(self.texel(a),(0,want))
        self.arm.uc.mem_write(DATA,b'abcd');self.call('glTexSubImage2D',T,0,0,0,1,1,RGBA,UB,DATA);self.assertEqual(self.texel(a),(0,b'abcd'))
    def test_mipmap_levels_are_independent_and_size_limited(self):
        a=self.bind();self.image();self.image(1,1,b'abcd',level=1)
        self.assertEqual(self.texel(a,level=1),(0,b'abcd'));self.assertEqual(self.texel(a),(0,bytes(range(4))))
        self.image(2,2,level=10);self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.texel(a,level=10)[0],0xffffffff)
    def test_invalid_uploads_are_atomic_and_do_not_replace_store(self):
        a=self.bind();self.image()
        for args,err in (((T,0,RGBA,3,2,0,RGBA,UB,DATA),0x501),((T,0,RGB,2,2,0,RGBA,UB,DATA),0x502),((T,-1,RGBA,2,2,0,RGBA,UB,DATA),0x501),((T,0,RGBA,2,2,1,RGBA,UB,DATA),0x501),((T,0,RGBA,2,2,0,RGBA,0x8363,DATA),0x502),((T,0,RGBA,2,2,0,RGBA,0xdead,DATA),0x500)):
            self.call('glTexImage2D',*args);self.assertEqual(self.call('glGetError'),err);self.assertEqual(self.texel(a),(0,bytes(range(4))))
    def test_invalid_subimages_leave_entire_image_unchanged(self):
        a=self.bind();self.image()
        for x,y,w,h in ((-1,0,1,1),(2,0,1,1),(0,1,2,2),(0,0,-1,1),(0x7fffffff,0,1,1)):
            self.call('glTexSubImage2D',T,0,x,y,w,h,RGBA,UB,DATA);self.assertEqual(self.call('glGetError'),0x501)
        self.call('glTexSubImage2D',T,1,0,0,1,1,RGBA,UB,DATA);self.assertEqual(self.call('glGetError'),0x502)
        self.assertEqual(self.texel(a,1,1),(0,bytes(range(12,16))))
    def test_zero_dimensions_null_data_and_source_address_overflow(self):
        a=self.bind();self.image(data=None);self.assertEqual(self.texel(a),(0,b'\0'*4))
        self.call('glTexImage2D',T,0,RGBA,2,2,0,RGBA,UB,0xfffffff8);self.assertEqual(self.call('glGetError'),0x501)
        self.image(0,2,b'x');self.assertEqual(self.stats()[1],0);self.assertEqual(self.texel(a),(0xffffffff,b'ZZZZ'))
    def test_memory_budget_oom_preserves_existing_store(self):
        a=self.bind();self.image();self.image(1024,1024,None);self.assertEqual(self.call('glGetError'),0x505)
        self.assertEqual(self.texel(a),(0,bytes(range(4))));self.assertEqual(self.stats()[1],16)
    def test_allocator_oom_during_bind_preserves_reserved_name_and_binding(self):
        self.assertEqual(self.arm.call('ds_runtime_init',1),0);a=self.names()[0];self.bind(a)
        self.assertEqual(self.call('glGetError'),0x505);self.assertEqual(self.query(0x8069,1),(0,));self.assertEqual(self.call('glIsTexture',a),0)
        self.assertEqual(self.arm.call('ds_runtime_init',1048576),0);self.bind(a);self.assertEqual(self.call('glIsTexture',a),1)
    def test_reallocation_allocator_oom_preserves_old_texels_and_counters(self):
        limit=self.arm.call('ds15_test_object_size')+48
        self.assertEqual(self.arm.call('ds_runtime_init',limit),0);a=self.bind();self.image()
        self.image(4,4,None);self.assertEqual(self.call('glGetError'),0x505)
        self.assertEqual(self.texel(a,1,1),(0,bytes(range(12,16))));self.assertEqual(self.stats(),(1,16,1,0))
    def test_pool_exhaustion_is_atomic_then_delete_recovers(self):
        names=self.names(32);self.arm.uc.mem_write(RESULT,b'ZZZZ');self.call('glGenTextures',1,RESULT)
        self.assertEqual(self.call('glGetError'),0x505);self.assertEqual(bytes(self.arm.uc.mem_read(RESULT,4)),b'ZZZZ')
        self.base.write(gl.OUT,names[0]);self.call('glDeleteTextures',1,gl.OUT);self.assertTrue(self.names()[0])
    def test_delete_detaches_all_units_and_close_reclaims_stores(self):
        a=self.bind();self.image();self.call('glActiveTexture',0x84c1);self.bind(a)
        self.base.write(gl.OUT,a,a,0,123);self.call('glDeleteTextures',4,gl.OUT);self.assertEqual(self.query(0x8069,1),(0,))
        self.call('glActiveTexture',0x84c0);self.assertEqual(self.query(0x8069,1),(0,));self.assertEqual(self.stats()[1],0)
        self.bind();self.image();self.image(level=1);self.image(data=None);self.arm.call('ds13_close',gl.CTX)
        self.arm.call('ds_runtime_stats',gl.OUT);self.assertEqual(self.base.words(gl.OUT,9)[4:6],(0,0))
    def test_parameters_defaults_validation_float_and_unscaled_fixed_enum(self):
        self.bind();self.assertEqual([self.param(n) for n in (0x2801,0x2800,0x2802,0x2803)], [0x2702,0x2601,0x2901,0x2901])
        self.call('glTexParameterx',T,0x2802,0x812f);self.assertEqual(self.param(0x2802),0x812f)
        self.call('glTexParameteri',T,0x2800,0x2700);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.param(0x2800),0x2601)
        self.call('glTexParameterf',T,0x2800,struct.unpack('<I',struct.pack('<f',9728.0))[0]);self.assertEqual(self.param(0x2800),0x2600)
        self.call('glTexParameterx',T,0x8191,1);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.param(0x8191),0)
    def test_pixel_store_validation_and_honest_maximum(self):
        self.assertEqual(self.query(0xd33,1),(1024,));self.assertEqual(self.query(0xcf5,1),(4,))
        for value in (1,2,4,8):self.call('glPixelStorei',0xcf5,value);self.assertEqual(self.query(0xcf5,1),(value,))
        self.call('glPixelStorei',0xcf5,3);self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.query(0xcf5,1),(8,))
        self.call('glPixelStorei',0xdead,1);self.assertEqual(self.call('glGetError'),0x500)
    def test_vector_parameter_abis_and_failed_queries_preserve_output(self):
        self.bind();self.base.write(DATA,0x812f)
        for fn in ('glTexParameteriv','glTexParameterxv'):
            self.call(fn,T,0x2803,DATA);self.assertEqual(self.param(0x2803),0x812f)
        self.arm.uc.mem_write(DATA,struct.pack('<f',9728.0));self.call('glTexParameterfv',T,0x2800,DATA)
        self.call('glGetTexParameterfv',T,0x2800,RESULT);self.assertEqual(struct.unpack('<f',self.arm.uc.mem_read(RESULT,4))[0],9728.0)
        self.call('glGetTexParameterxv',T,0x2800,RESULT);self.assertEqual(self.base.words(RESULT)[0],0x2600)
        self.arm.uc.mem_write(RESULT,b'ZZZZ');self.call('glGetTexParameteriv',T,0xdead,RESULT)
        self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(bytes(self.arm.uc.mem_read(RESULT,4)),b'ZZZZ')
    def test_delete_restores_default_object_without_changing_enable_state(self):
        self.image(1,1,b'zero');a=self.bind();self.image(1,1,b'live');self.call('glEnable',T)
        self.base.write(gl.OUT,a);self.call('glDeleteTextures',1,gl.OUT)
        self.assertEqual(self.texel(0),(0,b'zero'));self.assertEqual(self.call('glIsEnabled',T),1)
    def test_readback_bounds_preserve_output_and_bad_arguments(self):
        a=self.bind();self.image()
        for name,level,x,y in ((a,0,2,0),(a,11,0,0),(999,0,0,0),(a,0,0xffffffff,0)):
            self.assertEqual(self.texel(name,x,y,level),(0xffffffff,b'ZZZZ'))
        self.call('glGenTextures',-1,gl.OUT);self.assertEqual(self.call('glGetError'),0x501)
        self.call('glBindTexture',0xdead,123);self.assertEqual(self.call('glGetError'),0x500)
        self.assertLess(self.arm.call('ds13_context_size'),4096)
    def test_original_softfp_texture_fixture(self):
        blob=(gl.jni.BUILD/'fixture-textures.so').read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,gl.TABLE,67,gl.OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_textures',gl.OUT),0);name,error=self.base.words(gl.OUT,2)
        self.assertEqual(error,0);self.assertEqual(self.texel(name,1,1),(0,bytes((17,34,51,68))))
if __name__=='__main__':
    started=time.monotonic();names=[n for n in TextureTests.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(TextureTests(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,'game_rendered':False,
        'core_sha256':hashlib.sha256((gl.jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256((gl.jni.BUILD/'fixture-textures.so').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (gl.jni.cpp.PORTING/'analysis/textures-tests.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
