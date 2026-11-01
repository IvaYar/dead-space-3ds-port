"""Read-only verification of the two user-supplied Progress 0.1.4 runs.

Does not launch hardware, build binaries, change frame criteria or rewrite inputs.
Numeric reports may be regenerated; source and archive hashes must both match.
"""
import json
from pathlib import Path
import re

from azahar_resource_store import sha
from analyze_native_game_run import inspect

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-game-progress-v0.1.4-hardware'
CIA_SHA = '89973ea6d2607222895c28f1062d93db610461268befebf8cc19bc92dd34521f'


def read(path):
    return json.loads(path.read_text())


def workers(root, stage):
    d = read(root / ('threads-a1-' + stage + '.json'))
    return d, [w for w in d['workers'] if w['token'] & 255]


def verify():
    manifest = read(A / 'archive-manifest.json')
    observations = read(A / 'user-observations.json')
    assert observations['executed_by'] == 'user'
    assert observations['user_reports']['both_exited_successfully']
    assert observations['user_reports']['console_did_not_hang']
    before = read(A / 'software-release-gate-before-hardware.json')
    assert before['software_passed'] and before['completed_process_exits'] == 11
    assert before['CIA']['CIA_sha256'] == CIA_SHA
    assert sha(P / '3ds/build-native-game-v0.1.4r2-normal/native-game.cia') == CIA_SHA
    rows, captures = {}, {}
    for name, expected_files, expected_bytes, expected_callbacks, expected_captures, expected_io in [
        ('run-0001', 34, 3128442, 600, 9, 174),
        ('run-0002', 28, 2147091, 453, 6, 153),
    ]:
        m = manifest['files'][name]
        src, root = P / m['source'], P / m['archive']
        assert m['count'] == len(m['entries']) == expected_files
        assert m['bytes'] == sum(e['bytes'] for e in m['entries'].values()) == expected_bytes
        for directory in [src, root]:
            assert {p.name for p in directory.iterdir()} == set(m['entries'])
            for filename, e in m['entries'].items():
                assert (directory / filename).stat().st_size == e['bytes']
                assert sha(directory / filename) == e['sha256'], str(directory / filename)
        log = (root / 'native-game.log').read_text()
        guest, validation, close, wait = [read(root / f) for f in [
            'result.json', 'validation.json', 'close-state.json', 'loader-wait.json']]
        assert guest['status'] == 'failed' and validation['frame_status'] == 'FAIL'
        assert validation['callbacks_completed'] == expected_callbacks
        assert validation['last_crc565'] == 'bf2a6bfd' and validation['expected_crc565'] == 'ea733050'
        assert validation['safe_exit'] and validation['cleanup_complete'] and validation['cleanup_status'] == 'complete'
        assert guest['safe_exit'] and guest['active_threads'] == guest['finished_threads'] == 0
        assert guest['GL_error'] == guest['failed_submits'] == 0
        assert close['cleanup_complete'] and close['shutdown_attempts'] == 1 and not close['stopped_boundary']
        assert close['code_and_arenas_retained_until_process_teardown']
        assert wait['state'] == 'complete' and wait['token'] == 0x806 and wait['attempt'] == 1
        assert 60000 < wait['elapsed_ms'] < wait['hard_limit_ms'] == 180000
        assert wait['idle_ms'] < wait['idle_limit_ms'] == 30000 and wait['stop_reason'] == 0
        assert wait['bytes'] == 56134436 and wait['positive_reads'] == 10897
        assert wait['completed_files'] == 79 and wait['completed_IO_ops'] == 53330
        assert wait['active_IO_ops'] == wait['IO_errors'] == 0
        assert wait['cancel_requested'] and not wait['START_seen']
        assert not wait['completed_donor_jobs_available']
        assert 'CANCEL START acknowledged' not in log and 'STOPPED safe main boundary' not in log
        samples = [dict(zip(['elapsed_ms', 'idle_ms', 'bytes', 'files', 'completed_ops', 'active_ops',
                             'stop', 'START', 'HOME', 'APT'], map(int, v))) for v in re.findall(
            r'WAITJSON state=waiting token=806 elapsed=(\d+) idle=(\d+) bytes=(\d+) files=(\d+) '
            r'completed_ops=(\d+) active_ops=(\d+) stop=(\d+) START=(\d+) HOME=(\d+) APT=(\d+)', log)]
        assert len(samples) > 30 and samples[-1]['elapsed_ms'] > 60000
        assert all(b['elapsed_ms'] > a['elapsed_ms'] and b['bytes'] > a['bytes']
                   and b['completed_ops'] > a['completed_ops'] for a, b in zip(samples, samples[1:]))
        assert all(s['stop'] == s['START'] == 0 and s['idle_ms'] < 30000 for s in samples)
        snapshot, before_workers = workers(root, 'before_pause')
        late = next(w for w in before_workers if w['token'] == 0x806)
        assert late['userdata_vtable'][0] - snapshot['image_base'] == 0xb6e6c
        assert not late['done'] and late['kernel_wait'] != 0
        _, loaded = workers(root, 'after_loader_wait')
        late_done = next(w for w in loaded if w['token'] == 0x806)
        assert late_done['done'] == 1 and late_done['kernel_wait'] == 0
        _, quiescent = workers(root, 'after_quiesce')
        assert len(quiescent) == 6 and all(w['done'] == 1 and w['kernel_wait'] == 0 for w in quiescent)
        _, joined = workers(root, 'after_join')
        assert not joined
        io = re.findall(r'RESOURCES JNI=(\d+) stdio=(\d+) appdata=(\d+) IOactive=(\d+) '
                        r'opens/closes=(\d+)/(\d+) dirs=(\d+)', log)
        assert len(io) == 1 and tuple(map(int, io[0])) == (13, 0, 0, 0, expected_io, expected_io, 0)
        assert (root / 'exit.txt').read_text().strip() == 'Workers stopped; GPU drained; returning to HOME'
        drained = re.findall(r'LOADER drained token=806 Run=b6e6c completion=(\d+) pumps=(\d+) ms=(\d+) reason=(\d+)', log)
        assert len(drained) == 1 and drained[0][0:2] == ('0', '0') and drained[0][3] == '0'
        phases = ['CANCEL request attempt=1', 'LOADER drained', 'CALL MainActivity_NativeOnPause',
                  'RETURN MainActivity_NativeOnPause', 'CALL MainActivity_NativeOnStop',
                  'RETURN MainActivity_NativeOnStop', 'JOB 302 completion=0', 'JOB 403 completion=0',
                  'AUDIO 504 completion=0', 'AUDIO 605 completion=0', 'PERIODIC 201 completion=0',
                  'RESOURCES JNI=', 'SHUTDOWN live workers=0', 'PROCESS return']
        assert [log.index(s) for s in phases] == sorted(log.index(s) for s in phases)
        if name == 'run-0001':
            assert validation['failure_reason'] == 'CRC_FAIL: full frame gate not reached'
            assert close['source'] == 'none' and not close['close_pending'] and not close['home_pending']
            assert not wait['home_pending'] and not wait['close_pending']
            assert all(s['HOME'] == s['APT'] == 0 for s in samples)
            assert 'PROCESS return close_pending=0 source=none stopped_boundary=0 cleanup=complete attempts=1' in log
        else:
            assert validation['failure_reason'] == 'HOME requested before validation'
            assert close['source'] == 'APT' and close['close_pending'] and close['home_pending']
            assert wait['home_pending'] and not wait['close_pending']
            assert all(s['HOME'] == 1 and s['APT'] == 0 for s in samples)
            handover = ['SHUTDOWN live workers=0', 'APT HOME handover AFTER quiescence',
                        'APT HOME returned should_close=1', 'APT close pending; cleanup already complete',
                        'PROCESS return close_pending=1 source=APT stopped_boundary=0 cleanup=complete attempts=1']
            assert [log.index(s) for s in handover] == sorted(log.index(s) for s in handover)
        capture = inspect(root)
        assert capture['all_capture_checks'] and len(capture['captures']) == expected_captures
        last = capture['captures'][-1]
        assert last['different_pixels_from_frozen_reference'] == 9231
        same_raw = sha(root / last['raw_file']) == sha(P / 'analysis/hardware/native-game-stable-v0.1.2-user-run-0001/comparison-miss.raw')
        assert same_raw
        captures[name] = capture
        memory = [json.loads(s[8:]) for s in log.splitlines() if s.startswith('MEMJSON ')]
        assert max(m['donor_refusals'] for m in memory) == max(m['runtime_failures'] for m in memory) == 0
        rows[name] = {
            'frame_status': validation['frame_status'], 'frame_failure_reason': validation['failure_reason'],
            'callbacks_completed': expected_callbacks, 'guest_result_frame': guest['frame'],
            'last_crc565': validation['last_crc565'], 'capture_count': expected_captures,
            'all_capture_checks': True, 'different_pixels_from_frozen_reference': 9231,
            'last_saved_raw_byte_identical_to_Stable_v012_hardware': same_raw,
            'late_loader_Run_offset': '0xb6e6c', 'loader_wait': wait,
            'loader_drain_ms': int(drained[0][2]), 'shutdown_delegate_pumps': 0,
            'progress_samples': samples, 'kernel_joins': 6, 'worker_handles_remaining': 0,
            'IO_opens': expected_io, 'IO_closes': expected_io, 'IO_active': 0,
            'guest_safe_exit': True, 'guest_cleanup_complete': True, 'close_state': close,
            'gpu_drain_and_Fini_reached_by_verified_code_path_and_exit_marker': True,
            'peak_normal_allocator_footprint': max(m['normal_allocator_arena'] for m in memory),
            'peak_commit_bytes': max(m['commit'] for m in memory),
            'peak_donor_brk_bytes': max(m['donor_brk_peak'] for m in memory),
            'peak_donor_mmap_pages': max(m['donor_map_peak_pages'] for m in memory),
            'donor_refusals': 0, 'runtime_failures': 0,
        }
    result = {
        'hardware_tested': True, 'executed_by': 'user',
        'overall_result': 'shutdown_PASS_automatic_CRC_FAIL_exit_and_deferred_HOME_X;_frame_FAIL_preserved',
        'expected_CIA_sha256': CIA_SHA, 'installed_CIA_identity_independently_measured': False,
        'automatic_cleanup_first_attempt_passed': True, 'automatic_exit_without_registered_START': True,
        'physical_START_acknowledgement_exercised': False,
        'START_scope': 'User labels first test START; logs show CRC_FAIL then automatic completion, START_seen=false, source=none. Button timing is unknown; no extra test required.',
        'HOME_X_tested': True, 'HOME_X_passed': True,
        'user_confirms_both_exits_and_normal_console_operation': True,
        'hardware_STOPPED_recovery_exercised': False, 'hardware_idle_or_hard_deadline_exercised': False,
        'hardware_shutdown_delegate_pump_exercised': False,
        'hardware_heap_release_independently_measured': False,
        'user_reports_very_slow_loading_animation_shutdown': True,
        'total_startup_animation_or_shutdown_wall_time_measured': False,
        'IO_byte_counters_are_not_physical_SD_bandwidth': True,
        'completed_donor_job_counter_available': False, 'frame_status': 'FAIL',
        'received_files_preserved_SHA256': True, 'received_file_count': 62, 'received_bytes': 5275533,
        'repeat_current_CIA_needed': False, 'ready_for_one_separate_hardware_test': False,
        'new_hardware_run_authorized': False,
        'next_priority': 'Original difficulty screen and controls within Prod124, preserving shutdown guards; measure performance before targeted optimization.',
        'runs': rows,
    }
    return result, captures


def main():
    result, captures = verify()
    (A / 'hardware-result.json').write_text(json.dumps(result, indent=2) + '\n')
    (A / 'capture-audit.json').write_text(json.dumps(captures, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'runs'}, indent=2))


if __name__ == '__main__':
    main()
