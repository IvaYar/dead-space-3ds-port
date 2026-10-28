"""ARM JNI monitor ownership/lifetime contracts; contention uses the native DS7 backend."""
import hashlib,json,time,unittest
import test_jni10 as jni
class Monitors(jni.Jni10Tests):
    def mutexes(self):
        self.arm.call('ds7_stats',jni.OUT);return self.base.words(jni.OUT,6)[2]
    def test_recursive_enters_require_matching_exits(self):
        a=self.env(176,4)
        for _ in range(3):self.assertEqual(self.env(217,a),0)
        self.assertEqual(self.mutexes(),1)
        for _ in range(3):self.assertEqual(self.env(218,a),0)
        self.assertEqual(self.env(218,a),0xffffffff);self.assertTrue(self.exception());self.clear()
        self.delete(a);self.assertEqual(self.mutexes(),0)
    def test_global_alias_and_original_share_monitor(self):
        a=self.env(176,4);g=self.env(21,a)
        self.assertEqual(self.env(217,a),0);self.assertEqual(self.env(217,g),0);self.assertEqual(self.mutexes(),1)
        self.delete(a);self.assertEqual(self.env(171,g),4)
        for _ in range(2):self.assertEqual(self.env(218,g),0)
        self.delete(g,True);self.assertEqual(self.mutexes(),0)
    def test_different_payloads_have_independent_monitors(self):
        a,b=self.env(176,4),self.env(176,4)
        for obj in (a,b):self.assertEqual(self.env(217,obj),0)
        self.assertEqual(self.mutexes(),2)
        for obj in (b,a):self.assertEqual(self.env(218,obj),0);self.delete(obj)
        self.assertEqual(self.mutexes(),0)
    def test_exit_without_enter_raises_exception(self):
        a=self.find('java/lang/String');self.assertEqual(self.env(218,a),0xffffffff);self.assertTrue(self.exception())
        self.assertEqual(self.mutexes(),0)
    def test_null_and_stale_references_cannot_lock(self):
        a=self.env(176,4);self.delete(a)
        for slot in (217,218):
            for obj in (0,a,0x12345678):
                self.assertEqual(self.env(slot,obj),0xffffffff);self.assertTrue(self.exception());self.clear()
        self.assertEqual(self.mutexes(),0)
    def test_foreign_context_reference_is_rejected(self):
        a=self.find('java/lang/String');other=jni.CTX+0x2000
        self.assertEqual(self.arm.call('ds10_init',other,0,0),0)
        self.assertEqual(self.env(217,a,context=other),0xffffffff);self.assertEqual(self.arm.call('ds10_cleanup',other),0)
        self.assertEqual(self.mutexes(),0)
    def test_non_owner_cannot_release_or_erase_owner_depth(self):
        a=self.env(176,4);self.assertEqual(self.env(217,a),0)
        self.arm.call('ds7_test_select_tls',1)
        try:self.assertEqual(self.env(218,a),0xffffffff);self.assertTrue(self.exception())
        finally:self.arm.call('ds7_test_select_tls',0)
        self.clear();self.assertEqual(self.env(218,a),0);self.delete(a);self.assertEqual(self.mutexes(),0)
    def test_cleanup_refuses_entered_monitor_and_retains_context(self):
        a=self.env(176,4);self.assertEqual(self.env(217,a),0)
        self.assertEqual(self.arm.call('ds10_cleanup',jni.CTX),0xffffffff);self.assertEqual(self.env(171,a),4)
        self.assertEqual(self.arm.call('ds10_init',jni.CTX,0,0),16)
        self.clear();self.assertEqual(self.env(218,a),0)
        self.assertNotEqual(self.arm.call('ds10_cleanup',jni.CTX),0xffffffff);self.assertEqual(self.mutexes(),0)
    def test_capacity_refuses_extra_live_object_and_recovers_after_release(self):
        names=['com/ea/EAIO/EAIO','com/ea/blast/MainActivity','android/content/res/AssetManager','java/io/InputStream',
            'android/content/res/AssetFileDescriptor','java/io/FileDescriptor','com/ea/blast/SystemAndroidDelegate',
            'com/ea/blast/PowerManagerAndroid','com/ea/blast/DisplayAndroidDelegate','com/eamobile/Query',
            'com/ea/blast/GetAppDataDirectoryDelegate','com/ea/blast/DeviceOrientationHandlerAndroidDelegate',
            'com/ea/blast/AccelerometerAndroidDelegate','java/lang/String','[Ljava/lang/String;',
            'com/ea/blast/TouchSurfaceAndroid']
        refs=[self.find(name) for name in names];self.assertNotIn(0,refs)
        for obj in refs:self.assertEqual(self.env(217,obj),0);self.assertEqual(self.env(218,obj),0)
        a=self.env(176,4);self.assertEqual(self.env(217,a),0xffffffff);self.assertTrue(self.exception());self.clear()
        self.delete(refs.pop());self.assertEqual(self.env(217,a),0);self.assertEqual(self.env(218,a),0)
        for obj in refs+[a]:self.delete(obj)
        self.assertEqual(self.mutexes(),0)
    def test_idle_monitors_destroyed_by_cleanup(self):
        for _ in range(3):
            a=self.env(176,4);self.assertEqual(self.env(217,a),0);self.assertEqual(self.env(218,a),0)
        self.assertEqual(self.mutexes(),3);self.arm.call('ds10_cleanup',jni.CTX);self.assertEqual(self.mutexes(),0)
    def test_string_monitor_is_not_bound_to_reference_token(self):
        a=self.make_string('monitor');g=self.env(21,a);self.assertEqual(self.env(217,a),0)
        self.delete(a);self.assertEqual(self.env(168,g),7);self.assertEqual(self.env(218,g),0)
        self.delete(g,True);self.assertEqual(self.mutexes(),0)
    def test_native_mutex_pool_failure_does_not_leave_busy_or_uncollectable_monitor(self):
        words=[jni.cpp.OBJECT+i*4 for i in range(64)]
        for word in words:self.assertEqual(self.base.call('pthread_mutex_init',word,0),0)
        a=self.env(176,4);self.assertEqual(self.env(217,a),0xffffffff);self.assertTrue(self.exception());self.clear()
        self.delete(a);self.assertEqual(self.mutexes(),64)
        self.assertNotEqual(self.arm.call('ds10_cleanup',jni.CTX),0xffffffff)
        for word in words:self.assertEqual(self.base.call('pthread_mutex_destroy',word),0)
        self.assertEqual(self.mutexes(),0)
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Monitors.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Monitors(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (jni.cpp.PORTING/'analysis/jni-monitors-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
