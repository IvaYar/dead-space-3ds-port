"""Audit received 0.1.6 hardware, preserving failed input and strict FRAME FAIL."""
import hashlib
import json
from pathlib import Path
import re
import zlib
from audit_native_game_menu import packed

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-game-controls-v0.1.6-hardware'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = read(A / 'archive-manifest.json')
    source, archive = [P / manifest[k] for k in ['source', 'archive']]
    assert len(manifest['files']) == 200
    for root in [source, archive]:
        assert {f.name for f in root.iterdir()} == set(manifest['files'])
        for name, item in manifest['files'].items():
            assert (root / name).stat().st_size == item['bytes'] and sha(root / name) == item['sha256'], name
    observations = read(A / 'user-observations.json')
    assert observations['menu_wait_seconds'] == 554 and not observations['DOWN_selection_changed']
    log = (archive / 'native-game.log').read_text()

    def rows(tag):
        return [json.loads(l[len(tag) + 1:]) for l in log.splitlines() if l.startswith(tag + ' ')]

    result, validation, close = [read(archive / n) for n in ['result.json', 'validation.json', 'close-state.json']]
    assert result['environment'] == 'native' and result['native_RX_verified']
    assert result['status'] == 'failed' and validation['frame_status'] == 'FAIL'
    assert validation['expected_crc565'] == 'ea733050' and validation['matched_callback'] == 0
    assert result['safe_exit'] and validation['safe_exit'] and validation['cleanup_complete']
    assert validation['callbacks_completed'] == result['frame'] == 11208
    assert result['GL_error'] == result['failed_submits'] == result['active_threads'] == result['finished_threads'] == 0
    assert close['source'] == 'START' and close['shutdown_attempts'] == 1 and close['cleanup_complete']
    assert not close['stopped_boundary'] and not close['home_pending'] and not close['close_pending']
    assert close['code_and_arenas_retained_until_process_teardown']
    assert 'PROCESS return close_pending=0 source=START stopped_boundary=0 cleanup=complete attempts=1' in log
    assert 'Workers stopped; GPU drained; returning to HOME' in (archive / 'exit.txt').read_text()
    assert 'opens/closes=174/174 dirs=0' in log and 'stdio=0 appdata=0 IOactive=0' in log
    quiet, joined = [read(archive / ('threads-a1-' + s + '.json'))['workers']
                     for s in ['after_quiesce', 'after_join']]
    quiet = [w for w in quiet if w['entry']]
    assert len(quiet) == 5 and all(w['done'] == 1 and w['kernel_wait'] == 0 for w in quiet)
    assert not [w for w in joined if w['entry']]
    controls = re.findall(r'^CONTROL .*', log, re.M)
    rejected = re.findall(r'^HID_REJECT .*', log, re.M)
    assert not controls and not rejected
    state_lines = re.findall(r'^MENUSTATE .*', log, re.M)
    states = [dict((k, int(v, 16) if k in ['layer', 'held', 'down'] else int(v))
                   for k, v in re.findall(r'(frame|layer|phase|transition|closing|ready|selection|held|down)=([0-9a-f]+)', l))
              for l in state_lines]
    ready = [s for s in states if s['ready']]
    assert len(ready) == 59 and ready[0]['frame'] == 4200
    assert all(s['phase'] == 2 and s['selection'] == 1 and not s['transition'] and not s['closing'] for s in ready)
    assert all(s['held'] == s['down'] == 0 for s in states)
    captures, inputs = rows('CAPTUREJSON'), rows('INPUTJSON')
    assert len(captures) == len(inputs) == 93
    for c, i in zip(captures, inputs):
        raw = (archive / c['file']).read_bytes()
        assert len(raw) == 288000 and c['format'] == 'BGR8_CTR' and c['column_stride'] == 720
        assert c['raw_crc_a'] == c['raw_crc_b'] == f'{zlib.crc32(raw):08x}'
        assert c['crc565_a'] == c['crc565_b'] == f'{zlib.crc32(packed(raw)):08x}'
        assert i['frame'] == c['frame'] and not i['capture_truncated']
        assert (archive / i['file']).stat().st_size == i['command_bytes'] > 0
    menu = [c for c in captures if c['frame'] >= 4200]
    assert len(menu) == 59 and all(c['crc565_a'] == '95b893de' for c in menu)
    old = P / 'analysis/hardware/native-game-menu-v0.1.5-user-run-0001/explore-4440.raw'
    assert all((archive / c['file']).read_bytes() == old.read_bytes() for c in menu)
    callbacks = rows('CALLBACKJSON'); warm = max(callbacks, key=lambda c: c['ms'])
    assert warm['frame'] == 4132 and warm['ops'][0]['calls'] == 1146
    assert warm['page_saves'] == 201 and warm['page_loads'] == 166
    assert warm['ops'][10]['calls'] == 0 and warm['ops'][11]['calls'] == 367
    assert warm['ops'][11]['bytes'] == 1069965312
    assert warm['resource_bytes'] == warm['resource_reads'] == warm['IO_completions'] == 0
    pattern = r'^TEXALLOC frame=(\d+) w=(\d+) h=(\d+) linear=(\d+) ok=(\d+)'
    old_log = old.parent / 'native-game.log'

    def allocation_sequence(text, frame):
        return [m[1:] for m in re.findall(pattern, text, re.M) if int(m[0]) == frame]

    sequence = allocation_sequence(log, 4132)
    assert len(sequence) == 129 and sequence == allocation_sequence(old_log.read_text(), 4343)
    windows, memory, peaks = rows('PERFJSON'), rows('MEMJSON'), rows('PEAKJSON')
    steady = [w for w in windows if w['frame'] >= 4320]
    count = sum(w['callbacks'] for w in steady)
    assert not any(m['donor_refusals'] or m['runtime_failures'] for m in memory)
    assert all(m['query_result'] == 0 and m['commit'] <= m['limit'] == 124 * 1024 * 1024 for m in memory)
    gate = read(A / 'software-release-gate-before-hardware.json')
    assert sha(P.parent / gate['CIA']['path']) == gate['CIA']['sha256']
    for n, digest in gate['headers_sha256'].items():
        assert sha(P / '3ds/build-native-game-v0.1.6-final2' / n) == digest
    audit = {
        'hardware_tested': True, 'archive_verified': True,
        'archived_files': len(manifest['files']), 'archived_bytes': sum(f['bytes'] for f in manifest['files'].values()),
        'CIA': gate['CIA'], 'original_difficulty_menu_observed': True,
        'image_and_frame_status': 'FAIL', 'baseline_crc_unchanged': 'ea733050',
        'independently_verified_raw_readback_pairs': len(captures), 'complete_saved_GX_traces': len(inputs),
        'stable_menu_captures_byte_identical_to_hardware_015': len(menu),
        'hardware_menu_crc565': '95b893de', 'original_menu_guard_ready_observations': len(ready),
        'first_recorded_ready_frame': ready[0]['frame'], 'original_selection': 'Normal',
        'physical_DOWN_reported': 'Lower D-pad button, explicitly clarified by user.',
        'Dpad_DOWN_edge_logged': False, 'HID_rejection_logged': False,
        'original_input_event_logged': False, 'difficulty_changed': False,
        'input_root_cause_established': False,
        'input_conclusion': 'Guard reaches ready=1 on hardware. No DOWN relevant edge reaches the logged menu sample. Sparse held snapshots do not exclude short input activity between samples. No claim of a hardware defect or incorrect user control; no native event-delivery proof.',
        'safe_exit': True, 'exit_source': 'START', 'shutdown_attempts': 1,
        'kernel_completed_workers': len(quiet), 'worker_handles_remaining': 0,
        'balanced_IO': [174, 174], 'GL_error': 0, 'failed_submits': 0,
        'hardware_heap_release_independently_measured': False,
        'user_menu_wait_seconds': 554, 'user_START_to_HOME_seconds_approx': [1, 2],
        'slowest_original_draw_callback': warm,
        'same_129_texture_allocation_sequence_as_015': True,
        'timing': {
            'steady_FPS_including_diagnostics': 1000 * count / sum(w['elapsed_ms'] for w in steady),
            'steady_ms_per_callback': {k: sum(w[k] for w in steady) / count for k in
                ['callback_ms', 'present_ms', 'diagnostic_ms', 'gpu_queue_wait_ms', 'vblank_wait_ms']},
            'sum_loop_windows_through_first_saved_menu_ms': sum(w['elapsed_ms'] for w in windows if w['frame'] <= 4200),
            'sum_completed_loop_windows_ms': sum(w['elapsed_ms'] for w in windows),
            'limits': 'SDK tick windows omit initialization, shutdown and partial trailing window. Nested timings overlap. Old473285.745ms is a120-callback window, not a timed individual draw.'},
        'memory': {'normal_peak_footprint': max(m['normal_footprint'] for m in peaks),
                   'linear_peak_used': max(m['linear_used'] for m in peaks),
                   'linear_transient_headroom': 100 * 1024 * 1024 - max(m['linear_used'] for m in peaks),
                   'kernel_peak_commit': max(m['commit'] for m in memory),
                   'runtime_allocation_failures': 0, 'donor_allocation_refusals': 0},
        'gameplay_started': False, 'repeat_current_CIA_needed': False,
    }
    (A / 'hardware-result.json').write_text(json.dumps(audit, indent=2) + '\n')
    gate.update({'ready_for_one_separate_hardware_test': False, 'hardware_tested': True,
                 'hardware_run_authorized': False, 'hardware_loading_profile_measured': True,
                 'hardware_menu_confirmed': True, 'hardware_buttons_confirmed': False,
                 'hardware_menu_guard_ready_confirmed': True, 'hardware_safe_START_exit_confirmed': True,
                 'hardware_input_root_cause_established': False, 'repeat_current_CIA_needed': False,
                 'hardware_blocker': 'Physical D-pad DOWN has no relevant edge/event in menu adapter log; root cause remains open.',
                 'hardware_result': 'porting/analysis/native-game-controls-v0.1.6-hardware/hardware-result.json'})
    (P / 'analysis/native-game-controls-v0.1.6/release-gate.json').write_text(json.dumps(gate, indent=2) + '\n')
    print(json.dumps({'archive_verified': True, 'files': len(manifest['files']),
                      'safe_exit': True, 'guard_ready_observations': len(ready), 'input_proven': False,
                      'warm_callback_ms': warm['ms'], 'FPS': audit['timing']['steady_FPS_including_diagnostics']}))


if __name__ == '__main__':
    main()
