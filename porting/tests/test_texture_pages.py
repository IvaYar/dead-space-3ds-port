"""Bounded lossless texture working set through real ARM pager and injected SD boundary."""
import hashlib,json,time,unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_PC,UC_ARM_REG_LR
import test_framebuffers as fb
import test_first_frame as draw
import test_gles_state as gl
OPS=draw.DATA+3000;HOOK=0x06007200
class Pages(fb.Framebuffers):
    def setUp(self):
        super().setUp();self.files={};self.serial=0;self.fail_save=False;self.fail_load=False
        def callback(uc,address,size,user):
            op=(address-HOOK)//4;a,b,n=[uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)];result=0
            if op==0:
                if self.fail_save:result=0xffffffff
                else:
                    old=self.base.words(a)[0];self.serial+=1;self.files[self.serial]=bytes(uc.mem_read(b,n));self.base.write(a,self.serial);self.files.pop(old,None)
            elif op==1:
                if self.fail_load or a not in self.files or len(self.files[a])!=n:result=0xffffffff
                else:uc.mem_write(b,self.files[a])
            else:self.files.pop(a,None)
            uc.reg_write(UC_ARM_REG_R0,result);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        self.hook=self.arm.uc.hook_add(UC_HOOK_CODE,callback,begin=HOOK,end=HOOK+8)
        self.base.write(OPS,HOOK,HOOK+4,HOOK+8)
        self.assertEqual(self.arm.call('ds15_test_backing',OPS,32),0);self.assertEqual(self.arm.call('ds15_test_limits',128,48*1024*1024),0)
    def tearDown(self):
        try:super().tearDown();self.assertEqual(self.files,{})
        finally:self.arm.uc.hook_del(self.hook)
    def stats(self):self.arm.call('ds15_test_pages',draw.RESULT);return self.base.words(draw.RESULT,6)
    def image(self,v):
        t=self.tex();self.arm.uc.mem_write(draw.DATA+2100,bytes((v,v+1,v+2,v+3))*4)
        self.call('glTexSubImage2D',fb.T,0,0,0,2,2,0x1908,0x1401,draw.DATA+2100);return t
    def test_multiple_images_roundtrip_exact_bytes_with_bounded_resident_memory(self):
        names=[self.image(i) for i in (10,20,30,40,50)]
        for t,v in zip(names,(10,20,30,40,50)):
            self.assertEqual(self.pixel(t),bytes((v,v+1,v+2,v+3)));self.assertLessEqual(self.stats()[0],32)
        s=self.stats();self.assertGreater(s[2],0);self.assertGreater(s[3],0);self.assertEqual(s[4:],(0,80))
    def test_subimage_of_spilled_store_survives_next_eviction(self):
        a,b,c=[self.image(i) for i in (10,20,30)]
        self.call('glBindTexture',fb.T,a);self.arm.uc.mem_write(draw.DATA+2100,b'abcd');self.call('glTexSubImage2D',fb.T,0,1,1,1,1,0x1908,0x1401,draw.DATA+2100)
        self.pixel(b);self.pixel(c);self.assertEqual(self.pixel(a,1,1),b'abcd');self.assertEqual(self.pixel(a),bytes((10,11,12,13)))
    def test_spilled_attachment_is_complete_and_clear_modifications_persist(self):
        a,b,c=[self.image(i) for i in (10,20,30)];self.fbo();self.attach(a);self.assertEqual(self.status(),fb.COMPLETE)
        self.color(0,1,0);self.call('glClear',0x4000);self.call('glBindFramebufferOES',fb.FB,0)
        self.pixel(b);self.pixel(c);self.assertEqual(self.pixel(a),bytes((0,255,0,255)))
    def test_save_failure_preserves_existing_pixels(self):
        a,b=self.image(10),self.image(20);self.fail_save=True;self.tex();self.assertEqual(self.call('glGetError'),0x505)
        self.fail_save=False;self.assertEqual(self.pixel(a),bytes((10,11,12,13)));self.assertEqual(self.pixel(b),bytes((20,21,22,23)))
        self.assertEqual(self.stats()[4],1)
    def test_load_failure_never_returns_fabricated_texels_and_can_retry(self):
        a,b,c=[self.image(i) for i in (10,20,30)];self.fail_load=True;self.arm.uc.mem_write(draw.RESULT,b'ZZZZ')
        self.assertEqual(self.arm.call('ds15_test_read',a,0,0,0,draw.RESULT),0xffffffff);self.assertEqual(self.call('glGetError'),0x502)
        self.assertEqual(bytes(self.arm.uc.mem_read(draw.RESULT,4)),b'ZZZZ');self.fail_load=False;self.assertEqual(self.pixel(a),bytes((10,11,12,13)))
    def test_backing_cannot_attach_after_images_exist(self):
        self.image(10);self.assertEqual(self.arm.call('ds15_test_backing',OPS,64),0xffffffff)
    def test_oversize_image_refuses_without_overcommit(self):
        a=self.image(10);self.call('glTexImage2D',fb.T,0,0x1908,4,4,0,0x1908,0x1401,0)
        self.assertEqual(self.call('glGetError'),0x505);self.assertEqual(self.pixel(a),bytes((10,11,12,13)));self.assertEqual(self.stats()[5],16)
    def test_deleting_spilled_texture_drops_private_backing(self):
        a,b,c=[self.image(i) for i in (10,20,30)];self.assertTrue(self.files)
        self.base.write(draw.RESULT,a);self.call('glDeleteTextures',1,draw.RESULT);self.assertEqual(self.files,{})
        self.assertEqual(self.stats()[5],32)
    def test_deleted_unbound_fbo_attachment_can_be_paged_and_drawn(self):
        a=self.image(10);f=self.fbo();self.attach(a);self.call('glBindFramebufferOES',fb.FB,0)
        self.base.write(draw.RESULT,a);self.call('glDeleteTextures',1,draw.RESULT);b,c=self.image(20),self.image(30)
        self.call('glBindFramebufferOES',fb.FB,f);self.assertEqual(self.status(),fb.COMPLETE);self.color(1,0,0);self.call('glClear',0x4000)
        self.assertEqual(self.call('glGetError'),0)
    def test_pinned_fbo_and_two_sampled_stores_refuse_overcommit(self):
        a,b,c=[self.image(i) for i in (10,20,30)];self.fbo();self.attach(a);self.call('glClear',0x4000)
        self.call('glBindTexture',fb.T,b);self.call('glEnable',fb.T);self.call('glActiveTexture',0x84c1);self.call('glBindTexture',fb.T,c);self.call('glEnable',fb.T)
        self.quad_at();self.assertEqual(self.call('glGetError'),0x505);self.assertLessEqual(self.stats()[0],32)
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Pages.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Pages(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((gl.jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (draw.PORTING/'analysis/texture-pages-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
