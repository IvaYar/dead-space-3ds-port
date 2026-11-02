"""Execute the bounded raw-HID FIFO on ARM with adversarial sample timelines."""
import json
import struct
import subprocess
import sys
from test_arm_loader import ARMCore, PORTING
sys.path.insert(0, str(PORTING / 'tools'))
from azahar_resource_store import sha

HARNESS = r'''
#include <3ds.h>
#include <string.h>
#include "native_hid_queue.h"
static HidFifo fifo;static HidTransition output;
void *memset(void *p,int c,size_t n){volatile u8 *d=p;while(n--)*d++=c;return p;}
void reset(void){memset(&fifo,0,sizeof(fifo));}
void sample(u32 keys,u32 ms){hid_fifo_sample(&fifo,keys,(u64)ms,1,0,0);}
u32 take(void){return hid_fifo_take(&fifo,&output);}
u32 field(u32 i){switch(i){case 0:return output.id;case 1:return output.held;case 2:return output.down;case 3:return output.up;case 4:return output.epoch;default:return (u32)output.ticks;}}
u32 count(void){return fifo.count;}
u32 lost(void){return fifo.overflow;}
u32 seen(void){return fifo.seen;}
u32 barrier(void){return hid_fifo_barrier(&fifo);}
u32 map(u32 raw){return hid_nav_mask(raw);}
u32 mask(u32 i){const u32 values[]={KEY_DDOWN,KEY_DUP,KEY_DOWN,KEY_CPAD_DOWN,KEY_START};return values[i];}
'''


def main():
    d = PORTING.parent / '.local/native-hid-queue-tests'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'queue.c').write_text(HARNESS)
    subprocess.run([str(PORTING / 'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-gcc.exe'),
                    '-march=armv6k', '-O2', '-fno-builtin', '-nostdlib',
                    '-I' + str(PORTING / 'tests'), '-I' + str(PORTING / 'toolchain/devkitpro/libctru/include'),
                    str(d / 'queue.c'), '-Wl,-Ttext=0x100000,-e,reset', '-o', str(d / 'queue.elf')], check=True)
    arm = ARMCore(b'', d / 'queue.elf'); call = arm.call
    assert [call('mask', i) for i in range(5)] == [0x80, 0x40, 0x80000080, 0x80000000, 8]
    checks = ['actual SDK D-pad, generic, Circle Pad and START masks']
    # A physical key already held when the observer starts is not a new press.
    call('sample', 1, 0); assert call('seen') == 0
    assert call('take') == 1 and call('field', 2) == 0
    call('sample', 0, 4); call('take'); call('sample', 1, 8)
    assert call('seen') == 1
    checks.append('launch-held key is not a new preflight press')
    for gap in [100, 1000, 300000]:
        call('reset'); call('sample', 0, 0); call('take')
        # The legacy main-loop snapshots at 0 and gap both see released0.
        # The independent4ms observer still retains a20ms D-pad pulse.
        for t, key in [(12, 0x80), (16, 0x80), (28, 0x80), (32, 0), (gap, 0)]:
            call('sample', key, t)
        assert call('count') == 2
        assert call('take') == 1 and call('field', 2) == 0x80 and call('field', 5) == 12
        assert call('take') == 1 and call('field', 3) == 0x80 and call('field', 5) == 32
        assert call('take') == 0
    checks.append('20ms pulse survives low FPS and five-minute render gap without duplicate')
    call('reset'); call('sample', 0, 0); call('take')
    for t in range(4, 2001, 4): call('sample', 0x80, t)
    assert call('count') == 1
    call('take'); assert call('field', 2) == 0x80
    call('sample', 0, 2004); assert call('count') == 1
    checks.append('two-second hold emits one press and one release')
    assert call('map', 0x80) == call('map', 0x80000000) == call('map', 0x80000080) == 0x80
    assert call('map', 0x40000000) == 0x40 and call('map', 8) == 8
    assert call('map', 0xc0) == call('map', 0xc0000000) == 0
    checks.append('D-pad and Circle Pad merge without duplicate logical direction')
    call('reset'); call('sample', 0, 0); call('take')
    for i in range(64): call('sample', 0x80 if i % 2 == 0 else 0, i + 1)
    assert call('count') == 64 and call('lost') == 0
    call('sample', 0x80, 65); assert call('count') == 64 and call('lost') == 1
    for i in range(64):
        assert call('take') == 1 and call('field', 0) == i + 2
        assert call('field', 1) == (0x80 if i % 2 == 0 else 0)
    assert call('take') == 0
    checks.append('64-entry FIFO preserves order and reports overflow, never overwrites unread edges')
    call('reset'); call('sample', 0, 0); call('sample', 1, 4)
    assert call('barrier') == 2 and call('count') == 0
    call('sample', 1, 8); assert call('count') == 0
    call('sample', 0, 12); call('take'); assert call('field', 4) == 1
    call('sample', 1, 16); call('take'); assert call('field', 2) == 1
    checks.append('ready epoch barrier discards old presses and requires held key release/repress')
    result = {'passed': True, 'checks': checks, 'header_sha256': sha(PORTING / 'tests/native_hid_queue.h'),
              'fixture_scope': 'pure FIFO ARM contract; real SDK/shared memory tested separately in Azahar',
              'hardware_tested': False}
    (d / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
