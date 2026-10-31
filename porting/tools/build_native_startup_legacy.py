"""Repack the saved startup ELF: change only New3DS SystemModeExt to Legacy."""
import difflib
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1]
BASE = P / '3ds/build-native-startup-v0.1.0'
D = P / '3ds/build-native-startup-v0.1.0-legacy'
A = P / 'analysis/native-startup-legacy-v0.1.0'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload(raw):
    h, _, _, cert, ticket, tmd, _, size = struct.unpack_from('<IHHIIIIQ', raw)
    offset = sum((n + 63) & ~63 for n in [h, cert, ticket, tmd])
    data = raw[offset:offset + size]
    assert data[0x100:0x104] == b'NCCH'
    return data


def main():
    verify_existing = sys.argv[1:] == ['--verify-existing']
    assert not sys.argv[1:] or verify_existing
    if verify_existing:
        assert D.exists() and A.exists() and not (D / 'build-manifest.json').exists()
    else:
        assert not D.exists() and not A.exists(), 'Preserve existing artifacts/evidence'
    old_manifest = json.loads((BASE / 'build-manifest.json').read_text())
    for n, digest in old_manifest['outputs_sha256'].items():
        assert sha(BASE / n) == digest, n
    protected = json.loads((P / 'analysis/native-startup-memory-v0.1.0/preservation.json').read_text())['before']
    for folder in [BASE, P / 'analysis/azahar-native-startup-v0.1.0']:
        for file in folder.rglob('*'):
            if file.is_file():
                protected[file.relative_to(P).as_posix()] = sha(file)
    for name in ['tests/native_startup.c', 'tests/smoke_native_startup.py', 'tools/build_native_startup.py']:
        protected[name] = sha(P / name)
    if verify_existing:
        protected = json.loads((A / 'preservation.json').read_text())['before']
    else:
        D.mkdir(); A.mkdir()
        (A / 'preservation.json').write_text(json.dumps({'before': protected}, indent=2) + '\n')
        for name in ['startup.elf', 'startup.smdh', 'startup.bnr']:
            shutil.copyfile(BASE / name, D / name)
    for name in ['startup.elf', 'startup.smdh', 'startup.bnr']:
        assert sha(BASE / name) == sha(D / name), name
    original = (BASE / 'startup.rsf').read_text()
    assert original.count('SystemModeExt: 178MB') == 1
    rsf = original.replace('SystemModeExt: 178MB', 'SystemModeExt: Legacy')
    if verify_existing:
        assert (D / 'startup.rsf').read_text() == rsf
    else:
        (D / 'startup.rsf').write_text(rsf)
    (A / 'memory-mode-only.rsf.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), rsf.splitlines(True), fromfile='startup-178.rsf', tofile='startup-legacy.rsf')))
    commands = []
    for kind in ['cxi', 'cia']:
        cmd = [str(P / 'toolchain/extras/makerom/makerom.exe'), '-f', kind,
               '-o', str(D / ('startup-legacy.' + kind)), '-rsf', str(D / 'startup.rsf'),
               '-target', 't', '-exefslogo', '-elf', str(D / 'startup.elf'),
               '-icon', str(D / 'startup.smdh'), '-banner', str(D / 'startup.bnr'), '-ver', '1']
        commands.append(cmd)
        if not verify_existing:
            subprocess.run(cmd, cwd=D, check=True)
    old = payload((BASE / 'startup.cia').read_bytes())
    new = payload((D / 'startup-legacy.cia').read_bytes())
    (D / 'cia-payload.cxi').write_bytes(new)
    assert new == (D / 'startup-legacy.cxi').read_bytes()
    assert struct.unpack_from('<Q', old, 0x108)[0] == struct.unpack_from('<Q', new, 0x108)[0] == 0x000400000FDE7200
    before, after = old[0x200:0xa00], new[0x200:0xa00]
    assert before == (P / 'analysis/native-startup-memory-v0.1.0/startup-exheader.bin').read_bytes()
    (A / 'before-exheader.bin').write_bytes(before); (A / 'after-exheader.bin').write_bytes(after)
    diffs = [{'offset': hex(i), 'before': x, 'after': y}
             for i, (x, y) in enumerate(zip(before, after)) if x != y]
    # Actual ACI and its AccessDescriptor copy: no IDs/kernel/SVC/code changes.
    config_diffs = [d for d in diffs if not 0x400 <= int(d['offset'], 16) < 0x500]
    assert {int(d['offset'], 16) for d in config_diffs} == {0x20d, 0x60d}, config_diffs
    assert all(d['before'] == 2 and d['after'] == 0 for d in config_diffs), config_diffs
    assert before[0x500:0x600] == after[0x500:0x600], 'RSA public key changed'
    assert before[0x370:0x3f0] == after[0x370:0x3f0]
    def exefs(data):
        off, size = struct.unpack_from('<II', data, 0x1a0)
        return data[off * 512:(off + size) * 512]
    assert exefs(old) == exefs(new), 'Executable/icon/banner must be unchanged'
    ctr = subprocess.run([str(P / 'toolchain/extras/ctrtool/ctrtool.exe'), '--verify',
                          str(D / 'startup-legacy.cia')], capture_output=True, text=True)
    audit = ctr.stdout + ctr.stderr
    (A / 'CIA-container-audit.txt').write_text(audit)
    errors = [l for l in audit.splitlines() if ' ERROR]' in l]
    allowed = ['Signature for Ticket was invalid', 'Signature for TitleMetaData was invalid',
               'Signature for AccessDescriptor was invalid']
    assert len(errors) == 3 and all(any(x in e for x in allowed) for e in errors), errors
    assert 'System mode (New3DS):   ctr prod (AppMemory: 64MB)' in audit
    assert 'Kernel release version: 2.44' in audit
    assert all('(GOOD)' in l for l in audit.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)', l))
    comparisons = {'only_memory_mode_fields_changed': True, 'exheader_bytes': len(after),
                   'configuration_byte_differences': config_diffs,
                   'AccessDescriptor_signature_changed': before[0x400:0x500] != after[0x400:0x500],
                   'signature_changed_bytes': len(diffs) - len(config_diffs),
                   'byte_differences': diffs, 'unchanged_bytes': len(after) - len(diffs),
                   'ELF_identical': sha(BASE / 'startup.elf') == sha(D / 'startup.elf'),
                   'entire_ExeFS_identical': True, 'title_id_identical': True,
                   'kernel_2_44_and_SVC_permissions_unchanged': True,
                   'notes': 'Only settings: 0x20d actual ACI and 0x60d AccessDescriptor ACI copy. Derived AccessDescriptor RSA signature at0x400..0x4ff also changes; its public key is identical. NCCH/TMD hashes/signatures change outside exheader.'}
    (A / 'exheader-comparison.json').write_text(json.dumps(comparisons, indent=2) + '\n')
    changes = [n for n, digest in protected.items() if sha(P / n) != digest]
    assert not changes, changes
    manifest = {'startup_test_only': True, 'hardware_tested': False, 'hardware_run_authorized': False,
                'title_id': '000400000FDE7200', 'replaces_previous_startup_title': True,
                'same_ELF_no_recompile': True, 'memory_mode': 'Legacy', 'kernel_version': '2.44',
                'normal_heap_bytes': 2 << 20, 'linear_heap_bytes': 2 << 20,
                'hardcoded_guest_178_label_is_stale': True, 'commands': commands,
                'preserved_files': len(protected), 'baseline_changes': changes,
                'inputs_sha256': {str(q.relative_to(P)).replace('\\', '/'): sha(q)
                                  for q in [Path(__file__).resolve(), BASE / 'startup.elf', BASE / 'startup.smdh', BASE / 'startup.bnr', BASE / 'startup.rsf']},
                'outputs_sha256': {n: sha(D / n) for n in ['startup.elf', 'startup-legacy.cia', 'startup-legacy.cxi', 'cia-payload.cxi', 'startup.rsf']}}
    (D / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'CIA_sha256': sha(D / 'startup-legacy.cia'), 'bytes': (D / 'startup-legacy.cia').stat().st_size,
                      'configuration_byte_differences': config_diffs,
                      'derived_signature_bytes_changed': len(diffs) - len(config_diffs), 'ELF_identical': comparisons['ELF_identical']}))


if __name__ == '__main__':
    main()
