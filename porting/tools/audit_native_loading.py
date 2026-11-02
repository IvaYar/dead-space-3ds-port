"""Compare bounded loading experiments, exact readbacks and original input ACKs."""
import collections
import json
from pathlib import Path
import re
from audit_native_game_hid import audit_run, tagged
from audit_native_game_menu import packed
from azahar_resource_store import sha, STORE, verify_dataset
from build_native_loading import texture_source, framebuffer_source

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-loading-optimization'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def run(revision, attempt):
    inherited = audit_run(revision, attempt)
    root = P / ('analysis/azahar-native-menu-v0.1.7-' + revision + '-' + attempt)
    build = P / ('3ds/build-native-game-v0.1.7-' + revision)
    m = read(build / 'build-manifest.json')
    assert not list(build.glob('*.cia')) and m['CIA_created'] is False
    assert m['source_origin_sha256'] == sha(P / 'tests/native_game_hid.c')
    assert sha(build / 'ds27_pages_3ds.c') == sha(P / '3ds/build-native-game-v0.1.7-release/ds27_pages_3ds.c')
    assert sha(build / 'native_menu_page_crc.h') == sha(P / 'tests/native_menu_page_crc.h')
    for name, transform in [('ds15_textures.c', texture_source), ('ds26_framebuffer.c', framebuffer_source)]:
        assert (build / name).read_text() == transform((P / '3ds/source' / name).read_text(), m['clean_backing'])
        assert sha(build / name) == m['loading_sources_sha256'][name]
    private = root / 'Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001'
    log = (private / 'native-game.log').read_text()
    events = [json.loads(line) for line in (private / 'loading-pages.jsonl').read_text().splitlines()]
    assert events and all(e['result'] == 0 and e['total_ms'] >= e['crc_ms'] for e in events)
    warm = max(tagged(log, 'CALLBACKJSON'), key=lambda c: c['ms'])
    ev = [e for e in events if e['frame'] == warm['frame']]
    assert sum(e['kind'] == 1 for e in ev) == warm['page_saves']
    assert sum(e['kind'] == 2 for e in ev) == warm['page_loads'] == 166
    assert warm['ops'][0]['calls'] == 1146 and warm['ops'][2]['calls'] == 34
    assert warm['ops'][11]['calls'] == len(ev)
    assert warm['ops'][11]['bytes'] == sum(e['bytes'] for e in ev)
    request = float(re.search(r'HIDSESSION original_engine_request ms=([0-9.]+)', log)[1])
    ready = float(re.search(r'HID_BARRIER ms=([0-9.]+) ready=1', log)[1])
    summary = {'inherited_safety_and_input_audit': inherited,
               'clean_backing': m['clean_backing'], 'page_CRC_and_integrity_source_unchanged': True,
               'engine_request_to_menu_ready_ms': round(ready - request, 3),
               'slowest_callback': warm, 'page_events_sha256': sha(private / 'loading-pages.jsonl'),
               'paging_diff_sha256': sha(build / 'paging.diff'),
               'page_operations': {str(kind): {
                   'calls': sum(e['kind'] == kind for e in ev),
                   'payload_bytes': sum(e['bytes'] for e in ev if e['kind'] == kind),
                   'total_ms': round(sum(e['total_ms'] for e in ev if e['kind'] == kind), 3),
                   'CRC_ms': round(sum(e['crc_ms'] for e in ev if e['kind'] == kind), 3),
                   'non_CRC_ms': round(sum(e['total_ms'] - e['crc_ms'] for e in ev if e['kind'] == kind), 3)}
                   for kind in [1, 2]}}
    return summary, private, log, events, ev


