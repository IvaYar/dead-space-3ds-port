"""Audit received Close0.1.3 files without modifying originals or old baselines."""
import json
from pathlib import Path
import re
from azahar_resource_store import sha
from analyze_native_game_run import inspect

P = Path(__file__).resolve().parents[1]
A = P/'analysis/native-game-close-v0.1.3-hardware'
H = P/'analysis/hardware/native-game-close-v0.1.3-user-run-0001'


def read(p):
    return json.loads(p.read_text())


def snapshot(stage):
    d = read(H/('threads-'+stage+'.json'))
    return d, [w for w in d['workers'] if w['token']&255]


def main():
    manifest = read(A/'archive-manifest.json')
    source = P/'ds-native-game-v0.1.3/run-0001'
    assert len(manifest['files']) == 34
    assert all(sha(H/n) == e['sha256'] == sha(source/n) for n, e in manifest['files'].items())
    capture_audit = inspect(H)
    assert capture_audit['all_capture_checks'] and len(capture_audit['captures']) == 9
    (A/'capture-audit.json').write_text(json.dumps(capture_audit, indent=2)+'\n')
    log = (H/'native-game.log').read_text()
    guest, validation, close = [read(H/n) for n in ['result.json', 'validation.json', 'close-state.json']]
    progress = [dict(zip(['ms', 'opens', 'reads', 'bytes', 'closes', 'active'], map(int, m))) for m in re.findall(
        r'LOADER progress ms=(\d+) opens=(\d+) reads=(\d+) bytes=(\d+) closes=(\d+) active=(\d+)', log)]
    drained = re.findall(r'LOADER drained token=([0-9a-f]+) Run=([0-9a-f]+) completion=(\d+) pumps=(\d+) ms=(\d+)', log)
    assert len(drained) == 1 and drained[0][:4] == ('806', 'b6e6c', '110', '0')
    assert 60000 <= int(drained[0][4]) < 61000
    assert len(progress) == 12 and all(b['bytes'] > a['bytes'] and b['reads'] > a['reads'] for a, b in zip(progress, progress[1:]))
    timeout, tw = snapshot('after_loader_wait')
    b = timeout['image_base']
    later = next(w for w in tw if w['token'] == 0x806)
    assert later['userdata_vtable'][0] == b+0xb6e6c
    assert later['loader_sync_words'][4] == 0 and later['loader_sync_words'][5]&255 == 0
    assert later['late_flag68'] == 1 and later['done'] == 0 and later['kernel_wait'] != 0
    _, retained = snapshot('stopped_retained')
    assert len(retained) == 6 and all(w['done'] == 0 and w['kernel_wait'] != 0 for w in retained)
    _, retry = snapshot('before_pause')
    rb = next(w for w in retry if w['token'] == 0x806)
    assert rb['done'] == 1 and rb['kernel_wait'] == 0
    _, quiesce = snapshot('after_quiesce')
    assert len(quiesce) == 6 and all(w['done'] == 1 and w['kernel_wait'] == 0 for w in quiesce)
    _, joined = snapshot('after_join')
    assert not joined
    assert close['shutdown_attempts'] == 2 and close['stopped_boundary'] and close['cleanup_complete']
    assert not close['close_pending'] and not close['home_pending'] and close['source'] == 'none'
    assert guest['status'] == 'failed' and validation['frame_status'] == 'FAIL' and validation['cleanup_complete'] and guest['safe_exit']
    assert guest['active_threads'] == guest['finished_threads'] == 0
    assert guest['GL_error'] == guest['failed_submits'] == 0
    assert 'RESOURCES JNI=13 stdio=0 appdata=0 IOactive=0 opens/closes=174/174 dirs=0' in log
    assert 'SHUTDOWN live workers=0' in log and (H/'exit.txt').exists()
    assert 'PROCESS return close_pending=0 source=none stopped_boundary=1 cleanup=complete attempts=2' in log
    phases = ['LOADER drained', 'STOPPED safe main boundary', 'STOPPED retry close_pending=0 home_pending=0',
              'CALL MainActivity_NativeOnPause', 'JOB 302 completion=0', 'AUDIO 504 completion=0',
              'PERIODIC 201 completion=0', 'RESOURCES JNI=', 'SHUTDOWN live workers=0', 'PROCESS return']
    assert [log.index(s) for s in phases] == sorted(log.index(s) for s in phases)
    memory = [json.loads(s[8:]) for s in log.splitlines() if s.startswith('MEMJSON ')]
    trace = re.findall(r'^FRAMECRC frame=(\d+) crc565=([0-9a-f]+)', log, re.M)
    raw_same = sha(H/'comparison-miss.raw') == sha(P/'analysis/hardware/native-game-stable-v0.1.2-user-run-0001/comparison-miss.raw')
    assert raw_same and capture_audit['captures'][-1]['different_pixels_from_frozen_reference'] == 9231
    result = {
        'hardware_tested': True, 'executed_by': 'user',
        'overall_result': 'PARTIAL_frame_FAIL_automatic_cleanup_timeout_manual_START_retry_exit',
        'expected_CIA_sha256': '74f94904ea59e0f1468273dff92f65156e55ece7de82a5a88c40c4ca990fe3e0',
        'installed_CIA_identity_independently_measured': False,
        'frame_status': 'FAIL', 'callbacks_completed': 600, 'last_crc565': validation['last_crc565'],
        'first_final_hardware_CRC_callback': next(int(f) for f, c in trace if c == 'bf2a6bfd'),
        'all_capture_checks': True, 'capture_count': 9, 'different_pixels_from_frozen_reference': 9231,
        'final_raw_byte_identical_to_Stable_v012_hardware': raw_same,
        'automatic_cleanup_first_attempt_passed': False, 'late_loader_first_wait_ms': int(drained[0][4]),
        'late_loader_first_result_errno': 110, 'late_loader_shutdown_pumps': 0,
        'late_loader_at_timeout': {'token': 0x806, 'Run_offset': 0xb6e6c, 'sync_state': 0,
                                   'busy_byte': 0, 'flag68': 1, 'done': False, 'kernel_wait_timeout': True},
        'delegate_pending_deadlock_at_timeout': False,
        'hardware_shutdown_delegate_pump_exercised': False,
        'continuous_IO_progress_observed': True, 'IO_progress_samples': progress,
        'observed_IO_byte_rate_5s_to_60s': (progress[-1]['bytes']-progress[0]['bytes'])/55,
        'byte_rate_is_not_physical_SD_bandwidth': True,
        'loader_elapsed_until_actual_exit_known': False,
        'manual_START_retry_confirmed': True, 'late_loader_kernel_exited_before_retry': True,
        'kernel_joins_after_quiesce': 6, 'worker_handles_remaining': 0,
        'IO_opens': 174, 'IO_closes': 174, 'exit_marker_present': True,
        'guest_cleanup_complete': True, 'guest_safe_exit': True,
        'user_confirms_return_to_HOME_and_normal_console_operation': True,
        'hardware_heap_release_independently_measured': False,
        'HOME_X_tested': False, 'POWER_tested': False,
        'peak_normal_allocator_footprint': max(m['normal_allocator_arena'] for m in memory),
        'peak_commit_bytes': max(m['commit'] for m in memory),
        'peak_donor_brk_bytes': max(m['donor_brk_peak'] for m in memory),
        'peak_donor_mmap_pages': max(m['donor_map_peak_pages'] for m in memory),
        'donor_refusals': max(m['donor_refusals'] for m in memory),
        'runtime_failures': max(m['runtime_failures'] for m in memory),
        'before_pause_snapshot_overwritten_by_retry': True,
        'banner_version_stale_010_while_guest_reports_Close_013': True,
        'received_files_preserved_SHA256': True,
        'repeat_current_CIA_prohibited': True, 'ready_for_one_separate_hardware_test': False,
        'new_hardware_run_authorized': False,
    }
    (A/'hardware-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ['overall_result', 'late_loader_first_wait_ms', 'late_loader_at_timeout',
        'continuous_IO_progress_observed', 'kernel_joins_after_quiesce', 'worker_handles_remaining', 'HOME_X_tested']}, indent=2))


if __name__ == '__main__':
    main()
