"""Package the single prepared shader-mask candidate; never launch hardware."""
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

import build_ds34_uv_mask as b

P, B, A = b.P, b.D, b.A
E = P / 'analysis/azahar-ds34-uv-mask-v0.2.1'
D = P / 'dist/ds34-uv-mask-v0.2.1'


def main():
    if D.exists():
        raise SystemExit(f'Refusing to replace package: {D}')
    manifest = json.loads((B / 'build-manifest.json').read_text())
    test = json.loads((E / 'result.json').read_text())
    single = json.loads((E / 'single-factor.json').read_text())
    for key, root in [('inputs_sha256', P), ('outputs_sha256', B)]:
        for name, expected in manifest[key].items():
            assert b.sha(root / name) == expected, name
    assert test['passed'] and test['invalid_memory_accesses'] == 0
    assert test['CIA_sha256'] == b.sha(B / 'ds34-uv-mask.cia')
    assert test['START_guest_cleanup_before_host_unload'] and single['only_two_output_masks_changed']
    verification = subprocess.run([str(P / 'toolchain/extras/ctrtool/ctrtool.exe'), '--verify',
                                  str(B / 'ds34-uv-mask.cia')], capture_output=True, text=True)
    output = verification.stdout + verification.stderr
    errors = [line for line in output.splitlines() if ' ERROR]' in line]
    allowed = ['Signature for Ticket was invalid', 'Signature for TitleMetaData was invalid',
               'Signature for AccessDescriptor was invalid']
    assert len(errors) == 3 and all(any(e in line for e in allowed) for line in errors), errors
    hashes = [line.strip() for line in output.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)', line)]
    assert len(hashes) >= 3 and all('(GOOD)' in line for line in hashes), hashes
    copies = {
        B / 'ds34-uv-mask.cia': 'ds34-uv-mask.cia',
        P / '3ds/README-ds34-uv-mask.ru.md': 'README.ru.md',
        B / 'ds34_gpu.v.pica': 'source/ds34_gpu.v.pica',
        B / 'baseline.v.pica': 'source/baseline.v.pica',
        B / 'build-manifest.json': 'validation/build-manifest.json',
        b.prior.prior.stock.LIB / 'LICENSE': 'LICENSE-citro3d.md',
    }
    for name in ['shader.diff', 'report.ru.md', 'comparison.json']:
        copies[A / name] = 'validation/' + name
    for name in ['result.json', 'single-factor.json', 'screen.png', 'frame.png', 'START-cleanup.log']:
        copies[E / name] = 'validation/' + name
    for name in ['build_ds34_uv_mask.py', 'audit_pica_outputs.py']:
        copies[P / 'tools' / name] = 'source/' + name
    D.mkdir(parents=True)
    for source, name in copies.items():
        dest = D / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    report = dict(version='0.2.1', title_id=b.TITLE, hardware_tested=False,
                  hardware_run_authorized=False, Azahar_passed=True, runtime_runs=1,
                  source_and_ELF_only_two_output_masks_changed=True,
                  CIA_sha256=b.sha(B / 'ds34-uv-mask.cia'),
                  shader_sha256=b.sha(B / 'ds34.shbin'), container_hashes=hashes,
                  expected_unsigned_homebrew_signature_errors=errors,
                  game_resources_included=False,
                  files={name: dict(bytes=(D / name).stat().st_size, sha256=b.sha(D / name))
                         for name in sorted(copies.values())})
    (D / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    archive = D.parent / (D.name + '.zip')
    assert not archive.exists()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted([*copies.values(), 'manifest.json']):
            z.write(D / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist()) == set(copies.values()) | {'manifest.json'}
        for name, entry in report['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == entry['sha256']
    report.update(archive=archive.relative_to(P).as_posix(), archive_bytes=archive.stat().st_size,
                  archive_sha256=b.sha(archive))
    (A / 'package.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['CIA_sha256', 'archive', 'archive_bytes', 'archive_sha256']}, indent=2))


if __name__ == '__main__':
    main()
