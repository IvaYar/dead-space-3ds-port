"""Run the compiled native backend and actual libctru SVC wrappers in ARM11.

The simulated kernel models QueryMemory's R/W-only view and QueryProcessMemory's
R/W/X view. It does not exercise real MMU/cache hardware or replace a device test.
"""

import ctypes
import json
import struct
import time
import unittest
from test_arm_loader import ARMCore, PORTING, INFO_ADDR, IMAGE_ADDR
from unicorn import UC_HOOK_INTR
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_PC,
                               UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC)

REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5)
HANDLE = 0x1234


class ModelCacheTranslationAbort(Exception):
    """Model of an I-cache MVA operation on an unmapped remote-core VA."""


class BackendARM(ARMCore):
    def __init__(self, before_fix=False, before_cache_fix=False):
        name = 'exec-before-cache-fix-test.elf' if before_cache_fix else ('exec-before-fix-test.elf' if before_fix else 'exec-native-test.elf')
        super().__init__(b'', PORTING / '3ds/build-stage2' / name)
        # Horizon enables VFP for the application before its entry point.
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0x00f00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.events = []
        self.permissions = {}
        self.fail = {}
        self.override_permission = None
        self.shift_query_range = False
        self.luma_version = 0x0d030300
        self.remote_va_available = False
        self.uc.hook_add(UC_HOOK_INTR, self.interrupt)

    def outputs(self, *values):
        for reg, value in zip(REGS, values): self.uc.reg_write(reg, value & 0xffffffff)

    def interrupt(self, uc, number, unused):
        pc = uc.reg_read(UC_ARM_REG_PC)
        instruction = struct.unpack('<I', uc.mem_read(pc - 4, 4))[0]
        assert number == 2 and instruction & 0xff000000 == 0xef000000
        svc = instruction & 0xffffff
        args = [uc.reg_read(reg) for reg in REGS]
        self.events.append((svc, args))
        if svc in self.fail:
            self.outputs(self.fail[svc]); return
        if svc == 0x2a:  # GetSystemInfo: output pointer is preserved by the real wrapper.
            if args[1] == 0x20000: self.outputs(1, 0, 0)
            elif args[1] == 0x10000: self.outputs(0, self.luma_version, 0)
            else: raise AssertionError(args)
        elif svc == 0x27:
            assert args[1] == 0xffff8001
            self.outputs(0, HANDLE)
        elif svc == 0x54:
            assert args[0] == HANDLE and args[1] % 4096 == 0 and args[2] == 4096
            self.outputs(0)
        elif svc == 0x70:
            handle, address, other, size, operation, permission = args
            assert handle == HANDLE and other == 0 and size == 4096 and operation == 6
            assert address % 4096 == 0 and permission in (3, 5)
            self.permissions[address] = permission
            self.outputs(0)
        elif svc in (0x02, 0x7d):
            address = args[2] if svc == 0x02 else args[3]
            if svc == 0x7d: assert args[2] == HANDLE
            page = address & ~4095
            permission = self.permissions.get(page, 3)
            if self.override_permission is not None: permission = self.override_permission
            # Exact platform distinction that caused the reported fffffc15 failure.
            permission &= 3 if svc == 0x02 else 7
            self.outputs(0, page + (4096 if self.shift_query_range else 0), 4096, permission, 5, 0)
        elif svc == 0x93:
            assert args[0] % 4096 == 0 and args[1] == 4096
            if not self.remote_va_available:
                raise ModelCacheTranslationAbort(f'MVA {args[0]:08x} is not mapped in another core context')
            self.outputs(0)
        elif svc == 0x94:
            assert args[0] == 0 and args[1] == 0  # Entire cache, no application address operand.
            self.outputs(0)
        elif svc == 0x23:
            assert args[0] == HANDLE
            self.outputs(0)
        else:
            raise AssertionError(f'Unexpected SVC {svc:x}, args {args}')

    def open(self): return self.call('ds_exec_open', INFO_ADDR)
    def page(self, address=IMAGE_ADDR + 0x100): return self.call('ds_exec_page', INFO_ADDR, address)
    def close(self): return self.call('ds_exec_close', INFO_ADDR)
    def used(self): return [svc for svc, _ in self.events]


