"""Audit original-state controls and lossless page CRC optimization evidence."""
import argparse
import json
from pathlib import Path
import re
import zlib
from azahar_resource_store import sha, verify_dataset, STORE
from build_native_game_target_init import RUNTIME
from audit_native_game_menu import packed

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-game-controls-v0.1.6'
OLD = P / '3ds/build-native-game-v0.1.5-r14'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(log, tag):
    return [json.loads(l[len(tag) + 1:]) for l in log.splitlines() if l.startswith(tag + ' ')]


def audit_run(revision, attempt):
    root = P / ('analysis/azahar-native-menu-v0.1.6-' + revision + '-' + attempt)
    result = read(root / 'result.json')
    build = P / ('3ds/build-native-game-v0.1.6-' + revision)
    m = read(build / 'build-manifest.json')
    assert result['safety_passed'] and not result['invalid_memory_accesses']
    assert result['files_balanced'] and result['worker_handles_remaining'] == 0
    assert result['kernel_joins'] == result['handles_at_shutdown'] >= 5
    assert result['guest_result']['GL_error'] == result['guest_result']['failed_submits'] == 0
    assert result['validation']['frame_status'] == 'FAIL'
    assert result['validation']['expected_crc565'] == 'ea733050'
    assert result['validation']['safe_exit'] and result['validation']['cleanup_complete']
    assert result['CXI_sha256'] == sha(build / 'native-game.cxi')
    for key in ['outputs_sha256', 'headers_sha256', 'runtime_sha256']:
        for name, digest in m[key].items():
            assert sha(build / name) == digest, name
    for name in RUNTIME:
        assert sha(build / name) == sha(OLD / name), name
    source = (build / 'native-game-memory.c').read_text()
    old_source = (OLD / 'native-game-memory.c').read_text()
    marker = 'static u32 diagnostic_words(u32 address,u32 out[24]){'
    assert source[source.index(marker):] == old_source[old_source.index(marker):].replace(
        'ds-native-game-v0.1.5', 'ds-native-game-v0.1.6').replace(
        'DS Original Menu 0.1.5', 'DS Menu Controls 0.1.6')
    for name in ['native_menu_engine_state.h', 'native_menu_controls.h']:
        text = (build / name).read_text()
        assert 'crc' not in text.lower() and '7296717d' not in text
    original_page = P / '3ds/source/ds27_pages_3ds.c'
    assert sha(original_page) == m['original_page_source_sha256']
    if m['fast_page_crc32']:
        expected = original_page.read_text().replace('#include "ds27_pages.h"',
            '#include "ds27_pages.h"\nuint32_t menu_page_crc32(const uint8_t *,uint32_t);')
        expected = expected.replace('ds_crc32(', 'menu_page_crc32(')
        assert (build / original_page.name).read_text() == expected
        assert sha(build / original_page.name) == m['page_source_sha256']
    run = root / 'Azahar/sdmc/3ds/ds-native-game-v0.1.6/run-0001'
    log = (run / 'native-game.log').read_text()
    quiet = read(run / 'threads-a1-after_quiesce.json')['workers']
    joined = read(run / 'threads-a1-after_join.json')['workers']
    quiet = [w for w in quiet if w['entry']]
    assert len(quiet) == result['kernel_joins'] and all(w['done'] == 1 and w['kernel_wait'] == 0 for w in quiet)
    assert not [w for w in joined if w['entry']]
    captures, inputs = lines(log, 'CAPTUREJSON'), lines(log, 'INPUTJSON')
    assert len(captures) == len(inputs) > 0
    partial = []
    callback = lines(log, 'CALLBACKJSON')
    warm = max(callback, key=lambda c: c['ms'])
    for c, i in zip(captures, inputs):
        raw = (run / c['file']).read_bytes()
        assert len(raw) == 288000
        assert c['raw_crc_a'] == c['raw_crc_b'] == f'{zlib.crc32(raw):08x}'
        assert c['crc565_a'] == c['crc565_b'] == f'{zlib.crc32(packed(raw)):08x}'
        assert c['frame'] == i['frame'] and (run / i['file']).stat().st_size == i['command_bytes'] > 0
        if i['capture_truncated']:
            assert c['frame'] == warm['frame'] and i['draw_input_count'] >= 1000
            partial.append(c['frame'])
    memories, peaks = lines(log, 'MEMJSON'), lines(log, 'PEAKJSON')
    assert all(v['query_result'] == 0 and v['commit'] <= v['limit'] == 124 * 1024 * 1024 for v in memories)
    assert not any(v['runtime_failures'] or v['donor_refusals'] for v in memories)
    assert max(v['normal_footprint'] for v in peaks) <= 20 * 1024 * 1024
    assert max(v['linear_used'] for v in peaks) <= 100 * 1024 * 1024
    windows = lines(log, 'PERFJSON')
    steady = [w for w in windows if w['frame'] >= 3120]
    count = sum(w['callbacks'] for w in steady)
    summary = {
        'safety_passed': True, 'callbacks': result['validation']['callbacks_completed'],
        'CXI_sha256': result['CXI_sha256'], 'private_result_sha256': sha(root / 'result.json'),
        'source_sha256': m['source_sha256'], 'headers_sha256': m['headers_sha256'],
        'CPU_percent': result['cpu_percent'], 'host_seconds': result['elapsed_host_seconds'],
        'frame_status': 'FAIL', 'kernel_completed_workers': len(quiet),
        'worker_handles_remaining': 0, 'IO_balanced': True, 'GL_error': 0,
        'capture_count': len(captures), 'partial_initial_GX_frames': partial,
        'GPU_runtime_and_shader_identical_to_015': True, 'shutdown_source_unchanged': True,
        'normal_peak_footprint': max(v['normal_footprint'] for v in peaks),
        'linear_peak_used': max(v['linear_used'] for v in peaks),
        'kernel_peak_commit': max(v['commit'] for v in memories),
        'warm_callback': warm, 'close_state': result['close_state'],
        'steady_FPS_including_diagnostics': 1000 * count / sum(w['elapsed_ms'] for w in steady) if count else None,
        'steady_ms': {k: sum(w[k] for w in steady) / count for k in
                     ['callback_ms', 'present_ms', 'diagnostic_ms', 'gpu_queue_wait_ms', 'vblank_wait_ms']} if count else {},
        'controls': re.findall(r'^CONTROL .*', log, re.M),
        'original_BACK_return_from_initial_menu': False,
    }
    confirm = re.search(r'MENU_ONLY original confirm callback=(\d+) tail_complete=(\d+)', log)
    if confirm:
        a, tail = map(int, confirm.groups())
        assert tail == a + 2
        summary['original_confirm_frame'] = a
        summary['confirm_state_after_tail'] = re.findall(r'^MENU_CONFIRM_STATE .*', log, re.M)
    if 'button=UP' in log and 'button=DOWN' in log:
        frames = {c['frame']: c for c in captures}
        for f, selection in [(3361, 1), (3601, 2), (3841, 1), (4321, 2)]:
            assert re.search(rf'^MENUSTATE frame={f} .*ready=1 selection={selection} ', log, re.M)
        assert 'HID_REJECT frame=3121 mask=00000040 reason=selected_row_or_no_edge' in log
        assert frames[3360]['crc565_a'] != 'ea733050'
        for f, crc in [(3360, '7296717d'), (3480, '0ded835d'), (3720, '223b5e75'), (3960, '0ded835d'), (4200, '0ded835d')]:
            assert frames[f]['crc565_a'] == crc
        assert 'B=1 module=600 key=4' in log and 'B=0 module=600 key=4' in log
        assert confirm and a == 4321
        assert re.search(r'^MENU_CONFIRM_STATE frame=4323 .*phase=3 transition=0 closing=1 selection=0 ready=0$', log, re.M)
        summary.update({'navigation_original_state_and_image_verified': True,
                        'image_mismatch_does_not_block_input_proven': True,
                        'selected_row_reclick_rejected': True,
                        'Android_BACK_down_up_delivered': True,
                        'original_confirmation_state_acknowledged': True})
    if m['test_HOME_callback']:
        assert result['close_state']['home_pending'] and result['close_state']['close_pending']
        assert result['close_state']['source'] == 'APT'
        assert 'APT HOME handover AFTER quiescence' in log and 'APT HOME returned should_close=1' in log
        summary['HOME_cancel_after_quiescence_verified'] = True
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runs', required=True, help='revision:attempt,...')
    args = ap.parse_args()
    pairs = [name.split(':') for name in args.runs.split(',')]
    assert all(len(p) == 2 and all(s.isalnum() for s in p) for p in pairs)
    A.mkdir(exist_ok=True)
    rows = {':'.join(p): audit_run(*p) for p in pairs}
    protected = read(P / 'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for name, digest in protected.items():
        assert sha(P / name) == digest, name
    dataset = STORE / 'datasets/a46655efb24fab59c7649322986eea2ae0a5827454bca4c5e71be3d13818ceef'
    verified = verify_dataset(dataset)
    master = P / 'private/native-game-v0.1.0-sd/3ds/deadspace'
    assert all(sha(master / e['path']) == e['sha256'] for e in verified['files'])
    result = {'audited': True, 'runs': rows, 'protected_files_verified': len(protected),
              'resource_files_verified': len(verified['files']), 'hardware_tested': False,
              'frame_status': 'FAIL', 'baseline_crc': 'ea733050'}
    (A / 'software-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'audited': True, 'runs': list(rows), 'protected': len(protected)}))


if __name__ == '__main__':
    main()
