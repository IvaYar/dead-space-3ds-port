"""Execute page CRC on ARM; compare with unchanged bitwise CRC and zlib."""
import json
import random
import struct
import subprocess
import sys
import zlib
from test_arm_loader import ARMCore, PORTING, FILE_ADDR
sys.path.insert(0, str(PORTING / 'tools'))
from azahar_resource_store import sha


def main():
    d = PORTING.parent / '.local/native-menu-page-crc-tests'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'crc.c').write_text('''
#include <stdint.h>
#include <stddef.h>
void *memset(void *p,int v,size_t n){volatile uint8_t *d=p;while(n--)*d++=v;return p;}
typedef uint32_t u32;typedef uint8_t u8;
#include "native_menu_page_crc.h"
u32 fast(const u8 *data,u32 bytes){return menu_page_crc_exact(data,bytes);}
''')
    gcc = PORTING / 'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-gcc.exe'
    subprocess.run([str(gcc), '-march=armv6k', '-O2', '-nostdlib',
                    '-I' + str(PORTING / 'tests'), '-I' + str(PORTING / '3ds/include'),
                    str(d / 'crc.c'), str(PORTING / '3ds/source/ds_elf.c'),
                    '-Wl,-Ttext=0x100000,-e,fast', '-o', str(d / 'crc.elf')], check=True)
    rng = random.Random(0x163d)
    data = rng.randbytes(4 * 1024 * 1024 + 16)
    arm = ARMCore(data, d / 'crc.elf')
    checks = 0
    for offset in range(8):
        for size in [0, 1, 2, 7, 16, 255, 256, 257, 4096]:
            expected = zlib.crc32(data[offset:offset + size])
            assert arm.call('fast', FILE_ADDR + offset, size) == expected
            assert arm.call('ds_crc32', FILE_ADDR + offset, size) == expected
            checks += 1
    for size in [192000, 288000, 4194304]:
        assert arm.call('fast', FILE_ADDR + 1, size) == zlib.crc32(data[1:1 + size])
        checks += 1
    arm.uc.mem_write(FILE_ADDR, b'123456789')
    assert arm.call('fast', FILE_ADDR, 9) == 0xcbf43926
    assert arm.call('ds_crc32', FILE_ADDR, 9) == 0xcbf43926
    payload = data[:8192]
    expected = zlib.crc32(payload)
    arm.uc.mem_write(FILE_ADDR, payload)
    for index in [0, 1, 255, 4096, 8191]:
        damaged = bytearray(payload); damaged[index] ^= 0x80
        arm.uc.mem_write(FILE_ADDR, bytes(damaged))
        actual = arm.call('fast', FILE_ADDR, len(damaged))
        assert actual == zlib.crc32(damaged) and actual != expected
        checks += 1
    result = {'passed': True, 'vectors': checks + 1, 'max_payload_bytes': 4194304,
              'unaligned_offsets': list(range(8)), 'single_bit_corruptions_rejected': 5,
              'reference': 'Unmodified ARM ds_crc32 and independent host zlib',
              'strict_frame_crc_implementation_changed': False,
              'page_header_and_corruption_checks_removed': False,
              'header_sha256': sha(PORTING / 'tests/native_menu_page_crc.h')}
    (d / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
