"""Validate actual late-loader/APT proofs before packaging one local CIA."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
from azahar_resource_store import STORE, sha, verify_dataset
from build_native_game_target_init import RUNTIME, makerom
from build_native_startup_legacy import payload

P = Path(__file__).resolve().parents[1]
A = P/'analysis/native-game-close-v0.1.3'
BASE = P/'3ds/build-native-game-v0.1.2-normal'
CASES = {'normal': 3, 'crc': 1, 'late': 2, 'home': 1,
         'latestopped': 1, 'latecrc': 1, 'retain': 1}
DATASET = 'a46655efb24fab59c7649322986eea2ae0a5827454bca4c5e71be3d13818ceef'


def read(p):
    return json.loads(p.read_text())


def check_cycle(c, variant):
    assert c['passed'] and not c['invalid_memory_accesses']
    assert c['readback_and_independent_CRC_checks']
    guest, validation = c['final_guest_result'], c['validation']
    assert guest['GL_error'] == guest['failed_submits'] == 0
    if variant == 'retain':
        assert not c['safe_exit'] and not c['both_heaps_released']
        assert guest['status'] == 'blocked' and not validation['cleanup_complete']
        assert guest['active_threads'] == 6
        return
    assert c['safe_exit'] and c['both_heaps_released']
    assert validation['cleanup_complete'] and guest['safe_exit']
    assert guest['active_threads'] == guest['finished_threads'] == 0
    assert c['shutdown_proof']['kernel_joins'] == 6
    assert c['shutdown_proof']['worker_handles_remaining'] == 0
    assert c['shutdown_proof']['files_balanced']
    if variant in ['normal', 'home']:
        assert guest['status'] == 'passed' and validation['frame_status'] == 'PASS'
        assert c['different_pixels'] == 0 and c['sequence_frames'] == 8 and c['sequence_exact']
    else:
        assert guest['status'] == 'failed' and validation['frame_status'] == 'FAIL'
        if variant in ['crc', 'latecrc']:
            assert validation['callbacks_completed'] == 600


def audit():
    source = P/'tests/native_game_close.c'
    assert struct.unpack_from('<Q', (P/'3ds/build-native-game-v0.1.3-normal/native-game.cxi').read_bytes(), 0x108)[0] == 0x000400000FDE7600
    text = source.read_text()
    assert '#define MAX_CALLBACKS 600u' in text and '#define TARGET_RGB565_CRC 0xea733050u' in text
    negatives = read(A/'gate-negative-tests.json')
    assert negatives['passed'] and len(negatives['cases']) == 7 and all(c['rejected'] for c in negatives['cases'])
    protected = read(A/'preservation.json')
    old = read(P/'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for name, digest in {**old, **protected}.items():
        assert sha(P/name) == digest, name
    dataset = verify_dataset(STORE/'datasets'/DATASET)
    master = P/'private/native-game-v0.1.0-sd/3ds/deadspace'
    assert all(sha(master/e['path']) == e['sha256'] for e in dataset['files'])
    proofs = {}
    runner_digest = None
    for variant, count in CASES.items():
        build = P/('3ds/build-native-game-v0.1.3-'+variant)
        m = read(build/'build-manifest.json')
        assert m['entry_sha256'] == sha(source), variant
        for name, digest in m['outputs_sha256'].items():
            assert sha(build/name) == digest, (variant, name)
        assert all(m['runtime_sha256'][name] == sha(BASE/name) == sha(build/name) for name in RUNTIME)
        if variant not in ['home', 'latestopped']:
            assert m['HLE_HOME_screenshot_only_test_SDK'] is None
        else:
            assert m['HLE_HOME_screenshot_only_test_SDK'] == sha(build/'apt-test.o')
        root = P/('analysis/azahar-native-game-v0.1.3-'+variant+'-cxi')
        r = read(root/'result.json')
        assert r['passed'] and r['sequential_cycles'] == count and len(r['cycles']) == count
        assert r['CXI_sha256'] == sha(build/'native-game.cxi')
        assert r['runner_sha256'] == sha(build/'host-runner.py')
        if runner_digest is None:
            runner_digest = r['runner_sha256']
        assert runner_digest == r['runner_sha256'], 'Same host checks for every final case'
        rows = []
        for c in r['cycles']:
            check_cycle(c, variant)
            evidence = root/('cycle-%04d' % c['cycle'])
            log = (evidence/'native-game.log').read_text()
            if variant != 'retain':
                q, j = read(evidence/'threads-after_quiesce.json'), read(evidence/'threads-after_join.json')
                workers = [w for w in q['workers'] if w['token']&255]
                assert len(workers) == 6 and all(w['done'] == 1 and w['kernel_wait'] == 0 for w in workers)
                assert not any(w['token']&255 for w in j['workers'])
                assert log.index('SHUTDOWN live workers=0') < log.index('PROCESS return')
            if variant in ['late', 'latestopped']:
                pending = read(evidence/'threads-test_pending_delegate.json')
                b = pending['image_base']
                later = [w for w in pending['workers'] if w['userdata_vtable'] and w['userdata_vtable'][0] == b+0xb6e6c]
                assert len(later) == 1
                w = later[0]
                assert w['loader_sync_words'][4] == 1 and w['loader_sync_words'][5]&255 == 0
                assert w['late_flag68'] == 0 and w['kernel_wait'] != 0
                assert w['userdata_words'][5] == b+0xb6d04
                assert [w['wait_stack'][n]-b for n in [3, 11, 15]] == [0x3357d8, 0x321b64, 0xb7084]
                assert re.search(r'Run=b6e6c completion=0 pumps=1 ', log)
                assert log.index('LOADER drained') < log.index('CALL MainActivity_NativeOnPause')
            if variant == 'latecrc':
                before = read(evidence/'threads-before_pause.json')
                assert any(w['userdata_vtable'] and w['userdata_vtable'][0] == before['image_base']+0xb6e6c for w in before['workers'])
            if variant in ['home', 'latestopped']:
                state = read(evidence/'close-state.json')
                assert state['close_pending'] and state['home_pending'] and state['source'] == 'APT'
                assert state['cleanup_complete']
                assert 'APT HOME returned should_close=1' in log
                assert log.index('SHUTDOWN live workers=0') < log.index('APT HOME handover AFTER quiescence') < log.index('PROCESS return close_pending=1')
                if variant == 'latestopped':
                    assert state['stopped_boundary'] and state['shutdown_attempts'] == 2
                    retained = read(evidence/'threads-stopped_retained.json')
                    assert sum(not w['done'] and w['kernel_wait'] != 0 for w in retained['workers'] if w['token']&255) == 6
            rows.append({k: c[k] for k in ['cycle', 'safe_exit', 'both_heaps_released', 'shutdown_proof', 'elapsed_host_seconds']})
        proofs[variant] = {'CXI_sha256': r['CXI_sha256'], 'cycles': rows}
    return {'software_passed': True, 'completed_kernel_GPU_process_exits': 9,
            'retained_negative_case_passed_without_safe_exit': True,
            'exact_hardware_late_wait_reproduced': True, 'APT_wakeup_cancel_process_exit_tested': True,
            'APT_test_limit': 'HOME request injected at safe boundary; only unsupported HLE HOME screenshot readiness skipped; physical HOME Menu needs hardware verification',
            'source_sha256': sha(source), 'generated_runner_sha256': runner_digest,
            'driver_sha256': sha(P/'tests/smoke_native_game_close.py'),
            'protected_SHA_count': len({**old, **protected}), 'shared_dataset_id': DATASET,
            'store_and_private_master_verified_unchanged': True,
            'ready_for_one_separate_hardware_test': True, 'hardware_tested': False,
            'hardware_run_authorized': False, 'old_0_1_2_CIA_repeat_prohibited': True,
            'frame_oracle_hardware_mismatch_remains_FAIL': True, 'cases': proofs}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cia', action='store_true')
    args = ap.parse_args()
    gate = audit()
    build = P/'3ds/build-native-game-v0.1.3-normal'
    if args.cia:
        assert not (build/'native-game.cia').exists(), 'Only one new experimental CIA; preserve it'
        subprocess.run(makerom('cia', build), cwd=build, check=True)
        cia = build/'native-game.cia'
        data = payload(cia.read_bytes())
        assert data == (build/'native-game.cxi').read_bytes()
        (build/'cia-payload.cxi').write_bytes(data)
        manifest = {'title_id': '000400000FDE7600', 'CIA_sha256': sha(cia),
                    'CIA_bytes': cia.stat().st_size, 'payload_sha256': sha(build/'native-game.cxi'),
                    'source_sha256': gate['source_sha256'], 'software_gate_passed': True,
                    'hardware_tested': False, 'hardware_run_authorized': False}
        (build/'cia-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        gate['CIA'] = manifest
        gate['ready_for_one_separate_hardware_test'] = False
        gate['CIA_payload_test_pending'] = True
    elif (build/'cia-manifest.json').exists():
        gate['CIA'] = read(build/'cia-manifest.json')
        assert gate['CIA']['CIA_sha256'] == sha(build/'native-game.cia')
        assert payload((build/'native-game.cia').read_bytes()) == (build/'native-game.cxi').read_bytes()
        tested = read(P/'analysis/azahar-native-game-v0.1.3-normal-cia-payload/result.json')
        assert tested['passed'] and tested['sequential_cycles'] == 1
        assert tested['CIA_sha256'] == gate['CIA']['CIA_sha256']
        assert tested['CIA_payload_verified'] and tested['CXI_sha256'] == gate['CIA']['payload_sha256']
        assert tested['runner_sha256'] == gate['generated_runner_sha256']
        check_cycle(tested['cycles'][0], 'normal')
        gate['CIA_payload_test_passed'] = True
        gate['completed_kernel_GPU_process_exits'] += 1
    # Software proofs do not override subsequently received hardware results.
    hardware_path = P/'analysis/native-game-close-v0.1.3-hardware/hardware-result.json'
    if hardware_path.exists():
        hardware = read(hardware_path)
        assert hardware['expected_CIA_sha256'] == gate['CIA']['CIA_sha256']
        gate.update({'hardware_tested': True, 'hardware_result': hardware['overall_result'],
                     'hardware_automatic_cleanup_first_attempt_passed': hardware['automatic_cleanup_first_attempt_passed'],
                     'hardware_manual_START_retry_exit_confirmed': hardware['manual_START_retry_confirmed'],
                     'hardware_HOME_X_tested': hardware['HOME_X_tested'],
                     'ready_for_one_separate_hardware_test': False,
                     'repeat_current_CIA_prohibited': True,
                     'hardware_followup': 'Fix bounded automatic completion while real late IO is progressing; no repeat of current CIA needed.'})
    (A/'release-gate.json').write_text(json.dumps(gate, indent=2)+'\n')
    print(json.dumps({k: v for k, v in gate.items() if k != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
