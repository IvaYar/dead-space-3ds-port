"""Audit the received 0.1.5 console run; never manufacture an image PASS."""
import hashlib
import json
from pathlib import Path
import re
import zlib

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-game-menu-v0.1.5-hardware'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = read(A / 'archive-manifest.json')
    source, archive = [P / manifest[k] for k in ['source', 'archive']]
    for root in [source, archive]:
        assert {f.name for f in root.iterdir()} == set(manifest['files'])
        for name, item in manifest['files'].items():
            assert (root / name).stat().st_size == item['bytes']
            assert sha(root / name) == item['sha256'], name
    log = (archive / 'native-game.log').read_text(encoding='utf-8')

    def rows(tag):
        return [json.loads(line[len(tag) + 1:]) for line in log.splitlines()
                if line.startswith(tag + ' ')]

    result, validation, close = [read(archive / name) for name in
                                ['result.json', 'validation.json', 'close-state.json']]
    assert result['environment'] == 'native'
    assert result['status'] == 'failed' and validation['frame_status'] == 'FAIL'
    assert validation['expected_crc565'] == 'ea733050' and not validation['matched_callback']
    assert result['safe_exit'] and validation['safe_exit'] and validation['cleanup_complete']
    assert validation['callbacks_completed'] == result['frame'] == 12000
    assert result['active_threads'] == result['finished_threads'] == 0
    assert result['GL_error'] == result['failed_submits'] == 0
    assert close['shutdown_attempts'] == 1 and close['cleanup_complete']
    assert close['source'] == 'none' and not close['home_pending'] and not close['close_pending']
    assert not close['stopped_boundary'] and close['code_and_arenas_retained_until_process_teardown']
    assert 'MENU_ONLY original confirm' not in log
    assert 'PROCESS return close_pending=0 source=none stopped_boundary=0 cleanup=complete attempts=1' in log
    assert (archive / 'exit.txt').read_text().strip() == 'Workers stopped; GPU drained; returning to HOME'
    controls = re.findall(r'^CONTROL .*', log, re.M)
    assert not controls
    io = re.findall(r'RESOURCES JNI=(\d+) stdio=(\d+) appdata=(\d+) IOactive=(\d+) '
                    r'opens/closes=(\d+)/(\d+) dirs=(\d+)', log)
    assert io == [('13', '0', '0', '0', '174', '174', '0')]
    before, quiet, joined = [read(archive / ('threads-a1-' + stage + '.json'))['workers']
                             for stage in ['before_pause', 'after_quiesce', 'after_join']]
    before = [w for w in before if w['entry']]
    quiet = [w for w in quiet if w['entry']]
    joined = [w for w in joined if w['entry']]
    assert len(before) == len(quiet) == 5 and not joined
    assert {w['token'] for w in before} == {w['token'] for w in quiet}
    assert all(w['done'] == 1 and w['kernel_wait'] == 0 for w in quiet)

    captures, inputs = rows('CAPTUREJSON'), rows('INPUTJSON')
    assert len(captures) == len(inputs) == 100
    for c, i in zip(captures, inputs):
        raw = (archive / c['file']).read_bytes()
        assert len(raw) == 288000 and c['format'] == 'BGR8_CTR' and c['column_stride'] == 720
        assert c['raw_crc_a'] == c['raw_crc_b'] == f'{zlib.crc32(raw):08x}'
        packed = bytearray()
        for b, g, r in zip(raw[0::3], raw[1::3], raw[2::3]):
            pixel = (r >> 3) << 11 | (g >> 2) << 5 | b >> 3
            packed.extend((pixel & 255, pixel >> 8))
        assert c['crc565_a'] == c['crc565_b'] == f'{zlib.crc32(packed):08x}'
        assert i['frame'] == c['frame'] and not i['capture_truncated']
        assert (archive / i['file']).stat().st_size == i['command_bytes'] > 0
    # Render admission fingerprints are not the frozen validation baseline.
    header = P / '3ds/build-native-game-v0.1.5-r14/native_menu_input.h'
    allowed = re.findall(r'crc==0x([0-9a-f]{8})u', header.read_text())
    assert set(allowed) == {'7296717d', '223b5e75', '0ded835d'}
    observed = re.findall(r'^FRAMECRC frame=\d+ crc565=([0-9a-f]{8})', log, re.M)
    assert not set(allowed).intersection(observed)
    menu = [c for c in captures if c['frame'] >= 4440]
    assert all(c['crc565_a'] == '95b893de' for c in menu)

    perf, memory, peaks = rows('PERFJSON'), rows('MEMJSON'), rows('PEAKJSON')
    assert [w['frame'] for w in perf] == list(range(120, 12001, 120))
    steady = [w for w in perf if w['frame'] >= 4560]
    count = sum(w['callbacks'] for w in steady)
    slow = max(perf, key=lambda w: w['elapsed_ms'])
    assert not any(m['donor_refusals'] or m['runtime_failures'] for m in memory)
    assert all(m['query_result'] == 0 and m['commit'] <= m['limit'] == 124 * 1024 * 1024 for m in memory)
    gate = read(A / 'software-release-gate-before-hardware.json')
    assert sha(P.parent / gate['CIA']['path']) == gate['CIA']['sha256']
    audit = {
        'hardware_tested': True, 'archive_verified': True,
        'archived_files': len(manifest['files']),
        'archived_bytes': sum(f['bytes'] for f in manifest['files'].values()),
        'CIA': gate['CIA'], 'original_difficulty_menu_observed': True,
        'visual_evidence': 'User photo and independently decoded original hardware raw frame4440: Normal selected.',
        'hardware_menu_crc565': '95b893de', 'first_saved_menu_frame': 4440,
        'raw_readback_pairs_independently_verified': len(captures),
        'complete_saved_GX_traces': len(inputs),
        'physical_DOWN_reported': True, 'physical_DOWN_capture_logged': False,
        'original_navigation_event_delivered': False, 'difficulty_changed': False,
        'input_blocker': 'All hardware FRAMECRC observations miss the three Azahar-only input admission fingerprints; navigation/A remains inhibited. Physical HID sampling itself was not logged.',
        'software_input_admission_fingerprints': allowed,
        'gameplay_started': False, 'exit_cause': 'normal callback cap12000, no START/HOME/A-confirm or fault stop recorded',
        'safe_exit': True, 'shutdown_attempts': 1, 'kernel_completed_workers': len(quiet),
        'worker_handles_remaining': len(joined), 'IO_opens': 174, 'IO_closes': 174,
        'GL_error': 0, 'failed_submits': 0, 'frame_status': 'FAIL',
        'baseline_crc_unchanged': 'ea733050',
        'hardware_heap_release_independently_measured': False,
        'timing': {
            'steady_frame_range': [4560, 12000],
            'steady_FPS_including_diagnostics': 1000 * count / sum(w['elapsed_ms'] for w in steady),
            'steady_ms_per_callback': {k: sum(w[k] for w in steady) / count for k in
                ['callback_ms', 'present_ms', 'diagnostic_ms', 'gpu_queue_wait_ms', 'vblank_wait_ms']},
            'last_C3D_drawing_ms_range': [min(w['last_c3d_drawing_ms'] for w in steady), max(w['last_c3d_drawing_ms'] for w in steady)],
            'slowest_120_callback_window': slow,
            'sum_callback_loop_windows_ms': sum(w['elapsed_ms'] for w in perf),
            'sum_windows_through_first_saved_menu_ms': sum(w['elapsed_ms'] for w in perf if w['frame'] <= 4440),
            'limits': 'SDK tick intervals include diagnostics; omit preflight/shutdown. Window timing cannot identify an individual slow call. Queue/VBlank waits overlap measured sections; do not add twice. User wall times are approximate.'},
        'memory': {'normal_peak_footprint': max(m['normal_footprint'] for m in peaks),
                   'linear_peak_used': max(m['linear_used'] for m in peaks),
                   'linear_transient_headroom': 100 * 1024 * 1024 - max(m['linear_used'] for m in peaks),
                   'runtime_allocation_failures': 0, 'donor_allocation_refusals': 0},
        'repeat_current_CIA_needed': False,
    }
    (A / 'hardware-result.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    gate.update({
        'ready_for_one_separate_hardware_test': False,
        'hardware_tested': True, 'hardware_run_authorized': False,
        'hardware_FPS_measured': True,
        'hardware_menu_confirmed': True, 'hardware_buttons_confirmed': False,
        'hardware_safe_exit_confirmed': True,
        'repeat_current_CIA_needed': False,
        'hardware_result': 'porting/analysis/native-game-menu-v0.1.5-hardware/hardware-result.json',
        'next_hardware_test_requires_fixed_input_and_separate_authorization': True,
    })
    (P / 'analysis/native-game-menu-v0.1.5/release-gate.json').write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: audit[k] for k in ['archive_verified', 'archived_files', 'safe_exit',
                                          'original_navigation_event_delivered', 'exit_cause']}))


if __name__ == '__main__':
    main()
