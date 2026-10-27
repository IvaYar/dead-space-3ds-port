"""Run prior loader, I/O and memory/math suites against stage 6's ARM binary."""
import json
import time
import unittest
import test_arm_loader as common
import test_stage4_io as io
import test_stage5_runtime as runtime
from unicorn.arm_const import UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC

BUILD=common.PORTING/'3ds/build-stage6'

def arm(donor,context=False):
    result=common.ARMCore(donor,BUILD/'core-test.elf')
    result.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000); result.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
    if context: result.uc.mem_map(0x06000000,0x10000)
    return result

class LoaderRegression(common.LoaderTests):
    @classmethod
    def setUpClass(cls):
        cls.donor=(common.PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.arm=arm(cls.donor); cls.fixture_path=BUILD/'fixture-regression.so'; cls.results={}

class IORegression(io.IOTests):
    @classmethod
    def setUpClass(cls):
        cls.donor=(common.PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.asset=(common.PORTING/'analysis/candidate-sd/assets/published/data/achievements.sb').read_bytes()
        cls.fixture=(BUILD/'fixture-stage4.so').read_bytes(); cls.arm=arm(cls.donor,True)
        cls.size=cls.arm.call('ds_io_context_size'); cls.results={}

class RuntimeRegression(runtime.RuntimeTests):
    @classmethod
    def setUpClass(cls):
        cls.donor=(common.PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.fixture=(BUILD/'fixture-stage5.so').read_bytes(); cls.arm=arm(cls.donor,True)
        cls.exports,_=common.symbols(cls.fixture); cls.results={}

if __name__=='__main__':
    start=time.monotonic(); suite=unittest.TestSuite()
    for case in (LoaderRegression,IORegression,RuntimeRegression): suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tested_core':'stage6','tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
            'elapsed_seconds':round(time.monotonic()-start,3),'hardware_tested':False,
            'suites':['ELF loader','stage4 I/O','stage5 memory/string/math']}
    (common.PORTING/'analysis/stage6-regression.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
