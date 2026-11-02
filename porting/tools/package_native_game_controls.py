"""Package exactly one menu-controls CIA after its final evidence gates."""
import json
import struct
import subprocess
from audit_native_game_controls import P, A, read, audit_run
from azahar_resource_store import sha
from build_native_game_target_init import makerom
from build_native_startup_legacy import payload


def main():
    required = [('final2', 'confirm'), ('final2', 'repeat2'), ('final2', 'repeat3'),
                ('final2', 'earlyexit'), ('final2home', 'home')]
    audit = read(A / 'software-audit.json')
    assert audit['audited'] and audit['protected_files_verified'] == 375
    assert audit['resource_files_verified'] == 1752 and audit['frame_status'] == 'FAIL'
    runs = {':'.join(p): audit_run(*p) for p in required}
    for name in ['final2:confirm', 'final2:repeat2', 'final2:repeat3']:
        assert runs[name]['navigation_original_state_and_image_verified']
        assert runs[name]['image_mismatch_does_not_block_input_proven']
        assert runs[name]['original_confirmation_state_acknowledged']
    assert runs['final2:earlyexit']['close_state']['source'] == 'START'
    assert runs['final2home:home']['HOME_cancel_after_quiescence_verified']
    build = P / '3ds/build-native-game-v0.1.6-final2'
    m = read(build / 'build-manifest.json')
    assert m['source_sha256'] == sha(P / 'tests/native_game_menu_controls.c')
    for name, digest in m['headers_sha256'].items():
        assert sha(P / 'tests' / name) == digest
    assert m['fast_page_crc32'] and not m['scene_probe'] and not m['dense_capture']
    assert m['callbacks'] == 12000 and m['confirm_tail_callbacks'] == 2
    assert m['test_HOME_callback'] == 0 and m['test_only_SDK_sha256'] is None
    home = read(P / '3ds/build-native-game-v0.1.6-final2home/build-manifest.json')
    assert home['source_sha256'] == m['source_sha256'] and home['headers_sha256'] == m['headers_sha256']
    controls = read(A / 'input-tests.json'); crc = read(A / 'page-crc-tests.json')
    assert controls['passed'] and len(controls['checks']) == 12
    for name, digest in controls['headers_sha256'].items():
        assert m['headers_sha256'][name] == digest
    assert crc['passed'] and crc['vectors'] == 81 and crc['single_bit_corruptions_rejected'] == 5
    assert crc['header_sha256'] == m['headers_sha256']['native_menu_page_crc.h']
    assert not (build / 'native-game.cia').exists(), 'Preserve the only packaged CIA'
    subprocess.run(makerom('cia', build), cwd=build, check=True)
    data = payload((build / 'native-game.cia').read_bytes())
    assert data == (build / 'native-game.cxi').read_bytes()
    assert struct.unpack_from('<Q', data, 0x108)[0] == 0x000400000FDE7900
    (build / 'cia-payload.cxi').write_bytes(data)
    gate = {
        'ready_for_one_separate_hardware_test': True,
        'hardware_tested': False, 'hardware_run_authorized': False,
        'software_safety_passed': True, 'completed_final_process_exits': len(runs),
        'scope': 'Original difficulty menu: UP/DOWN, A original confirmation acknowledged, +2 callbacks then safe exit. B original BACK delivery; initial original screen ignores return. No gameplay candidate.',
        'CIA': {'path': (build / 'native-game.cia').relative_to(P.parent).as_posix(),
                'title': 'DS Original Menu 0.1.6', 'title_id': '000400000FDE7900',
                'bytes': (build / 'native-game.cia').stat().st_size,
                'sha256': sha(build / 'native-game.cia'), 'payload_sha256': sha(build / 'cia-payload.cxi'),
                'payload_byte_identical_to_tested_CXI': True},
        'source_sha256': m['source_sha256'], 'headers_sha256': m['headers_sha256'],
        'software_audit_sha256': sha(A / 'software-audit.json'),
        'input_checks': len(controls['checks']), 'page_crc_vectors': crc['vectors'],
        'memory_MiB': m['memory_MiB'], 'frame_status': 'FAIL',
        'baseline_crc_unchanged': 'ea733050',
        'input_admission_depends_on_framebuffer': False,
        'original_confirmation_state_acknowledged': True,
        'B_event_delivery_verified': True, 'B_return_from_first_menu_supported': False,
        'GPU_and_shaders_identical_to_015': True,
        'shutdown_source_unchanged': True,
        'hardware_loading_speedup_measured': False,
        'known_limits': ['Initial original difficulty screen deliberately ignores BACK; no forced return implemented.',
                        'Cold font/menu callback still expensive; SD texture paging remains.',
                        'Only bounded menu confirmation; original first-scene audio NULL/fog blockers remain.'],
    }
    (A / 'release-gate.json').write_text(json.dumps(gate, indent=2) + '\n')
    print(json.dumps(gate['CIA'], indent=2))


if __name__ == '__main__':
    main()
