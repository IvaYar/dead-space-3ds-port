"""Run the JNI subset and bounded original-game JNI paths as compiled ARM code."""
import ctypes
import json
import struct
import time
import unittest
from test_arm_loader import ARMCore, PORTING, FILE_ADDR, INFO_ADDR, IMAGE_ADDR
from unicorn.arm_const import UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC

CTX = 0x06000000
INPUT = CTX + 0x8000
OUT = INPUT + 0x1000
PLAN = INFO_ADDR + 0x200


class JniTests(unittest.TestCase):
    results = {}

    @classmethod
    def setUpClass(cls):
        cls.donor = (PORTING / 'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.arm = ARMCore(cls.donor, PORTING / '3ds/build-stage3/core-test.elf')
        cls.arm.uc.reg_write(UC_ARM_REG_C1_C0_2, 0x00f00000)
        cls.arm.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        cls.arm.uc.mem_map(CTX, 0x10000)
        cls.size = cls.arm.call('ds_jni_context_size')
        assert cls.size < 0x8000

    def setUp(self):
        self.arm.set_file(self.donor)
        self.arm.call('ds_jni_init', CTX)

    def word(self, address): return struct.unpack('<I', self.arm.uc.mem_read(address, 4))[0]
    def stats(self): return struct.unpack('<5I', self.arm.uc.mem_read(CTX + self.size - 20, 20))

    def invoke(self, address, *args):
        self.arm.exports['__jni_call'] = address
        return self.arm.call('__jni_call', *args)

    def env_call(self, slot, *args):
        address = self.word(self.word(CTX) + slot * 4)
        self.assertNotEqual(address, 0)
        return self.invoke(address, CTX, *args)

    def new(self, text):
        self.arm.uc.mem_write(INPUT, text + b'\0')
        return self.env_call(167, INPUT)

    def verify(self, capacity=None):
        _, info = self.arm.inspect()
        return self.arm.call('ds_bootstrap_verify', FILE_ADDR, len(self.donor), IMAGE_ADDR,
                             info.image_size if capacity is None else capacity, IMAGE_ADDR, INFO_ADDR, PLAN)

    def test_jni_slots_and_vm_getenv(self):
        self.assertEqual(self.env_call(4), 0x10004)
        vm = CTX + 8
        getter = self.word(self.word(vm) + 6 * 4)
        self.assertEqual(self.invoke(getter, vm, OUT, 0x10004), 0)
        self.assertEqual(self.word(OUT), CTX)
        self.assertEqual(self.env_call(219, OUT), 0)
        self.assertEqual(self.word(OUT), vm)

    def test_unsupported_jni_version_clears_output(self):
        self.arm.uc.mem_write(OUT, struct.pack('<I', 0xdeadbeef))
        self.assertEqual(self.arm.call('ds_jni_get_env', CTX, 0x10006, OUT), ctypes.c_uint32(-3).value)
        self.assertEqual(self.word(OUT), 0)

    def test_utf_bytes_borrow_release_and_delete(self):
        text = b'A\xc0\x80\xd0\x91'
        string = self.new(text); self.assertNotEqual(string, 0)
        self.assertEqual(self.env_call(168, string), len(text))
        self.arm.uc.mem_write(OUT, b'\x63')
        chars = self.env_call(169, string, OUT)
        self.assertEqual(bytes(self.arm.uc.mem_read(chars, len(text) + 1)), text + b'\0')
        self.assertEqual(bytes(self.arm.uc.mem_read(OUT, 1)), b'\0')
        self.env_call(170, string, chars)
        self.env_call(23, string)
        self.assertEqual(self.word(string), 0)
        self.assertEqual(self.stats()[:4], (0, 1, 1, 1))

    def test_pinned_string_cannot_be_deleted(self):
        string = self.new(b'x'); chars = self.env_call(169, string, 0)
        self.env_call(23, string)
        self.assertEqual(self.stats()[0], 5)
        self.assertEqual(self.word(string), 1)
        self.env_call(170, string, chars); self.env_call(23, string)
        self.assertEqual(self.word(string), 0)

    def test_wrong_release_does_not_unpin(self):
        string = self.new(b'x'); chars = self.env_call(169, string, 0)
        self.env_call(170, string, chars + 1)
        self.assertEqual(self.stats()[0], 4)
        self.assertEqual(self.word(string + 8), 1)

    def test_foreign_handle_is_not_dereferenced(self):
        self.assertEqual(self.env_call(169, 0xdeadbeef, 0), 0)
        self.assertEqual(self.stats()[0], 1)

    def test_long_string_rejected(self):
        self.assertEqual(self.new(b'a' * 256), 0)
        self.assertEqual(self.stats()[0], 3)

    def test_string_pool_exhaustion(self):
        strings = [self.new(b'x') for _ in range(8)]
        self.assertEqual(len(set(strings)), 8)
        self.assertEqual(self.new(b'ninth'), 0)
        self.assertEqual(self.stats()[0], 2)

    def test_game_jni_onload_only_writes_verified_vm_slot(self):
        result, info = self.arm.prepare(); self.assertEqual(result, 0)
        self.assertEqual(self.verify(), 0)
        load, storage, _, _ = struct.unpack('<4I', self.arm.uc.mem_read(PLAN, 16))
        before = bytearray(self.arm.uc.mem_read(IMAGE_ADDR, info.image_size))
        version = self.invoke(IMAGE_ADDR + load - info.load_min, CTX + 8, 0)
        self.assertEqual(version, 0x10004)
        struct.pack_into('<I', before, storage - info.load_min, CTX + 8)
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR, info.image_size)), bytes(before))
        self.results['game_jni_onload_version'] = '00010004'
        self.results['only_expected_vm_storage_changed'] = True

    def test_actual_game_wrappers_call_native_jni(self):
        result, info = self.arm.prepare(); self.assertEqual(result, 0)
        self.assertEqual(self.verify(), 0)
        _, _, get, release = struct.unpack('<4I', self.arm.uc.mem_read(PLAN, 16))
        text = b'sdmc:/3ds/deadspace/assets/published/'
        string = self.new(text)
        chars = self.invoke(IMAGE_ADDR + get - info.load_min, CTX, string, OUT)
        self.assertEqual(bytes(self.arm.uc.mem_read(chars, len(text))), text)
        self.invoke(IMAGE_ADDR + release - info.load_min, CTX, string, chars)
        self.arm.call('ds_jni_delete_string', CTX, string)
        self.assertEqual(self.stats()[:4], (0, 1, 1, 1))
        self.assertEqual(self.word(string), 0)
        self.results['game_string_roundtrip'] = 'MATCH'

    def test_modified_mapped_instructions_rejected(self):
        self.assertEqual(self.arm.prepare()[0], 0)
        self.arm.uc.mem_write(IMAGE_ADDR + 0x23615c, struct.pack('<I', 0xeafffffe))
        self.assertEqual(self.verify(), 10)

    def test_bad_got_pointer_rejected(self):
        self.assertEqual(self.arm.prepare()[0], 0)
        self.arm.uc.mem_write(IMAGE_ADDR + 0x43ef74, struct.pack('<I', CTX))
        self.assertEqual(self.verify(), 5)

    def test_vm_storage_must_be_zero_before_load(self):
        self.assertEqual(self.arm.prepare()[0], 0)
        self.arm.uc.mem_write(IMAGE_ADDR + 0x44c0c8, struct.pack('<I', CTX))
        self.assertEqual(self.verify(), 5)

    def test_image_capacity_guard(self):
        self.assertEqual(self.arm.prepare()[0], 0)
        self.assertEqual(self.verify(capacity=4096), 8)


if __name__ == '__main__':
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(JniTests))
    report = {'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
              'elapsed_seconds':round(time.monotonic()-started,3),'hardware_tested':False,
              'game_constructors_called':False,'game_engine_started':False,**JniTests.results}
    (PORTING/'analysis/stage3-jni-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
