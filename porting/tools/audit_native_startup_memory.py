"""Read-only audit of saved game/startup artifacts; never runs either title."""
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-startup-memory-v0.1.0'
BIN = P / 'toolchain/devkitpro/devkitARM/bin'


def output(tool, *args):
    return subprocess.check_output([str(BIN / (tool + '.exe')), *map(str, args)])


def globals_from_elf(path):
    raw = path.read_bytes()
    assert raw[:6] == b'\x7fELF\x01\x01'
    phoff = struct.unpack_from('<I', raw, 28)[0]
    phsize, count = struct.unpack_from('<HH', raw, 42)
    loads = []
    for i in range(count):
        kind, off, addr, _, size, _, _, _ = struct.unpack_from('<8I', raw, phoff + i * phsize)
        if kind == 1:
            loads.append((off, addr, size))
    result = {}
    symbols = output('arm-none-eabi-nm', path).decode().replace('\r\n', '\n')
    for name in ['__ctru_heap_size', '__ctru_linear_heap_size', '__stacksize__']:
        found = re.search(r'^([0-9a-f]+) ([A-Za-z]) ' + name + r'$', symbols, re.M)
        assert found and found[2] == 'D', (name, found)
        address = int(found[1], 16)
        for off, addr, size in loads:
            if addr <= address <= addr + size - 4:
                result[name] = struct.unpack_from('<I', raw, off + address - addr)[0]
                break
        assert name in result
    return result


def pre_heap_model(exheader):
    raw = exheader.read_bytes()
    text_pages = struct.unpack_from('<I', raw, 0x14)[0]
    stack = struct.unpack_from('<I', raw, 0x1c)[0]
    ro_pages = struct.unpack_from('<I', raw, 0x24)[0]
    data = struct.unpack_from('<I', raw, 0x38)[0]
    bss = struct.unpack_from('<I', raw, 0x3c)[0]
    image = (text_pages + ro_pages) * 4096 + ((data + bss + 4095) & ~4095)
    return {'image_bytes': image, 'stack_bytes': stack, 'TLS_allowance_bytes': 4096,
            'image_and_stack_bytes': image + stack,
            'total_with_TLS_allowance_bytes': image + stack + 4096}


def main():
    budget = json.loads((A / 'memory-budget.json').read_text())
    games = P / '3ds/build-native-game-v0.1.0-h2'
    startup = P / '3ds/build-native-startup-v0.1.0'
    actual = {'h2': globals_from_elf(games / 'native-game.elf'),
              'startup': globals_from_elf(startup / 'startup.elf')}
    assert actual['h2'] == dict(__ctru_heap_size=40 << 20, __ctru_linear_heap_size=132 << 20, __stacksize__=256 << 10)
    assert actual['startup'] == dict(__ctru_heap_size=2 << 20, __ctru_linear_heap_size=2 << 20, __stacksize__=256 << 10)
    models = {name: pre_heap_model(A / filename) for name, filename in
              [('h2', 'h2-exheader.bin'), ('startup', 'startup-exheader.bin')]}
    assert models['h2']['total_with_TLS_allowance_bytes'] == 786432
    assert models['startup']['image_and_stack_bytes'] == 409600
    tests = json.loads((P / 'analysis/azahar-native-startup-v0.1.0/result.json').read_text())
    assert tests['passed'] and len(tests['cycles']) == 3
    for cycle in tests['cycles']:
        assert cycle['READY']['pre_heap_current_bytes'] == models['startup']['image_and_stack_bytes']
        assert cycle['READY']['heap_commit_delta_bytes'] == 4 << 20
        assert cycle['START_cleanup_before_host_unload']
    sdk = P / 'toolchain/devkitpro/libctru'
    matches = {}
    for name in ['os.h', 'env.h']:
        matches[name] = (A / 'references/libctru/include/3ds' / name).read_bytes() == (sdk / 'include/3ds' / name).read_bytes()
    assert all(matches.values())
    # Extract to a file: this Windows ar translates binary stdout in `ar p`.
    obj = A / 'allocateHeaps.o'
    subprocess.run([str(BIN / 'arm-none-eabi-ar.exe'), 'x',
                    str(sdk / 'lib/libctru.a'), 'allocateHeaps.o'], cwd=A, check=True)
    asm = output('arm-none-eabi-objdump', '-dr', obj).decode()
    assert '<__system_allocateHeaps>' in asm and 'svcControlMemory' in asm
    (A / 'linked-allocateHeaps.asm.txt').write_text(asm)
    budget.update(linked_ELF_globals=actual, commit_models=models,
                  pinned_headers_match_SDK=matches,
                  donor_arena_is_suballocation_of_linear_heap=True,
                  startup_image_and_stack_match_three_Azahar_measurements=True,
                  Azahar_does_not_charge_TLS_allowance_in_measured_pre_heap_commit=True)
    (A / 'memory-budget.json').write_text(json.dumps(budget, indent=2) + '\n')
    before = json.loads((A / 'preservation.json').read_text())['before']
    changes = [name for name, digest in before.items()
               if not (P / name).is_file() or hashlib.sha256((P / name).read_bytes()).hexdigest() != digest]
    assert not changes, changes
    evidence = {'protected_files': len(before), 'changed': changes,
                'baseline_preserved': True, 'overflow_proven': False,
                'hardware_tested': False, 'model_is_not_hardware_measurement': True}
    (A / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))


if __name__ == '__main__':
    main()
