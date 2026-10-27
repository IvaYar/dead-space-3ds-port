"""Run existing loader regression tests against stage 2's ARM binary."""
import json
import time
import unittest
import test_arm_loader as common


def setup(cls):
    cls.donor = (common.PORTING / "analysis/candidate-sd/libEAMGameDeadSpace_orig.so").read_bytes()
    cls.arm = common.ARMCore(cls.donor, common.PORTING / "3ds/build-stage2/core-test.elf")
    cls.fixture_path = common.PORTING / "3ds/build-stage2/fixture-regression.so"
    cls.results = {}


if __name__ == "__main__":
    common.LoaderTests.setUpClass = classmethod(setup)
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(common.LoaderTests))
    report = {"tests_run": result.testsRun, "errors": len(result.errors), "failures": len(result.failures),
              "elapsed_seconds": round(time.monotonic() - started, 3), "hardware_tested": False,
              "tested_core": "stage2", **common.LoaderTests.results}
    (common.PORTING / "analysis/stage2-regression.json").write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