def main():
    A.mkdir(exist_ok=True)
    rows = {n: run(*n.split(':')) for n in ['loadbase:measure', 'loadclean:measure', 'loadclean:repeat', 'loadhome:check']}
    baseline = rows['loadbase:measure']; clean = rows['loadclean:measure']
    matches = {}
    caps = {c['frame']: c for c in tagged(baseline[2], 'CAPTUREJSON') if c['frame'] >= 3120}
    assert len(caps) == 13
    for name in ['loadclean:measure', 'loadclean:repeat']:
        row = rows[name]; byframe = {c['frame']: c for c in tagged(row[2], 'CAPTUREJSON')}
        matched = []
        for frame, c in caps.items():
            data = (baseline[1] / c['file']).read_bytes()
            compared = (row[1] / byframe[frame]['file']).read_bytes()
            assert data == compared
            matched.append({'frame': frame, 'raw_sha256': sha(row[1] / byframe[frame]['file']),
                            'RGB565_crc': c['crc565_a'], 'bytes_equal': len(data)})
        assert [(e['bytes'], e['crc']) for e in baseline[4] if e['kind'] == 2] == [(e['bytes'], e['crc']) for e in row[4] if e['kind'] == 2]
        matches[name] = matched
    # Link each replacement token to its original canonical page lineage.
    metadata, origins, reused, reads = {}, {}, [], collections.Counter()
    for e in baseline[3]:
        if e['kind'] == 1:
            origins[e['token']] = origins.get(e['old_token'], e['token'])
            if e['frame'] == baseline[0]['slowest_callback']['frame'] and e['old_token'] in metadata:
                assert e['bytes'] == metadata[e['old_token']]['bytes'] and e['crc'] == metadata[e['old_token']]['crc']
                reused.append(e)
            metadata[e['token']] = e
        elif e['frame'] == baseline[0]['slowest_callback']['frame']:
            reads[origins[e['token']]] += 1
    assert len(reused) == 163 and sum(e['bytes'] for e in reused) == 511180800
    assert baseline[0]['slowest_callback']['page_saves'] == 201
    assert all(rows[n][0]['slowest_callback']['page_saves'] == 38 for n in ['loadclean:measure', 'loadclean:repeat', 'loadhome:check'])
    working_set = {
        'canonical_CPU_residency_limit_bytes': 6 * 1024 * 1024,
        'largest_page_bytes': 4 * 1024 * 1024,
        'two_largest_pages_need_bytes': 8 * 1024 * 1024,
        'same_snapshot_resaves': len(reused), 'same_snapshot_resave_payload_bytes': sum(e['bytes'] for e in reused),
        'warm_page_load_lineages': [{'origin_token': token, 'loads': count, 'bytes': metadata[token]['bytes']} for token, count in reads.most_common()],
        'load_sequence_sizes_and_CRC_identical': True,
        'warm_load_payload_bytes': sum(e['bytes'] for e in baseline[4] if e['kind'] == 2),
        'interpretation': '4MiB canonical CPU pages alternate under unchanged6MiB LRU. Every old spill rewrites unchanged snapshots. GPU8MiB cache is separate and unchanged.',
    }
    hardware = P / 'analysis/hardware/native-game-hid-v0.1.7-user-run-0001/native-game.log'
    log = hardware.read_text(); hardware_warm = max(tagged(log, 'CALLBACKJSON'), key=lambda c: c['ms'])
    windows = [w for w in tagged(log, 'PERFJSON') if w['frame'] <= 4080]
    sums = {k: round(sum(w[k] for w in windows), 3) for k in
            ['elapsed_ms', 'callback_ms', 'present_ms', 'diagnostic_ms', 'gpu_queue_wait_ms', 'vblank_wait_ms']}
    total = 559327.446; outside = round(total - hardware_warm['ms'], 3)
    bootstrap = 2647.471
    slow = [c for c in tagged(log, 'CALLBACKJSON') if c['frame'] <= 4080 and c['ms'] > 100]
    breakdown = {
        'source_hardware_log_sha256': sha(hardware), 'hardware_engine_to_menu_ready_ms': total,
        'hardware_slowest_callback': hardware_warm, 'outside_slowest_callback_ms': outside,
        'bootstrap_to_init_return_ms': bootstrap, 'pre_heavy_windows_through_frame4080': sums,
        'pre_heavy_window_other_ms': round(sums['elapsed_ms'] - sums['callback_ms'] - sums['present_ms'] - sums['diagnostic_ms'], 3),
        'unwindowed_edges_ms': round(outside - bootstrap - sums['elapsed_ms'], 3),
        'other_slow_callbacks_before_heavy': slow,
        'limits': 'Queue/VBlank are nested. Callback resource counters include concurrent loader activity, not pure IO time. Unwindowed edges include main/profile/present near the heavy draw. No new hardware measurement.',
    }
    protected = read(P / 'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for name, digest in protected.items(): assert sha(P / name) == digest
    dataset = verify_dataset(STORE / 'datasets/a46655efb24fab59c7649322986eea2ae0a5827454bca4c5e71be3d13818ceef')
    for e in dataset['files']:
        assert sha(P / 'private/native-game-v0.1.0-sd/3ds/deadspace' / e['path']) == e['sha256']
    tests = read(P.parent / '.local/native-loading-pages-tests-verified/result.json')
    assert tests['passed'] and tests['tests_run'] == 13
    for name, digest in tests['optimized_source_sha256'].items():
        assert sha(P / '3ds/build-native-game-v0.1.7-loadclean' / name) == digest
    result = {
        'software_checks_passed': True, 'hardware_tested_this_stage': False, 'CIA_created': False,
        'experiments': {n: v[0] for n, v in rows.items()}, 'exact_readback_comparisons': matches,
        'all_166_warm_loaded_pages_same_sizes_and_CRC_sequence': True,
        'ready_time_reduction_percent': round(100 * (1 - clean[0]['engine_request_to_menu_ready_ms'] / baseline[0]['engine_request_to_menu_ready_ms']), 3),
        'heavy_callback_reduction_percent': round(100 * (1 - clean[0]['slowest_callback']['ms'] / baseline[0]['slowest_callback']['ms']), 3),
        'no_memory_budget_increase': True, 'protected_files_verified': len(protected),
        'resource_files_verified': len(dataset['files']), 'CRC_status': 'FAIL', 'unchanged_baseline': 'ea733050',
        'next_stage': 'Stop loading experiments; original audio NULL/fog and first scene. No CIA/hardware/push authorized.',
    }
    for name, value in [('result.json', result), ('hardware-breakdown.json', breakdown),
                        ('page-working-set.json', working_set), ('pager-tests.json', tests)]:
        (A / name).write_text(json.dumps(value, indent=2) + '\n')
    (A / 'paging.diff').write_text((P / '3ds/build-native-game-v0.1.7-loadclean/paging.diff').read_text())
    print(json.dumps({'passed': True, 'runs': len(rows), 'page_tests': 13, 'exact_frame_pairs': sum(map(len, matches.values())),
                      'menu_time_reduction_percent': result['ready_time_reduction_percent'],
                      'heavy_reduction_percent': result['heavy_callback_reduction_percent'], 'CIA_created': False}))


if __name__ == '__main__':
    main()
