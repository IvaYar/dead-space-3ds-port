"""Original compiled ARM OES objects, lifetime, color/depth/stencil and texture composition."""
import hashlib,json,struct,time,unittest
import test_first_frame as draw
import test_gles_state as gl
FB=0x8d40;RB=0x8d41;C=0x8ce0;D=0x8d00;S=0x8d20;T=0xde1;COMPLETE=0x8cd5
class Framebuffers(draw.DrawTests):
    def setUp(self):
        super().setUp();n=self.arm.call('ds26_bindings',gl.TABLE,32);self.assertEqual(n,15)
        for i in range(n):name,fn=self.base.words(gl.TABLE+i*8,2);self.gl[self.base.text(name)]=fn
    def gen(self,family='Framebuffers',n=1):
        self.call('glGen'+family+'OES',n,draw.RESULT);return self.base.words(draw.RESULT,n)
    def fbo(self):
        f=self.gen()[0];self.call('glBindFramebufferOES',FB,f);return f
    def tex(self,w=2,h=2,fmt=0x1908):
        self.call('glGenTextures',1,draw.RESULT);t=self.base.words(draw.RESULT)[0];self.call('glBindTexture',T,t)
        for p in (0x2800,0x2801):self.call('glTexParameteri',T,p,0x2600)
        self.call('glTexImage2D',T,0,fmt,w,h,0,fmt,0x1401,0);return t
    def attach(self,t):self.call('glFramebufferTexture2DOES',FB,C,T,t,0)
    def status(self):return self.call('glCheckFramebufferStatusOES',FB)
    def pixel(self,t,x=0,y=0):
        self.assertEqual(self.arm.call('ds15_test_read',t,0,x,y,draw.RESULT),0);return bytes(self.arm.uc.mem_read(draw.RESULT,4))
    def rbo(self,fmt=0x81a5,w=2,h=2,attachment=D):
        r=self.gen('Renderbuffers')[0];self.call('glBindRenderbufferOES',RB,r);self.call('glRenderbufferStorageOES',RB,fmt,w,h)
        self.call('glFramebufferRenderbufferOES',FB,attachment,RB,r);return r
    def setup_target(self):
        t=self.tex();f=self.fbo();self.attach(t);self.call('glViewport',0,0,2,2);self.assertEqual(self.status(),COMPLETE);return f,t
    def quad_at(self,z=0):
        self.quad((-1,-1,z,1,-1,z,-1,1,z,1,1,z));self.call('glDrawArrays',5,0,4)
    def parameter(self,name):
        self.call('glGetRenderbufferParameterivOES',RB,name,draw.RESULT);return self.base.words(draw.RESULT)[0]
    def test_reserved_names_become_objects_only_on_bind_and_delete_unbinds(self):
        f=self.gen()[0];self.assertEqual(self.call('glIsFramebufferOES',f),0);self.call('glBindFramebufferOES',FB,f)
        self.assertEqual(self.call('glIsFramebufferOES',f),1);self.assertEqual(self.query(0x8ca6,1),(f,))
        self.base.write(draw.RESULT,f);self.call('glDeleteFramebuffersOES',1,draw.RESULT)
        self.assertEqual(self.query(0x8ca6,1),(0,));self.assertEqual(self.call('glIsFramebufferOES',f),0)
    def test_missing_attachment_clear_and_draw_leave_default_pixels_unchanged(self):
        before=self.pixels();self.fbo();self.assertEqual(self.status(),0x8cd7)
        self.color(1,0,0);self.call('glClear',0x4000);self.assertEqual(self.call('glGetError'),0x506)
        self.quad_at();self.assertEqual(self.call('glGetError'),0x506);self.assertEqual(self.pixels(),before)
    def test_clear_writes_attached_texture_and_preserves_screen(self):
        before=self.pixels();_,t=self.setup_target();self.color(.2,.4,.6,.8);self.call('glClear',0x4000)
        self.assertEqual(self.pixel(t,1,1),bytes((51,102,153,204)));self.assertEqual(self.pixels(),before)
        self.assertEqual(self.query(0xd55,1),(8,))
    def test_color_mask_and_scissor_apply_to_rgba_attachment(self):
        _,t=self.setup_target();self.color(1,0,0,.25);self.call('glClear',0x4000)
        self.call('glEnable',0xc11);self.call('glScissor',1,0,1,1);self.call('glColorMask',0,1,0,0)
        self.color(0,1,0,1);self.call('glClear',0x4000)
        self.assertEqual(self.pixel(t,1,0),bytes((255,255,0,64)));self.assertEqual(self.pixel(t,0,0),bytes((255,0,0,64)))
    def test_triangle_rendering_writes_rgba_store(self):
        _,t=self.setup_target();self.rgba(0,1,0,.5);self.quad_at();self.assertEqual(self.pixel(t,1,1),bytes((0,255,0,128)))
        self.assertEqual(self.call('glGetError'),0)
    def test_render_texture_can_then_be_sampled_on_default_surface(self):
        _,t=self.setup_target();self.rgba(1,0,0,1);self.quad_at();self.call('glBindFramebufferOES',FB,0)
        self.call('glViewport',0,0,4,3);self.rgba(1,1,1,1);self.call('glEnable',T)
        self.floats(draw.DATA+128,(0,0,1,0,0,1,1,1));self.call('glTexCoordPointer',2,0x1406,0,draw.DATA+128);self.call('glEnableClientState',0x8078)
        self.quad_at();self.assertEqual(self.pixels(),bytes((255,0,0))*12);self.assertEqual(self.pixel(t),bytes((255,0,0,255)))
    def test_redefining_texture_revalidates_dimensions(self):
        _,t=self.setup_target();r=self.rbo();self.assertEqual(self.status(),COMPLETE)
        self.call('glTexImage2D',T,0,0x1908,4,4,0,0x1908,0x1401,0);self.assertEqual(self.status(),0x8cd9)
        self.call('glRenderbufferStorageOES',RB,0x81a5,4,4);self.assertEqual(self.status(),COMPLETE)
    def test_undefined_and_non_renderable_texture_are_incomplete(self):
        t=self.tex(0,0);self.fbo();self.attach(t);self.assertEqual(self.status(),0x8cd6)
        self.call('glTexImage2D',T,0,0x1906,2,2,0,0x1906,0x1401,0);self.assertEqual(self.status(),0x8cd6)
    def test_delete_texture_detaches_bound_but_retains_unbound_attachment(self):
        f,t=self.setup_target();self.color(1,0,0);self.call('glClear',0x4000);self.call('glBindFramebufferOES',FB,0)
        self.base.write(draw.RESULT,t);self.call('glDeleteTextures',1,draw.RESULT);self.call('glBindFramebufferOES',FB,f)
        self.assertEqual(self.status(),COMPLETE);self.color(0,1,0);self.call('glClear',0x4000)
        self.call('glBindTexture',T,t);self.call('glTexImage2D',T,0,0x1908,2,2,0,0x1908,0x1401,0)
        self.assertEqual(self.pixel(t),b'\0'*4);self.attach(t);self.assertEqual(self.status(),COMPLETE)
        self.base.write(draw.RESULT,t);self.call('glDeleteTextures',1,draw.RESULT);self.assertEqual(self.status(),0x8cd7)
    def test_depth16_controls_visibility_and_depth_mask(self):
        _,t=self.setup_target();self.rbo();self.call('glEnable',0xb71);self.call('glClear',0x4100)
        self.rgba(1,0,0,1);self.quad_at(0);self.rgba(0,1,0,1);self.quad_at(.75);self.assertEqual(self.pixel(t),bytes((255,0,0,255)))
        self.call('glDepthMask',0);self.rgba(0,0,1,1);self.quad_at(-.75);self.rgba(0,1,0,1);self.quad_at(-.5)
        self.assertEqual(self.pixel(t),bytes((0,255,0,255)));self.assertEqual(self.query(0xd56,1),(16,))
    def test_stencil_compare_and_zpass_update(self):
        _,t=self.setup_target();self.rbo(0x8d48,attachment=S);self.call('glClearStencil',3);self.call('glClear',0x4400)
        self.call('glEnable',0xb90);self.call('glStencilFunc',0x202,3,255);self.call('glStencilOp',0x1e00,0x1e00,0x1e02)
        self.rgba(0,1,0,1);self.quad_at();self.rgba(1,0,0,1);self.quad_at();self.assertEqual(self.pixel(t),bytes((0,255,0,255)))
        self.assertEqual(self.query(0xd57,1),(8,))
    def test_renderbuffer_format_bits_and_atomic_storage_errors(self):
        self.fbo();self.rbo(0x8056,attachment=C);self.assertEqual(self.parameter(0x8d42),2);self.assertEqual(self.parameter(0x8d53),4)
        self.call('glRenderbufferStorageOES',RB,0xdead,4,4);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.parameter(0x8d42),2)
        self.color(.5,.5,.5,.5);self.call('glClear',0x4000);self.assertEqual(self.status(),COMPLETE)
    def test_deleting_renderbuffer_detaches_current_fbo_and_unbinds(self):
        self.fbo();r=self.rbo(0x8d62,attachment=C);self.assertEqual(self.status(),COMPLETE)
        self.base.write(draw.RESULT,r);self.call('glDeleteRenderbuffersOES',1,draw.RESULT)
        self.assertEqual(self.status(),0x8cd7);self.assertEqual(self.query(0x8ca7,1),(0,));self.assertEqual(self.call('glIsRenderbufferOES',r),0)
    def test_framebuffer_attachment_query_and_invalid_calls_are_atomic(self):
        f,t=self.setup_target();self.call('glGetFramebufferAttachmentParameterivOES',FB,C,0x8cd0,draw.RESULT)
        self.assertEqual(self.base.words(draw.RESULT)[0],0x1702)
        self.call('glFramebufferTexture2DOES',FB,C,T,t,1);self.assertEqual(self.call('glGetError'),0x501)
        self.call('glFramebufferTexture2DOES',FB,0xdead,T,0,0);self.assertEqual(self.call('glGetError'),0x500)
        self.assertEqual(self.status(),COMPLETE);self.assertEqual(self.query(0x8ca6,1),(f,))
    def test_name_capacity_failure_does_not_partly_write_output(self):
        self.gen(n=8);self.base.write(draw.RESULT,0xabcdef01)
        self.call('glGenFramebuffersOES',1,draw.RESULT);self.assertEqual(self.call('glGetError'),0x505)
        self.assertEqual(self.base.words(draw.RESULT)[0],0xabcdef01)
    def test_context_cleanup_releases_retained_deleted_texture_and_rbo(self):
        f,t=self.setup_target();self.rbo();self.call('glBindFramebufferOES',FB,0)
        self.base.write(draw.RESULT,t);self.call('glDeleteTextures',1,draw.RESULT);self.arm.call('ds13_close',gl.CTX)
        self.assertEqual(self.arm.call('ds_runtime_cleanup'),0)
    def test_read_pixels_rgba_matches_rendered_texture_and_preserves_guards(self):
        _,t=self.setup_target();self.color(1,.5,0,.25);self.call('glClear',0x4000)
        self.arm.uc.mem_write(draw.DATA+1024,b'Z'*32);self.call('glReadPixels',0,0,2,2,0x1908,0x1401,draw.DATA+1028)
        self.assertEqual(bytes(self.arm.uc.mem_read(draw.DATA+1028,16)),bytes((255,128,0,64))*4)
        self.assertEqual(bytes(self.arm.uc.mem_read(draw.DATA+1024,4)),b'Z'*4);self.assertEqual(bytes(self.arm.uc.mem_read(draw.DATA+1044,12)),b'Z'*12)
    def test_rgb_readback_pack_alignment_preserves_row_padding(self):
        self.setup_target();self.color(0,1,0);self.call('glClear',0x4000);self.arm.uc.mem_write(draw.DATA+1024,b'Z'*16)
        self.call('glReadPixels',0,0,1,2,0x1907,0x1401,draw.DATA+1024)
        self.assertEqual(bytes(self.arm.uc.mem_read(draw.DATA+1024,8)),b'\0\xff\0Z\0\xff\0Z')
    def test_readback_default_surface_uses_bottom_left_rows(self):
        self.arm.uc.mem_write(gl.PIX,bytes(range(36)));self.call('glReadPixels',1,1,1,1,0x1908,0x1401,draw.RESULT)
        self.assertEqual(bytes(self.arm.uc.mem_read(draw.RESULT,4)),bytes((15,16,17,255)))
    def test_packed_565_readback_and_invalid_read_are_atomic(self):
        self.setup_target();self.color(1,0,1);self.call('glClear',0x4000);self.call('glReadPixels',0,0,1,1,0x1907,0x8363,draw.RESULT)
        self.assertEqual(self.base.words(draw.RESULT,1)[0]&65535,0xf81f)
        self.arm.uc.mem_write(draw.RESULT,b'ZZZZ')
        for args in ((0,0,-1,1,0x1908,0x1401),(0,0,1,1,0x1906,0x1401)):
            self.call('glReadPixels',*args,draw.RESULT);self.assertNotEqual(self.call('glGetError'),0);self.assertEqual(bytes(self.arm.uc.mem_read(draw.RESULT,4)),b'ZZZZ')
    def test_extended_texture_names_are_opt_in_and_bounded(self):
        self.assertEqual(self.arm.call('ds15_test_limits',128,48*1024*1024),0)
        self.call('glGenTextures',128,draw.DATA+1536);names=self.base.words(draw.DATA+1536,128)
        self.assertEqual(len(set(names)),128);self.assertNotIn(0,names)
        self.call('glGenTextures',1,draw.RESULT);self.assertEqual(self.call('glGetError'),0x505)
        self.call('glBindTexture',T,names[-1]);self.call('glTexImage2D',T,0,0x1908,2,2,0,0x1908,0x1401,0)
        self.assertEqual(self.pixel(names[-1]),b'\0'*4)
    def test_texture_limit_shrink_cannot_orphan_live_names(self):
        self.assertEqual(self.arm.call('ds15_test_limits',128,48*1024*1024),0)
        self.call('glGenTextures',33,draw.DATA+1536);self.assertEqual(self.arm.call('ds15_test_limits',32,48*1024*1024),0xffffffff)
        self.call('glGenTextures',1,draw.RESULT);self.assertEqual(self.call('glGetError'),0)
    def test_invalid_limits_preserve_existing_texture_data(self):
        t=self.tex();self.color(1,0,0);self.fbo();self.attach(t);self.call('glClear',0x4000)
        for names,size in ((0,100),(129,100),(32,0),(32,15)):
            self.assertEqual(self.arm.call('ds15_test_limits',names,size),0xffffffff);self.assertEqual(self.pixel(t),bytes((255,0,0,255)))
    def test_read_pixels_overflow_refuses_before_touching_output(self):
        self.setup_target();self.arm.uc.mem_write(draw.RESULT,b'ZZZZ')
        self.call('glReadPixels',0,0,0x7fffffff,0x7fffffff,0x1908,0x1401,draw.RESULT)
        self.assertEqual(self.call('glGetError'),0x501);self.assertEqual(bytes(self.arm.uc.mem_read(draw.RESULT,4)),b'ZZZZ')
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Framebuffers.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Framebuffers(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((gl.jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (draw.PORTING/'analysis/framebuffer-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
