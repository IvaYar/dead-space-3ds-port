"""Exercise import binding and the three exact donor getters as compiled ARM code."""

import ctypes
import json
from pathlib import Path
import struct
import time
import unittest
from test_arm_loader import ARMCore, PORTING, FILE_ADDR, INFO_ADDR, IMAGE_ADDR, STACK_ADDR, STOP_ADDR, symbols
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

NAMES_ADDR, BIND_ADDR, RESULT_ADDR = INFO_ADDR + 0x500, INFO_ADDR + 0x200, INFO_ADDR + 0x300
HOST_ADDR = 0x06000000
PROBES = [
    ('Java_com_ea_blast_ModuleCatalog_NativeGetModuleTypeIdInvalid', 0xe3e00000, -1),
    ('Java_com_ea_blast_DisplayAndroidDelegate_NativeGetOrientationNormal', 0xe3a00001, 1),
    ('Java_com_ea_blast_DeviceOrientationHandlerAndroidDelegate_NativeGetDeviceOrientationUnknown', 0xe3a00000, 0),
]


class Stage2Tests(unittest.TestCase):
    results = {}

    @classmethod
    def setUpClass(cls):
        cls.fixture = (PORTING / '3ds/build-stage2/fixture-stage2.so').read_bytes()
        cls.donor = (PORTING / 'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.arm = ARMCore(cls.fixture, PORTING / '3ds/build-stage2/core-test.elf')
        cls.arm.uc.mem_map(HOST_ADDR, 4096)
        cls.arm.uc.mem_write(HOST_ADDR, struct.pack('<III', 0xe0800080, 0xe2800001, 0xe12fff1e))

    def setUp(self):
        self.arm.set_file(self.fixture)

    def bind(self, count=2):
        first, second = b'host_integer\0', b'host_add_float\0'
        self.arm.uc.mem_write(NAMES_ADDR, first + second)
        self.arm.uc.mem_write(BIND_ADDR, struct.pack('<IIII', NAMES_ADDR, HOST_ADDR, NAMES_ADDR + len(first), HOST_ADDR))
        result = self.arm.call('ds_elf_resolve', FILE_ADDR, INFO_ADDR, IMAGE_ADDR, BIND_ADDR, count, RESULT_ADDR)
        fields = struct.unpack('<IIIII', self.arm.uc.mem_read(RESULT_ADDR, 20))
        return result, fields

    def test_unresolved_strong_import_is_atomic(self):
        result, info = self.arm.prepare(); self.assertEqual(result, 0)
        before = bytes(self.arm.uc.mem_read(IMAGE_ADDR, info.image_size))
        result, resolved = self.bind(count=1)
        self.assertEqual(result, 9)
        self.assertEqual(resolved[:4], (3, 1, 1, 1))
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR, info.image_size)), before)

    def test_bound_module_calls_host_and_missing_weak_is_null(self):
        result, info = self.arm.prepare(); self.assertEqual(result, 0)
        result, resolved = self.bind()
        self.assertEqual(result, 0)
        self.assertEqual(resolved[:4], (3, 2, 0, 1))
        self.assertGreater(resolved[4], 0)
        exports, _ = symbols(self.fixture)
        for name, argument, expected in [('probe_integer', 5, 58), ('probe_weak', 0, 7)]:
            self.arm.uc.reg_write(UC_ARM_REG_R0, argument)
            self.arm.uc.reg_write(UC_ARM_REG_SP, STACK_ADDR + 0x8000)
            self.arm.uc.reg_write(UC_ARM_REG_LR, STOP_ADDR)
            self.arm.uc.emu_start(IMAGE_ADDR + exports[name] - info.load_min, STOP_ADDR, count=10000)
            self.assertEqual(self.arm.uc.reg_read(UC_ARM_REG_PC), STOP_ADDR)
            self.assertEqual(self.arm.uc.reg_read(UC_ARM_REG_R0), expected)
        self.results['fixture_integer'] = 58; self.results['fixture_weak_null'] = 7

    def test_real_donor_constant_getters_verify_and_execute(self):
        self.arm.set_file(self.donor)
        result, info = self.arm.prepare(); self.assertEqual(result, 0)
        observed = {}
        for name, instruction, expected in PROBES:
            self.arm.uc.mem_write(NAMES_ADDR, name.encode() + b'\0')
            result = self.arm.call('ds_elf_constant_export', FILE_ADDR, INFO_ADDR, NAMES_ADDR, instruction, RESULT_ADDR)
            self.assertEqual(result, 0)
            address = struct.unpack('<I', self.arm.uc.mem_read(RESULT_ADDR, 4))[0]
            self.arm.uc.reg_write(UC_ARM_REG_R0, 0); self.arm.uc.reg_write(UC_ARM_REG_R1, 0)
            self.arm.uc.reg_write(UC_ARM_REG_LR, STOP_ADDR)
            self.arm.uc.emu_start(IMAGE_ADDR + address - info.load_min, STOP_ADDR, count=3)
            self.assertEqual(self.arm.uc.reg_read(UC_ARM_REG_PC), STOP_ADDR)
            value = ctypes.c_int32(self.arm.uc.reg_read(UC_ARM_REG_R0)).value
            self.assertEqual(value, expected); observed[name] = value
        self.results['donor_getters'] = observed
        self.results['game_entry_point_called'] = False

    def test_modified_getter_is_rejected(self):
        data = bytearray(self.donor)
        # Known instruction address in the selected file-backed first PT_LOAD segment.
        struct.pack_into('<I', data, 0x3733cc, 0xeafffffe)
        self.arm.set_file(data); self.assertEqual(self.arm.inspect()[0], 0)
        name, instruction, _ = PROBES[1]
        self.arm.uc.mem_write(NAMES_ADDR, name.encode() + b'\0')
        self.assertEqual(self.arm.call('ds_elf_constant_export', FILE_ADDR, INFO_ADDR, NAMES_ADDR, instruction, RESULT_ADDR), 10)


if __name__ == '__main__':
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Stage2Tests))
    report = {'tests_run': result.testsRun, 'errors': len(result.errors), 'failures': len(result.failures),
              'hardware_tested': False, 'native_page_permissions_tested': False,
              'elapsed_seconds': round(time.monotonic() - started, 3), **Stage2Tests.results}
    (PORTING / 'analysis/stage2-tests.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
