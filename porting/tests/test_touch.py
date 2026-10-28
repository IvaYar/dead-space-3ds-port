"""Execute the one-pointer Android input adapter as ARM code, including softfp."""
import hashlib,json,struct,time,unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_PC,UC_ARM_REG_LR
import test_platform_jni as platform
from test_jni10 import CTX,OUT
TOUCH=0x06008800;HOOK=0x06007f00
class TouchTests(platform.PlatformTests):
    def setUp(self):
        super().setUp();self.events=[]
        def emit(uc,address,size,user):
            regs=[uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
            pid,x,y=struct.unpack('<Iff',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),12))
            self.events.append((*regs,pid,x,y));uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        self.hook=self.arm.uc.hook_add(UC_HOOK_CODE,emit,begin=HOOK,end=HOOK)
    def tearDown(self):
        self.arm.call('ds23_touch_close',TOUCH);self.arm.uc.hook_del(self.hook);super().tearDown()
    def init(self,w=320,h=240,fn=HOOK):return self.arm.call('ds23_touch_init',TOUCH,CTX,w,h,fn)
    def sample(self,pressed,x=0,y=0):return self.arm.call('ds23_touch_sample',TOUCH,pressed,x,y)
    def count(self):
        c,o=self.obj('com/ea/blast/SystemAndroidDelegate');m=self.method(c,'GetTouchScreenCount','()Ljava/lang/String;')
        s=self.env(34,o,m);value=self.value(s)
        for handle in (s,o,c):self.delete(handle)
        return value
    def test_capability_only_while_real_callback_backend_attached(self):
        self.assertEqual(self.count(),'0');self.assertEqual(self.init(),0);self.assertEqual(self.count(),'1')
        self.assertEqual(self.arm.call('ds23_touch_close',TOUCH),0);self.assertEqual(self.count(),'0')
    def test_invalid_source_dimensions_and_missing_callback_are_atomic(self):
        before=bytes(self.arm.uc.mem_read(TOUCH,40))
        for w,h,fn in ((0,240,HOOK),(320,0,HOOK),(4097,1,HOOK),(1,4097,HOOK),(320,240,0)):
            self.assertEqual(self.init(w,h,fn),0xffffffff);self.assertEqual(bytes(self.arm.uc.mem_read(TOUCH,40)),before)
        self.assertEqual(self.count(),'0')
    def test_second_attachment_cannot_steal_bridge_or_active_state(self):
        self.init();self.sample(1,40,50);before=bytes(self.arm.uc.mem_read(TOUCH,40))
        self.assertEqual(self.init(),0xffffffff)
        self.assertEqual(self.arm.call('ds23_touch_init',TOUCH+64,CTX,320,240,HOOK),0xffffffff)
        self.assertEqual(bytes(self.arm.uc.mem_read(TOUCH,40)),before)
    def test_softfp_signature_has_three_integer_and_two_float_arguments(self):
        self.init();self.assertEqual(self.sample(1,160,120),1)
        self.assertEqual(self.events,[(CTX,0,0x6000c,1000,0,200.0,120.0)])
    def test_down_move_up_sequence_and_surface_coordinate_scaling(self):
        self.init();self.sample(1,0,0);self.sample(1,319,239);self.sample(0)
        self.assertEqual([e[2] for e in self.events],[0x6000c,0x4000c,0x8000c])
        self.assertEqual(self.events[1][-2:],(398.75,239.0));self.assertEqual(self.events[2][-2:],(398.75,239.0))
    def test_stationary_hold_and_repeated_release_emit_no_duplicates(self):
        self.init();self.assertEqual(self.sample(0),0);self.sample(1,5,6)
        for _ in range(10):self.assertEqual(self.sample(1,5,6),0)
        self.assertEqual(self.sample(0),1);self.assertEqual(self.sample(0),0);self.assertEqual(len(self.events),2)
    def test_invalid_samples_keep_pressed_state_coordinates_and_event_count(self):
        self.init();self.sample(1,80,90);before=bytes(self.arm.uc.mem_read(TOUCH,40))
        for p,x,y in ((2,0,0),(1,320,0),(1,0,240),(1,0xffffffff,10)):
            self.assertEqual(self.sample(p,x,y),0xffffffff);self.assertEqual(bytes(self.arm.uc.mem_read(TOUCH,40)),before)
        self.assertEqual(len(self.events),1)
    def test_release_ignores_hid_invalid_or_zero_coordinates(self):
        self.init();self.sample(1,80,90);self.sample(0,0xffffffff,0xffffffff)
        self.assertEqual(self.events[-1][-2:],(100.0,90.0))
    def test_close_cancels_held_pointer_and_clears_capability(self):
        self.init();self.sample(1,120,100);self.arm.call('ds23_touch_close',TOUCH)
        self.assertEqual(self.events[-1][2],12);self.assertEqual(self.events[-1][-2:],(150.0,100.0));self.assertEqual(self.count(),'0')
        self.assertEqual(self.sample(1),0xffffffff)
    def test_idle_close_sends_no_cancel_and_reinitialization_starts_fresh(self):
        self.init();self.arm.call('ds23_touch_close',TOUCH);self.assertEqual(self.events,[])
        self.assertEqual(self.init(),0);self.sample(1);self.assertEqual(self.events[-1][2],0x6000c)
    def test_input_does_not_consume_local_reference_slots_or_native_heap(self):
        self.init();self.env(19,8);before=self.stats()[4]
        for i in range(150):self.sample(1,i%320,i%240)
        self.sample(0);self.env(20,0);self.assertEqual(self.stats()[4],before)
        self.arm.call('ds_runtime_stats',OUT);self.assertEqual(self.base.words(OUT,9)[4:6],(0,0))
    def test_missing_or_cleaned_java_context_is_rejected(self):
        self.assertEqual(self.arm.call('ds23_touch_init',TOUCH,0,320,240,HOOK),0xffffffff)
        self.init();self.arm.call('ds10_cleanup',CTX);self.assertEqual(self.sample(1),0xffffffff);self.assertEqual(self.events,[])
    def test_custom_source_dimensions_preserve_logical_surface_coordinates(self):
        self.init(800,480);self.sample(1,400,240);self.assertEqual(self.events[-1][-2:],(200.0,120.0))
    def test_multitouch_query_matches_single_pointer_backend_and_refuses_absence(self):
        c=self.find('com/ea/blast/TouchSurfaceAndroid');m=self.method(c,'IsTouchScreenMultiTouch','()Z',True)
        self.assertEqual(self.env(117,c,m),0);self.assertTrue(self.exception());self.clear()
        self.init();self.assertEqual(self.env(117,c,m),0);self.assertFalse(self.exception())
        self.env(114,c,m);self.assertTrue(self.exception())

if __name__=='__main__':
    start=time.monotonic();names=[n for n in TouchTests.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(TouchTests(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((platform.jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-start,3)}
    (platform.jni.cpp.PORTING/'analysis/touch-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
