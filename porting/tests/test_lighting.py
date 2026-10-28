"""ARM ES1.1 lighting parameters, transforms and actual RGBA triangle pixels."""
import hashlib,json,math,struct,time,unittest
import test_framebuffers as fb
import test_first_frame as draw
import test_gles_state as gl
L=0x4000;FB=0x408;AMB=0x1200;DIF=0x1201;SPEC=0x1202;POS=0x1203
class Lighting(fb.Framebuffers):
    def setUp(self):
        super().setUp();self.assertEqual(self.arm.call('ds32_attach',gl.CTX),0)
        n=self.arm.call('ds32_bindings',gl.TABLE,32);self.assertEqual(n,18)
        for i in range(n):name,fn=self.base.words(gl.TABLE+i*8,2);self.gl[self.base.text(name)]=fn
        _,self.target=self.setup_target();self.quad()
    def vector(self,api,args,values):
        self.floats(draw.DATA+1500,values);self.call(api,*args,draw.DATA+1500)
    def material(self,name,values):self.vector('glMaterialfv',(FB,name),values)
    def light(self,name,values,id=L):self.vector('glLightfv',(id,name),values)
    def model(self,name,values):self.vector('glLightModelfv',(name,),values)
    def get(self,api,args,n=4,fixed=False):
        self.arm.uc.mem_write(draw.RESULT,b'Z'*32);self.call(api,*args,draw.RESULT)
        self.assertEqual(bytes(self.arm.uc.mem_read(draw.RESULT+n*4,4)),b'Z'*4)
        return struct.unpack('<'+('i' if fixed else 'f')*n,self.arm.uc.mem_read(draw.RESULT,n*4))
    def mat(self,name=DIF,face=0x404):return self.get('glGetMaterialfv',(face,name),1 if name==0x1601 else 4)
    def lit(self):self.call('glEnable',0xb50);self.call('glEnable',L)
    def white(self):
        self.material(AMB,(0,0,0,1));self.material(DIF,(1,1,1,1));self.material(SPEC,(0,0,0,1));self.material(0x1600,(0,0,0,1));self.model(0xb53,(0,0,0,1))
    def render(self):self.call('glDrawArrays',5,0,4);return self.pixel(self.target)
    def near(self,p,want):
        for x,y in zip(p,want):self.assertLessEqual(abs(x-y),1,(p,want))
    def normal(self,x=0,y=0,z=1):self.call('glNormal3f',draw.bits(x),draw.bits(y),draw.bits(z))
    def test_defaults_material_lights_model_and_normal(self):
        self.near(tuple(x*255 for x in self.mat(AMB)),(51,51,51,255));self.near(tuple(x*255 for x in self.mat()),(204,204,204,255))
        self.assertEqual(self.mat(SPEC),(0,0,0,1));self.assertEqual(self.mat(0x1600),(0,0,0,1));self.assertEqual(self.mat(0x1601),(0,))
        self.assertEqual(self.get('glGetLightfv',(L,DIF)),(1,1,1,1));self.assertEqual(self.get('glGetLightfv',(L+1,DIF)),(0,0,0,1))
        self.assertEqual(self.get('glGetLightfv',(L,POS)),(0,0,1,0));self.assertEqual(self.get('glGetLightfv',(L,0x1204),3),(0,0,-1))
        self.assertEqual(self.query(0xd31,1),(8,));self.assertEqual(self.query(0xb52,1),(0,))
        self.call('glGetFloatv',0xb02,draw.RESULT);self.assertEqual(struct.unpack('<3f',self.arm.uc.mem_read(draw.RESULT,12)),(0,0,1))
    def test_ambient_scene_with_lighting_and_no_enabled_lights(self):
        self.call('glEnable',0xb50);self.near(self.render(),(10,10,10,255))
    def test_default_directional_light_adds_diffuse(self):
        self.lit();self.near(self.render(),(214,214,214,255))
    def test_disabled_lighting_preserves_primary_color(self):
        self.rgba(.25,.5,.75,.5);self.call('glEnable',L);self.near(self.render(),(64,128,191,128))
    def test_directional_normal_sign_controls_diffuse(self):
        self.white();self.lit();self.assertEqual(self.render(),bytes((255,)*4));self.normal(z=-1);self.assertEqual(self.render(),bytes((0,0,0,255)))
    def test_emission_and_negative_ambient_are_clamped_after_lighting(self):
        self.white();self.material(AMB,(1,1,1,1));self.model(0xb53,(-.5,0,0,1));self.material(0x1600,(.75,.2,.3,1));self.call('glEnable',0xb50)
        self.near(self.render(),(64,51,76,255))
    def test_material_unbounded_colors_and_diffuse_alpha(self):
        self.white();self.material(DIF,(2,-1,.5,.25));self.assertEqual(self.mat(),(2,-1,.5,.25));self.lit();self.near(self.render(),(255,0,128,64))
    def test_specular_half_vector_and_shininess(self):
        self.white();self.material(DIF,(0,0,0,1));self.material(SPEC,(1,0,0,1));self.call('glMaterialf',FB,0x1601,draw.bits(4));self.normal(0,math.sqrt(.5),math.sqrt(.5));self.lit()
        self.near(self.render(),(64,0,0,255));self.normal(z=-1);self.assertEqual(self.render(),bytes((0,0,0,255)))
    def test_positional_light_constant_linear_and_quadratic_attenuation(self):
        self.white();self.light(POS,(0,0,2,1));self.lit();self.near(self.render(),(208,208,208,255))
        self.call('glLightf',L,0x1207,draw.bits(2));self.near(self.render(),(104,104,104,255))
        self.call('glLightf',L,0x1207,draw.bits(1));self.call('glLightf',L,0x1208,draw.bits(1));self.near(self.render(),(60,60,60,255))
        self.call('glLightf',L,0x1208,0);self.call('glLightf',L,0x1209,draw.bits(1));self.near(self.render(),(30,30,30,255))
    def test_spot_cone_exponent_and_reversed_direction(self):
        self.white();self.light(POS,(0,0,2,1));self.call('glLightf',L,0x1206,draw.bits(45));self.call('glLightf',L,0x1205,draw.bits(2));self.lit()
        self.near(self.render(),(139,139,139,255));self.call('glLightf',L,0x1206,draw.bits(30));self.assertEqual(self.render(),bytes((0,0,0,255)))
        self.call('glLightf',L,0x1206,draw.bits(45));self.light(0x1204,(0,0,1));self.assertEqual(self.render(),bytes((0,0,0,255)))
    def test_light_position_transforms_when_set_and_remains_in_eye_space(self):
        self.call('glTranslatef',draw.bits(1),draw.bits(2),draw.bits(3));self.light(POS,(0,0,1,1));self.call('glLoadIdentity')
        self.assertEqual(self.get('glGetLightfv',(L,POS)),(1,2,4,1))
    def test_spot_direction_uses_modelview_linear_part_not_inverse(self):
        self.call('glScalef',draw.bits(2),draw.bits(3),draw.bits(4));self.light(0x1204,(1,2,-1));self.call('glLoadIdentity')
        self.assertEqual(self.get('glGetLightfv',(L,0x1204),3),(2,6,-4))
    def test_inverse_transpose_normal_and_normalize(self):
        self.white();self.light(POS,(1,0,0,0));self.normal(1,0,1);self.lit();self.call('glScalef',draw.bits(2),draw.bits(1),draw.bits(1))
        self.call('glMatrixMode',0x1701);self.call('glScalef',draw.bits(.5),draw.bits(1),draw.bits(1));self.near(self.render(),(128,128,128,255))
        self.call('glEnable',0xba1);self.near(self.render(),(114,114,114,255))
    def test_rescale_normal_and_normalize_on_uniform_scale(self):
        self.white();self.lit();self.call('glScalef',draw.bits(2),draw.bits(2),draw.bits(2));self.call('glMatrixMode',0x1701);self.call('glScalef',draw.bits(.5),draw.bits(.5),draw.bits(.5))
        self.near(self.render(),(128,128,128,255));self.call('glEnable',0x803a);self.assertEqual(self.render(),bytes((255,)*4))
        self.call('glEnable',0xba1);self.assertEqual(self.render(),bytes((255,)*4))
    def test_shear_inverse_transpose_normal(self):
        self.white();self.light(POS,(0,0,-1,0));self.normal(1,0,0);self.lit();self.call('glEnable',0xba1)
        m=[float(i%5==0) for i in range(16)];m[8]=2;self.floats(draw.DATA+1500,m);self.call('glLoadMatrixf',draw.DATA+1500);self.near(self.render(),(228,228,228,255))
    def test_two_sided_lighting_selects_back_color_from_winding(self):
        self.white();self.normal(z=-1);self.lit();self.call('glFrontFace',0x900);self.assertEqual(self.render(),bytes((0,0,0,255)))
        self.call('glLightModelx',0xb52,1);self.assertEqual(self.query(0xb52,1),(1,));self.assertEqual(self.render(),bytes((255,)*4))
        self.call('glFrontFace',0x901);self.assertEqual(self.render(),bytes((0,0,0,255)))
    def test_clipped_two_sided_colors_survive_clipping(self):
        self.white();self.normal(z=-1);self.lit();self.call('glFrontFace',0x900);self.call('glLightModelx',0xb52,65536)
        self.quad((-3,-1,0,1,-1,0,-3,1,0,1,1,0));self.assertEqual(self.render(),bytes((255,)*4))
    def test_signed_byte_normal_array_conversion(self):
        self.white();self.lit();self.arm.uc.mem_write(draw.DATA+600,bytes((0,0,64))*4);self.call('glNormalPointer',0x1400,0,draw.DATA+600);self.call('glEnableClientState',0x8075)
        self.near(self.render(),(129,129,129,255));self.call('glEnable',0xba1);self.near(self.render(),(255,255,255,255))
    def test_float_normal_array_and_flat_provoking_vertex(self):
        self.white();self.lit();self.floats(draw.DATA+600,(0,0,0,0,0,1,0,0,0,0,0,1));self.call('glNormalPointer',0x1406,0,draw.DATA+600);self.call('glEnableClientState',0x8075);self.call('glShadeModel',0x1d00)
        self.render();self.assertEqual(self.pixel(self.target,0,0),bytes((0,0,0,255)));self.assertEqual(self.pixel(self.target,1,1),bytes((255,)*4))
    def test_multiple_lights_add_and_enable_independently(self):
        self.white();self.light(DIF,(.2,0,0,1));self.light(DIF,(0,.4,0,1),L+1);self.lit();self.call('glEnable',L+1)
        self.near(self.render(),(51,102,0,255));self.call('glDisable',L);self.near(self.render(),(0,102,0,255))
    def test_color_material_enable_track_and_disable_is_permanent(self):
        self.rgba(.25,.5,.75,.5);self.call('glEnable',0xb57);self.assertEqual(self.mat(),(.25,.5,.75,.5));self.assertEqual(self.mat(AMB),(.25,.5,.75,.5))
        self.rgba(1,0,0,.25);self.call('glDisable',0xb57);self.rgba(0,1,0,.75);self.assertEqual(self.mat(),(1,0,0,.25))
    def test_color_material_tracks_unclamped_color_before_lighting(self):
        self.white();self.call('glEnable',0xb57);self.rgba(2,-1,.5,.25);self.assertEqual(self.mat(),(2,-1,.5,.25));self.lit();self.near(self.render(),(255,0,128,64))
    def test_color_array_tracks_material_and_last_vertex_persists(self):
        self.white();self.lit();self.call('glEnable',0xb57);colors=(1,0,0,1,0,1,0,1,0,0,1,1,.75,.25,.5,.25)
        self.floats(draw.DATA+600,colors);self.call('glColorPointer',4,0x1406,0,draw.DATA+600);self.call('glEnableClientState',0x8076);self.render();self.assertEqual(self.mat(),(.75,.25,.5,.25))
        self.arm.uc.mem_write(draw.DATA+512,bytes((0,1,2,2,1,0)))
        self.call('glDrawElements',4,6,0x1401,draw.DATA+512);self.assertEqual(self.mat(),(1,0,0,1))
        # A repeated index still tracks its original source color, and a new
        # draw must see edits to the same client storage without rebinding it.
        self.floats(draw.DATA+600,(2,-1,.5,.25))
        self.call('glDrawElements',4,6,0x1401,draw.DATA+512);self.assertEqual(self.mat(),(2,-1,.5,.25))
    def test_fixed_vector_scalar_and_get_entrypoints(self):
        self.base.write(draw.DATA+1500,32768,65536,0,16384);self.call('glMaterialxv',FB,DIF,draw.DATA+1500)
        self.assertEqual(self.get('glGetMaterialxv',(0x405,DIF),fixed=True),(32768,65536,0,16384))
        self.call('glMaterialx',FB,0x1601,4*65536);self.assertEqual(self.mat(0x1601),(4,))
        self.call('glLightx',L,0x1207,2*65536);self.assertEqual(self.get('glGetLightxv',(L,0x1207),1,True),(131072,))
        self.base.write(draw.DATA+1500,0,0,65536,0);self.call('glLightxv',L,POS,draw.DATA+1500);self.assertEqual(self.get('glGetLightfv',(L,POS)),(0,0,1,0))
        self.call('glNormal3x',0,32768,65536);self.call('glGetFloatv',0xb02,draw.RESULT);self.assertEqual(struct.unpack('<3f',self.arm.uc.mem_read(draw.RESULT,12)),(0,.5,1))
        self.base.write(draw.DATA+1500,65536,0,0,65536);self.call('glLightModelxv',0xb53,draw.DATA+1500)
        self.call('glGetFloatv',0xb53,draw.RESULT);self.assertEqual(struct.unpack('<4f',self.arm.uc.mem_read(draw.RESULT,16)),(1,0,0,1))
    def test_invalid_scalar_parameters_are_atomic(self):
        for api,args in (('glMaterialf',(FB,0x1601,draw.bits(129))),('glLightf',(L,0x1205,draw.bits(-1))),('glLightf',(L,0x1206,draw.bits(91))),('glLightf',(L,0x1207,draw.bits(-1)))):
            self.call(api,*args);self.assertEqual(self.call('glGetError'),0x501)
        self.assertEqual(self.mat(0x1601),(0,));self.assertEqual(self.get('glGetLightfv',(L,0x1206),1),(180,));self.assertEqual(self.get('glGetLightfv',(L,0x1207),1),(1,))
    def test_invalid_enums_faces_null_and_nan_leave_state(self):
        for api,args,error in (('glMaterialf',(0x404,0x1601,0),0x500),('glLightf',(L+8,0x1207,draw.bits(1)),0x500),('glLightModelf',(0xb53,0),0x500),('glMaterialfv',(FB,DIF,0),0x501)):
            self.call(api,*args);self.assertEqual(self.call('glGetError'),error)
        self.light(DIF,(1,float('nan'),0,1));self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(self.get('glGetLightfv',(L,DIF)),(1,1,1,1))
        self.base.write(draw.RESULT,0x12345678);self.call('glGetMaterialfv',FB,DIF,draw.RESULT);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.base.words(draw.RESULT)[0],0x12345678)
    def test_singular_normal_transform_refuses_before_pixels(self):
        self.lit();self.call('glScalef',0,draw.bits(1),draw.bits(1));self.render();self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.pixel(self.target),bytes(4))
    def test_repeated_attach_keeps_live_material(self):
        self.material(DIF,(.25,.5,.75,1));self.assertEqual(self.arm.call('ds32_attach',gl.CTX),0xffffffff);self.assertEqual(self.mat(),(.25,.5,.75,1))
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Lighting.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Lighting(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((draw.PORTING/'3ds/build-emulator/core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (draw.PORTING/'analysis/lighting-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
