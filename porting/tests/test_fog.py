"""Actual ARM ES1.1 fog state and post-texture pixels, including clipped geometry."""
import hashlib,json,math,struct,time,unittest
import test_framebuffers as fb
import test_first_frame as draw
import test_gles_state as gl
F=0xb60;MODE=0xb65;DENSITY=0xb62;START=0xb63;END=0xb64;COLOR=0xb66
class Fog(fb.Framebuffers):
    def setUp(self):
        super().setUp();self.assertEqual(self.arm.call('ds30_attach',gl.CTX),0)
        n=self.arm.call('ds30_bindings',gl.TABLE,16);self.assertEqual(n,4)
        for i in range(n):name,fn=self.base.words(gl.TABLE+i*8,2);self.gl[self.base.text(name)]=fn
    def get(self,name,kind='Float',n=1):
        self.call('glGet'+kind+'v',name,draw.RESULT)
        return struct.unpack('<'+('f' if kind=='Float' else 'B' if kind=='Boolean' else 'i')*n,self.arm.uc.mem_read(draw.RESULT,n*(1 if kind=='Boolean' else 4)))
    def fog(self,name,value):self.call('glFogf',name,draw.bits(value))
    def fog_color(self,values):self.floats(draw.DATA+700,values);self.call('glFogfv',COLOR,draw.DATA+700)
    def eye(self,z):
        self.call('glMatrixMode',0x1700);self.call('glLoadIdentity');self.call('glTranslatef',0,0,draw.bits(z))
        self.call('glMatrixMode',0x1701);self.call('glLoadIdentity');self.call('glTranslatef',0,0,draw.bits(-z));self.call('glMatrixMode',0x1700)
    def render(self,z=0,rgba=(1,0,0,1)):
        self.quad();self.eye(z);self.rgba(*rgba);self.call('glDrawArrays',5,0,4)
    def reds(self):return tuple(self.pixels()[i] for i in range(0,12,3))
    def linear(self,start=0,end=1):self.call('glFogx',MODE,0x2601);self.fog(START,start);self.fog(END,end);self.call('glEnable',F)
    def test_defaults_and_typed_mode_queries(self):
        self.assertEqual(self.call('glIsEnabled',F),0);self.assertEqual(self.query(MODE,1),(0x800,))
        self.assertEqual(self.get(MODE,'Fixed'),(0x800,));self.assertEqual(self.get(MODE),(float(0x800),))
        for name,v in ((DENSITY,1),(START,0),(END,1)):self.assertEqual(self.get(name),(v,))
        self.assertEqual(self.get(COLOR,n=4),(0,0,0,0))
    def test_mode_enum_fixed_not_scaled_and_float_must_be_exact(self):
        self.call('glFogx',MODE,0x801);self.assertEqual(self.query(MODE,1),(0x801,))
        self.fog(MODE,0x2601);self.assertEqual(self.query(MODE,1),(0x2601,))
        for value in (0x2601+.5,7,-1):
            self.fog(MODE,value);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.query(MODE,1),(0x2601,))
    def test_density_negative_nan_infinity_refuse_atomically(self):
        self.fog(DENSITY,.5)
        for value in (-1,float('nan'),float('inf')):
            self.fog(DENSITY,value);self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.get(DENSITY),(.5,))
    def test_scalar_color_and_unknown_parameter_are_invalid_enum(self):
        for name in (COLOR,0xdead):self.fog(name,1);self.assertEqual(self.call('glGetError'),0x500)
        self.assertEqual(self.get(COLOR,n=4),(0,0,0,0))
    def test_fixed_distance_vectors_and_queries(self):
        self.call('glFogx',START,-32768);self.base.write(draw.DATA+700,163840);self.call('glFogxv',END,draw.DATA+700)
        self.assertEqual(self.get(START),(-.5,));self.assertEqual(self.get(END),(2.5,));self.assertEqual(self.get(END,'Fixed'),(163840,))
    def test_color_clamp_copy_and_integer_conversion(self):
        self.fog_color((-1,.5,2,.25));self.floats(draw.DATA+700,(0,0,0,0))
        self.assertEqual(self.get(COLOR,n=4),(0,.5,1,.25));self.assertEqual(self.get(COLOR,'Fixed',4),(0,32768,65536,16384))
        self.assertEqual(self.get(COLOR,'Boolean',4),(0,1,1,1));self.assertEqual(self.query(COLOR),(0,1073741824,2147483647,536870912))
    def test_fixed_color_vector_keeps_four_components(self):
        self.base.write(draw.DATA+700,65536,32768,0,16384);self.call('glFogxv',COLOR,draw.DATA+700)
        self.assertEqual(self.get(COLOR,n=4),(1,.5,0,.25))
    def test_null_and_invalid_vector_do_not_change_state(self):
        for api in ('glFogfv','glFogxv'):
            self.call(api,COLOR,0);self.assertEqual(self.call('glGetError'),0x501)
        self.fog_color((0,1,0,1));self.floats(draw.DATA+700,(1,0,float('nan'),0));self.call('glFogfv',COLOR,draw.DATA+700)
        self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.get(COLOR,n=4),(0,1,0,1))
    def test_fog_disabled_preserves_pixels_with_nondefault_parameters(self):
        self.fog_color((0,0,1,1));self.fog(DENSITY,100);self.render(.5)
        self.assertEqual(self.pixels(),bytes((255,0,0))*12)
    def test_linear_distance_endpoints_and_absolute_eye_z(self):
        self.linear(0,2)
        for z,red in ((0,255),(.5,191),(-1,128),(2,0),(3,0)):
            self.render(z);self.assertEqual(self.pixels(),bytes((red,0,0))*12)
    def test_exponential_actual_fragment_color(self):
        self.call('glEnable',F);self.render(math.log(2));self.assertTrue(all(abs(v-128)<=1 for v in self.reds()))
    def test_exponential_squared_actual_fragment_color(self):
        self.call('glFogx',MODE,0x801);self.fog(DENSITY,.5);self.call('glEnable',F);self.render(2)
        self.assertEqual(self.pixels(),bytes((94,0,0))*12)
    def test_zero_density_disables_exponential_attenuation(self):
        self.fog(DENSITY,0);self.call('glEnable',F);self.render(1000)
        self.assertEqual(self.pixels(),bytes((255,0,0))*12)
    def gradient(self,flat=False,left=-1):
        self.linear();self.quad((left,-1,0,1,-1,1,left,1,0,1,1,1));self.rgba(1,0,0,1)
        matrix=[float(i%5==0) for i in range(16)];matrix[10]=0
        self.floats(draw.DATA+700,matrix);self.call('glMatrixMode',0x1701);self.call('glLoadMatrixf',draw.DATA+700)
        if flat:self.call('glShadeModel',0x1d00)
        self.call('glDrawArrays',5,0,4)
    def test_vertex_fog_factors_interpolate_across_quad(self):
        self.gradient();self.assertEqual(self.reds(),(223,159,96,32))
    def test_flat_color_shading_does_not_flatten_fog(self):
        self.gradient(True);self.assertEqual(self.reds(),(223,159,96,32))
    def test_fog_interpolation_uses_reciprocal_clip_w(self):
        self.linear();self.rgba(1,0,0,1)
        self.floats(draw.DATA,(-1,-1,0,1,3,-3,1,3,-1,1,0,1,3,3,1,3))
        self.call('glVertexPointer',4,0x1406,0,draw.DATA);self.call('glEnableClientState',0x8074)
        matrix=[float(i%5==0) for i in range(16)];matrix[10]=0
        self.floats(draw.DATA+700,matrix);self.call('glMatrixMode',0x1701);self.call('glLoadMatrixf',draw.DATA+700)
        self.call('glDrawArrays',5,0,4)
        for x,actual in enumerate(self.reds()):
            u=(x+.5)/4;expected=255*(1-u)/(1-u+u/3);self.assertLessEqual(abs(actual-expected),1)
    def test_clipped_vertices_interpolate_fog_and_keep_guard_bytes(self):
        self.gradient(left=-3);self.assertEqual(self.reds(),(112,80,48,16))
    def test_fog_blends_after_texture_replace_and_preserves_alpha(self):
        _,t=self.setup_target();self.texture(pixels=bytes((255,0,0,128))*4);self.call('glTexEnvi',0x2300,0x2200,0x1e01)
        self.linear(0,2);self.fog_color((0,0,1,1));self.render(1)
        self.assertEqual(self.pixel(t),bytes((128,0,128,128)))
    def test_fog_does_not_change_alpha_test_input(self):
        _,t=self.setup_target();self.linear(0,2);self.fog_color((0,0,1,1));self.call('glEnable',0xbc0);self.call('glAlphaFunc',0x204,draw.bits(.5));self.render(1,(1,0,0,.25))
        self.assertEqual(self.pixel(t),bytes(4))
    def test_fog_runs_before_source_alpha_blending(self):
        _,t=self.setup_target();self.linear(0,2);self.fog_color((0,0,1,0));self.call('glEnable',0xbe2);self.call('glBlendFunc',0x302,0x303);self.render(1,(1,0,0,.5))
        self.assertEqual(self.pixel(t),bytes((64,0,64,64)))
    def test_repeated_attach_refuses_without_resetting_live_state(self):
        self.fog(DENSITY,.25);self.assertEqual(self.arm.call('ds30_attach',gl.CTX),0xffffffff);self.assertEqual(self.get(DENSITY),(.25,))
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Fog.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Fog(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((draw.PORTING/'3ds/build-emulator/core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (draw.PORTING/'analysis/fog-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
