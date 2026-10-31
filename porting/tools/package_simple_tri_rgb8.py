"""Validate/package the prepared RGB8 output experiment, without running it."""
import hashlib
import json
import re
import shutil
import struct
import subprocess
import zipfile

import build_simple_tri_rgb8 as b

P, B, A = b.P, b.D, b.A
E = P / 'analysis/azahar-simple-tri-rgb8'
D = P / 'dist/simple-tri-rgb8-v0.1.0'
sha = b.sha


def main():
    manifest = json.loads((B / 'build-manifest.json').read_text())
    test = json.loads((E / 'result.json').read_text())
    for key, root in [('inputs_sha256', P), ('outputs_sha256', B)]:
        for name, expected in manifest[key].items():
            assert sha(root / name) == expected, name
    assert test['passed'] and test['START_guest_GSP_release_and_heap_free']
    assert test['invalid_accesses_in_host_log'] == 0
    assert test['CIA_sha256'] == sha(B / 'simple-tri-rgb8.cia')
    assert test['payload_sha256'] == sha(B / 'cia-payload.cxi')
    original = (b.previous.D / 'main.c').read_text()
    expected = original
    for before, after in b.EDITS:
        assert expected.count(before) == 1
        expected = expected.replace(before, after)
    assert (B / 'main.c').read_text() == expected
    assert sha(B / 'vshader.shbin.o') == sha(b.previous.stock.D / 'vshader.shbin.o')
    current = b.previous.stock.payload((B / 'simple-tri-rgb8.cia').read_bytes())
    old = b.previous.stock.payload((b.previous.D / 'simple-tri-rgb565.cia').read_bytes())
    for start, end in [(0x408, 0x600), (0x20d, 0x210), (0x21c, 0x220)]:
        assert current[start:end] == old[start:end]
    assert struct.unpack_from('<Q', current, 0x108)[0] == int(b.TITLE, 16)
    nm = P / 'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-nm.exe'
    symbols = subprocess.check_output([str(nm), '-g', '--defined-only', str(B / 'triangle.elf')], text=True)
    assert re.search(r' T gxCmdQueueInterrupt\b', symbols)
    assert not re.search(r'\b(?:__wrap_|ds34_|ds22_|ds_runtime_|clear_events_|NativeOnDrawFrame)\w*', symbols)
    verify = subprocess.run([str(P / 'toolchain/extras/ctrtool/ctrtool.exe'), '--verify',
                             str(B / 'simple-tri-rgb8.cia')], capture_output=True, text=True)
    output = verify.stdout + verify.stderr
    errors = [x for x in output.splitlines() if ' ERROR]' in x]
    allowed = ['Signature for Ticket was invalid', 'Signature for TitleMetaData was invalid',
               'Signature for AccessDescriptor was invalid']
    assert len(errors) == 3 and all(any(e in x for e in allowed) for x in errors), errors
    hashes = [x.strip() for x in output.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)', x)]
    assert len(hashes) >= 3 and all('(GOOD)' in x for x in hashes)
    copies = {B / 'simple-tri-rgb8.cia': 'simple-tri-rgb8.cia',
              P / '3ds/README-simple-tri-rgb8.ru.md': 'README.ru.md',
              b.previous.stock.LIB / 'LICENSE': 'LICENSE-citro3d.md',
              B / 'main.c': 'source/main.c', A / 'source.diff': 'validation/source.diff',
              b.previous.D / 'main.c': 'reference/rgb565-main.c',
              b.previous.stock.A / 'upstream/graphics/gpu/simple_tri/source/vshader.v.pica': 'reference/vshader.v.pica',
              B / 'build-manifest.json': 'validation/build-manifest.json'}
    for name in ['result.json', 'azahar-host.log', 'top-60.png', 'top-90.png', 'top-120.png']:
        copies[E / name] = 'validation/' + name
    if D.exists():
        raise SystemExit(f'Package directory already exists: {D}')
    D.mkdir(parents=True)
    for source, name in copies.items():
        dest = D / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    report = {'prepared': True, 'version': '0.1.0', 'date': '2026-10-30',
              'hardware_tested': False, 'hardware_run_authorized': False,
              'Azahar_passed': True, 'diagnostic_cycles': 1, 'title_id': b.TITLE,
              'CIA_sha256': sha(B / 'simple-tri-rgb8.cia'), 'ELF_sha256': sha(B / 'triangle.elf'),
              'source_output_only_whitelist_verified': True,
              'shader_SDK_flags_capabilities_and_draw_preserved': True,
              'real_SDK_queue_handler_no_wrappers': True, 'container_hashes': hashes,
              'expected_unsigned_homebrew_signature_errors': errors,
              'game_resources_included': False, 'DS34_changed': False,
              'files': {name: {'bytes': (D / name).stat().st_size, 'sha256': sha(D / name)}
                        for name in sorted(copies.values())}}
    (D / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    names = set(copies.values()) | {'manifest.json'}
    assert {q.relative_to(D).as_posix() for q in D.rglob('*') if q.is_file()} == names
    archive = P / 'dist/simple-tri-rgb8-v0.1.0.zip'
    assert not archive.exists()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):
            z.write(D / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist()) == names
        for name, entry in report['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == entry['sha256']
    report.update(archive=archive.relative_to(P).as_posix(), archive_bytes=archive.stat().st_size,
                  archive_sha256=sha(archive))
    (A / 'package.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in
                      ['files', 'container_hashes', 'expected_unsigned_homebrew_signature_errors']}, indent=2))


if __name__ == '__main__':
    main()
