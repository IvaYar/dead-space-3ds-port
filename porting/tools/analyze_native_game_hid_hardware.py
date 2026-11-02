"""Verify the received0.1.7 hardware run; never launch or modify the candidate."""
import json
from pathlib import Path
import re
import zlib
from audit_native_game_menu import packed
from azahar_resource_store import sha

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-game-hid-v0.1.7-hardware'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    manifest = read(A / 'archive-manifest.json')
    source, archive = [P / manifest[k] for k in ['source', 'archive']]
    assert len(manifest['files']) == 126
    for root in [source, archive]:
        assert {f.name for f in root.iterdir()} == set(manifest['files'])
        for name, item in manifest['files'].items():
            assert (root / name).stat().st_size == item['bytes'] and sha(root / name) == item['sha256'], name
    log = (archive / 'native-game.log').read_text()

    def rows(tag):
        return [json.loads(line[len(tag) + 1:]) for line in log.splitlines() if line.startswith(tag + ' ')]

    def stamp(pattern):
        found = re.findall(pattern, log, re.M)
        assert len(found) == 1, pattern
        return float(found[0])

    result, validation, close = [read(archive / n) for n in ['result.json', 'validation.json', 'close-state.json']]
    capture, preflight = [read(archive / n) for n in ['hid-capture.json', 'hid-preflight.json']]
    observations = read(A / 'user-observations.json')
    assert result['environment'] == 'native' and result['native_RX_verified']
    assert result['status'] == 'failed' and validation['frame_status'] == 'FAIL'
    assert result['reason'] == 'MENU_ONLY: original confirm delivered; scene continuation bounded'
    assert validation['expected_crc565'] == 'ea733050' and validation['matched_callback'] == 0
    assert result['safe_exit'] and validation['safe_exit'] and validation['cleanup_complete']
    assert validation['callbacks_completed'] == result['frame'] == 6363
    assert result['GL_error'] == result['failed_submits'] == result['active_threads'] == result['finished_threads'] == 0
    assert close['source'] == 'none' and close['shutdown_attempts'] == 1 and close['cleanup_complete']
    assert not close['stopped_boundary'] and not close['home_pending'] and not close['close_pending']
    assert close['code_and_arenas_retained_until_process_teardown']
    assert 'PROCESS return close_pending=0 source=none stopped_boundary=0 cleanup=complete attempts=1' in log
    assert 'Workers stopped; GPU drained; returning to HOME' in (archive / 'exit.txt').read_text()
    assert 'stdio=0 appdata=0 IOactive=0 opens/closes=176/176 dirs=0' in log
    quiet = [w for w in read(archive / 'threads-a1-after_quiesce.json')['workers'] if w['entry']]
    joined = [w for w in read(archive / 'threads-a1-after_join.json')['workers'] if w['entry']]
    assert len(quiet) == 5 and all(w['done'] == 1 and w['kernel_wait'] == 0 for w in quiet) and not joined
    assert capture['collector_joined'] and capture['thread_freed'] and capture['overflow'] == capture['invalid_samples'] == 0
    assert capture['transitions'] == 31 and capture['scans'] == 135940
    assert preflight['raw_buttons_passed'] and preflight['state'] == 'passed_engine_requested'
    assert preflight['seen_mask'] & 0xf3 == 0xf3 and not preflight['engine_loaded']
    assert preflight['overflow'] == preflight['invalid_samples'] == 0
    assert log.index('HID_COLLECTOR freed before donor shutdown') < log.index('STAGE shutdown lifecycle')
    assert 'HID_COLLECTOR join result=00000000' in log
    assert 'HIDMASK DDOWN=00000080 DUP=00000040 CPAD_DOWN=80000000 GENERIC_DOWN=80000080 START=00000008' in log
    raw = {int(v[1]): {'ms': float(v[0]), 'stage': v[2], 'epoch': int(v[3]),
                      'held': int(v[4], 16), 'down': int(v[5], 16), 'up': int(v[6], 16)}
           for v in re.findall(r'^HIDRAW ms=([0-9.]+) id=(\d+) stage=(\w+) epoch=(\d+) index=\d+ held=([0-9a-f]+) down=([0-9a-f]+) up=([0-9a-f]+)', log, re.M)}
    assert set(raw) == set(range(1, 32))
    assert any(e['stage'] == 'preflight' and e['down'] == 0x80 for e in raw.values())
    assert 'stage=preflight down=00000080 held=00000080 raw=00000080' in log
    maps = re.findall(r'^HIDMAP ms=([0-9.]+) frame=(\d+) id=(\d+) raw_to_pointer=(\d+),(\d+) target_selection=(\d+)', log, re.M)
    hosts = {int(v[1]): {'ms': float(v[0]), 'SDKdown': int(v[2], 16), 'SDKheld': int(v[3], 16), 'queue_age_ms': float(v[4])}
             for v in re.findall(r'^HIDHOST ms=([0-9.]+) frame=\d+ id=(\d+) ready=1 .*SDKdown=([0-9a-f]+) SDKheld=([0-9a-f]+) age_ms=([0-9.]+)', log, re.M)}
    acks = {int(v[2]): {'ms': float(v[0]), 'frame': int(v[1]), 'phase': int(v[3]), 'closing': int(v[4]), 'selection': int(v[5])}
            for v in re.findall(r'^HIDACK ms=([0-9.]+) frame=(\d+) id=(\d+) phase=(\d+) closing=(\d+) selection=(\d+)', log, re.M)}
    assert [int(v[2]) for v in maps] == [22, 24, 26, 30]
    assert [int(v[5]) for v in maps] == [2, 1, 2, 0]
    chains = []
    for ms, frame, sid, x, y, target in maps:
        eid = int(sid); r = raw[eid]; ack = acks[eid]; host = hosts[eid]
        assert r['stage'] == 'game' and r['epoch'] == 2 and r['down'] in [0x80, 0x40, 1]
        assert r['ms'] <= host['ms'] <= float(ms) <= ack['ms']
        assert ack['selection'] == int(target)
        for event in ['0006000c', '0008000c']:
            enter = stamp(rf'^HIDCOMPAT ms=([0-9.]+) .*id={eid} event={event} module=1000 .* ENTER$')
            returned = stamp(rf'^HIDORIGINAL ms=([0-9.]+) .*id={eid} event={event} RETURN .*')
            assert float(ms) <= enter <= returned <= ack['ms']
        if int(target):
            assert ack['phase'] == 2 and ack['closing'] == 0
        else:
            assert ack['phase'] == 3 and ack['closing'] == 1 and int(frame) + 2 == result['frame']
        assert raw[eid + 1]['up'] == r['down'] and raw[eid + 1]['down'] == 0
        chains.append({'event_id': eid, 'raw_down': r['down'], 'raw_ms': r['ms'], 'pointer': [int(x), int(y)],
                       'pointer_frame': int(frame), 'target_selection': int(target), 'ACK': ack, **host,
                       'raw_to_ACK_ms': round(ack['ms'] - r['ms'], 3),
                       'raw_hold_ms': round(raw[eid + 1]['ms'] - r['ms'], 3)})
    assert all(c['SDKdown'] == 0 for c in chains)
    assert chains[-1]['SDKheld'] == 0  # Actual physical A captured despite both main SDK snapshots0.
    assert 'CONTROL frame=6361 button=A pointer=284,225 original_selection=2' in log
    assert 'B=1 module=600 key=4' in log and 'B=0 module=600 key=4' in log
    assert re.search(r'^HIDORIGINAL .*id=28 BACK=1 RETURN$', log, re.M)
    assert re.search(r'^HIDORIGINAL .*id=29 BACK=0 RETURN$', log, re.M)
    assert 'MENU_ONLY original confirm callback=6361 tail_complete=6363' in log
    assert 'MENU_CONFIRM_STATE frame=6363' in log and 'phase=0 transition=0 closing=1 selection=0 ready=0' in log
    assert 'TEST HID_STALL' not in log and 'APT HOME handover' not in log
    captures, inputs = rows('CAPTUREJSON'), rows('INPUTJSON')
    assert len(captures) == len(inputs) == 55
    for c, i in zip(captures, inputs):
        data = (archive / c['file']).read_bytes()
        assert len(data) == 288000 and c['format'] == 'BGR8_CTR' and c['column_stride'] == 720
        assert c['raw_crc_a'] == c['raw_crc_b'] == f'{zlib.crc32(data):08x}'
        assert c['crc565_a'] == c['crc565_b'] == f'{zlib.crc32(packed(data)):08x}'
        assert c['frame'] == i['frame'] and not i['capture_truncated']
        assert (archive / i['file']).stat().st_size == i['command_bytes'] > 0
    assert captures[-1]['crc565_a'] == validation['last_crc565'] == '22d19b9c'
    initial_normal = [c for c in captures if 4200 <= c['frame'] <= 4800]
    assert len(initial_normal) == 6 and all(c['crc565_a'] == '95b893de' for c in initial_normal)
    old = P / 'analysis/hardware/native-game-controls-v0.1.6-user-run-0001'
    assert all((archive / c['file']).read_bytes() == (old / 'explore-4200.raw').read_bytes() for c in initial_normal)
    easy = [c for c in captures if c['crc565_a'] == '799656aa']
    assert easy and len({sha(archive / c['file']) for c in easy}) == 1
    assert next(c for c in captures if c['frame'] == 5400)['crc565_a'] == 'f49fe214'
    callbacks, windows = rows('CALLBACKJSON'), rows('PERFJSON')
    warm = max(callbacks, key=lambda c: c['ms'])
    assert warm['frame'] == 4082 and warm['ops'][0]['calls'] == 1146
    assert warm['page_saves'] == 201 and warm['page_loads'] == 166
    assert warm['ops'][11]['calls'] == 367 and warm['ops'][11]['bytes'] == 1069965312
    assert warm['resource_bytes'] == warm['resource_reads'] == warm['IO_completions'] == 0
    previous = read(P / 'analysis/native-game-controls-v0.1.6-hardware/hardware-result.json')
    pattern = r'^TEXALLOC frame=(\d+) w=(\d+) h=(\d+) linear=(\d+) ok=(\d+)'
    alloc = lambda text, frame: [v[1:] for v in re.findall(pattern, text, re.M) if int(v[0]) == frame]
    assert len(alloc(log, 4082)) == 129 and alloc(log, 4082) == alloc((old / 'native-game.log').read_text(), 4132)
    steady = [w for w in windows if w['frame'] >= 4320]
    count = sum(w['callbacks'] for w in steady)
    memory, peaks = rows('MEMJSON'), rows('PEAKJSON')
    assert all(m['query_result'] == 0 and m['commit'] <= m['limit'] == 124 * 1024 * 1024 for m in memory)
    assert not any(m['donor_refusals'] or m['runtime_failures'] for m in memory)
    assert max(m['normal_footprint'] for m in peaks) <= 20 * 1024 * 1024
    assert max(m['linear_used'] for m in peaks) <= 100 * 1024 * 1024
    request_ms = stamp(r'^HIDSESSION original_engine_request ms=([0-9.]+)$')
    init_ms = stamp(r'^HIDSESSION engine_init_return ms=([0-9.]+)$')
    ready_ms = stamp(r'^HID_BARRIER ms=([0-9.]+) ready=1 .*')
    before_gate = read(A / 'software-release-gate-before-hardware.json')
    assert sha(P.parent / before_gate['CIA']['path']) == before_gate['CIA']['sha256']
    build = P / '3ds/build-native-game-v0.1.7-release'
    assert before_gate['source_sha256'] == sha(build / 'native-game-memory.c') == sha(P / 'tests/native_game_hid.c')
    for name, digest in before_gate['headers_sha256'].items():
        assert sha(build / name) == sha(P / 'tests' / name) == digest
    protected = read(P / 'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for name, digest in protected.items():
        assert sha(P / name) == digest, name
    audit = {
        'hardware_tested': True, 'archive_verified': True, 'archived_files': 126,
        'archived_bytes': sum(i['bytes'] for i in manifest['files'].values()),
        'CIA_candidate': before_gate['CIA'], 'installed_CIA_hash_independently_attested': False,
        'raw_preflight': preflight, 'raw_capture': capture,
        'original_menu_navigation_confirmed': True, 'Easy_confirmed_before_A': True,
        'original_input_chains': chains, 'B_original_down_up_delivered': True,
        'B_visible_return': False, 'original_confirmation_phase3_closing1_ACK': acks[30],
        'safe_exit': True, 'exit_reason': result['reason'], 'shutdown_attempts': 1,
        'remaining_native_workers_kernel_completed': len(quiet), 'worker_handles_remaining': 0,
        'HID_collector_joined_and_freed_before_shutdown': True, 'balanced_IO': [176, 176],
        'GL_error': 0, 'failed_submits': 0, 'HOME_X_tested_this_run': False,
        'user_A_to_HOME_seconds_approx': observations['A_to_HOME_seconds_approx'],
        'hardware_heap_release_independently_measured': False,
        'frame_status': 'FAIL', 'baseline_crc_unchanged': 'ea733050',
        'independently_verified_raw_readback_pairs': len(captures), 'complete_saved_GX_traces': len(inputs),
        'initial_Normal_byte_identical_to_hardware_016_frames': [c['frame'] for c in initial_normal],
        'Easy_stable_saved_frames': [c['frame'] for c in easy],
        'Normal_after_UP_saved_frame_crc': {'frame': 5400, 'crc565': 'f49fe214'},
        'historical_016_input_loss_exact_cause_proven': False,
        'correction_effective_on_received_hardware_run': True,
        'slowest_original_draw_callback': warm, 'same_129_texture_allocations_as_hardware_016': True,
        'timing': {
            'preflight_engine_request_ms': request_ms, 'original_engine_init_return_ms': init_ms,
            'first_menu_ready_ms': ready_ms,
            'engine_request_to_init_return_ms': round(init_ms - request_ms, 3),
            'engine_request_to_menu_ready_ms': round(ready_ms - request_ms, 3),
            'steady_menu_FPS_including_diagnostics': 1000 * count / sum(w['elapsed_ms'] for w in steady),
            'steady_ms_per_callback': {k: sum(w[k] for w in steady) / count for k in
                ['callback_ms', 'present_ms', 'diagnostic_ms', 'gpu_queue_wait_ms', 'vblank_wait_ms']},
            'previous_hardware_slowest_callback_ms': previous['slowest_original_draw_callback']['ms'],
            'limits': 'Tick timestamps include trace IO; ready is a state-admission timestamp, not a camera timer. Nested timing overlaps. A-to-HOME is user estimate; no final process timestamp. No loading optimization this stage.'},
        'memory': {'normal_peak_footprint': max(m['normal_footprint'] for m in peaks),
                   'linear_peak_used': max(m['linear_used'] for m in peaks),
                   'linear_transient_headroom': 100 * 1024 * 1024 - max(m['linear_used'] for m in peaks),
                   'kernel_peak_commit': max(m['commit'] for m in memory),
                   'runtime_allocation_failures': 0, 'donor_allocation_refusals': 0},
        'protected_files_verified': len(protected),
        'gameplay_started': False, 'repeat_current_CIA_needed': False,
    }
    (A / 'hardware-result.json').write_text(json.dumps(audit, indent=2) + '\n')
    gate = dict(before_gate)
    gate['known_limits'] = [s for s in gate['known_limits'] if not s.startswith('No new physical hardware evidence')]
    gate['known_limits'].append('One received hardware run confirms navigation and bounded A exit; gameplay and HOME/X were not tested in that run.')
    gate.update({'ready_for_one_separate_hardware_test': False, 'hardware_tested': True,
                 'hardware_run_authorized': False, 'hardware_menu_confirmed': True,
                 'hardware_raw_Dpad_confirmed': True, 'hardware_navigation_confirmed': True,
                 'hardware_original_A_confirmation_ACK': True, 'hardware_safe_bounded_A_exit_confirmed': True,
                 'hardware_HOME_X_tested_this_run': False, 'repeat_current_CIA_needed': False,
                 'hardware_loading_profile_measured': True,
                 'hardware_loading_speedup_measured_this_stage': False,
                 'hardware_result': 'porting/analysis/native-game-hid-v0.1.7-hardware/hardware-result.json'})
    (P / 'analysis/native-game-hid-v0.1.7/release-gate.json').write_text(json.dumps(gate, indent=2) + '\n')
    print(json.dumps({'archive_verified': True, 'files': 126, 'navigation_and_A_confirmed': True,
                      'safe_exit': True, 'engine_to_ready_ms': audit['timing']['engine_request_to_menu_ready_ms'],
                      'slowest_callback_ms': warm['ms'], 'FPS': audit['timing']['steady_menu_FPS_including_diagnostics']}))


if __name__ == '__main__':
    main()
