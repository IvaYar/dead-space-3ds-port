"""Release audit of software evidence; never launches a CIA or rewrites baselines."""
import json
import struct
import subprocess
from pathlib import Path
import numpy as np
from build_native_game_stable import A, BASE, P, RUNTIME, SOURCE, runner_matches, verify_result
from build_native_startup_legacy import payload, sha
from audit_native_startup_memory import globals_from_elf
from analyze_native_game_image import unpack8, unpack565, quantize


def main():
    d = P/'3ds/build-native-game-v0.1.2-normal'
    cycles = []
    measurements = []
    for variant, container, count, suffix in [('normal', 'cxi', 3, ''), ('poison', 'cxi', 3, ''),
                                             ('crc', 'cxi', 1, ''), ('normal', 'cia', 3, '-r2')]:
        build = P/('3ds/build-native-game-v0.1.2-'+variant)
        manifest = json.loads((build/'build-manifest.json').read_text())
        assert manifest['inputs_sha256']['entry'] == sha(SOURCE)
        for name, digest in manifest['outputs_sha256'].items():
            assert sha(build/name) == digest
        assert all(sha(build/n) == manifest['runtime_sha256'][n] == sha(BASE/n) for n in RUNTIME)
        root = P/('analysis/azahar-native-game-v0.1.2-'+variant+'-'+container+suffix)
        r = verify_result(root, build, count)
        if container == 'cia':
            assert r['CIA_payload_verified'] and r['CIA_sha256'] == sha(d/'native-game.cia')
        for c in r['cycles']:
            assert c['readback_and_independent_CRC_checks']
            v = c['validation']
            if variant == 'normal':
                assert c['different_pixels'] == 0 and c['sequence_exact'] and c['sequence_frames'] == 8
                assert v['frame_status'] == 'PASS' and c['final_guest_result']['status'] == 'passed'
            else:
                assert v['frame_status'] == 'FAIL' and c['final_guest_result']['status'] == 'failed'
                assert v['callbacks_completed'] == 600 and not c['final_guest_result']['frame_saved']
            log = (root/('cycle-%04d' % c['cycle'])/'native-game.log').read_text()
            measurements += [json.loads(l[8:]) for l in log.splitlines() if l.startswith('MEMJSON ')]
            cycles.append({'variant': variant, 'container': container, 'cycle': c['cycle'],
                           'frame_status': v['frame_status'], 'callbacks': v['callbacks_completed'],
                           'sequence_callbacks': v['sequence_completed'], 'safe_exit': c['safe_exit'],
                           'kernel_joins': c['shutdown_proof']['kernel_joins']})
    retained = json.loads((P/'analysis/azahar-native-game-v0.1.2-retain-cxi/result.json').read_text())
    assert retained['passed'] and not retained['safe_exit'] and not retained['validation']['cleanup_complete']
    assert runner_matches(retained['runner_sha256']) and retained['final_guest_result']['active_threads'] == 6
    assert retained['CXI_sha256'] == sha(P/'3ds/build-native-game-v0.1.2-retain/native-game.cxi')
    assert not retained['both_heaps_released'] and retained['final_guest_result']['status'] == 'blocked'
    assert globals_from_elf(d/'native-game.elf') == dict(__ctru_heap_size=20<<20, __ctru_linear_heap_size=100<<20, __stacksize__=256<<10)
    cxi = (d/'native-game.cxi').read_bytes()
    assert payload((d/'native-game.cia').read_bytes()) == cxi == (d/'cia-payload.cxi').read_bytes()
    assert struct.unpack_from('<Q', cxi, 0x108)[0] == 0x000400000FDE7500
    assert struct.unpack_from('<II', cxi, 0x1b0) == (0, 0), 'No RomFS/game assets'
    ex, old = cxi[0x200:0xa00], (BASE/'native-game.cxi').read_bytes()[0x200:0xa00]
    assert ex[0x20d] == ex[0x60d] == 1
    assert ex[0x208:0x400] == old[0x208:0x400] and ex[0x608:0x800] == old[0x608:0x800]
    assert b'INJECTED cleanup incomplete' not in (d/'native-game.elf').read_bytes()
    assert all(m['commit'] < m['limit'] == 124<<20 and not m['donor_refusals'] and not m['runtime_failures'] for m in measurements)
    before = json.loads((A/'preservation.json').read_text())['before']
    for name, digest in before.items():
        assert sha(P/name) == digest, name
    command = [str(P/'toolchain/extras/ctrtool/ctrtool.exe'), '--verify', str(d/'native-game.cia')]
    proc = subprocess.run(command, capture_output=True, text=True)
    audit = proc.stdout+proc.stderr
    (A/'CIA-container-audit.txt').write_text(audit)
    assert not any('Hash:' in l and '(FAIL)' in l for l in audit.splitlines())
    errors = [l for l in audit.splitlines() if ' ERROR]' in l]
    allowed = ['Signature for Ticket was invalid', 'Signature for TitleMetaData was invalid', 'Signature for AccessDescriptor was invalid']
    assert len(errors) == 3 and all(any(a in e for a in allowed) for e in errors), errors
    assert json.loads((A/'software-capture-audit.json').read_text())['all_capture_checks']
    hardware = unpack8((P/'analysis/hardware/native-game-target-init-v0.1.1-user-run-0001/comparison-miss.raw').read_bytes())
    baseline = unpack565((P/'analysis/gpu-safety/first-game-frame.raw').read_bytes())
    q = quantize(hardware)
    early = unpack565((P/'analysis/gpu-sequence-8-17/gpu-frame-16.raw').read_bytes())
    mask = np.any(baseline, axis=-1)
    mask[:180] = False
    mask[220:] = False
    findings = {'hardware_RGB565_unique_colors': len(np.unique((q[..., 0] << 11) | (q[..., 1] << 5) | q[..., 2])),
                'baseline_RGB565_unique_colors': len(np.unique((baseline[..., 0] << 11) | (baseline[..., 1] << 5) | baseline[..., 2])),
                'lower_reference_nonblack_pixels': int(mask.sum()),
                'lower_reference_exactly_equal_to_EA_frame16_at_same_pixels': int((np.all(early == baseline, axis=-1) & mask).sum()),
                'clears_in_all_positive_and_negative_software_samples': 0,
                'hardware_difference_cause_fully_proven': False,
                'late_software600_RGB565_exact': json.loads((A/'software600-image-comparison.json').read_text())['RGB565']['different_pixels'] == 0}
    logs = [P/('analysis/azahar-native-game-v0.1.2-'+v+'-cxi/cycle-0001/native-game.log') for v in ['normal', 'poison', 'crc']]
    assert all(json.loads(l[12:])['clears'] == 0 for f in logs for l in f.read_text().splitlines() if l.startswith('CAPTUREJSON '))
    (A/'image-findings.json').write_text(json.dumps(findings, indent=2)+'\n')
    hardware_path = P/'analysis/native-game-stable-v0.1.2-hardware/hardware-result.json'
    hardware = json.loads(hardware_path.read_text()) if hardware_path.exists() else None
    assert hardware is None or hardware['expected_CIA_sha256'] == sha(d/'native-game.cia'), 'Hardware record belongs to another candidate'
    hardware_failed = bool(hardware and hardware['overall_result'] != 'PASS_frame_and_cleanup')
    result = {'software_original_frame_and_sequence_PASS': True, 'CRC_FAIL_cooperative_exit_PASS': True,
              'incomplete_cleanup_not_reported_as_PASS': True, 'CIA_payload_three_cycles_PASS': True,
              'title_id': '000400000FDE7500', 'CIA_sha256': sha(d/'native-game.cia'),
              'CIA_bytes': (d/'native-game.cia').stat().st_size, 'CXI_sha256': sha(d/'native-game.cxi'),
              'protected_files_unchanged': len(before), 'runtime_GPU_shader_threads_identical': True,
              'process_commit_peak_bytes': max(m['commit'] for m in measurements),
              'normal_allocator_footprint_peak_bytes': max(m['normal_allocator_arena'] for m in measurements),
              'hardware_tested': bool(hardware), 'hardware_run_authorized': False,
              'hardware_result': hardware['overall_result'] if hardware else 'NOT_TESTED',
              'ready_for_one_separate_hardware_test': hardware is None,
              'repeat_current_CIA_prohibited': hardware_failed,
              'hardware_failure_record': str(hardware_path.relative_to(P)) if hardware else None,
              'hardware_image_issue_resolved': False,
              'full_gameplay_supported': False, 'host_Azahar_reload_crash_fixed': False,
              'host_only_CIA_directory_fix_proven_no_guest_or_assertion_changes': True, 'cycles': cycles}
    (A/'release-gate.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
