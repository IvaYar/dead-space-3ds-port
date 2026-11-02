"""Run the actual linked libctru HID scanner on ARM shared-memory fixtures."""
import argparse
import json
import struct
import sys
from test_arm_loader import ARMCore, PORTING, INFO_ADDR
sys.path.insert(0, str(PORTING / 'tools'))
from azahar_resource_store import sha


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision', required=True)
    args = ap.parse_args()
    assert args.revision.isalnum()
    elf = PORTING / ('3ds/build-native-game-v0.1.7-' + args.revision) / 'native-game.elf'
    arm = ARMCore(b'', elf); call = arm.call

    def word(index, value):
        arm.uc.mem_write(INFO_ADDR + index * 4, struct.pack('<I', value))

    arm.uc.mem_write(arm.exports['hidSharedMem'], struct.pack('<I', INFO_ADDR))
    word(0, 1)  # Valid0th entry differs from previous timestamp.
    vectors = 0
    for index in range(8):
        word(4, index)
        for mask in [0x80, 0x40, 0x20, 0x10, 1, 2, 8, 0x80000000, 0x40000000]:
            word(10 + index * 4, 0); call('hidScanInput')
            word(10 + index * 4, mask); call('hidScanInput')
            assert call('hidKeysDown') == mask and call('hidKeysDown') == mask
            assert call('hidKeysHeld') == mask
            call('hidScanInput')  # Equivalent to an extra sensor HID scan.
            assert call('hidKeysDown') == 0 and call('hidKeysHeld') == mask
            word(10 + index * 4, 0); call('hidScanInput')
            assert call('hidKeysHeld') == call('hidKeysDown') == 0
            vectors += 1
    # A press and release entirely between main samples leave both getters0.
    # The FIFO tests retain precisely that independently observed transition.
    result = {'passed': True, 'SDK_ARM_vectors': vectors, 'PAD_ring_slots': 8,
              'key_getter_is_nonconsuming': True,
              'extra_scan_clears_down_but_preserves_held': True,
              'released_before_next_scan_has_no_down_or_held': True,
              'compiled_candidate_ELF_sha256': sha(elf),
              'scope': 'Actual linked SDK ARM instructions, fixture shared memory; not physical hardware proof.'}
    d = PORTING.parent / '.local/native-sdk-hid-tests'; d.mkdir(parents=True, exist_ok=True)
    (d / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
