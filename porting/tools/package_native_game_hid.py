"""Package one HID/menu CIA after auditing the final compiled candidate."""
import json
import struct
import subprocess
from audit_native_game_hid import P, A, read, audit_run
from azahar_resource_store import sha
from build_native_game_target_init import makerom
from build_native_startup_legacy import payload


def main():
    required = [('release', a) for a in ['raw', 'missing', 'pulse', 'hold', 'circle', 'early']]
    required += [('releasestall', 'stall'), ('releasehome', 'home')]
    audit = read(A / 'software-audit.json')
    assert audit['audited'] and audit['protected_files_verified'] == 375
    assert audit['resource_files_verified'] == 1752 and audit['in_game_frame_status'] == 'FAIL'
    runs = {':'.join(p): audit_run(*p) for p in required}
    assert set(audit['runs']) == set(runs) and audit['runs'] == runs
    for name in ['release:pulse', 'release:hold', 'release:circle', 'releasestall:stall']:
        assert runs[name]['original_navigation_and_confirm_ACK_verified']
        assert runs[name]['frame_mismatch_does_not_block_input']
    assert runs['release:raw']['raw_Dpad_AB_START_and_CirclePad_verified']
    assert runs['release:missing']['missing_Dpad_blocks_engine_without_wait']
    assert runs['release:pulse']['short_pulses_recovered_while_SDK_main_snapshots_zero']
    assert runs['releasestall:stall']['two_second_main_stall_pulse_recovered']
    assert runs['release:early']['close_state']['source'] == 'START'
    assert runs['releasehome:home']['deferred_HOME_verified']
    build = P / '3ds/build-native-game-v0.1.7-release'
    m = read(build / 'build-manifest.json')
    assert m['source_sha256'] == sha(P / 'tests/native_game_hid.c')
    for name, digest in m['headers_sha256'].items():
        assert sha(P / 'tests' / name) == digest
    assert m['fast_page_crc32'] and not m['scene_probe'] and not m['dense_capture']
    assert m['callbacks'] == 12000 and m['confirm_tail_callbacks'] == 2
    assert m['test_HOME_callback'] == m['test_input_stall_frame'] == 0
    assert m['test_only_SDK_sha256'] is None
    for revision in ['releasestall', 'releasehome']:
        fixture = read(P / ('3ds/build-native-game-v0.1.7-' + revision) / 'build-manifest.json')
        assert fixture['source_sha256'] == m['source_sha256']
        assert fixture['headers_sha256'] == m['headers_sha256']
    queue = read(A / 'queue-tests.json'); sdk = read(A / 'SDK-tests.json')
    crc = read(P / 'analysis/native-game-controls-v0.1.6/page-crc-tests.json')
    assert queue['passed'] and len(queue['checks']) == 7
    assert queue['header_sha256'] == m['headers_sha256']['native_hid_queue.h']
    assert sdk['passed'] and sdk['SDK_ARM_vectors'] == 72
    assert sdk['compiled_candidate_ELF_sha256'] == sha(build / 'native-game.elf')
    assert crc['passed'] and crc['vectors'] == 81 and crc['single_bit_corruptions_rejected'] == 5
    assert crc['header_sha256'] == m['headers_sha256']['native_menu_page_crc.h']
    assert m['memory_MiB'] == {'application': 124, 'normal': 20, 'linear': 100, 'donor_arena': 85.5}
    existing = list((P / '3ds').glob('build-native-game-v0.1.7-*/*.cia'))
    assert not existing, 'Preserve the single CIA; never replace or package a second one'
    subprocess.run(makerom('cia', build), cwd=build, check=True)
    data = payload((build / 'native-game.cia').read_bytes())
    assert data == (build / 'native-game.cxi').read_bytes()
    assert struct.unpack_from('<Q', data, 0x108)[0] == 0x000400000FDE7A00
    gate = {
        'ready_for_one_separate_hardware_test': True,
        'hardware_tested': False, 'hardware_run_authorized': False,
        'software_safety_passed': True, 'completed_final_process_exits': len(runs),
        'CIA': {'path': (build / 'native-game.cia').relative_to(P.parent).as_posix(),
                'title': 'DS HID Menu 0.1.7', 'title_id': '000400000FDE7A00',
                'bytes': (build / 'native-game.cia').stat().st_size,
                'sha256': sha(build / 'native-game.cia'), 'payload_sha256': sha(build / 'native-game.cxi'),
                'payload_byte_identical_to_tested_CXI': True},
        'source_sha256': m['source_sha256'], 'headers_sha256': m['headers_sha256'],
        'software_audit_sha256': sha(A / 'software-audit.json'),
        'queue_checks': 7, 'SDK_ARM_vectors': 72, 'inherited_page_crc_vectors': 81,
        'memory_MiB': m['memory_MiB'], 'frame_status': 'FAIL',
        'baseline_crc_unchanged': 'ea733050',
        'input_admission_depends_on_framebuffer': False,
        'raw_preflight_before_original_engine': True,
        'original_navigation_and_confirmation_ACK_verified': True,
        'B_original_event_delivered': True, 'B_return_from_first_menu_supported': False,
        'GPU_runtime_and_shaders_identical_to_016': True,
        'donor_shutdown_functions_identical_to_016': True,
        'hardware_016_input_loss_exact_cause_established': False,
        'hardware_loading_speedup_measured_this_stage': False,
        'known_limits': [
            'Polling period4ms is nominal; observed ready-phase Azahar gaps reach135.719ms. Unsampled raw pulses cannot be recovered.',
            'Original first difficulty menu ignores BACK; no forced return.',
            'Only menu confirmation plus2 original callbacks; first-scene audio NULL/fog blockers remain.',
            'Texture paging/font preparation remains slow; no loading optimization in this stage.',
            'No new physical hardware evidence; FIFO/raw observer correction still needs one approved test.'],
    }
    (A / 'release-gate.json').write_text(json.dumps(gate, indent=2) + '\n')
    print(json.dumps(gate['CIA'], indent=2))


if __name__ == '__main__':
    main()
