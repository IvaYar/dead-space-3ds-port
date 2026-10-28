"""ARM texture-combiner state and actual two-unit RGBA/FBO output."""
import hashlib,json,struct,time,unittest
import test_framebuffers as fb
import test_first_frame as draw
import test_gles_state as gl
TARGET=0x2300;MODE=0x2200;RGB=0x8571;ALPHA=0x8572;SCALE=0x8573;ASCALE=0xd1c
class Combine(fb.Framebuffers):
    def setUp(self):
        super().setUp();self.assertEqual(self.arm.call('ds31_attach',gl.CTX),0)
        _,self.target=self.setup_target();self.texture(pixels=bytes((64,128,192,128))*4)
        self.quad();self.rgba(.5,.25,.75,.5);self.env(MODE,0x8570)
        self.floats(draw.DATA+700,(.25,.75,.125,.25));self.call('glTexEnvfv',TARGET,0x2201,draw.DATA+700)
    def env(self,name,value):self.call('glTexEnvi',TARGET,name,value)
    def get(self,name,kind='Integer'):
        self.base.write(draw.RESULT,0x12345678,0xaabbccdd);self.call('glGetTexEnv'+{'Integer':'iv','Float':'fv','Fixed':'xv'}[kind],TARGET,name,draw.RESULT)
        self.assertEqual(self.base.words(draw.RESULT+4)[0],0xaabbccdd)
        return struct.unpack('<f' if kind=='Float' else '<i',self.arm.uc.mem_read(draw.RESULT,4))[0]
    def render(self):self.call('glDrawArrays',5,0,4);return self.pixel(self.target)
    def near(self,p,want):
        for x,y in zip(p,want):self.assertLessEqual(abs(x-y),1,(p,want))
    def test_default_functions_sources_operands_and_scales(self):
        self.assertEqual(self.get(RGB),0x2100);self.assertEqual(self.get(ALPHA),0x2100)
        for base in (0x8580,0x8588):self.assertEqual(tuple(self.get(base+i) for i in range(3)),(0x1702,0x8578,0x8576))
        self.assertEqual(tuple(self.get(0x8590+i) for i in range(3)),(0x300,0x300,0x302))
        self.assertEqual(tuple(self.get(0x8598+i) for i in range(3)),(0x302,)*3)
        self.assertEqual(self.get(SCALE,'Float'),1);self.assertEqual(self.get(ASCALE,'Fixed'),65536)
    def test_default_modulate_matches_real_texture_times_primary(self):self.assertEqual(self.render(),bytes((32,32,144,64)))
    def test_rgb_replace_add_signed_interpolate_and_subtract(self):
        for mode,want in ((0x1e01,(64,128,192,64)),(0x104,(192,192,255,64)),(0x8574,(64,64,255,64)),(0x8575,(112,80,191,64)),(0x84e7,(0,64,1,64))):
            self.env(RGB,mode);self.near(self.render(),want)
    def test_rgb_sources_primary_previous_constant_and_texture(self):
        self.env(RGB,0x1e01)
        for src,want in ((0x8577,(128,64,191,64)),(0x8578,(128,64,191,64)),(0x8576,(64,191,32,64)),(0x1702,(64,128,192,64))):
            self.env(0x8580,src);self.near(self.render(),want)
    def test_all_rgb_operand_swizzles(self):
        self.env(RGB,0x1e01)
        for op,want in ((0x300,(64,128,192,64)),(0x301,(191,127,63,64)),(0x302,(128,128,128,64)),(0x303,(127,127,127,64))):
            self.env(0x8590,op);self.near(self.render(),want)
    def test_alpha_functions_independent_of_rgb(self):
        for mode in (0x1e01,0x2100,0x104,0x8574,0x8575,0x84e7):
            self.env(ALPHA,mode);a,b,c=128/255,.5,.25
            value={0x1e01:a,0x2100:a*b,0x104:a+b,0x8574:a+b-.5,0x8575:a*c+b*(1-c),0x84e7:a-b}[mode]
            p=self.render();self.near(p,(32,32,144,round(max(0,min(1,value))*255)))
    def test_alpha_sources_and_one_minus_operand(self):
        self.env(ALPHA,0x1e01)
        for src,want in ((0x8577,128),(0x8578,128),(0x8576,64),(0x1702,128)):
            self.env(0x8588,src);self.near(self.render(),(32,32,144,want))
        self.env(0x8588,0x8576);self.env(0x8598,0x303);self.near(self.render(),(32,32,144,191))
    def test_rgb_alpha_scale_types_clamp_and_integer_values(self):
        self.call('glTexEnvx',TARGET,SCALE,131072);self.assertEqual(self.get(SCALE,'Float'),2);self.assertEqual(self.get(SCALE,'Fixed'),131072);self.assertEqual(self.get(SCALE),2)
        self.env(ASCALE,4);self.near(self.render(),(64,64,255,255))
        self.call('glTexEnvf',TARGET,SCALE,draw.bits(4));self.assertEqual(self.get(SCALE),4)
    def test_scale_and_enum_vector_entrypoints(self):
        self.base.write(draw.DATA+700,131072);self.call('glTexEnvxv',TARGET,SCALE,draw.DATA+700);self.assertEqual(self.get(SCALE),2)
        self.base.write(draw.DATA+700,4);self.call('glTexEnviv',TARGET,SCALE,draw.DATA+700);self.assertEqual(self.get(SCALE),4)
        self.floats(draw.DATA+700,(2,));self.call('glTexEnvfv',TARGET,ASCALE,draw.DATA+700);self.assertEqual(self.get(ASCALE),2)
        self.base.write(draw.DATA+700,0x1e01);self.call('glTexEnvxv',TARGET,RGB,draw.DATA+700);self.assertEqual(self.get(RGB,'Fixed'),0x1e01)
    def test_invalid_scales_refuse_atomically(self):
        for value in (0,3,-1):
            self.env(SCALE,value);self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.get(SCALE),1)
        self.call('glTexEnvf',TARGET,ASCALE,draw.bits(float('nan')));self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.get(ASCALE),1)
    def test_invalid_sources_crossbar_and_alpha_rgb_operands_refuse(self):
        for name,value in ((0x8580,0x84c0),(0x8588,0xdead),(0x8590,0x304),(0x8598,0x300),(ALPHA,0x86ae),(RGB,0xdead)):
            old=self.get(name);self.env(name,value);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.get(name),old)
    def test_null_vector_wrong_target_and_unknown_query_keep_output(self):
        self.call('glTexEnvfv',TARGET,RGB,0);self.assertEqual(self.call('glGetError'),0x501)
        self.call('glTexEnvi',0xdead,RGB,0x1e01);self.assertEqual(self.call('glGetError'),0x500)
        self.base.write(draw.RESULT,0x12345678);self.call('glGetTexEnviv',TARGET,0xdead,draw.RESULT);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.base.words(draw.RESULT)[0],0x12345678)
    def second(self):
        self.env(RGB,0x1e01);self.call('glActiveTexture',0x84c1);self.call('glClientActiveTexture',0x84c1)
        self.texture(pixels=bytes((32,64,128,64))*4);self.env(MODE,0x8570)
    def test_second_unit_previous_differs_from_primary(self):
        self.second();self.env(RGB,0x1e01);self.env(0x8580,0x8578);self.near(self.render(),(64,128,192,16))
        self.env(0x8580,0x8577);self.near(self.render(),(128,64,191,16))
    def test_each_unit_state_is_independent(self):
        self.env(RGB,0x8574);self.call('glActiveTexture',0x84c1);self.assertEqual(self.get(RGB),0x2100);self.env(RGB,0x84e7)
        self.call('glActiveTexture',0x84c0);self.assertEqual(self.get(RGB),0x8574)
    def test_disabled_unit_passes_previous_result_without_combining(self):
        self.second();self.call('glDisable',0xde1);self.near(self.render(),(64,128,192,64))
    def dot(self):
        self.rgba(.75,.5,.5,.5);self.floats(draw.DATA+700,(.75,.5,.5,.25));self.call('glTexEnvfv',TARGET,0x2201,draw.DATA+700)
        self.env(0x8580,0x8577);self.env(0x8581,0x8576);self.env(ALPHA,0x1e01)
    def test_dot3_rgb_preserves_independent_alpha(self):
        self.dot();self.env(RGB,0x86ae);self.near(self.render(),(64,64,64,128))
    def test_dot3_rgba_ignores_alpha_function_and_uses_scales(self):
        self.dot();self.env(RGB,0x86af);self.env(SCALE,2);self.env(ASCALE,4);self.near(self.render(),(128,128,128,255))
    def test_negative_dot_product_clamps_to_zero(self):
        self.dot();self.env(RGB,0x86ae);self.floats(draw.DATA+700,(.25,.5,.5,.25));self.call('glTexEnvfv',TARGET,0x2201,draw.DATA+700);self.near(self.render(),(0,0,0,128))
    def test_alpha_texture_rgb_source_is_black_in_combine_mode(self):
        self.texture(format=0x1906,pixels=bytes((128,))*4);self.env(RGB,0x1e01);self.near(self.render(),(0,0,0,64))
    def test_fog_runs_after_combiner_without_changing_alpha(self):
        self.assertEqual(self.arm.call('ds30_attach',gl.CTX),0)
        n=self.arm.call('ds30_bindings',gl.TABLE,16)
        for i in range(n):name,fn=self.base.words(gl.TABLE+i*8,2);self.gl[self.base.text(name)]=fn
        self.env(RGB,0x1e01);self.call('glFogx',0xb65,0x2601);self.call('glFogx',0xb64,131072)
        self.floats(draw.DATA+700,(0,0,1,1));self.call('glFogfv',0xb66,draw.DATA+700);self.call('glEnable',0xb60)
        self.call('glTranslatef',0,0,draw.bits(1));self.call('glMatrixMode',0x1701);self.call('glTranslatef',0,0,draw.bits(-1))
        self.near(self.render(),(32,64,224,64))
    def test_return_to_legacy_mode_and_attach_refusal_preserve_state(self):
        self.env(RGB,0x104);self.env(MODE,0x1e01);self.assertEqual(self.render(),bytes((64,128,192,128)))
        self.assertEqual(self.arm.call('ds31_attach',gl.CTX),0xffffffff);self.assertEqual(self.get(RGB),0x104)
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Combine.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Combine(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((draw.PORTING/'3ds/build-emulator/core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (draw.PORTING/'analysis/combine-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
