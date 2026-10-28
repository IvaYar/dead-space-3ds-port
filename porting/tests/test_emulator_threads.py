"""Emulator semaphore capacity after observed native 32-slot exhaustion."""
import hashlib,json,time,unittest
import test_jni10 as jni
class Capacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):jni.cpp.CppTests.setUpClass()
    def setUp(self):
        self.base=jni.cpp.CppTests();self.base.setUp();self.arm=self.base.arm
    def tearDown(self):self.base.tearDown()
    def sem(self,i):return jni.cpp.OBJECT+i*4
    def count(self):
        self.arm.call('ds7_stats',jni.OUT);return self.base.words(jni.OUT,6)[4]
    def test_all_64_slots_are_real_and_independent(self):
        for i in range(64):self.assertEqual(self.base.call('sem_init',self.sem(i),0,i),0)
        self.assertEqual(self.count(),64)
        for i in range(64):
            self.assertEqual(self.base.call('sem_getvalue',self.sem(i),jni.OUT),0);self.assertEqual(self.base.words(jni.OUT)[0],i)
            self.assertEqual(self.base.call('sem_destroy',self.sem(i)),0)
        self.assertEqual(self.count(),0)
    def test_65th_refusal_preserves_output_and_recovers_after_destroy(self):
        for i in range(64):self.assertEqual(self.base.call('sem_init',self.sem(i),0,0),0)
        self.base.write(self.sem(64),0xabcdef01)
        self.assertEqual(self.base.call('sem_init',self.sem(64),0,0),-1)
        self.assertEqual(self.base.words(self.arm.call('ds_io_errno'))[0],28);self.assertEqual(self.base.words(self.sem(64))[0],0xabcdef01)
        self.assertEqual(self.base.call('sem_destroy',self.sem(17)),0);self.assertEqual(self.base.call('sem_init',self.sem(64),0,3),0)
        for i in list(range(17))+list(range(18,65)):self.assertEqual(self.base.call('sem_destroy',self.sem(i)),0)
        self.assertEqual(self.count(),0)
    def test_reinitializing_live_slot_keeps_count_and_value(self):
        self.assertEqual(self.base.call('sem_init',self.sem(0),0,7),0)
        self.assertEqual(self.base.call('sem_init',self.sem(0),0,1),-1)
        self.assertEqual(self.base.words(self.arm.call('ds_io_errno'))[0],16);self.assertEqual(self.count(),1)
        self.assertEqual(self.base.call('sem_getvalue',self.sem(0),jni.OUT),0);self.assertEqual(self.base.words(jni.OUT)[0],7)
        self.assertEqual(self.base.call('sem_destroy',self.sem(0)),0)
    def test_consumption_and_post_work_above_old_32_slot_limit(self):
        for i in range(40):self.assertEqual(self.base.call('sem_init',self.sem(i),0,1),0)
        self.assertEqual(self.base.call('sem_wait',self.sem(39)),0);self.assertEqual(self.base.call('sem_trywait',self.sem(39)),-1)
        self.assertEqual(self.base.call('sem_post',self.sem(39)),0);self.assertEqual(self.base.call('sem_wait',self.sem(39)),0)
        for i in range(40):self.assertEqual(self.base.call('sem_destroy',self.sem(i)),0)
        self.assertEqual(self.count(),0)
if __name__=='__main__':
    started=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Capacity))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (jni.cpp.PORTING/'analysis/emulator-threads-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
