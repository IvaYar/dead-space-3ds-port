"""Build one isolated native-game revision; preserve renderer and old evidence."""
import argparse
import difflib
import json
import shutil
import subprocess
from pathlib import Path
from build_native_startup_legacy import payload, sha
from build_native_game_target_init import RUNTIME, makerom

P = Path(__file__).resolve().parents[1]
BASE = P/'3ds/build-native-game-v0.1.1-black'
A = P/'analysis/native-game-stable-v0.1.2'
SOURCE = P/'tests/native_game_stable.c'
VARIANTS = {'normal': [], 'poison': ['-DTARGET_INITIAL_RGBA=0x7f11abffu'],
            'crc': ['-DFORCE_CRC_FAIL=1'], 'retain': ['-DFORCE_CLEANUP_INCOMPLETE=1']}


def runner_matches(digest):
    current = P/'tests/smoke_native_game_stable.py'
    if digest == sha(current):
        return True
    # The first CIA host attempt failed before loading the guest: smoke_azahar
    # had already created ROOT for its log. Preserve the tested CXI runner and
    # prove the only difference is idempotent host directory creation.
    before = A/'runner-before-CIA-path-fix.py'
    return (before.exists() and digest == sha(before) and
            before.read_bytes().replace(b'ROOT.mkdir()', b'ROOT.mkdir(exist_ok=True)') == current.read_bytes())


def verify_result(root, build, expected=3):
    r = json.loads((root/'result.json').read_text())
    assert r['passed'] and r['sequential_cycles'] == expected and r['safe_exit']
    assert r['CXI_sha256'] == sha(build/'native-game.cxi')
    assert runner_matches(r['runner_sha256'])
    for c in r['cycles']:
        assert c['passed'] and c['both_heaps_released'] and not c['invalid_memory_accesses']
        assert c['shutdown_proof']['kernel_joins'] == 6 and c['shutdown_proof']['worker_handles_remaining'] == 0
        assert c['shutdown_proof']['files_balanced']
    return r


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', choices=VARIANTS, default='normal')
    parser.add_argument('--cia', action='store_true')
    parser.add_argument('--pass-attempt', default='')
    args = parser.parse_args()
    d = P/('3ds/build-native-game-v0.1.2-'+args.variant)
    if args.cia:
        assert args.variant == 'normal' and not (d/'native-game.cia').exists()
        assert not args.pass_attempt or args.pass_attempt.isalnum()
        for variant, count in [('normal', 3), ('poison', 3), ('crc', 1)]:
            suffix = '-'+args.pass_attempt if variant == 'normal' and args.pass_attempt else ''
            r = verify_result(P/('analysis/azahar-native-game-v0.1.2-'+variant+'-cxi'+suffix),
                              P/('3ds/build-native-game-v0.1.2-'+variant), count)
            if variant == 'normal':
                assert all(c['different_pixels'] == 0 and c['sequence_frames'] == 8 for c in r['cycles'])
            else:
                assert all(c['final_guest_result']['status'] == 'failed' and not c['final_guest_result']['frame_saved'] for c in r['cycles'])
        retained = json.loads((P/'analysis/azahar-native-game-v0.1.2-retain-cxi/result.json').read_text())
        assert retained['passed'] and not retained['safe_exit']
        assert retained['CXI_sha256'] == sha(P/'3ds/build-native-game-v0.1.2-retain/native-game.cxi')
        assert runner_matches(retained['runner_sha256'])
        m = json.loads((d/'build-manifest.json').read_text())
        for n, h in m['outputs_sha256'].items():
            assert sha(d/n) == h
        assert m['inputs_sha256']['entry'] == sha(SOURCE)
        subprocess.run(makerom('cia', d), cwd=d, check=True)
        raw = payload((d/'native-game.cia').read_bytes())
        assert raw == (d/'native-game.cxi').read_bytes()
        (d/'cia-payload.cxi').write_bytes(raw)
        (d/'cia-manifest.json').write_text(json.dumps({'title_id': '000400000FDE7500',
            'CIA_sha256': sha(d/'native-game.cia'), 'CIA_bytes': (d/'native-game.cia').stat().st_size,
            'payload_sha256': sha(d/'cia-payload.cxi'), 'hardware_tested': False,
            'hardware_run_authorized': False}, indent=2)+'\n')
        print('One experimental CIA created; hardware execution is not authorized.')
        return
    assert not d.exists(), 'Preserve existing evidence; use a new revision'
    baseline = json.loads((BASE/'build-manifest.json').read_text())
    for n, h in baseline['outputs_sha256'].items():
        assert sha(BASE/n) == h, n
    d.mkdir()
    shutil.copyfile(SOURCE, d/'native-game-memory.c')
    for n in RUNTIME+['native-game.bnr']:
        shutil.copyfile(BASE/n, d/n)
    rsf = (BASE/'native-game.rsf').read_text().replace('DS-GAME-INIT', 'DS-GAME-STBL').replace('CTR-H-DGIN', 'CTR-H-DGST').replace('0xFDE74', '0xFDE75')
    (d/'native-game.rsf').write_text(rsf)
    text = SOURCE.read_text()
    (d/'entry.diff').write_text(''.join(difflib.unified_diff((BASE/'native-game-memory.c').read_text().splitlines(True), text.splitlines(True), fromfile='Init 0.1.1', tofile='Stable 0.1.2')))
    cmd = [q.replace(str(BASE), str(d)) for q in baseline['commands'][0]]
    cmd[1:1] = VARIANTS[args.variant]
    cmd.insert(-2, '-Wl,--wrap=BufInfo_Add,--wrap=C3D_DrawArrays')
    commands = [cmd]
    subprocess.run(cmd, cwd=d, check=True)
    cmd = [str(P/'toolchain/devkitpro/tools/bin/smdhtool.exe'), '--create', 'DS Game Stable 0.1.2',
           'Original frames; strict CRC; safe failure exit', 'Dead Space port research',
           str(P/'toolchain/devkitpro/libctru/default_icon.png'), str(d/'native-game.smdh')]
    commands.append(cmd)
    subprocess.run(cmd, cwd=d, check=True)
    cmd = makerom('cxi', d)
    commands.append(cmd)
    subprocess.run(cmd, cwd=d, check=True)
    manifest = {'variant': args.variant, 'commands': commands, 'hardware_run_authorized': False,
                'inputs_sha256': {'entry': sha(SOURCE), 'builder': sha(Path(__file__)),
                                 'baseline_entry': sha(BASE/'native-game-memory.c')},
                'runtime_sha256': {n: sha(d/n) for n in RUNTIME},
                'outputs_sha256': {n: sha(d/n) for n in ['native-game-memory.c', 'native-game.elf', 'native-game.cxi', 'native-game.rsf']}}
    assert all(sha(d/n) == sha(BASE/n) for n in RUNTIME)
    (d/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Built', args.variant, 'CXI; GPU/shader/thread runtime unchanged.')


if __name__ == '__main__':
    main()
