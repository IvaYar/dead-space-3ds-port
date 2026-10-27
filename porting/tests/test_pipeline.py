"""ARM pipeline state, typed queries and arithmetic used by a future renderer."""
import hashlib,json,struct,time,unittest
import test_gles_state as gl
from test_arm_loader import FILE_ADDR,INFO_ADDR,IMAGE_ADDR
DATA=0x16000400;OTHER=0x16000440;RESULT=0x16000600
def f(v):return struct.unpack('<I',struct.pack('<f',v))[0]
class PipelineTests(gl.GlesTests):
    def typed(self,name,kind='Float',n=1):
        self.arm.uc.mem_write(RESULT,b'Z'*32);self.call('glGet'+kind+'v',name,RESULT)
        return struct.unpack('<'+('f' if kind=='Float' else 'B' if kind=='Boolean' else 'i')*n,self.arm.uc.mem_read(RESULT,n*(1 if kind=='Boolean' else 4)))
    def test_pipeline_defaults_match_gles(self):
        for name in (0xb44,0xb71,0xbc0,0xb90,0x8037,0xb50,0xb57,0xba1,0x803a,0x4000,0x4007):self.assertEqual(self.call('glIsEnabled',name),0)
        for name,want in ((0xb45,0x405),(0xb46,0x901),(0xb74,0x201),(0xb72,1),(0xbc1,0x207),(0xbe1,1),(0xbe0,0),(0xb54,0x1d01)):
            self.assertEqual(self.query(name,1),(want,))
    def test_enable_disable_changes_each_capability_independently(self):
        for name in (0xb44,0xb71,0xbc0,0xb90,0x8037,0xb50,0xb57,0xba1,0x803a,0x4000,0x4007):
            self.call('glEnable',name);self.assertEqual(self.call('glIsEnabled',name),1);self.assertEqual(self.query(name,1),(1,))
            self.call('glDisable',name);self.assertEqual(self.call('glIsEnabled',name),0)
        self.call('glEnable',0xdead);self.assertEqual(self.call('glGetError'),0x500)
    def test_cull_orientation_and_modes_change_actual_classification(self):
        self.call('glEnable',0xb44)
        self.assertEqual(self.arm.call('ds16_test_cull',f(2)),0);self.assertEqual(self.arm.call('ds16_test_cull',f(-2)),1)
        self.call('glFrontFace',0x900);self.assertEqual(self.arm.call('ds16_test_cull',f(2)),1)
        self.call('glCullFace',0x404);self.assertEqual(self.arm.call('ds16_test_cull',f(2)),0)
        self.call('glCullFace',0x408);self.assertEqual(self.arm.call('ds16_test_cull',f(2)),1)
        self.call('glDisable',0xb44);self.assertEqual(self.arm.call('ds16_test_cull',f(2)),0)
    def test_invalid_cull_and_front_face_leave_old_state(self):
        self.call('glCullFace',0xdead);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.query(0xb45,1),(0x405,))
        self.call('glFrontFace',0xdead);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.query(0xb46,1),(0x901,))
    def test_all_eight_alpha_comparisons(self):
        self.call('glEnable',0xbc0)
        for i,want in enumerate(((0,0,0),(1,0,0),(0,1,0),(1,1,0),(0,0,1),(1,0,1),(0,1,1),(1,1,1))):
            self.call('glAlphaFunc',0x200+i,f(.5))
            self.assertEqual(tuple(self.arm.call('ds16_test_alpha',f(x)) for x in (.25,.5,.75)),want)
        self.call('glDisable',0xbc0);self.assertEqual(self.arm.call('ds16_test_alpha',f(0)),1)
    def test_alpha_ref_clamp_fixed_and_invalid_func_are_atomic(self):
        self.call('glAlphaFuncx',0x204,32768);self.assertEqual(self.typed(0xbc2),(.5,))
        self.call('glAlphaFunc',0x204,f(2));self.assertEqual(self.typed(0xbc2),(1,))
        self.call('glAlphaFunc',0xdead,f(.25));self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.typed(0xbc2),(1,))
    def test_depth_compare_mask_and_reversed_clamped_range(self):
        self.call('glEnable',0xb71);self.assertEqual(self.arm.call('ds16_test_depth',f(.25),f(.5)),1)
        self.call('glDepthFunc',0x204);self.assertEqual(self.arm.call('ds16_test_depth',f(.25),f(.5)),0)
        self.call('glDepthMask',0);self.assertEqual(self.query(0xb72,1),(0,))
        self.call('glDepthRangef',f(2),f(-1));self.assertEqual(self.typed(0xb70,n=2),(1,0))
        self.call('glDepthRangex',49152,16384);self.assertEqual(self.typed(0xb70,n=2),(.75,.25))
    def test_invalid_depth_and_nan_range_keep_previous_state(self):
        self.call('glDepthFunc',0xdead);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.query(0xb74,1),(0x201,))
        self.call('glDepthRangef',0x7fc00000,f(.5));self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.typed(0xb70,n=2),(0,1))
    def blend(self,src,dst,alias=False):
        self.arm.uc.mem_write(DATA,struct.pack('<4f',*src));self.arm.uc.mem_write(OTHER,struct.pack('<4f',*dst));out=DATA if alias else RESULT
        self.arm.call('ds16_test_blend',DATA,OTHER,out);return struct.unpack('<4f',self.arm.uc.mem_read(out,16))
    def test_source_alpha_blend_and_disabled_path(self):
        src=(1,0,0,.25);dst=(0,0,1,1)
        self.assertEqual(self.blend(src,dst),src);self.call('glEnable',0xbe2);self.call('glBlendFunc',0x302,0x303)
        self.assertEqual(self.blend(src,dst),(.25,0,.75,.8125));self.assertEqual(self.blend(src,dst,True),(.25,0,.75,.8125))
    def test_blend_saturate_alpha_factor_and_output_clamping(self):
        self.call('glEnable',0xbe2);self.call('glBlendFunc',0x308,1)
        self.assertEqual(self.blend((1,1,1,.5),(0,0,0,.75)),(.25,.25,.25,1))
        self.call('glBlendFunc',1,1);self.assertEqual(self.blend((1,1,1,1),(1,1,1,1)),(1,1,1,1))
    def test_blend_validation_preserves_both_factors(self):
        for src,dst in ((0x300,1),(1,0x306),(1,0x308),(0xdead,0)):
            self.call('glBlendFunc',src,dst);self.assertEqual(self.call('glGetError'),0x500)
            self.assertEqual(self.query(0xbe1,1),(1,));self.assertEqual(self.query(0xbe0,1),(0,))
    def test_shade_offset_float_fixed_and_invalid_values(self):
        self.call('glShadeModel',0x1d00);self.assertEqual(self.query(0xb54,1),(0x1d00,))
        self.call('glShadeModel',0xdead);self.assertEqual(self.call('glGetError'),0x500)
        self.call('glPolygonOffsetx',-98304,147456);self.assertEqual(self.typed(0x8038),(-1.5,));self.assertEqual(self.typed(0x2a00),(2.25,))
    def test_stencil_state_masks_and_zero_bit_reference_clamp(self):
        self.call('glStencilFunc',0x202,77,0xf0f0);self.call('glStencilMask',0x12345678);self.call('glStencilOp',0x1e01,0x1e02,0x150a)
        for name,want in ((0xb92,0x202),(0xb97,0),(0xb93,0xf0f0),(0xb98,0x12345678),(0xb94,0x1e01),(0xb95,0x1e02),(0xb96,0x150a)):
            self.assertEqual(self.query(name,1),(want,))
        self.call('glStencilOp',0x1e00,0xdead,0x1e00);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.query(0xb94,1),(0x1e01,))
    def test_float_fixed_boolean_queries_preserve_vector_size(self):
        self.color(.25,.5,.75,1);self.assertEqual(self.typed(0xc22,n=4),(.25,.5,.75,1))
        self.assertEqual(self.typed(0xc22,'Fixed',4),(16384,32768,49152,65536));self.assertEqual(self.typed(0xc22,'Boolean',4),(1,1,1,1))
        self.assertEqual(bytes(self.arm.uc.mem_read(RESULT+4,4)),b'ZZZZ')
        self.call('glViewport',1,2,3,4);self.assertEqual(self.typed(0xba2,n=4),(1,2,3,4))
        self.color(0,.5,1,1);self.assertEqual(self.query(0xc22),(0,1073741824,0x7fffffff,0x7fffffff))
    def test_fixed_enums_unscaled_booleans_scaled_and_large_integers_saturate(self):
        self.assertEqual(self.typed(0xb45,'Fixed'),(0x405,));self.assertEqual(self.typed(0xb72,'Fixed'),(65536,))
        self.call('glViewport',0x7fffffff,0x80000000,3,4);self.assertEqual(self.typed(0xba2,'Fixed',4)[:2],(0x7fffffff,-0x80000000))
        self.assertEqual(self.typed(0xb93)[0],4294967296.0)
    def test_unknown_queries_and_null_outputs_fail_without_writes(self):
        for kind in ('Float','Fixed','Boolean'):
            self.typed(0xdead,kind);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(bytes(self.arm.uc.mem_read(RESULT,16)),b'Z'*16)
            self.call('glGet'+kind+'v',0xb45,0);self.assertEqual(self.call('glGetError'),0x501)
    def test_pipeline_does_not_change_color_clear_semantics(self):
        for name in (0xb44,0xb71,0xbc0,0xb90,0xbe2):self.call('glEnable',name)
        self.call('glDepthMask',0);self.call('glAlphaFunc',0x200,0);self.color(1,0,0);self.call('glClear',0x4000)
        self.assertEqual(self.pixels(),bytes((255,0,0))*12)
    def test_original_softfp_pipeline_fixture(self):
        blob=(gl.jni.BUILD/'fixture-pipeline.so').read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,gl.TABLE,67,gl.OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_pipeline',gl.OUT),0);self.assertEqual(self.base.words(gl.OUT,2),(0x404,0))
if __name__=='__main__':
    started=time.monotonic();names=[n for n in PipelineTests.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(PipelineTests(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,'game_rendered':False,
        'core_sha256':hashlib.sha256((gl.jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256((gl.jni.BUILD/'fixture-pipeline.so').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (gl.jni.cpp.PORTING/'analysis/pipeline-tests.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
