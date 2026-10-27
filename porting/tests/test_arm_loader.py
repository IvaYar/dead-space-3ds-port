"""Run the actual ARMv6 loader core under Unicorn, including real donor mapping.

This checks CPU code and file handling, not Horizon OS, PICA200 or real hardware.
"""

import collections
import ctypes
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import unittest
import zlib

PORTING = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORTING / "toolchain/python"))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_ALL
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_CPU_ARM_11MPCORE

FILE_ADDR, INFO_ADDR, IMAGE_ADDR, STACK_ADDR, STOP_ADDR = 0x01000000, 0x07000000, 0x08000000, 0x0f000000, 0x0ff00000
FIELDS = "phoff phnum load_count load_min load_max image_size symoff symcount stroff strsize reloff relcount pltoff pltcount init_array init_count init_function needed imports weak_imports jni_exports relative abs32 glob_dat jump_slot unsupported local_relocations external_relocations arm_flags entry".split()


class Info(ctypes.LittleEndianStructure):
    _fields_ = [(field, ctypes.c_uint32) for field in FIELDS]

    def as_dict(self):
        return {key: getattr(self, key) for key in FIELDS}


def u32(data, off): return struct.unpack_from("<I", data, off)[0]
def set32(data, off, value): struct.pack_into("<I", data, off, value)


def segments(data):
    off, count = u32(data, 28), struct.unpack_from("<H", data, 44)[0]
    return [struct.unpack_from("<IIIIIIII", data, off + i * 32) for i in range(count)]


def symbols(data):
    # Independent section-based ELF reader; the C loader uses PT_DYNAMIC instead.
    shoff, entsize, count, names_index = u32(data, 32), *struct.unpack_from("<HHH", data, 46)
    headers = [struct.unpack_from("<IIIIIIIIII", data, shoff + i * entsize) for i in range(count)]
    sn = headers[names_index]; names = data[sn[4]:sn[4] + sn[5]]
    def text(buf, off): return buf[off:buf.index(0, off)].decode()
    named = {text(names, s[0]): s for s in headers}
    sym = named[".symtab"] if ".symtab" in named else named[".dynsym"]
    sn = headers[sym[6]]
    strings = data[sn[4]:sn[4] + sn[5]]
    return {text(strings, row[0]): row[1] for off in range(sym[4], sym[4] + sym[5], sym[9])
            if (row := struct.unpack_from("<IIIBBH", data, off))[0]}, named


class ARMCore:
    def __init__(self, data, core_path=None):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.ctl_set_cpu_model(UC_CPU_ARM_11MPCORE)
        code = (core_path or PORTING / "3ds/build/core-test.elf").read_bytes()
        self.exports, _ = symbols(code)
        code_end = max(p[2] + p[5] for p in segments(code) if p[0] == 1)
        assert code_end < FILE_ADDR, "ARM test code overlaps input file mapping"
        self.uc.mem_map(0x000f0000, ((code_end + 4095) & ~4095) - 0x000f0000, UC_PROT_ALL)
        for p in segments(code):
            if p[0] == 1: self.uc.mem_write(p[2], code[p[1]:p[1] + p[4]])
        self.uc.mem_map(FILE_ADDR, 8 * 1024 * 1024)
        self.uc.mem_map(INFO_ADDR, 4096)
        self.uc.mem_map(IMAGE_ADDR, 8 * 1024 * 1024)
        self.uc.mem_map(STACK_ADDR, 65536)
        self.uc.mem_map(STOP_ADDR, 4096)
        self.set_file(data)

    def set_file(self, data):
        self.data = bytes(data)
        self.uc.mem_write(FILE_ADDR, self.data)

    def call(self, name, *args, limit=200_000_000):
        regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
        sp = STACK_ADDR + 0x8000
        self.uc.reg_write(UC_ARM_REG_SP, sp)
        self.uc.reg_write(UC_ARM_REG_LR, STOP_ADDR)
        for reg, value in zip(regs, args): self.uc.reg_write(reg, value)
        for i, value in enumerate(args[4:]): self.uc.mem_write(sp + i * 4, struct.pack("<I", value))
        self.uc.emu_start(self.exports[name], STOP_ADDR, count=limit)
        if self.uc.reg_read(UC_ARM_REG_PC) != STOP_ADDR:
            raise RuntimeError(f"Instruction limit reached in {name}")
        return self.uc.reg_read(UC_ARM_REG_R0)

    def inspect(self, size=None):
        result = self.call("ds_elf_inspect", FILE_ADDR, len(self.data) if size is None else size, INFO_ADDR)
        return result, Info.from_buffer_copy(self.uc.mem_read(INFO_ADDR, ctypes.sizeof(Info)))

    def prepare(self, capacity=8 * 1024 * 1024):
        result = self.call("ds_elf_prepare", FILE_ADDR, len(self.data), IMAGE_ADDR, capacity, IMAGE_ADDR, INFO_ADDR)
        return result, Info.from_buffer_copy(self.uc.mem_read(INFO_ADDR, ctypes.sizeof(Info)))


