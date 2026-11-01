"""Isolated 0.1.3 loader/APT revision. Never overwrite a previous build."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from build_native_startup_legacy import sha
from build_native_game_target_init import RUNTIME, makerom

P = Path(__file__).resolve().parents[1]
BASE = P/'3ds/build-native-game-v0.1.2-normal'
SOURCE = P/'tests/native_game_close.c'
A = P/'analysis/native-game-close-v0.1.3'
VARIANTS = {'normal': [], 'crc': ['-DFORCE_CRC_FAIL=1'],
            'lateprobe': ['-DFORCE_CRC_FAIL=1', '-DTEST_LATE_LOADER=1'],
            'latepending': ['-DFORCE_CRC_FAIL=1', '-DTEST_LATE_LOADER=1', '-DTEST_LATE_PENDING=1']}
VARIANTS.update({'latefixed': ['-DFORCE_CRC_FAIL=1', '-DTEST_LATE_LOADER=1', '-DTEST_LATE_PENDING=1'],
                 'latecrc': ['-DFORCE_CRC_FAIL=1', '-DTEST_LATE_LOADER=1'],
                 'apt': ['-DTEST_APT_CLOSE=1'],
                 'stopped': ['-DTEST_APT_CLOSE=1', '-DTEST_STOPPED_CLOSE=1'],
                 'retain': ['-DFORCE_CLEANUP_INCOMPLETE=1']})
VARIANTS['latefixed2'] = VARIANTS['latefixed']
VARIANTS['latefixed3'] = VARIANTS['latefixed']
VARIANTS['lateprogress'] = VARIANTS['latefixed']
VARIANTS['apthome'] = ['-DTEST_APT_CLOSE=1', '-DTEST_APT_HOME_TRANSITION=1']
VARIANTS['latefinal'] = VARIANTS['latefixed']
VARIANTS['apt2'] = ['-DTEST_APT_CLOSE=1']
VARIANTS['stopped2'] = ['-DTEST_APT_CLOSE=1', '-DTEST_STOPPED_CLOSE=1']
VARIANTS['late'] = VARIANTS['latefixed']
VARIANTS['latehome'] = VARIANTS['latefixed']+['-DTEST_APT_CLOSE=1', '-DTEST_LATE_HOME=1']
VARIANTS['latestopped'] = VARIANTS['latefixed']+['-DTEST_APT_CLOSE=1', '-DTEST_STOPPED_CLOSE=1']
VARIANTS['home'] = VARIANTS['apt2']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--variant', choices=VARIANTS, required=True)
    args = ap.parse_args()
    d = P/('3ds/build-native-game-v0.1.3-'+args.variant)
    assert not d.exists(), 'Preserve previous build'
    m = json.loads((BASE/'build-manifest.json').read_text())
    for n, h in m['outputs_sha256'].items():
        assert sha(BASE/n) == h, n
    d.mkdir()
    shutil.copyfile(SOURCE, d/'native-game-memory.c')
    for n in RUNTIME+['native-game.bnr']:
        shutil.copyfile(BASE/n, d/n)
    (d/'native-game.rsf').write_text((BASE/'native-game.rsf').read_text().replace('0xFDE75', '0xFDE76'))
    cmd = [s.replace(str(BASE), str(d)) for s in m['commands'][0]]
    cmd[1:1] = VARIANTS[args.variant]
    test_sdk = None
    if '-DTEST_APT_CLOSE=1' in VARIANTS[args.variant]:
        tc = P/'toolchain/devkitpro/devkitARM/bin'
        subprocess.run([str(tc/'arm-none-eabi-ar.exe'), 'x', str(P/'toolchain/devkitpro/libctru/lib/libctru.a'), 'apt.o'], cwd=d, check=True)
        test_sdk = d/'apt-test.o'
        subprocess.run([str(tc/'arm-none-eabi-objcopy.exe'), '--globalize-symbol=aptScreenTransfer',
                        '--weaken-symbol=aptScreenTransfer', str(d/'apt.o'), str(test_sdk)], check=True)
        cmd.insert(1, str(test_sdk))
    commands = [cmd]
    subprocess.run(cmd, cwd=d, check=True)
    cmd = [str(P/'toolchain/devkitpro/tools/bin/smdhtool.exe'), '--create', 'DS Game Close 0.1.3',
           'Loader delegate drain and pending APT close', 'Dead Space port research',
           str(P/'toolchain/devkitpro/libctru/default_icon.png'), str(d/'native-game.smdh')]
    commands.append(cmd)
    subprocess.run(cmd, cwd=d, check=True)
    cmd = makerom('cxi', d)
    commands.append(cmd)
    subprocess.run(cmd, cwd=d, check=True)
    result = {'variant': args.variant, 'commands': commands,
              'entry_sha256': sha(SOURCE), 'builder_sha256': sha(Path(__file__)),
              'hardware_run_authorized': False,
              'HLE_HOME_screenshot_only_test_SDK': sha(test_sdk) if test_sdk else None,
              'runtime_sha256': {n: sha(d/n) for n in RUNTIME},
              'outputs_sha256': {n: sha(d/n) for n in ['native-game-memory.c', 'native-game.elf', 'native-game.cxi', 'native-game.rsf']}}
    assert all(sha(d/n) == sha(BASE/n) for n in RUNTIME)
    (d/'build-manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Built isolated', args.variant, 'CXI')


if __name__ == '__main__':
    main()
