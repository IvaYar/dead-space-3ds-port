"""Read-only native DS34 archive/SDK/binary audit. No build or runtime test."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/ds34-rgba8-queue-audit'
N = P / 'analysis/hardware/ds34-rgba8-v0.1.0-repeat-user'
B = P / '3ds/build-ds34-rgba8-v0.1.0'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    archive = json.loads((N / 'archive-manifest.json').read_text())
    assert sha(P / archive['archive']) == archive['archive_sha256']
    for name, entry in archive['files'].items():
        assert sha(N / name) == entry['sha256'], name
    log = (N / 'gpu-test.log').read_text()
    assert 'environment=native bytes=288000 layout=1 flags=00001000' in log
    phases = re.findall(r'PHASE ms=(\d+) frame=(\d+) vb=(\d+),(\d+) (.*)', log)
    assert phases[-1] == ('4253', '0', '27', '27', 'SDK FRAME BEGIN')
    assert 'SDK FRAME END OK' in log and 'SDK SYNC OK' in log
    queues = [json.loads((N / f'queue-{i:02}.json').read_text()) for i in range(5)]
    assert queues[3]['total'] == queues[3]['submitted'] == queues[3]['completed'] == 1
    q = queues[4]
    assert q['phase'] == 'before-run' and (q['total'], q['submitted'], q['completed']) == (3, 0, 0)
    fill, pica, display = q['entries']
    assert [w[0] & 255 for w in q['entries']] == [2, 1, 3]
    assert fill[3] - fill[1] == fill[6] - fill[4] == 384000
    assert fill[2] == 0x68b0d8ff and fill[5] == 0 and fill[7] == 0x02010201
    assert display[1] == fill[1] and display[3:] == [0x019000f0, 0x019000f0, 0x1000, 0, 0]
    assert pica[2] == 1168 and not any(pica[3:])
    spans = [(fill[1], fill[3]), (fill[4], fill[6]), (display[2], display[2] + 288000),
             (pica[1], pica[1] + pica[2])]
    assert all(start % 128 == 0 and start < end for start, end in spans)
    assert all(end <= s or e <= start for i, (start, end) in enumerate(spans) for s, e in spans[i + 1:])
    emulator = P / 'analysis/azahar-ds34-rgba8-v0.1.0'
    queue_matches = [q == json.loads((emulator / f'queue-{i:02}.json').read_text()) for i, q in enumerate(queues)]
    assert all(queue_matches)
    sdk_reference = json.loads((P / 'analysis/gpu-clear-audit/sources.json').read_text())
    sources = [P / 'analysis/gpu-clear-audit/upstream' / name for name in ['gxqueue.c', 'gx.c', 'gspgpu.c', 'gfx.c']]
    for path in sources:
        assert sha(path) == sdk_reference[path.name]['sha256']
    library = json.loads((P / 'toolchain/citro3d/build-manifest.json').read_text())
    for name in ['renderqueue.c', 'framebuffer.c', 'base.c']:
        path = P / 'toolchain/citro3d-source/source' / name
        assert sha(path) == library['source_sha256']['source/' + name]
        sources.append(path)
    manifest = json.loads((B / 'build-manifest.json').read_text())
    for name, expected in manifest['inputs_sha256'].items():
        assert sha(P / name) == expected, name
    for name, expected in manifest['outputs_sha256'].items():
        assert sha(B / name) == expected, name
    stock = json.loads((P / '3ds/build-official-simple-tri/build-manifest.json').read_text())
    for name in ['toolchain/citro3d/lib/libcitro3d.a', 'toolchain/devkitpro/libctru/lib/libctru.a']:
        assert manifest['inputs_sha256'][name] == stock['inputs_sha256'][name]
    tool = P / 'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-objdump.exe'
    disasm = subprocess.check_output([str(tool), '-d', str(B / 'ds34-rgba8.elf')], text=True)
    names = ['C3D_FrameBegin', 'C3D_FrameSync', 'C3D_FrameEnd', 'gxCmdQueueRun', 'gxCmdQueueWait',
             'gxCmdQueueInterrupt', 'gspEventThreadMain', 'ds34_diagnostic_mark', 'ds34_diagnostic_begin',
             '__wrap_gxCmdQueueRun']  # dump_records is inlined into the diagnostic mark.
    functions = {}
    for name in names:
        match = re.search(r'^[0-9a-f]+ <' + name + r'>:\n.*?(?=\n[0-9a-f]+ <|\Z)', disasm, re.M | re.S)
        assert match, name
        functions[name] = match.group()
    # This build inlines FrameSync into FrameBegin; wrapping the public
    # FrameSync symbol alone would miss this second VBlank wait.
    assert '<gspWaitForAnyEvent>' in functions['C3D_FrameBegin']
    assert '<gxCmdQueueWait>' in functions['C3D_FrameBegin']
    assert '<__wrap_gxCmdQueueRun>' in functions['C3D_FrameEnd']
    assert '<gxCmdQueueInterrupt>' in functions['gspEventThreadMain']
    assert '<gxCmdQueueWait>' not in functions['C3D_FrameSync']
    assert '<gspWaitForAnyEvent>' in functions['C3D_FrameSync']
    (A / 'linked-functions.asm.txt').write_text('\n'.join(functions.values()))
    records = []
    for words, name, event in zip(q['entries'], ['FILL', 'PICA', 'DISPLAY'], ['PSC0 (PSC1 ignored by SDK queue)', 'P3D', 'PPF']):
        records.append({'operation': name, 'expected_completion': event, 'raw_words_hex': [f'{w:08x}' for w in words]})
    report = {
        'date': '2026-10-31', 'static_checks_passed': True, 'runtime_tests_run': False, 'CIA_built': False,
        'hardware_archive': archive, 'native_environment_marker': True, 'final_phase': phases[-1],
        'initial_TEXCOPY_credited_completed': True,
        'queue_04_is_before_run_not_live_after_run': True, 'native_post_run_counters_available': False,
        'all_5_queue_records_match_saved_Azahar_JSON': queue_matches,
        'native_PICA_vertex_texture_payloads_compared': False,
        'SDK_sources_and_libraries_match_pinned_build': True,
        'linked_binary_inlines_VBlank_wait_before_GX_wait_in_FrameBegin': True,
        'linked_real_GX_IRQ_handler_reachable': True,
        'operations': records, 'nonoverlapping_known_memory_spans': [[f'{s:08x}', f'{e:08x}'] for s, e in spans],
        'inference': 'Incomplete GX queue is plausible but not established by before-run counters; nested VBlank wait and logging windows also remain.',
        'first_GPU_candidate_to_measure': 'PICA/P3D completion (hypothesis, not a localized native failure)',
        'known_limits': ['No native post-Run fields, submission Results or event deltas',
                         'FrameBegin(SYNCDRAW) has another unlabelled FrameSync',
                         'Last PHASE line does not prove its fflush returned or exclude post-Begin dump I/O',
                         'No native stock GX/PICA payload capture'],
        'sources_sha256': {q.relative_to(P).as_posix(): sha(q) for q in sources},
    }
    (A / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Static audit PASS: all hardware files, exact queue words, pinned SDK and linked wait/IRQ paths verified.')
    print('No new build or runtime/hardware test.')


if __name__ == '__main__':
    main()
