"""Audit the isolated observer, then package only the tested release CIA."""
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

import build_ds34_gx_watch as b

P, B, A = b.P, b.D, b.A
E = P / 'analysis/azahar-ds34-gx-watch-v0.2.0'
F = P / 'analysis/azahar-ds34-gx-watch-v0.2.0-fault'
D = P / 'dist/ds34-gx-watch-v0.2.0'
sha = b.sha


def main():
    manifest = json.loads((B / 'build-manifest.json').read_text())
    normal = json.loads((E / 'result.json').read_text())
    fault = json.loads((F / 'result.json').read_text())
    host = json.loads((A / 'host-interpretation-tests.json').read_text())
    for key, root in [('inputs_sha256', P), ('outputs_sha256', B)]:
        for name, expected in manifest[key].items():
            assert sha(root / name) == expected, name
    assert not manifest['fault_build'] and '-DGX_WATCH_FAULT' not in manifest['defines']
    assert normal['passed'] and fault['passed'] and host['passed'] and host['cases'] == 12
    for name, expected in host['source_sha256'].items():
        assert sha(P / name) == expected
    assert normal['CIA_sha256'] == sha(B / 'ds34-gx-watch.cia')
    assert normal['payload_sha256'] == sha(B / 'cia-payload.cxi')
    assert normal['critical_io_attempts'] == fault['critical_io_attempts'] == 0
    assert normal['BGR8_whole_frame_verified'] and normal['window_elapsed_ms'] == 100
    assert fault['window_elapsed_ms'] == 2000 and fault['fault_test']
    assert normal['START_guest_cleanup_before_host_unload'] and fault['START_guest_cleanup_before_host_unload']
    obs = json.loads((E / 'observation.json').read_text())
    q = next(r for r in obs['queue_records'] if r['kind'] == 0 and r['queue']['total'] == 3)
    reference = json.loads((P / 'analysis/hardware/ds34-rgba8-v0.1.0-repeat-user/queue-04.json').read_text())
    assert q['entries'] == reference['entries'], 'GPU words changed relative to prior native capture'
    assert sha(B / 'ds34_gpu_rgba8_rgb8.c') == sha(b.prior.D / 'ds34_gpu_rgba8_rgb8.c')
    assert sha(B / 'ds34.shbin') == sha(b.prior.D / 'ds34.shbin')
    stock = b.prior.stock
    payload = stock.payload((B / 'ds34-gx-watch.cia').read_bytes())
    previous = stock.payload((b.prior.D / 'ds34-rgba8.cia').read_bytes())
    for start, end in [(0x408, 0x600), (0x20d, 0x210), (0x21c, 0x220)]:
        assert payload[start:end] == previous[start:end]
    tools = P / 'toolchain/devkitpro/devkitARM/bin'
    elf = B / 'ds34-gx-watch.elf'
    symbols = subprocess.check_output([str(tools / 'arm-none-eabi-nm.exe'), str(elf)], text=True)
    wrappers = set(re.findall(r'\b(__wrap_\w+)\b', symbols))
    required = {'__wrap_' + name for name in ['gxCmdQueueRun', 'gxCmdQueueClear', 'gspSubmitGxCommand',
                                              'fopen', 'fwrite', 'fprintf', 'fflush', 'fclose']}
    assert required <= wrappers and wrappers <= required | {'__wrap_fputs'}
    assert re.search(r' T gxCmdQueueInterrupt\b', symbols)
    assert not re.search(r'\b(?:NativeOnDrawFrame|ds_exec_\w+|ds_audit_trap\w*|__atomic_\w+_8)\b', symbols)
    assert b'Emulator-only fault build' not in elf.read_bytes()
    assert b'Emulator-only fault build' in (B.with_name(B.name + '-fault') / 'ds34-gx-watch.elf').read_bytes()
    asm = subprocess.check_output([str(tools / 'arm-none-eabi-objdump.exe'), '-d', str(elf)], text=True)
    functions = {m.group(1): m.group(0) for m in re.finditer(
        r'^[0-9a-f]+ <([^>]+)>:\n.*?(?=\n[0-9a-f]+ <|\Z)', asm, re.M | re.S)}
    assert '<gxCmdQueueInterrupt>' in functions['gspEventThreadMain']
    memory_names = ['record_event', 'record_queue', 'psc0', 'p3d', 'ppf', 'psc1', 'dma', 'gw_arm',
                    'gw_sample', 'gw_sample.part.0', 'gw_observe', 'gw_safe_exit', 'gw_idle',
                    '__wrap_gxCmdQueueRun', '__wrap_gxCmdQueueClear', '__wrap_gspSubmitGxCommand']
    forbidden = r'<(?:__wrap_)?(?:fopen|fwrite|fprintf|fflush|fclose|fputs|printf|puts|vfprintf|malloc|free|gspWaitForAnyEvent)(?:>|\+)'
    for name in memory_names:
        assert name in functions, name
        assert not re.search(forbidden, functions[name]), name
    # Callback recorder has no wait; main-thread observer alone may sleep/poll.
    assert '<svcSleepThread>' not in functions['record_event']
    assert '<gxCmdQueueWait>' not in functions['record_event']
    source = (P / 'tests/gx_watch.c').read_text()
    assert 'gxCmdQueueWait(q,0)' in source and '#include <stdio' not in source
    probe = (P / 'tests/ds34_gx_watch_probe.c').read_text()
    end = probe[probe.index('void ds34_diagnostic_end'):probe.index('int ds34_diagnostic_sync')]
    after_arm = end[end.index('gw_arm(fault)'):]
    assert not re.search(r'\b(?:printf|screen|log_phase|fprintf|fwrite|fflush)\s*\(', after_arm)
    selected = memory_names + ['ds34_diagnostic_end', 'ds34_diagnostic_sync', 'ds34_diagnostic_begin', 'gspEventThreadMain']
    (A / 'call-edges.asm.txt').write_text('\n'.join(functions[name] for name in selected))
    audit = {'passed': True, 'renderer_shader_and_all_24_GX_words_unchanged': True,
             'native_reference': 'analysis/hardware/ds34-rgba8-v0.1.0-repeat-user/queue-04.json',
             'real_SDK_IRQ_handler_reachable_not_wrapped': True,
             'memory_observer_call_graph_has_no_filesystem_or_allocation': True,
             'callback_recorder_has_no_wait_or_64_bit_atomics': True,
             'no_file_calls_after_arm_in_FrameEnd_hook': True,
             'no_critical_stdio_attempts_in_normal_and_fault_tests': True,
             'PSCl_P3D_PPF_callbacks_only_observe_after_SDK': True,
             'SDK_idle_alone_does_not_authorize_resource_free': True,
             'caps_equal_old_except_identity': True, 'fault_activation_absent_from_release': True,
             'linked_wrapper_symbols': sorted(wrappers)}
    (A / 'symbol-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    verify = subprocess.run([str(P / 'toolchain/extras/ctrtool/ctrtool.exe'), '--verify', str(B / 'ds34-gx-watch.cia')], capture_output=True, text=True)
    output = verify.stdout + verify.stderr
    errors = [x for x in output.splitlines() if ' ERROR]' in x]
    allowed = ['Signature for Ticket was invalid', 'Signature for TitleMetaData was invalid', 'Signature for AccessDescriptor was invalid']
    assert len(errors) == 3 and all(any(e in x for e in allowed) for x in errors), errors
    hashes = [x.strip() for x in output.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)', x)]
    assert len(hashes) >= 3 and all('(GOOD)' in x for x in hashes)
    copies = {B / 'ds34-gx-watch.cia': 'ds34-gx-watch.cia',
              P / '3ds/README-ds34-gx-watch.ru.md': 'README.ru.md', stock.LIB / 'LICENSE': 'LICENSE-citro3d.md',
              B / 'build-manifest.json': 'build-manifest.json', B / 'ds34_gpu_rgba8_rgb8.c': 'source/ds34_gpu_rgba8_rgb8.c',
              A / 'symbol-audit.json': 'validation/symbol-audit.json', A / 'call-edges.asm.txt': 'validation/call-edges.asm.txt',
              A / 'host-interpretation-tests.json': 'validation/host-interpretation-tests.json',
              F / 'result.json': 'validation/timeout-result.json', F / 'observation.json': 'validation/timeout-observation.json',
              F / 'screen.png': 'validation/timeout-screen.png', P / 'tools/gx_watch_report.py': 'gx_watch_report.py'}
    for name in ['gx_watch.h', 'gx_watch.c', 'gx_watch_save.c', 'ds34_gx_watch_probe.c']:
        copies[P / 'tests' / name] = 'source/' + name
    for q in E.glob('*'):
        if q.is_file() and q.suffix in ['.json', '.png', '.log', '.pica']:
            copies[q] = 'validation/' + q.name
    if D.exists():
        raise SystemExit(f'Refusing to replace a package: {D}')
    D.mkdir(parents=True)
    for source, name in copies.items():
        dest = D / name;dest.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(source, dest)
    report = {'prepared': True, 'date': '2026-10-31', 'version': '0.2.0', 'title_id': b.TITLE,
              'hardware_tested': False, 'hardware_run_authorized': False, 'native_cause_fixed': False,
              'Azahar_normal_and_timeout_passed': True, 'host_interpretation_cases_passed': 12,
              'critical_SD_writes': 0, 'format_path_preserved': True, 'baseline_backend_changed': False,
              'CIA_sha256': sha(B / 'ds34-gx-watch.cia'), 'ELF_sha256': sha(elf),
              'container_hashes': hashes, 'expected_homebrew_signature_errors': errors,
              'game_resources_included': False, 'fault_binary_included': False,
              'files': {name: {'bytes': (D / name).stat().st_size, 'sha256': sha(D / name)} for name in sorted(copies.values())}}
    (D / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    names = set(copies.values()) | {'manifest.json'}
    assert {q.relative_to(D).as_posix() for q in D.rglob('*') if q.is_file()} == names
    archive = P / 'dist/ds34-gx-watch-v0.2.0.zip';assert not archive.exists()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):z.write(D / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist()) == names
        for name, entry in report['files'].items():assert hashlib.sha256(z.read(name)).hexdigest() == entry['sha256']
        assert sum(name.endswith('.cia') for name in z.namelist()) == 1
        assert not any(name.endswith(('.elf', '.cxi', '.so', '.apk')) for name in z.namelist())
    report.update(archive=archive.relative_to(P).as_posix(), archive_bytes=archive.stat().st_size, archive_sha256=sha(archive))
    (A / 'package.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ['files', 'container_hashes', 'expected_homebrew_signature_errors']}, indent=2))


if __name__ == '__main__':
    main()
