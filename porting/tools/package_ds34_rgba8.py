"""Offline GX/SDK/container verification and packaging of one DS34 test CIA."""
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

import build_ds34_rgba8 as b

P, B, A = b.P, b.D, b.A
E = P / 'analysis/azahar-ds34-rgba8-v0.1.0'
D = P / 'dist/ds34-rgba8-v0.1.0'
sha = b.sha


def main():
    manifest = json.loads((B / 'build-manifest.json').read_text())
    test = json.loads((E / 'result.json').read_text())
    assert test['passed'] and test['frames_verified'] == 9 and test['queue_runs_completed'] == 9
    assert test['A_gate_stale_result_and_START_cleanup_verified'] and test['invalid_accesses'] == 0
    for key, root in [('inputs_sha256', P), ('outputs_sha256', B)]:
        for name, expected in manifest[key].items():
            assert sha(root / name) == expected, name
    assert test['CIA_sha256'] == sha(B / 'ds34-rgba8.cia')
    original = (P / '3ds/source/ds34_gpu_3ds.c').read_text()
    expected = original
    for before, after in b.EDITS:
        assert expected.count(before) == 1
        expected = expected.replace(before, after)
    assert expected == (B / 'ds34_gpu_rgba8_rgb8.c').read_text()
    assert sha(P / '3ds/source/ds34_gpu_3ds.c') == manifest['backend_source_unchanged']
    queues = [json.loads(q.read_text()) for q in sorted(E.glob('queue-*.json'))]
    runs = [q for q in queues if q['phase'] == 'before-run' and q['total'] == 3]
    comparisons = []
    for q in runs:
        fill, pica, transfer = q['entries']
        assert [fill[0], pica[0], transfer[0]] == [0x01000102, 0x01000101, 0x01000103]
        assert fill[2] == 0x68B0D8FF and fill[5] == 0 and fill[7] == 0x02010201
        assert fill[3] - fill[1] == fill[6] - fill[4] == 384000
        assert transfer[1] == fill[1]
        assert transfer[3:] == [0x019000f0, 0x019000f0, 0x1000, 0, 0]
        # VRAM banks, alignment, nonoverlap and actual useful LCD output range.
        spans = [(fill[1], fill[3]), (fill[4], fill[6]), (transfer[2], transfer[2] + 288000)]
        assert all(start % 128 == 0 and end > start for start, end in spans)
        assert all(0x1f000000 <= start < end <= 0x1f600000 for start, end in spans[:2])
        assert all(end <= other_start or other_end <= start for i, (start, end) in enumerate(spans)
                   for other_start, other_end in spans[i + 1:])
        comparisons.append({'queue_index': q['index'], 'FILL_words_hex': [f'{w:08x}' for w in fill],
                            'DISPLAY_words_hex': [f'{w:08x}' for w in transfer],
                            'PICA_cpu_address': f'{pica[1]:08x}', 'PICA_bytes': pica[2],
                            'color_bytes': 384000, 'depth_bytes': 384000, 'LCD_bytes': 288000})
    assert len(comparisons) == 9
    stock_manifest = json.loads((b.stock.D / 'build-manifest.json').read_text())
    stock_payload = b.stock.payload((b.stock.D / 'simple_tri-profile.cia').read_bytes())
    payload = b.stock.payload((B / 'ds34-rgba8.cia').read_bytes())
    for start, end in [(0x408, 0x600), (0x20d, 0x210), (0x21c, 0x220)]:
        assert payload[start:end] == stock_payload[start:end]
    for name in ['toolchain/citro3d/lib/libcitro3d.a', 'toolchain/devkitpro/libctru/lib/libctru.a']:
        assert manifest['inputs_sha256'][name] == stock_manifest['inputs_sha256'][name]
    tools = P / 'toolchain/devkitpro/devkitARM/bin'
    symbols = subprocess.check_output([str(tools / 'arm-none-eabi-nm.exe'), '-g', '--defined-only', str(B / 'ds34-rgba8.elf')], text=True)
    wrappers = re.findall(r'\b(__wrap_\w+)\b', symbols)
    assert set(wrappers) == {'__wrap_gxCmdQueueRun', '__wrap_gxCmdQueueClear'}
    assert re.search(r' T gxCmdQueueInterrupt\b', symbols)
    assert not re.search(r'\b(?:NativeOnDrawFrame|ds_exec_\w+|ds_audit_trap\w*)\b', symbols)
    disasm = subprocess.check_output([str(tools / 'arm-none-eabi-objdump.exe'), '-d', str(B / 'ds34-rgba8.elf')], text=True)
    functions = {}
    for name in ['record_queue', '__wrap_gxCmdQueueRun', '__wrap_gxCmdQueueClear', 'ds34_attach',
                 'ds34_diagnostic_begin', 'ds34_diagnostic_sync', 'ds34_diagnostic_end']:
        match = re.search(r'^([0-9a-f]+) <' + re.escape(name) + r'>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)', disasm, re.M | re.S)
        assert match, name
        functions[name] = match.group(0)
    assert not re.search(r'<(?:fopen|fprintf|fflush|fwrite|malloc|svcSleepThread|gspSetEventCallback)\b',
                         '\n'.join(functions[n] for n in ['record_queue', '__wrap_gxCmdQueueRun', '__wrap_gxCmdQueueClear']))
    assert '<C3D_FrameBegin>' in functions['ds34_diagnostic_begin']
    assert '<C3D_FrameSync>' in functions['ds34_diagnostic_sync']
    assert '<C3D_FrameEnd>' in functions['ds34_diagnostic_end']
    (A / 'call-edges.asm.txt').write_text('\n'.join(functions.values()))
    compare = {'passed': True, 'source_of_stock_expectations': 'Pinned stock main.c + same pinned SDK; no native stock GX capture available',
               'native_stock_addresses_measured': False, 'new_arguments_captured_in': 'Azahar queue-*.json',
               'stock_and_DS34_color_depth_fill_dimensions_transfer_match': True,
               'same_SDK_libraries_and_CIA_capabilities_except_identity': True,
               'Run_Clear_wrappers_memory_only_call_edges_verified': True,
               'real_SDK_IRQ_handler_linked_and_not_wrapped': True, 'baseline_source_unchanged': True,
               'stock_expected': {'target': '240x400 RGBA8 / D24S8', 'clear_word': '68b0d8ff',
                                  'color_depth_bytes': [384000, 384000], 'fill_controls': [0x201, 0x201],
                                  'transfer_dimensions': [0x019000f0, 0x019000f0], 'transfer_flags': 0x1000},
               'measured_new_runs': comparisons,
               'differences': ['DS34 shader/GLES, 4xfloat4 vertex and scissor; 2 triangles instead of stock 1',
                               'Inactive 256-byte texture copy, stream and CPU-runtime allocations',
                               'RGB-only writes, alpha kept one', 'FrameDrawOn before clear/FrameSplit',
                               'Explicit present with extra FrameSync/Begin and CPU readback',
                               'A gate, bottom console, phase logging, Run/Clear observation and SD capture',
                               'Extra compiler diagnostics/section flags; different ELF/code/address layout/identity'],
               'hardware_success_not_claimed': True}
    (A / 'comparison.json').write_text(json.dumps(compare, indent=2) + '\n')
    verify = subprocess.run([str(P / 'toolchain/extras/ctrtool/ctrtool.exe'), '--verify', str(B / 'ds34-rgba8.cia')], capture_output=True, text=True)
    output = verify.stdout + verify.stderr
    errors = [x for x in output.splitlines() if ' ERROR]' in x]
    allowed_errors = ['Signature for Ticket was invalid', 'Signature for TitleMetaData was invalid', 'Signature for AccessDescriptor was invalid']
    assert len(errors) == 3 and all(any(e in x for e in allowed_errors) for x in errors), errors
    hashes = [x.strip() for x in output.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)', x)]
    assert len(hashes) >= 3 and all('(GOOD)' in x for x in hashes)
    copies = {B / 'ds34-rgba8.cia': 'ds34-rgba8.cia', P / '3ds/README-ds34-rgba8.ru.md': 'README.ru.md',
              b.stock.LIB / 'LICENSE': 'LICENSE-citro3d.md', B / 'build-manifest.json': 'build-manifest.json',
              B / 'ds34_gpu_rgba8_rgb8.c': 'source/ds34_gpu_rgba8_rgb8.c', P / 'tests/ds34_rgba8_probe.c': 'source/ds34_rgba8_probe.c',
              A / 'backend.diff': 'source/backend.diff', A / 'comparison.json': 'validation/comparison.json',
              A / 'call-edges.asm.txt': 'validation/call-edges.asm.txt'}
    for q in E.glob('*'):
        if q.is_file() and q.suffix in ['.json', '.png', '.log']:
            copies[q] = 'validation/' + q.name
    if D.exists():
        raise SystemExit(f'Refusing to overwrite a package: {D}')
    D.mkdir(parents=True)
    for source, name in copies.items():
        dest = D / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    report = {'prepared': True, 'version': '0.1.0', 'title_id': b.TITLE, 'hardware_tested': False,
              'hardware_run_authorized': False, 'Azahar_passed': True, 'frames_verified': 9,
              'diagnostic_cycles': 2, 'comparison_passed': True, 'container_hashes': hashes,
              'expected_homebrew_signature_errors': errors, 'game_resources_included': False,
              'CIA_sha256': sha(B / 'ds34-rgba8.cia'), 'ELF_sha256': sha(B / 'ds34-rgba8.elf'),
              'files': {name: {'bytes': (D / name).stat().st_size, 'sha256': sha(D / name)} for name in sorted(copies.values())}}
    (D / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    names = set(copies.values()) | {'manifest.json'}
    assert {q.relative_to(D).as_posix() for q in D.rglob('*') if q.is_file()} == names
    archive = P / 'dist/ds34-rgba8-v0.1.0.zip'
    assert not archive.exists()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):
            z.write(D / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist()) == names
        for name, entry in report['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == entry['sha256']
    report.update(archive=archive.relative_to(P).as_posix(), archive_bytes=archive.stat().st_size, archive_sha256=sha(archive))
    (A / 'package.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ['files', 'container_hashes', 'expected_homebrew_signature_errors']}, indent=2))


if __name__ == '__main__':
    main()
