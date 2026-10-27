"""JNI sensor ownership, Android delay and callbacks through actual ARM code."""
import hashlib,json,struct,time,unittest
import test_platform_jni as platform
from test_jni10 import CTX,OUT
class SensorJniTests(platform.PlatformTests):
    def setup_sensor(self):
        self.assertEqual(self.arm.call('ds12_test_attach',CTX,0),0)
        cls,obj=self.obj('com/ea/blast/AccelerometerAndroidDelegate')
        return cls,obj,self.method(cls,'SetEnabled','(Z)V'),self.method(cls,'SetUpdateFrequency','(I)V')
    def sensor_stats(self):
        self.arm.call('ds12_test_stats',CTX,OUT);return self.base.words(OUT,13)
    def pump(self,t):return self.arm.call('ds12_test_pump',CTX,t&0xffffffff,t>>32)
    def test_capability_only_after_backend_attachment(self):
        cls,o=self.obj('com/ea/blast/SystemAndroidDelegate');m=self.method(cls,'GetAccelerometerCount','()Ljava/lang/String;')
        before=self.env(34,o,m);self.assertEqual(self.value(before),'0');self.delete(before)
        self.assertEqual(self.arm.call('ds12_test_attach',CTX,0),0)
        after=self.env(34,o,m);self.assertEqual(self.value(after),'1');self.delete(after)
        self.assertEqual(self.arm.call('ds12_test_attach',CTX,0),0xffffffff)
    def test_constructor_refuses_unattached_backend(self):
        cls=self.find('com/ea/blast/AccelerometerAndroidDelegate');m=self.method(cls,'<init>','()V')
        self.assertEqual(self.env(30,cls,m,0),0);self.assertTrue(self.exception())
    def test_android_delay_controls_callback_interval(self):
        cls,o,on,rate=self.setup_sensor();self.assertEqual(self.sensor_stats()[1],200000)
        self.env(63,o,rate,self.values(2));self.assertEqual(self.sensor_stats()[1],60000)
        self.env(63,o,on,self.values(1));self.assertEqual(self.pump(0),1);self.assertEqual(self.pump(59999),0);self.assertEqual(self.pump(60000),1)
        self.env(63,o,rate,self.values(-1));self.assertTrue(self.exception());self.assertEqual(self.sensor_stats()[1],60000)
        self.clear();self.env(63,o,rate,self.values(1));self.assertEqual(self.sensor_stats()[1],20000)
        self.assertEqual(self.sensor_stats()[3],3);self.assertEqual(self.pump(60001),1)
    def test_softfp_callback_uses_live_receiver_and_scoped_references(self):
        cls,o,on,rate=self.setup_sensor();before=self.stats()[4];self.env(63,o,on,self.values(1))
        self.assertEqual(self.pump(0),1);a=self.sensor_stats();self.assertEqual(a[5],1);self.assertEqual(a[6],CTX)
        self.assertEqual(a[12],1)
        self.assertEqual(self.env(24,a[7],o),0);self.assertTrue(self.exception());self.clear()
        xyz=struct.unpack('<3f',struct.pack('<3I',*a[8:11]))
        for actual,want in zip(xyz,(9.80665,-4.903325,-9.80665)):self.assertAlmostEqual(actual,want,places=5)
        self.assertEqual(self.stats()[4],before)
    def test_service_lives_after_local_frame_is_popped(self):
        self.env(19,8);cls,o,on,rate=self.setup_sensor();self.env(63,o,on,self.values(1));self.env(20,0)
        self.assertEqual(self.pump(0),1);self.assertEqual(self.sensor_stats()[5],1)
    def test_enable_failure_does_not_publish_enabled_state(self):
        cls,o,on,rate=self.setup_sensor();self.arm.call('ds12_test_failure',1,1)
        self.env(63,o,on,self.values(1));self.assertTrue(self.exception());self.assertEqual(self.sensor_stats()[0],0)
        self.arm.call('ds12_test_failure',0,1)
    def test_cleanup_failure_preserves_state_for_retry(self):
        cls,o,on,rate=self.setup_sensor();self.env(63,o,on,self.values(1));self.arm.call('ds12_test_failure',1,1)
        self.assertEqual(self.arm.call('ds10_cleanup',CTX),0xffffffff);self.assertEqual(self.sensor_stats()[0],1)
        self.arm.call('ds12_test_failure',0,1);self.clear();self.assertNotEqual(self.arm.call('ds10_cleanup',CTX),0xffffffff)
        self.assertEqual(self.sensor_stats()[0],0)
    def test_disable_cancels_events_and_reinit_requires_cleanup(self):
        cls,o,on,rate=self.setup_sensor();self.env(63,o,on,self.values(1));self.pump(0)
        self.env(63,o,on,self.values(0));self.assertEqual(self.pump(200000),0);self.assertEqual(self.sensor_stats()[5],1)
        self.assertEqual(self.arm.call('ds10_init',CTX,0,0),16)
if __name__=='__main__':
    start=time.monotonic();names=[n for n in SensorJniTests.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(SensorJniTests(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'elapsed_seconds':round(time.monotonic()-start,3),'core_sha256':hashlib.sha256((platform.jni.BUILD/'core-test.elf').read_bytes()).hexdigest()}
    (platform.jni.cpp.PORTING/'analysis/sensor-jni-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