class NativeBackendTests(unittest.TestCase):
    def test_before_fix_reproduces_hardware_error(self):
        arm = BackendARM(before_fix=True)
        self.assertEqual(arm.open(), 0)
        self.assertEqual(arm.page(), 0xfffffc15)
        self.assertEqual(arm.permissions[IMAGE_ADDR], 5)
        self.assertIn(0x02, arm.used()); self.assertNotIn(0x7d, arm.used())
        self.assertNotIn(0x93, arm.used())
        self.assertEqual(arm.close(), 0); self.assertEqual(arm.permissions[IMAGE_ADDR], 3)

    def test_fixed_backend_uses_full_permission_query_and_restores(self):
        arm = BackendARM(); self.assertEqual(arm.open(), 0)
        self.assertEqual(arm.page(), 0)
        self.assertIn(0x7d, arm.used()); self.assertNotIn(0x02, arm.used())
        self.assertEqual(arm.used()[-3:], [0x70, 0x7d, 0x94])
        self.assertEqual(arm.permissions[IMAGE_ADDR], 5)
        self.assertEqual(struct.unpack('<I', arm.uc.mem_read(INFO_ADDR + 108, 4))[0], 5)
        self.assertEqual(arm.close(), 0); self.assertEqual(arm.permissions[IMAGE_ADDR], 3)

    def test_duplicate_page_is_not_reprotected(self):
        arm = BackendARM(); self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0)
        count = len(arm.events)
        self.assertEqual(arm.page(IMAGE_ADDR + 0x200), 0); self.assertEqual(len(arm.events), count)
        self.assertEqual(arm.close(), 0)

    def test_before_cache_fix_uses_mva_that_can_fault_on_another_core(self):
        arm = BackendARM(before_cache_fix=True); self.assertEqual(arm.open(), 0)
        with self.assertRaises(ModelCacheTranslationAbort): arm.page()
        self.assertIn(0x93, arm.used()); self.assertNotIn(0x94, arm.used())
        self.assertEqual(arm.close(), 0)

    def test_entire_cache_path_does_not_depend_on_remote_va(self):
        arm = BackendARM(); arm.remote_va_available = False
        self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0)
        self.assertIn(0x94, arm.used()); self.assertNotIn(0x93, arm.used())
        self.assertEqual(arm.close(), 0)

    def test_rejects_readonly_query_before_execution(self):
        arm = BackendARM(); arm.override_permission = 1
        self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0xfffffc15)
        self.assertNotIn(0x94, arm.used()); self.assertEqual(arm.close(), 0)

    def test_rejects_rwx_query_before_execution(self):
        arm = BackendARM(); arm.override_permission = 7
        self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0xfffffc15)
        self.assertNotIn(0x94, arm.used()); self.assertEqual(arm.close(), 0)

    def test_rejects_query_for_a_different_region(self):
        arm = BackendARM(); arm.shift_query_range = True
        self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0xfffffc15)
        self.assertNotIn(0x94, arm.used()); self.assertEqual(arm.close(), 0)

    def test_failed_cache_flush_does_not_change_permissions(self):
        arm = BackendARM(); arm.fail[0x54] = 0xd9001bf7
        self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0xd9001bf7)
        self.assertNotIn(0x70, arm.used()); self.assertNotIn(0x94, arm.used()); self.assertEqual(arm.close(), 0)

    def test_failed_protect_does_not_query_or_execute(self):
        arm = BackendARM(); arm.fail[0x70] = 0xd9001bf7
        self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0xd9001bf7)
        self.assertNotIn(0x7d, arm.used()); self.assertNotIn(0x94, arm.used()); self.assertEqual(arm.close(), 0)

    def test_failed_query_still_restores_protected_page(self):
        arm = BackendARM(); arm.fail[0x7d] = 0xd9001bf7
        self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0xd9001bf7)
        self.assertNotIn(0x94, arm.used()); self.assertEqual(arm.close(), 0)
        self.assertEqual(arm.permissions[IMAGE_ADDR], 3)

    def test_restore_failure_is_reported(self):
        arm = BackendARM(); self.assertEqual(arm.open(), 0); self.assertEqual(arm.page(), 0)
        arm.fail[0x70] = 0xd9001bf7
        self.assertEqual(arm.close(), 0xd9001bf7); self.assertEqual(arm.used()[-1], 0x23)

    def test_unsupported_backend_never_changes_memory(self):
        arm = BackendARM(); arm.luma_version = 0
        self.assertEqual(arm.open(), ctypes.c_uint32(-1001).value)
        self.assertEqual(arm.used(), [0x2a, 0x2a])

    def test_page_limit_and_all_pages_restored(self):
        arm = BackendARM(); self.assertEqual(arm.open(), 0)
        for i in range(16): self.assertEqual(arm.page(IMAGE_ADDR + i * 4096), 0)
        self.assertEqual(arm.page(IMAGE_ADDR + 16 * 4096), ctypes.c_uint32(-1002).value)
        self.assertEqual(arm.close(), 0)
        self.assertEqual(len(arm.permissions), 16); self.assertEqual(set(arm.permissions.values()), {3})


if __name__ == '__main__':
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeBackendTests))
    report = {'tests_run': result.testsRun, 'errors': len(result.errors), 'failures': len(result.failures),
              'elapsed_seconds': round(time.monotonic() - started, 3),
              'method': 'Compiled ARM native backend + real libctru wrappers; simulated kernel SVC boundary',
              'before_fix_reproduced_error': 'fffffc15', 'hardware_tested': False,
              'cache_range_fault_model': 'Remote-core VA unmapped; v0.2.1 range path faults in the model; v0.2.2 entire-cache path has no MVA operand',
              'mmu_or_cache_hardware_tested': False}
    (PORTING / 'analysis/stage2-backend-tests.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
