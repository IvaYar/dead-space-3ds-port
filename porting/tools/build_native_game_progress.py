"""Build isolated progress-budget revision; old source/runtime/evidence immutable."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import wave
from PIL import Image, ImageDraw, ImageFont
from azahar_resource_store import sha
from build_native_game_target_init import RUNTIME, makerom

P = Path(__file__).resolve().parents[1]
BASE = P/'3ds/build-native-game-v0.1.3-normal'
SOURCE = P/'tests/native_game_progress.c'
LATE = ['-DFORCE_CRC_FAIL=1', '-DTEST_LATE_LOADER=1', '-DTEST_LATE_PENDING=1']
VARIANTS = {'normal': [], 'crc': ['-DFORCE_CRC_FAIL=1'],
            'latecrc': ['-DFORCE_CRC_FAIL=1', '-DTEST_LATE_LOADER=1'],
            'slow': LATE+['-DTEST_SLOW_IO=1'], 'start': LATE+['-DTEST_SLOW_IO=1'],
            'home': LATE+['-DTEST_SLOW_IO=1', '-DTEST_APT_CLOSE=1', '-DTEST_HOME_WAIT=1'],
            'system': LATE+['-DTEST_SLOW_IO=1', '-DTEST_SYSTEM_CLOSE=1'],
            'stall': LATE+['-DTEST_STALL_IO=1', '-DTEST_RELEASE_IO=1', '-DLOADER_IDLE_MS=3000'],
            'stuck': LATE+['-DTEST_STALL_IO=1', '-DLOADER_IDLE_MS=3000', '-DTEST_APT_CLOSE=1', '-DTEST_HOME_WAIT=1'],
            'hard': LATE+['-DTEST_SLOW_IO=1', '-DLOADER_HARD_MS=12000']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--variant', choices=VARIANTS, required=True)
    args = ap.parse_args()
    d = P/('3ds/build-native-game-v0.1.4r2-'+args.variant)
    assert not d.exists(), 'Preserve prior builds'
    m = json.loads((BASE/'build-manifest.json').read_text())
    for name, digest in m['outputs_sha256'].items():
        assert sha(BASE/name) == digest
    d.mkdir()
    shutil.copyfile(SOURCE, d/'native-game-memory.c')
    for name in RUNTIME:
        shutil.copyfile(BASE/name, d/name)
    (d/'native-game.rsf').write_text((BASE/'native-game.rsf').read_text().replace('0xFDE76', '0xFDE77').replace('DS-GAME-STBL', 'DS-GAME-PROG').replace('CTR-H-DGST', 'CTR-H-DGPR'))
    command = [s.replace(str(BASE), str(d)) for s in m['commands'][0]]
    command[1:1] = VARIANTS[args.variant]
    test_sdk = None
    if args.variant in ['home', 'stuck', 'system']:
        tc = P/'toolchain/devkitpro/devkitARM/bin'
        subprocess.run([str(tc/'arm-none-eabi-ar.exe'), 'x', str(P/'toolchain/devkitpro/libctru/lib/libctru.a'), 'apt.o'], cwd=d, check=True)
        test_sdk = d/'apt-test.o'
        subprocess.run([str(tc/'arm-none-eabi-objcopy.exe'), '--globalize-symbol=aptScreenTransfer', '--weaken-symbol=aptScreenTransfer',
                        '--globalize-symbol=aptFlags', str(d/'apt.o'), str(test_sdk)], check=True)
        command.insert(1, str(test_sdk))
    commands = [command]
    subprocess.run(command, cwd=d, check=True)
    banner = Image.new('RGB', (256,128), (7,20,30))
    draw = ImageDraw.Draw(banner)
    draw.rectangle((8,8,247,119), outline=(90,230,222), width=2)
    for label, y, size in [('DS GAME PROGRESS',24,19), ('SAFE AUTOMATIC EXIT',61,15), ('EXPERIMENTAL 0.1.4',92,13)]:
        draw.text((128,y), label, fill=(180,240,235), font=ImageFont.load_default(size=size), anchor='mt')
    banner.save(d/'banner.png')
    with wave.open(str(d/'silence.wav'), 'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(22050);audio.writeframes(b'\0'*8820)
    for cmd in [
        [str(P/'toolchain/extras/bannertool/bannertool.exe'), 'makebanner', '-i', str(d/'banner.png'), '-a', str(d/'silence.wav'), '-o', str(d/'native-game.bnr')],
        [str(P/'toolchain/devkitpro/tools/bin/smdhtool.exe'), '--create', 'DS Game Progress 0.1.4', 'Bounded progress wait; safe close', 'Dead Space port research', str(P/'toolchain/devkitpro/libctru/default_icon.png'), str(d/'native-game.smdh')],
        makerom('cxi', d),
    ]:
        commands.append(cmd);subprocess.run(cmd, cwd=d, check=True)
    assert all(sha(d/n) == sha(BASE/n) for n in RUNTIME)
    manifest = {'variant': args.variant, 'commands': commands, 'source_sha256': sha(SOURCE),
                'headers_sha256': {n: sha(P/'tests'/n) for n in ['native_loader_budget.h', 'native_loader_io_monitor.h']},
                'runtime_sha256': {n: sha(d/n) for n in RUNTIME},
                'test_only_SDK': sha(test_sdk) if test_sdk else None,
                'banner_text': ['DS GAME PROGRESS', 'SAFE AUTOMATIC EXIT', 'EXPERIMENTAL 0.1.4'],
                'hardware_run_authorized': False,
                'outputs_sha256': {n: sha(d/n) for n in ['native-game-memory.c', 'native-game.elf', 'native-game.cxi', 'native-game.rsf', 'native-game.smdh', 'native-game.bnr', 'banner.png']}}
    (d/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Built isolated', args.variant, 'CXI')


if __name__ == '__main__':
    main()
