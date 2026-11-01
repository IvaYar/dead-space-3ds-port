"""Offline comparison of the three preserved stock-derived graphics variants."""
import json
import struct

import build_simple_tri_rgb565 as old
import build_simple_tri_rgb8 as new


def read(path):
    return path.read_text(encoding='utf-8')


def main():
    stock = old.stock
    P = old.P
    manifests = [d / 'build-manifest.json' for d in [stock.D, old.D, new.D]]
    stock_m, old_m, new_m = [json.loads(read(q)) for q in manifests]
    sources = [stock.A / 'upstream/graphics/gpu/simple_tri/source/main.c',
               old.D / 'main.c', new.D / 'main.c']
    for before_path, after_path, edits in [(sources[0], sources[1], old_m['source_edits']),
                                          (sources[1], sources[2], new.EDITS)]:
        expected = read(before_path)
        for before, after in edits:
            assert expected.count(before) == 1
            expected = expected.replace(before, after)
        assert expected == read(after_path)
    assert stock_m['compiler_flags'] == old_m['compiler_flags'] == new_m['compiler_flags']
    for name in ['vshader.shbin', 'vshader.shbin.o', 'vshader_shbin.h']:
        assert len({stock.sha(d / name) for d in [stock.D, old.D, new.D]}) == 1
    rsfs = [read(q) for q in [stock.D / 'simple_tri.rsf', old.D / 'triangle.rsf', new.D / 'triangle.rsf']]
    assert len({r[r.index('AccessControlInfo:'):] for r in rsfs}) == 1
    cias = [stock.D / 'simple_tri-profile.cia', old.D / 'simple-tri-rgb565.cia', new.D / 'simple-tri-rgb8.cia']
    payloads = [stock.payload(q.read_bytes()) for q in cias]
    for start, end in [(0x408, 0x600), (0x20d, 0x210), (0x21c, 0x220)]:
        assert len({q[start:end] for q in payloads}) == 1
    hardware = [P / 'analysis/hardware/official-simple-tri-profile-cia-v0.1.0-user-result.json',
                P / 'analysis/hardware/simple-tri-rgb565-v0.1.0-user-result.json']
    for cia, report in zip(cias, hardware):
        assert stock.sha(cia) == json.loads(read(report))['expected_CIA_sha256']
    inputs = sources + manifests + hardware + [
        P / '3ds/source/ds34_gpu_3ds.c', P / 'tests/engine_azahar.c',
        P / '3ds/source/ds13_gles.c', P / 'tools/export_native_frame.py']
    report = {
        'date': '2026-10-30', 'passed': True, 'analysis_only_no_hardware': True,
        'working_to_failed_source_edits_exactly_verified': old_m['source_edits'],
        'failed_to_new_source_edits_exactly_verified': new_m['source_edits'],
        'no_other_main_source_differences': True, 'compiler_flags_identical': True,
        'shader_binary_object_header_identical': True,
        'RSF_AccessControl_and_SystemControl_identical': True,
        'binary_capabilities_system_flags_stack_identical_except_identity': True,
        'old_CIA_hashes_match_hardware_reports_expected_files': True,
        'device_binary_hash_measured': False,
        'inputs_sha256': {q.relative_to(P).as_posix(): stock.sha(q) for q in inputs},
        'builds': [],
        'interpretation': 'Format/framebuffer preparation combination differs; root cause and individual stalled command unconfirmed. RGB8->RGB8 is optional for RGBA8->RGB8 integration.',
    }
    for directory, cia, payload, status in zip([stock.D, old.D, new.D], cias, payloads,
            ['visual+START PASS', 'thin strip+hang/POWER FAIL', 'NOT TESTED']):
        report['builds'].append({'directory': directory.relative_to(P).as_posix(),
                                'CIA_sha256': stock.sha(cia),
                                'title_id': f'{struct.unpack_from("<Q", payload, 0x108)[0]:016X}',
                                'hardware_status': status})
    (P / 'analysis/rgba8-rgb8-route/comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Verified exact source whitelists, shader/flags/RSF/capabilities and hardware-reference hashes.')


if __name__ == '__main__':
    main()