class LoaderTests(unittest.TestCase):
    results = {}
    fixture_path = PORTING / "3ds/build/fixture.so"
    @classmethod
    def setUpClass(cls):
        cls.donor = (PORTING / "analysis/candidate-sd/libEAMGameDeadSpace_orig.so").read_bytes()
        cls.arm = ARMCore(cls.donor)
        cls.results = {}

    def setUp(self): self.arm.set_file(self.donor)

    def test_real_donor_metadata(self):
        result, info = self.arm.inspect()
        self.assertEqual(result, 0)
        _, sections = symbols(self.donor)
        types = collections.Counter()
        for name in (".rel.dyn", ".rel.plt"):
            section = sections[name]
            for off in range(section[4], section[4] + section[5], 8): types[u32(self.donor, off + 4) & 255] += 1
        self.assertEqual(info.imports, 392)
        self.assertEqual(info.load_count, 2)
        self.assertEqual(info.needed, 5)
        self.assertEqual(info.init_count, 209)
        self.assertEqual(info.relative, types[23])
        self.assertEqual(info.abs32, types[2])
        self.assertEqual(info.glob_dat, types[21])
        self.assertEqual(info.jump_slot, types[22])
        self.assertEqual(info.unsupported, 0)
        self.results["real_donor"] = info.as_dict()

    def test_real_donor_mapping_against_independent_reference(self):
        result, info = self.arm.prepare()
        self.assertEqual(result, 0)
        expected = bytearray(info.image_size)
        for p in segments(self.donor):
            if p[0] == 1:
                expected[p[2] - info.load_min:p[2] - info.load_min + p[4]] = self.donor[p[1]:p[1] + p[4]]
        _, sections = symbols(self.donor)
        syms = sections['.dynsym']; bias = IMAGE_ADDR - info.load_min
        applied = pending = 0
        for name in (".rel.dyn", ".rel.plt"):
            section = sections[name]
            for off in range(section[4], section[4] + section[5], 8):
                target, entry = struct.unpack_from("<II", self.donor, off)
                kind, symbol = entry & 255, entry >> 8
                if kind == 0: continue
                target -= info.load_min
                if kind == 23: value = u32(expected, target) + bias
                else:
                    row = struct.unpack_from("<IIIBBH", self.donor, syms[4] + symbol * 16)
                    if row[5] == 0:
                        pending += 1; continue
                    value = row[1] + (0 if row[5] == 0xfff1 else bias)
                    if kind == 2: value += u32(expected, target)
                set32(expected, target, value & 0xffffffff); applied += 1
        actual = bytes(self.arm.uc.mem_read(IMAGE_ADDR, info.image_size))
        self.assertEqual(actual, expected)
        self.assertEqual(info.local_relocations, applied)
        self.assertEqual(info.external_relocations, pending)
        self.results['mapped_image_crc32'] = f'{zlib.crc32(actual):08x}'
        self.results['runtime_base_in_emulator'] = hex(IMAGE_ADDR)

    def test_fixture_executes_after_mapping_but_constructor_does_not(self):
        fixture = self.fixture_path.read_bytes()
        self.arm.set_file(fixture)
        result, info = self.arm.prepare()
        self.assertEqual(result, 0)
        self.assertGreater(info.init_count, 0)
        self.assertEqual(info.imports, 1)
        names, _ = symbols(fixture)
        address = IMAGE_ADDR + names['fixture_read'] - info.load_min
        self.arm.uc.reg_write(UC_ARM_REG_SP, STACK_ADDR + 0x8000)
        self.arm.uc.reg_write(UC_ARM_REG_LR, STOP_ADDR)
        self.arm.uc.emu_start(address, STOP_ADDR, count=1000)
        self.assertEqual(self.arm.uc.reg_read(UC_ARM_REG_PC), STOP_ADDR)
        self.assertEqual(self.arm.uc.reg_read(UC_ARM_REG_R0), 42)
        self.assertGreater(info.abs32, 0)
        self.assertGreater(info.glob_dat, 0)
        address = IMAGE_ADDR + names['fixture_exported'] - info.load_min
        self.arm.uc.reg_write(UC_ARM_REG_LR, STOP_ADDR)
        self.arm.uc.emu_start(address, STOP_ADDR, count=1000)
        self.assertEqual(self.arm.uc.reg_read(UC_ARM_REG_R0), 34)
        self.results['original_test_module_return_value'] = 42
        self.results['local_abs32_and_glob_dat_test_value'] = 34
        self.results['constructors_executed'] = False
        self.results['game_code_executed'] = False

    def test_truncated_header(self):
        self.assertEqual(self.arm.inspect(51)[0], 1)

    def test_wrong_architecture(self):
        data = bytearray(self.donor); struct.pack_into('<H', data, 18, 183)
        self.arm.set_file(data); self.assertEqual(self.arm.inspect()[0], 1)

    def test_program_headers_outside_file(self):
        data = bytearray(self.donor); set32(data, 28, 0xfffffff0)
        self.arm.set_file(data); self.assertEqual(self.arm.inspect()[0], 2)

    def test_segment_file_larger_than_memory(self):
        data = bytearray(self.donor); p = u32(data, 28) + 32
        set32(data, p + 20, 1)
        self.arm.set_file(data); self.assertEqual(self.arm.inspect()[0], 3)

    def test_overlapping_segments(self):
        data = bytearray(self.donor); p = u32(data, 28) + 64
        set32(data, p + 8, 0x29bc)
        self.arm.set_file(data); self.assertEqual(self.arm.inspect()[0], 3)

    def test_invalid_symbol_count(self):
        _, info = self.arm.inspect()
        data = bytearray(self.donor); set32(data, 0xd4 + 4, 0xffffffff)
        self.arm.set_file(data); self.assertEqual(self.arm.inspect()[0], 5)

    def test_relocation_outside_image(self):
        _, info = self.arm.inspect()
        data = bytearray(self.donor); set32(data, info.reloff, 0xfffffff0)
        self.arm.set_file(data); self.assertEqual(self.arm.inspect()[0], 6)

    def test_relocation_into_gap(self):
        _, info = self.arm.inspect()
        data = bytearray(self.donor); set32(data, info.reloff, 0x422a00)
        self.arm.set_file(data); self.assertEqual(self.arm.inspect()[0], 6)

    def test_unsupported_relocation_does_not_modify_image(self):
        _, info = self.arm.inspect()
        data = bytearray(self.donor); set32(data, info.reloff + 4, 255)
        self.arm.set_file(data)
        marker = b'\xa5' * 4096
        self.arm.uc.mem_write(IMAGE_ADDR, marker)
        self.assertEqual(self.arm.prepare()[0], 7)
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR, 4096)), marker)

    def test_too_small_buffer_does_not_modify_image(self):
        marker = b'\x6a' * 4096
        self.arm.uc.mem_write(IMAGE_ADDR, marker)
        self.assertEqual(self.arm.prepare(capacity=4096)[0], 8)
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR, 4096)), marker)

    def test_crc32_matches_python(self):
        data = b'123456789'
        self.arm.set_file(data)
        self.assertEqual(self.arm.call('ds_crc32', FILE_ADDR, len(data)), zlib.crc32(data))


if __name__ == '__main__':
    started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LoaderTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'elapsed_seconds': round(time.monotonic() - started, 3), 'cpu': 'ARM11 MPCore (Unicorn)',
              'hardware_tested': False, **LoaderTests.results}
    (PORTING / 'analysis/stage1-tests.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
