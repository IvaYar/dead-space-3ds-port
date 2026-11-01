"""Repack the hardware-PASS startup ELF, changing only Legacy -> Prod124."""
import difflib
import json
import shutil
import struct
import subprocess
from pathlib import Path
from build_native_startup_legacy import payload, sha

P = Path(__file__).resolve().parents[1]
BASE = P / '3ds/build-native-startup-v0.1.0-legacy'
D = P / '3ds/build-native-startup-v0.1.0-prod124'
A = P / 'analysis/native-startup-prod124-v0.1.0'


def main():
    assert not D.exists() and not A.exists(), 'Preserve completed artifacts/evidence'
    manifest = json.loads((BASE / 'build-manifest.json').read_text())
    for n, digest in manifest['outputs_sha256'].items():
        assert sha(BASE / n) == digest, n
    protected = json.loads((P / 'analysis/native-startup-legacy-v0.1.0/preservation.json').read_text())['before']
    for folder in [BASE, P / 'analysis/azahar-native-startup-legacy-v0.1.0-r2',
                   P / 'analysis/hardware/native-startup-legacy-v0.1.0-user-run-0001']:
        for q in folder.rglob('*'):
            if q.is_file():
                protected[q.relative_to(P).as_posix()] = sha(q)
    for n in ['tests/native_startup.c', 'tools/build_native_startup_legacy.py',
              'tests/smoke_native_startup_legacy.py', 'tests/native_game.c']:
        protected[n] = sha(P / n)
    assert all(sha(P / n) == h for n, h in protected.items())
    D.mkdir(); A.mkdir()
    (A / 'preservation.json').write_text(json.dumps({'before': protected}, indent=2) + '\n')
    for n in ['startup.elf', 'startup.smdh', 'startup.bnr']:
        shutil.copyfile(BASE / n, D / n)
    original = (BASE / 'startup.rsf').read_text()
    assert original.count('SystemModeExt: Legacy') == 1
    rsf = original.replace('SystemModeExt: Legacy', 'SystemModeExt: 124MB')
    (D / 'startup.rsf').write_text(rsf)
    (A / 'memory-mode-only.rsf.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), rsf.splitlines(True), fromfile='startup-Legacy.rsf', tofile='startup-Prod124.rsf')))
    commands = []
    for kind in ['cxi', 'cia']:
        cmd = [str(P / 'toolchain/extras/makerom/makerom.exe'), '-f', kind,
               '-o', str(D / ('startup-prod124.' + kind)), '-rsf', str(D / 'startup.rsf'),
               '-target', 't', '-exefslogo', '-elf', str(D / 'startup.elf'),
               '-icon', str(D / 'startup.smdh'), '-banner', str(D / 'startup.bnr'), '-ver', '1']
        commands.append(cmd); subprocess.run(cmd, cwd=D, check=True)
    current = payload((D / 'startup-prod124.cia').read_bytes())
    assert current == (D / 'startup-prod124.cxi').read_bytes()
    (D / 'cia-payload.cxi').write_bytes(current)
    comparisons = {}
    after = current[0x200:0xa00]
    assert after[0x20d] & 15 == after[0x60d] & 15 == 1
    for label, folder, filename, mode in [
        ('Legacy', BASE, 'startup-legacy.cia', 0),
        ('Dev1_178', P / '3ds/build-native-startup-v0.1.0', 'startup.cia', 2),
    ]:
        before_ncch = payload((folder / filename).read_bytes()); before = before_ncch[0x200:0xa00]
        diffs = [{'offset': hex(i), 'before': x, 'after': y}
                 for i, (x, y) in enumerate(zip(before, after)) if x != y]
        settings = [d for d in diffs if not 0x400 <= int(d['offset'], 16) < 0x500]
        assert settings == [{'offset': '0x20d', 'before': mode, 'after': 1},
                            {'offset': '0x60d', 'before': mode, 'after': 1}], settings
        assert before[0x500:0x600] == after[0x500:0x600]
        assert struct.unpack_from('<Q', current, 0x108)[0] == struct.unpack_from('<Q', before_ncch, 0x108)[0] == 0x000400000FDE7200
        off, size = struct.unpack_from('<II', current, 0x1a0)
        assert current[off * 512:(off + size) * 512] == before_ncch[off * 512:(off + size) * 512]
        assert sha(D / 'startup.elf') == sha(folder / 'startup.elf')
        (A / (label + '-exheader.bin')).write_bytes(before)
        comparisons[label] = {'configuration_byte_differences': settings,
                              'signature_changed_bytes': len(diffs) - len(settings),
                              'ELF_and_ExeFS_identical': True, 'kernel_and_SVC_identical': True,
                              'all_byte_differences': diffs}
    (A / 'Prod124-exheader.bin').write_bytes(after)
    (A / 'exheader-comparison.json').write_text(json.dumps({
        'only_memory_mode_configuration_changed': True,
        'actual_mode': 1, 'AccessDesc_mode': 1, 'mode_within_AccessDesc': True,
        'derived_signature_range': '0x400..0x4ff', 'comparisons': comparisons}, indent=2) + '\n')
    ctr = subprocess.run([str(P / 'toolchain/extras/ctrtool/ctrtool.exe'), '--verify',
                          str(D / 'startup-prod124.cia')], capture_output=True, text=True)
    audit = ctr.stdout + ctr.stderr; (A / 'CIA-container-audit.txt').write_text(audit)
    errors = [l for l in audit.splitlines() if ' ERROR]' in l]
    allowed = ['Signature for Ticket was invalid', 'Signature for TitleMetaData was invalid', 'Signature for AccessDescriptor was invalid']
    assert len(errors) == 3 and all(any(x in e for x in allowed) for e in errors), errors
    assert 'System mode (New3DS):   snake prod (AppMemory: 124MB)' in audit
    assert 'Kernel release version: 2.44' in audit
    assert not any('Hash:' in l and '(FAIL)' in l for l in audit.splitlines())
    assert all(sha(P / n) == h for n, h in protected.items())
    inputs = [Path(__file__).resolve(), P / 'tools/build_native_startup_legacy.py',
              *[BASE / n for n in ['startup.elf', 'startup.smdh', 'startup.bnr', 'startup.rsf']]]
    result = {'startup_only': True, 'hardware_tested': False, 'hardware_run_authorized': False,
              'same_ELF_no_recompile': True, 'memory_mode': 'Prod124', 'title_id': '000400000FDE7200',
              'replaces_previous_startup_title': True, 'kernel_version': '2.44',
              'normal_heap_bytes': 2 << 20, 'linear_heap_bytes': 2 << 20,
              'hardcoded_guest_178_label_is_stale': True, 'commands': commands,
              'protected_files': len(protected), 'baseline_changes': [],
              'inputs_sha256': {q.relative_to(P).as_posix(): sha(q) for q in inputs},
              'outputs_sha256': {n: sha(D / n) for n in ['startup.elf', 'startup-prod124.cia', 'startup-prod124.cxi', 'cia-payload.cxi', 'startup.rsf']}}
    (D / 'build-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'CIA_sha256': sha(D / 'startup-prod124.cia'), 'bytes': (D / 'startup-prod124.cia').stat().st_size,
                      'actual_AccessDesc_modes': [after[0x20d] & 15, after[0x60d] & 15],
                      'compared_to_Legacy_and_178': True, 'ELF_identical': True}))


if __name__ == '__main__':
    main()
