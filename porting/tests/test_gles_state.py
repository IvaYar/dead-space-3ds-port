"""ARM GLES state, bounded real framebuffer writes and Android softfp imports."""
import hashlib,json,struct,time,unittest
import test_jni10 as jni
from test_arm_loader import FILE_ADDR,INFO_ADDR,IMAGE_ADDR
CTX=0x0600d000;PIX=0x16000010;OUT=0x06009000;TABLE=0x06004000
class GlesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):jni.cpp.CppTests.setUpClass()
    def setUp(self):
        self.base=jni.cpp.CppTests();self.base.setUp();self.arm=self.base.arm
        self.arm.uc.mem_map(0x16000000,4096);self.arm.uc.mem_write(PIX-16,b'Z'*68)
        self.assertEqual(self.arm.call('ds13_init',CTX,PIX,4,3,36,0),0);self.assertEqual(self.arm.call('ds13_current',CTX),0)
        n=self.arm.call('ds13_bindings',TABLE,128);self.assertEqual(n,99);self.gl={}
        for i in range(n):
            name,fn=self.base.words(TABLE+i*8,2);self.gl[self.base.text(name)]=fn
    def tearDown(self):
        self.arm.call('ds13_close',CTX);self.base.tearDown()
        self.assertEqual(bytes(self.arm.uc.mem_read(PIX-16,16)),b'Z'*16)
        self.assertEqual(bytes(self.arm.uc.mem_read(PIX+36,16)),b'Z'*16)
    def call(self,name,*args):
        self.arm.exports['_gl']=self.gl[name];return self.arm.call('_gl',*(v&0xffffffff for v in args))
    def query(self,name,n=4):
        self.arm.uc.mem_write(OUT,b'\x7a'*16);self.call('glGetIntegerv',name,OUT);return self.base.words(OUT,n)
    def pixels(self):return bytes(self.arm.uc.mem_read(PIX,36))
    def color(self,r,g,b,a=1):self.call('glClearColor',*(struct.unpack('<I',struct.pack('<f',f))[0] for f in (r,g,b,a)))
    def test_initial_viewport_and_scissor_match_real_surface(self):
        self.assertEqual(self.query(0xba2),(0,0,4,3));self.assertEqual(self.query(0xc10),(0,0,4,3))
        self.assertEqual(self.call('glIsEnabled',0xc11),0);self.assertEqual(self.call('glIsEnabled',0xbd0),1)
    def test_viewport_mutation_clamp_and_negative_size_refusal(self):
        self.call('glViewport',-5,7,2000,3000);self.assertEqual(self.query(0xba2),(0xfffffffb,7,1024,1024))
        self.call('glViewport',0,0,-1,1);self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.query(0xba2)[0],0xfffffffb)
    def test_first_error_is_sticky_then_resets(self):
        self.call('glViewport',0,0,-1,1);self.call('glEnable',0x1234)
        self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.call('glGetError'),0)
    def test_unsupported_query_keeps_output_unchanged(self):
        self.assertEqual(self.query(0xdeadbeef),(0x7a7a7a7a,)*4);self.assertEqual(self.call('glGetError'),0x500)
    def test_server_and_client_texture_selectors_are_independent(self):
        self.call('glActiveTexture',0x84c1);self.assertEqual(self.query(0x84e0,1),(0x84c1,));self.assertEqual(self.query(0x84e1,1),(0x84c0,))
        self.call('glClientActiveTexture',0x84c1);self.assertEqual(self.query(0x84e1,1),(0x84c1,))
        self.call('glActiveTexture',0x84c2);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.query(0x84e0,1),(0x84c1,))
    def test_clear_writes_rgb_and_ignores_viewport_bounds(self):
        self.call('glViewport',0,0,0,0);self.color(1,.5,-1);self.call('glClear',0x4000)
        self.assertEqual(self.pixels(),bytes((255,128,0))*12)
    def test_scissor_clips_negative_origin_to_surface(self):
        self.color(0,1,0);self.call('glScissor',-1,1,3,4);self.call('glEnable',0xc11);self.call('glClear',0x4000)
        expected=bytearray(b'Z'*36)
        for y in (1,2):
            for x in (0,1):expected[(y*4+x)*3:(y*4+x)*3+3]=bytes((0,255,0))
        self.assertEqual(self.pixels(),bytes(expected))
    def test_extreme_empty_scissor_does_not_wrap_or_write(self):
        self.call('glEnable',0xc11)
        for x in (0x7fffffff,0x80000000):
            self.call('glScissor',x,x,0x7fffffff,0x7fffffff);self.call('glClear',0x4000)
        self.assertEqual(self.pixels(),b'Z'*36)
    def test_color_mask_preserves_disabled_channels(self):
        self.color(1,0,1);self.call('glColorMask',0,1,0,1);self.call('glClear',0x4000)
        self.assertEqual(self.pixels(),bytes((90,0,90))*12)
        self.assertEqual(self.query(0xc23),(0,1,0,1))
        self.call('glColorMask',0,0,0,0);self.call('glClear',0x4000)
        self.assertEqual(self.pixels(),bytes((90,0,90))*12);self.arm.call('ds13_stats',CTX,OUT)
        self.assertEqual(self.base.words(OUT,4)[2],12)
    def test_absent_depth_stencil_and_invalid_clear_mask(self):
        self.call('glClear',0x100|0x400);self.assertEqual(self.pixels(),b'Z'*36)
        self.call('glClear',0xffffffff);self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.pixels(),b'Z'*36)
    def test_ctr_column_major_bgr_layout(self):
        self.arm.call('ds13_close',CTX);self.assertEqual(self.arm.call('ds13_init',CTX,PIX,4,3,36,1),0);self.arm.call('ds13_current',CTX)
        self.color(1,0,.5);self.call('glScissor',1,2,1,1);self.call('glEnable',0xc11);self.call('glClear',0x4000)
        expected=bytearray(b'Z'*36);expected[15:18]=bytes((128,0,255));self.assertEqual(self.pixels(),bytes(expected))
    def test_target_rotation_preserves_context_state(self):
        self.call('glViewport',1,2,3,4);self.assertEqual(self.arm.call('ds13_target',CTX,PIX+128,36),0)
        self.assertEqual(self.query(0xba2),(1,2,3,4));self.color(0,1,0);self.call('glClear',0x4000)
        self.assertEqual(self.pixels(),b'Z'*36);self.assertEqual(bytes(self.arm.uc.mem_read(PIX+128,36)),bytes((0,255,0))*12)
    def test_rgb565_surface_quantization_and_mask(self):
        self.arm.call('ds13_close',CTX);self.assertEqual(self.arm.call('ds13_init',CTX,PIX,4,3,24,2),0);self.arm.call('ds13_current',CTX)
        self.color(1,.5,0);self.call('glClear',0x4000)
        self.assertEqual(bytes(self.arm.uc.mem_read(PIX,24)),struct.pack('<H',0xfc00)*12)
        self.call('glColorMask',0,1,0,0);self.color(0,1,1);self.call('glClear',0x4000)
        self.assertEqual(bytes(self.arm.uc.mem_read(PIX,24)),struct.pack('<H',0xffe0)*12)
        self.assertEqual(self.query(0xd52,1),(5,));self.assertEqual(self.query(0xd53,1),(6,))
    def test_bad_context_binding_and_registry_capacity_refuse(self):
        self.assertEqual(self.arm.call('ds13_init',CTX,PIX,4,3,36,0),0xffffffff)
        self.assertEqual(self.arm.call('ds13_target',CTX,PIX,35),0xffffffff)
        self.arm.uc.mem_write(OUT,b'\xa5'*16);self.assertEqual(self.arm.call('ds13_bindings',OUT,1),0);self.assertEqual(bytes(self.arm.uc.mem_read(OUT,16)),b'\xa5'*16)
        self.arm.call('ds13_current',0);self.assertEqual(self.call('glGetError'),0x502)
    def test_fixed_point_and_float_android_fixture(self):
        blob=(jni.BUILD/'fixture-graphics.so').read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,TABLE,67,OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_graphics',OUT),0);self.assertEqual(self.pixels(),bytes((0,255,128))*12)
        self.assertEqual(self.base.words(OUT,2),(1,1))
    def test_flush_finish_complete_synchronous_work(self):
        self.call('glFlush');self.call('glFinish');self.arm.call('ds13_stats',CTX,OUT)
        self.assertEqual(self.base.words(OUT,4),(0,0,0,2))
    def test_failed_surface_sync_sets_error_without_claiming_flush(self):
        code=0x16000800;self.arm.uc.mem_write(code,struct.pack('<2I',0xe3a00001,0xe12fff1e))
        self.arm.call('ds13_observer',CTX,0,code);self.call('glFlush')
        self.assertEqual(self.call('glGetError'),0x502);self.arm.call('ds13_stats',CTX,OUT)
        self.assertEqual(self.base.words(OUT,4)[3],0)
if __name__=='__main__':
    started=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GlesTests))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,'game_rendered':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256((jni.BUILD/'fixture-graphics.so').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (jni.cpp.PORTING/'analysis/gles-tests.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
