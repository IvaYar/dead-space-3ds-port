"""Run earlier ARM loader/runtime/thread suites against the stage 8 core."""
import json,time,unittest
import test_stage7_regression as previous
import test_stage7_threads as threads
BUILD=previous.old.common.PORTING/'3ds/build-stage8'
previous.old.BUILD=previous.BUILD=BUILD
class ThreadRegression(threads.ThreadTests):
    @classmethod
    def setUpClass(cls):
        cls.donor=(threads.PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.fixture=(BUILD/'fixture-stage7.so').read_bytes()
        cls.arm=previous.old.arm(cls.donor,True)
if __name__=='__main__':
    start=time.monotonic(); suite=unittest.TestSuite()
    for case in (previous.old.LoaderRegression,previous.old.IORegression,previous.old.RuntimeRegression,previous.LibcRegression,ThreadRegression):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tested_core':'stage8','tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
        'elapsed_seconds':round(time.monotonic()-start,3),'hardware_tested':False,'suites':['ELF','I/O','runtime','Bionic','thread ABI']}
    (threads.PORTING/'analysis/stage8-regression.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
