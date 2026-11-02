"""Audit raw HID -> queued host event -> original callbacks -> menu ACK."""
import argparse
import json
from pathlib import Path
import re
import zlib
from azahar_resource_store import sha, verify_dataset, STORE
from build_native_game_target_init import RUNTIME
from audit_native_game_menu import packed

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-game-hid-v0.1.7'
OLD = P / '3ds/build-native-game-v0.1.6-final2'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def tagged(log, tag):
    return [json.loads(l[len(tag) + 1:]) for l in log.splitlines() if l.startswith(tag + ' ')]


def audit_run(revision, attempt):
    root = P / ('analysis/azahar-native-menu-v0.1.7-' + revision + '-' + attempt)
    build = P / ('3ds/build-native-game-v0.1.7-' + revision)
    result = read(root / 'result.json'); m = read(build / 'build-manifest.json')
    assert result['safety_passed'] and result['collector_joined']
    assert result['CXI_sha256'] == sha(build / 'native-game.cxi')
    for field in ['outputs_sha256', 'headers_sha256', 'runtime_sha256']:
        for name, digest in m[field].items():
            assert sha(build / name) == digest, name
    for name in RUNTIME:
        assert sha(build / name) == sha(OLD / name), name
    src = (build / 'native-game-memory.c').read_text(); old_src = (OLD / 'native-game-memory.c').read_text()
    marker = 'static u32 diagnostic_words(u32 address,u32 out[24]){'
    assert src[src.index(marker):src.index('int main(void)')] == old_src[old_src.index(marker):old_src.index('int main(void)')]
    assert sha(build / 'native_menu_engine_state.h') == sha(OLD / 'native_menu_engine_state.h')
    assert sha(build / 'native_menu_page_crc.h') == sha(OLD / 'native_menu_page_crc.h')
    assert m['fast_page_crc32'] and not m['scene_probe']
    for name in ['native_menu_hid_controls.h', 'native_hid_queue.h', 'native_hid_collector.h']:
        assert '7296717d' not in (build / name).read_text()
    collector = (build / 'native_hid_collector.h').read_text()
    body = collector[collector.index('static void hid_collector(void *arg)'):collector.index('static int hid_collector_start')]
    assert all(token not in body for token in ['hidScanInput(', 'hidKeysDown(', 'hidKeysHeld(', 'report(', 'menu_engine_state(', 'fopen('])
    assert 'LightLock_Lock(&hid_fifo_lock)' in body and 'LightLock_Unlock(&hid_fifo_lock)' in body
    assert 'budget<HID_FIFO_CAPACITY' in collector  # preflight draining is bounded too.
    run = root / 'Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001'
    log = (run / 'native-game.log').read_text()
    capture = read(run / 'hid-capture.json'); preflight = read(run / 'hid-preflight.json')
    assert capture['collector_joined'] and capture['thread_freed'] and capture['overflow'] == 0
    assert capture['scans'] > 500 and capture['period_ms'] == 4 and capture['capacity'] == 64
    assert 'HID_COLLECTOR join result=00000000' in log
    assert 'HIDMASK DDOWN=00000080 DUP=00000040 CPAD_DOWN=80000000 GENERIC_DOWN=80000080 START=00000008' in log
    raw_rows = re.findall(r'^HIDRAW ms=([0-9.]+) id=(\d+) stage=(\w+) epoch=(\d+) index=(\d+) held=([0-9a-f]+) down=([0-9a-f]+) up=([0-9a-f]+)', log, re.M)
    raw = {int(v[1]): {'ms': float(v[0]), 'stage': v[2], 'held': int(v[5], 16), 'down': int(v[6], 16), 'up': int(v[7], 16)} for v in raw_rows}
    assert len(raw) == len(raw_rows)
    summary = {'safety_passed': True, 'CXI_sha256': result['CXI_sha256'],
               'source_sha256': m['source_sha256'], 'headers_sha256': m['headers_sha256'],
               'GPU_runtime_and_shader_unchanged': True, 'donor_shutdown_functions_unchanged': True,
               'raw_readonly_observer': True, 'preflight': preflight, 'capture': capture,
               'host_seconds': result['elapsed_host_seconds'], 'raw_transition_count_logged': len(raw),
               'private_result_sha256': sha(root / 'result.json')}
    if result.get('raw_only'):
        assert not (run / 'validation.json').exists() and 'STAGE preflight' not in log
        assert 'HID_PREFLIGHT START exit engine_loaded=0' in log
        assert preflight['state'] == 'START_exit' and not preflight['engine_loaded']
        if attempt == 'missing':
            assert not preflight['raw_buttons_passed'] and not (preflight['seen_mask'] & 0x80)
            assert 'HID_PREFLIGHT X blocked missing=00000080' in log
            summary['missing_Dpad_blocks_engine_without_wait'] = True
        else:
            assert preflight['raw_buttons_passed'] and preflight['seen_mask'] & 0xf3 == 0xf3
            assert preflight['seen_mask'] & 0xc0000000 == 0xc0000000
            summary['raw_Dpad_AB_START_and_CirclePad_verified'] = True
        summary['engine_loaded'] = False
        return summary
    assert result['validation']['frame_status'] == 'FAIL' and result['validation']['expected_crc565'] == 'ea733050'
    assert result['validation']['cleanup_complete'] and result['validation']['safe_exit']
    assert result['guest_result']['GL_error'] == result['guest_result']['failed_submits'] == 0
    assert not result['invalid_memory_accesses'] and result['files_balanced']
    assert result['kernel_joins'] == result['handles_at_shutdown'] >= 5 and result['worker_handles_remaining'] == 0
    assert log.index('HID_COLLECTOR freed before donor shutdown') < log.index('STAGE shutdown lifecycle')
    summary.update({'engine_loaded': True, 'frame_status': 'FAIL', 'callbacks': result['validation']['callbacks_completed'],
                    'kernel_joins': result['kernel_joins'], 'close_state': result['close_state']})
    quiet = read(run / 'threads-a1-after_quiesce.json')['workers']
    assert all(w['done'] == 1 and w['kernel_wait'] == 0 for w in quiet if w['entry'])
    assert not [w for w in read(run / 'threads-a1-after_join.json')['workers'] if w['entry']]
    caps, inputs = tagged(log, 'CAPTUREJSON'), tagged(log, 'INPUTJSON')
    assert len(caps) == len(inputs) > 0
    partial = []
    callbacks = tagged(log, 'CALLBACKJSON'); warm = max(callbacks, key=lambda v: v['ms'])
    for c, i in zip(caps, inputs):
        data = (run / c['file']).read_bytes()
        assert len(data) == 288000 and c['raw_crc_a'] == c['raw_crc_b'] == f'{zlib.crc32(data):08x}'
        assert c['crc565_a'] == c['crc565_b'] == f'{zlib.crc32(packed(data)):08x}'
        assert c['frame'] == i['frame'] and (run / i['file']).stat().st_size == i['command_bytes'] > 0
        if i['capture_truncated']:
            assert c['frame'] == warm['frame'] and i['draw_input_count'] >= 1000
            partial.append(c['frame'])
    memory, peaks = tagged(log, 'MEMJSON'), tagged(log, 'PEAKJSON')
    assert all(v['query_result'] == 0 and v['commit'] <= v['limit'] == 124 * 1024 * 1024 for v in memory)
    assert not any(v['runtime_failures'] or v['donor_refusals'] for v in memory)
    assert max(v['normal_footprint'] for v in peaks) <= 20 * 1024 * 1024
    assert max(v['linear_used'] for v in peaks) <= 100 * 1024 * 1024
    windows = tagged(log, 'PERFJSON'); steady = [w for w in windows if w['frame'] >= 3120]
    count = sum(w['callbacks'] for w in steady)
    summary.update({'capture_count': len(caps), 'partial_initial_GX': partial,
                    'normal_peak_footprint': max(v['normal_footprint'] for v in peaks),
                    'linear_peak_used': max(v['linear_used'] for v in peaks),
                    'kernel_peak_commit': max(v['commit'] for v in memory),
                    'slowest_callback': warm,
                    'steady_FPS_including_diagnostics': 1000 * count / sum(w['elapsed_ms'] for w in steady) if count else None})
    maps = re.findall(r'^HIDMAP ms=([0-9.]+) frame=(\d+) id=(\d+) raw_to_pointer=(\d+),(\d+) target_selection=(\d+)', log, re.M)
    acks = {int(v[2]): {'ms': float(v[0]), 'frame': int(v[1]), 'selection': int(v[3])} for v in re.findall(r'^HIDACK ms=([0-9.]+) frame=(\d+) id=(\d+) phase=\d+ closing=\d+ selection=(\d+)', log, re.M)}
    host = {int(v[1]): {'age_ms': float(v[6]), 'SDKdown': int(v[4], 16), 'SDKheld': int(v[5], 16)} for v in re.findall(r'^HIDHOST .*frame=(\d+) id=(\d+) ready=1 raw=([0-9a-f]+) mapped=([0-9a-f]+) SDKdown=([0-9a-f]+) SDKheld=([0-9a-f]+) age_ms=([0-9.]+)', log, re.M)}
    chains = []
    for ms, frame, sid, x, y, selection in maps:
        eid = int(sid); target = int(selection)
        assert eid in raw and eid in host and eid in acks
        assert float(ms) >= raw[eid]['ms'] and acks[eid]['ms'] >= float(ms)
        assert acks[eid]['selection'] == target
        for event in ['0006000c', '0008000c']:
            assert re.search(rf'^HIDCOMPAT .*id={eid} event={event} module=1000 .* ENTER$', log, re.M)
            assert re.search(rf'^HIDORIGINAL .*id={eid} event={event} RETURN', log, re.M)
        chains.append({'event_id': eid, 'raw_down': raw[eid]['down'], 'pointer': [int(x), int(y)],
                       'target_selection': target, 'ACK': acks[eid], **host[eid]})
    if maps:
        assert [int(v[5]) for v in maps] == [2, 1, 2, 0]
        assert len(set(int(v[2]) for v in maps)) == len(maps)  # No held-key duplicates.
        assert 'B=1 module=600 key=4' in log and 'B=0 module=600 key=4' in log
        assert re.search(r'^MENU_CONFIRM_STATE .*phase=3 transition=0 closing=1 selection=0 ready=0$', log, re.M)
        assert 'reason=selected_row_or_no_edge' in log
        assert any(c['crc565_a'] == '0ded835d' for c in caps) and any(c['crc565_a'] == '223b5e75' for c in caps)
        assert any(c['crc565_a'] != 'ea733050' for c in caps)
        summary.update({'original_navigation_and_confirm_ACK_verified': True, 'frame_mismatch_does_not_block_input': True,
                        'BACK_down_up_returned': True, 'original_first_menu_BACK_action': 'Ignored by original engine, unchanged.',
                        'chains': chains})
        if result['host_pulses']:
            assert all(c['SDKdown'] == c['SDKheld'] == 0 for c in chains)
            summary['short_pulses_recovered_while_SDK_main_snapshots_zero'] = True
        if m['test_input_stall_frame']:
            assert chains[0]['age_ms'] >= 1900 and 'TEST HID_STALL frame=3361' in log
            summary['two_second_main_stall_pulse_recovered'] = True
    if m['test_HOME_callback']:
        assert result['close_state']['source'] == 'APT' and result['close_state']['home_pending'] and result['close_state']['close_pending']
        assert 'APT HOME handover AFTER quiescence' in log and 'APT HOME returned should_close=1' in log
        summary['deferred_HOME_verified'] = True
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--runs', required=True)
    args = ap.parse_args(); pairs = [n.split(':') for n in args.runs.split(',')]
    assert all(len(p) == 2 and all(v.isalnum() for v in p) for p in pairs)
    rows = {':'.join(p): audit_run(*p) for p in pairs}
    protected = read(P / 'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for name, digest in protected.items(): assert sha(P / name) == digest, name
    dataset = verify_dataset(STORE / 'datasets/a46655efb24fab59c7649322986eea2ae0a5827454bca4c5e71be3d13818ceef')
    master = P / 'private/native-game-v0.1.0-sd/3ds/deadspace'
    for e in dataset['files']: assert sha(master / e['path']) == e['sha256']
    A.mkdir(exist_ok=True)
    result = {'audited': True, 'runs': rows, 'protected_files_verified': len(protected),
              'resource_files_verified': len(dataset['files']), 'hardware_tested': False,
              'hardware_016_input_loss_exact_cause_established': False, 'baseline_crc': 'ea733050',
              'in_game_frame_status': 'FAIL', 'raw_only_does_not_claim_frame_validation': True}
    (A / 'software-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    hardware_path = P / 'analysis/native-game-controls-v0.1.6-hardware/hardware-result.json'
    hardware = read(hardware_path)
    performance = {
        'new_hardware_tested': False, 'loading_optimization_this_stage': False,
        'timing_units': 'Guest SDK ticks converted to milliseconds; not accelerated host wall time.',
        'operation_ids': ['glDrawElements', 'glDrawArrays', 'glTexImage2D', 'glTexSubImage2D',
                          'glClear', 'glFinish', 'glReadPixels', 'ds34_begin_draw',
                          'ds34_end_draw', 'ds15_resident', 'texture_copy', 'page_CRC32'],
        'hardware_016_source_sha256': sha(hardware_path),
        'hardware_016_user_start_to_menu_seconds': hardware['user_menu_wait_seconds'],
        'hardware_016_slowest_callback': hardware['slowest_original_draw_callback'],
        'hardware_016_timing': hardware['timing'],
        'software_017': {name: {key: row[key] for key in [
            'slowest_callback', 'steady_FPS_including_diagnostics', 'capture',
            'normal_peak_footprint', 'linear_peak_used', 'kernel_peak_commit']}
            for name, row in rows.items() if row['engine_loaded']},
        'interpretation': [
            'Hardware draw4132 takes297416.915ms: 1146draws,201page saves,166page loads,367CRC operations over1069965312bytes.',
            'Measured residency/paging and CPU preparation dominate; original loader IO0 does not mean texture-page IO0.',
            'Timings are nested and must not be added. Subtracting CRC is not an independent pure-IO measurement.',
            'Software reproduces the expensive original font/menu preparation; callback numbers vary with scheduling.',
            'No claim of hardware speedup. Stable software and previous hardware FPS are different environments.',
            'Collector4ms is nominal: raw observation has scheduling gaps. Queue retains observed transitions only.'],
    }
    (A / 'performance.json').write_text(json.dumps(performance, indent=2) + '\n')
    experiments = {
        'final_frozen_runs': list(rows), 'completed_process_exits': len(rows),
        'hardware_runs_this_stage': 0,
        'normal_candidate_revision': 'release',
        'fixture_revisions_not_for_CIA': {'releasestall': '2s main-boundary sleep',
                                         'releasehome': 'Deferred HOME/X fixture'},
        'software_cases': {
            'raw': 'D-pad U/D/L/R,A,B,START and separate CirclePad raw flags; no original engine load.',
            'missing': 'Missing physical D-pad DOWN blocks X launch; START exits without game loading.',
            'pulse': '2-host-frame pulses; original Normal/Easy navigation and A confirm while main SDK masks0.',
            'hold': 'Held directions produce one logical action, with explicit releases.',
            'circle': 'Real emulator analog HID: CirclePad down/up and physical D-pad down via same original pipeline.',
            'early': 'START during original startup, before menu.',
            'stall': 'Short DOWN retained2054.936ms across2s main-boundary pause, original Easy ACK.',
            'home': 'HOME request, quiesce then SDK HOME handover/X-close; no unsafe resource return.'},
        'drafts': 'Earlier CXI-only drafts and evidence preserved privately; final claims use release/releasestall/releasehome only.',
        'old_hardware_loss_conclusion': 'Not observed before host-to-Android dispatch; no raw trace in0.1.6, exact physical cause remains unknown.',
        'original_first_menu_BACK': 'Down/up delivered; first LayerDifficulty deliberately ignores BACK. No forced return.',
        'gameplay': 'Original confirm plus2 callbacks, then cooperative exit. No controllable Isaac scene claimed.',
    }
    (A / 'experiments.json').write_text(json.dumps(experiments, indent=2) + '\n')
    print(json.dumps({'audited': True, 'runs': list(rows), 'protected': len(protected)}))


if __name__ == '__main__':main()
