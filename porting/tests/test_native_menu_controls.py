"""ARM contract tests: real-state admission stays independent of image CRC."""
import json
from pathlib import Path
import struct
import subprocess
import sys
from test_arm_loader import ARMCore, PORTING
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_R0, UC_ARM_REG_R2, UC_ARM_REG_PC, UC_ARM_REG_LR
sys.path.insert(0, str(PORTING / 'tools'))
from azahar_resource_store import sha
from test_native_menu_input import HARNESS as OLD_HARNESS


def main():
    d = PORTING.parent / '.local/native-menu-controls-tests'
    d.mkdir(parents=True, exist_ok=True)
    harness = OLD_HARNESS.replace('#include "native_menu_input.h"', '''
#define DS_GAME_ARENA_BYTES (8u*1024*1024)
#define DS_IO_SOFT DS_JNI_SOFT
static u8 *image=(void *)0x08000000;
static void *arena=(void *)0x01000000;
#include "native_menu_engine_state.h"
#include "native_menu_controls.h"
static u32 observed_crc;static int frame_failed=1;
void observe(u32 crc){observed_crc=crc;}
u32 failed(void){return frame_failed;}
u32 ready(void){return menu_engine_state().ready;}
u32 selected(void){return menu_engine_state().selection;}
''').replace('void observe(u32 crc){menu_input_observe(crc);}', '')
    (d / 'harness.c').write_text(harness)
    gcc = PORTING / 'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-gcc.exe'
    subprocess.run([str(gcc), '-march=armv6k', '-mfpu=vfp', '-mfloat-abi=hard', '-O2',
                    '-fno-builtin', '-nostdlib', '-I' + str(PORTING / 'tests'),
                    '-I' + str(PORTING / '3ds/include'),
                    '-I' + str(PORTING / 'toolchain/devkitpro/libctru/include'),
                    str(d / 'harness.c'), str(PORTING / '3ds/source/ds23_touch.c'),
                    '-Wl,-Ttext=0x100000,-e,init', '-o', str(d / 'input.elf')], check=True)
    arm = ARMCore(b'', d / 'input.elf')
    arm.uc.reg_write(UC_ARM_REG_C1_C0_2, 0x00f00000)
    arm.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    call = arm.call

    def write(address, value):
        arm.uc.mem_write(address, struct.pack('<I', value))

    app, layer, buckets, normal_node, easy_node, normal, easy = [0x01001000 + i * 0x1000 for i in range(7)]
    # Only the readonly lookup ABI is a unit fixture. Integration uses the
    # actual original lookup, tree, button states and callbacks in Azahar.
    def lookup(uc, address, size, user):
        out = uc.reg_read(UC_ARM_REG_R0)
        key = uc.reg_read(UC_ARM_REG_R2)
        text = struct.unpack('<I', bytes(uc.mem_read(key, 4)))[0]
        node = normal_node if text == 0x083c3268 else easy_node
        uc.mem_write(out, struct.pack('<II', node, buckets))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    hook = arm.uc.hook_add(UC_HOOK_CODE, lookup, begin=0x081ab8c4, end=0x081ab8c4)
    write(0x0844a1b4, app)
    write(app + 0xd8, layer)
    write(layer, 0x08427dd8)
    write(layer + 0x80, buckets); write(layer + 0x84, 1)
    write(normal_node + 0x14, normal); write(easy_node + 0x14, easy)
    def choose(value):
        write(normal + 0x64, 4 if value == 0 else 0)
        write(easy + 0x64, 4 if value == 1 else 0)
    choose(0)
    assert call('init') == 0 and call('ready') == 0
    call('frame_number', 100)
    call('sample', 0, 1 << 7); call('sample', 0, 0)
    assert call('events') == 0
    write(layer + 0xcc, 2)
    assert call('ready') == 1 and call('selected') == 1

    def event(row):
        return [call('get', row, i) for i in range(4)]

    # Neither the frozen oracle nor a software/hardware UI fingerprint is
    # needed. Arbitrarily mismatched frames keep FRAME FAIL and admit input.
    for index, crc in enumerate([0x95b893de, 0xdeadbeef, 0]):
        frame = 120 + index * 12
        call('frame_number', frame); call('observe', crc)
        choose(0)
        n = call('events')
        call('sample', 0, 1 << 6); call('sample', 0, 0)
        assert call('events') == n  # Never tap selected Normal.
        call('sample', 0, 1 << 7)
        assert event(n)[:2] == [0x6000c, 1000]
        xy = tuple(struct.unpack('<f', struct.pack('<I', v))[0] for v in event(n)[2:])
        assert xy == (200., 134.) and call('failed') == 1
        call('frame_number', frame + 1); call('sample', 0, 1 << 7)
        assert event(n + 1)[0] == 0x8000c
        call('sample', 0, 1 << 7)
        assert call('events') == n + 2
        call('sample', 0, 0)
    choose(1)
    call('frame_number', 180); n = call('events')
    call('sample', 0, 1 << 7); call('sample', 0, 0)
    assert call('events') == n  # Never tap selected Easy.
    call('sample', 0, 1 << 6); call('frame_number', 181); call('sample', 0, 0)
    assert event(n)[0] == 0x6000c and event(n + 1)[0] == 0x8000c
    # Reject transition/closing/wrong-modal/corrupt profile objects.
    for address, invalid, valid in [(layer + 0x18, 1, 0), (layer + 0x44, 1, 0),
                                  (layer + 0xcc, 3, 2), (layer, 0x08427e60, 0x08427dd8),
                                  (layer + 0x84, 0, 1), (app + 0xd8, 0xffff0000, layer)]:
        write(address, invalid); assert call('ready') == 0
        write(address, valid); assert call('ready') == 1
    # B uses original Android keyboard BACK. The original first menu ignores
    # back; no manual layer-pop is introduced to manufacture a visible action.
    call('frame_number', 200); n = call('events'); call('sample', 0, 2)
    assert event(n) == [2, 600, 4, 0]
    call('frame_number', 201); call('sample', 0, 0)
    assert event(n + 1) == [3, 600, 4, 0]
    call('frame_number', 220); n = call('events'); call('sample', 0, 1)
    assert call('confirmation') == 220
    call('frame_number', 221); call('sample', 0, 1)
    call('frame_number', 222); call('sample', 0, 1 << 7)
    assert call('events') == n + 2
    assert call('close_input') == 0 and call('confirmation') == 0
    assert call('init') == 0
    choose(0); call('frame_number', 240); call('sample', 0, 1 << 7)
    choose(1); call('frame_number', 241); call('sample', 0, 1 << 6)
    n = call('events'); call('sample', 0, 0)
    call('frame_number', 243); call('sample', 0, 1 << 6)
    assert call('events') == n  # Queued pointer pulse still settling.
    call('sample', 0, 0); call('frame_number', 245); call('sample', 0, 1 << 6)
    assert call('events') == n + 1
    call('frame_number', 246); call('sample', 0, 0)
    call('frame_number', 260); n = call('events'); call('sample', 0, 2)
    assert event(n) == [2, 600, 4, 0]
    assert call('close_input') == 0 and event(n + 1) == [3, 600, 4, 0]
    assert call('close_input') == 0 and call('events') == n + 2
    choose(0)
    original = bytes(arm.uc.mem_read(0x01000000, 0x9000))
    assert call('ready') == 1
    assert bytes(arm.uc.mem_read(0x01000000, 0x9000)) == original
    checks = ['unready modal rejects input', 'hardware/different/zero image CRC admits ready menu with FAIL',
              'D-pad original pointer ABI and scaled coordinates', 'selected Normal/Easy suppressed',
              'held edge and original UP release', 'transition/closing/wrong modal rejected',
              'invalid pointers/widget-map rejected', 'B original Android BACK down/up ABI',
              'A bounded confirm and close reset', 'pending pulse prevents rapid opposite tap',
              'held BACK released once on close', 'state observation never writes original UI objects']
    result = {'passed': True, 'checks': checks, 'headers_sha256': {n: sha(PORTING / 'tests' / n)
              for n in ['native_menu_engine_state.h', 'native_menu_controls.h']},
              'lookup_fixture_is_unit_contract_only': True, 'hardware_tested': False}
    (d / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
