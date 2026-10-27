"""Run earlier loader, I/O, math and Bionic adapter suites on stage 7 ARM code."""
import json
import time
import unittest
import test_stage6_regression as old
import test_stage6_libc as libc

BUILD=old.common.PORTING/'3ds/build-stage7'
old.BUILD=BUILD

class LibcRegression(libc.LibcTests):
    @classmethod
    def setUpClass(cls):
        cls.donor=(old.common.PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.fixture=(BUILD/'fixture-stage6.so').read_bytes(); cls.arm=old.arm(cls.donor,True)
        cls.exports,_=old.common.symbols(cls.fixture)

if __name__=='__main__':
    start=time.monotonic(); suite=unittest.TestSuite()
    for case in (old.LoaderRegression,old.IORegression,old.RuntimeRegression,LibcRegression):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tested_core':'stage7','tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
            'elapsed_seconds':round(time.monotonic()-start,3),'hardware_tested':False,
            'suites':['ELF loader','stage4 I/O','stage5 memory/string/math','stage6 Bionic adapters']}
    (old.common.PORTING/'analysis/stage7-regression.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
