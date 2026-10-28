"""ARM default depth/stencil ownership, clear masks, color swaps and FBO isolation."""
import hashlib,json,struct,time,unittest
import test_framebuffers as fb
import test_first_frame as draw
import test_gles_state as gl
class Default(fb.Framebuffers):
    def setUp(self):super().setUp();self.assertEqual(self.arm.call('ds33_attach',gl.CTX,16,8),0)
    def quad_z(self,z,color):self.quad((-1,-1,z,1,-1,z,-1,1,z,1,1,z));self.rgba(*color);self.call('glDrawArrays',5,0,4)
    def test_bits_and_stencil_ref_reflect_real_default_attachments(self):
        self.assertEqual(self.query(0xd56,1),(16,));self.assertEqual(self.query(0xd57,1),(8,));self.call('glStencilFunc',0x207,511,255);self.assertEqual(self.query(0xb97,1),(255,))
    def test_depth_rejects_farther_geometry_on_default_surface(self):
        self.call('glEnable',0xb71);self.quad_z(-.5,(1,0,0,1));self.quad_z(.5,(0,1,0,1));self.assertEqual(self.pixels(),bytes((255,0,0))*12)
    def test_depth_function_and_write_mask(self):
        self.call('glEnable',0xb71);self.call('glDepthMask',0);self.quad_z(-.5,(1,0,0,1));self.call('glDepthMask',1);self.quad_z(.5,(0,1,0,1));self.assertEqual(self.pixels(),bytes((0,255,0))*12)
        self.call('glDepthFunc',0x204);self.quad_z(.75,(0,0,1,1));self.assertEqual(self.pixels(),bytes((0,0,255))*12)
    def test_scissor_depth_clear_affects_only_selected_pixel(self):
        self.call('glEnable',0xb71);self.quad_z(-.5,(1,0,0,1));self.call('glEnable',0xc11);self.call('glScissor',1,1,1,1);self.call('glClear',0x100);self.call('glDisable',0xc11)
        self.quad_z(.5,(0,1,0,1));expected=bytearray(bytes((255,0,0))*12);expected[(1*4+1)*3:(1*4+2)*3]=bytes((0,255,0));self.assertEqual(self.pixels(),expected)
    def test_depth_clear_respects_depth_write_mask(self):
        self.call('glEnable',0xb71);self.quad_z(-.5,(1,0,0,1));self.call('glDepthMask',0);self.call('glClear',0x100);self.call('glDepthMask',1);self.quad_z(.5,(0,1,0,1));self.assertEqual(self.pixels(),bytes((255,0,0))*12)
    def test_stencil_clear_mask_and_comparison(self):
        self.call('glStencilMask',15);self.call('glClearStencil',0xa5);self.call('glClear',0x400);self.call('glEnable',0xb90);self.call('glStencilFunc',0x202,5,255)
        self.quad_z(0,(0,1,0,1));self.call('glStencilFunc',0x202,0xa5,255);self.quad_z(0,(1,0,0,1));self.assertEqual(self.pixels(),bytes((0,255,0))*12)
    def test_stencil_depth_fail_op_updates_actual_storage(self):
        self.call('glEnable',0xb71);self.quad_z(-.5,(1,0,0,1));self.call('glEnable',0xb90);self.call('glStencilFunc',0x207,7,255);self.call('glStencilOp',0x1e00,0x1e01,0x1e00);self.quad_z(.5,(0,1,0,1))
        self.call('glDisable',0xb71);self.call('glStencilFunc',0x202,7,255);self.quad_z(0,(0,0,1,1));self.assertEqual(self.pixels(),bytes((0,0,255))*12)
    def test_color_target_swap_preserves_owned_depth(self):
        self.call('glEnable',0xb71);self.quad_z(-.5,(1,0,0,1));new=draw.DATA+1200;self.arm.uc.mem_write(new,bytes((0,0,255))*12)
        self.assertEqual(self.arm.call('ds13_target',gl.CTX,new,36),0);self.quad_z(.5,(0,1,0,1));self.assertEqual(bytes(self.arm.uc.mem_read(new,36)),bytes((0,0,255))*12)
        self.assertEqual(self.arm.call('ds13_target',gl.CTX,gl.PIX,36),0);self.assertEqual(self.pixels(),bytes((255,0,0))*12)
    def test_fbo_depth_storage_does_not_alias_default(self):
        self.call('glEnable',0xb71);self.quad_z(0,(1,0,0,1));self.setup_target();self.rbo();self.call('glClear',0x4100);self.quad_z(-.75,(0,1,0,1))
        self.assertEqual(self.query(0xd57,1),(0,));self.call('glBindFramebufferOES',fb.FB,0);self.call('glViewport',0,0,4,3);self.assertEqual(self.query(0xd57,1),(8,))
        self.quad_z(.5,(0,0,1,1));self.assertEqual(self.pixels(),bytes((255,0,0))*12)
    def test_depth_only_and_stencil_only_configurations(self):
        self.arm.call('ds33_close',gl.CTX);self.assertEqual(self.arm.call('ds33_attach',gl.CTX,16,0),0);self.assertEqual(self.query(0xd56,1),(16,));self.assertEqual(self.query(0xd57,1),(0,))
        self.arm.call('ds33_close',gl.CTX);self.assertEqual(self.arm.call('ds33_attach',gl.CTX,0,8),0);self.assertEqual(self.query(0xd56,1),(0,));self.assertEqual(self.query(0xd57,1),(8,))
    def test_invalid_configs_and_repeated_attach_are_atomic(self):
        for depth,stencil in ((0,0),(24,8),(16,16)):
            self.assertEqual(self.arm.call('ds33_attach',gl.CTX,depth,stencil),0xffffffff)
        self.assertEqual(self.arm.call('ds33_attach',gl.CTX,16,8),0xffffffff);self.assertEqual(self.query(0xd56,1),(16,))
    def test_rgb565_ctr_color_layout_uses_same_logical_depth_indices(self):
        self.arm.call('ds13_close',gl.CTX);self.assertEqual(self.arm.call('ds13_init',gl.CTX,gl.PIX,4,3,24,2),0);self.arm.call('ds13_current',gl.CTX);self.assertEqual(self.arm.call('ds33_attach',gl.CTX,16,8),0)
        self.assertEqual(self.arm.call('ds22_client_range',gl.CTX,draw.DATA,4096),0)
        self.call('glEnable',0xb71);self.quad_z(-.5,(1,0,0,1));self.quad_z(.5,(0,1,0,1));self.call('glReadPixels',0,0,4,3,0x1908,0x1401,draw.RESULT);self.assertEqual(self.call('glGetError'),0)
        self.assertEqual(bytes(self.arm.uc.mem_read(draw.RESULT,48)),bytes((255,0,0,255))*12)
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Default.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Default(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((draw.PORTING/'3ds/build-emulator/core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (draw.PORTING/'analysis/default-surface-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
