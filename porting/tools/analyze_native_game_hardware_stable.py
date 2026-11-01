"""Numerical evidence for the received Stable0.1.2 hardware run; read originals only."""
import hashlib
import json
import re
import struct
from pathlib import Path
from audit_pica_outputs import command_list

P = Path(__file__).resolve().parents[1]
A = P/'analysis/native-game-stable-v0.1.2-hardware'
H = P/'analysis/hardware/native-game-stable-v0.1.2-user-run-0001'
S = P/'analysis/azahar-native-game-v0.1.2-crc-cxi/Azahar/sdmc/3ds/ds-native-game-v0.1.2/run-0001'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def writes(path):
    blob = path.read_bytes()
    offset, result = 0, []
    while offset < len(blob):
        *words, size = struct.unpack_from('<9I', blob, offset)
        offset += 36
        payload = blob[offset:offset+size]
        offset += size
        if words[0] & 255 == 1:
            result += command_list(payload)['writes']
    assert offset == len(blob)
    return result


def pica_bytes(path):
    blob = path.read_bytes()
    offset, chunks = 0, []
    while offset < len(blob):
        *words, size = struct.unpack_from('<9I', blob, offset)
        offset += 36
        payload = blob[offset:offset+size]
        offset += size
        if words[0] & 255 == 1:
            chunks.append(payload)
    return b''.join(chunks)


def generic_workers(path):
    r = json.loads(path.read_text())
    base = r['image_base']
    return [{'token': w['token'], 'entry_offset': w['entry_offset'],
             'callback_offset': w['argument_words'][3]-base,
             'runnable_vtable_offset': w['userdata_words'][0]-base,
             'virtual_Run_offset': w['userdata_vtable'][0]-base,
             'done': w['done'], 'kernel_wait': w['kernel_wait'],
             'last_recorded_wait_caller_offset': w['wait_caller']-base,
             'last_sleep_nanoseconds': w['sleep_nanoseconds'],
             'note': 'Wait/sleep fields are sampled diagnostic history, not a stopped CPU PC.'}
            for w in r['workers'] if len(w['argument_words']) > 4 and w['argument_words'][3] == base+0x320624 and w['userdata_vtable']]


def main():
    archive = json.loads((A/'archive-manifest.json').read_text())
    assert all(digest(H/n) == f['sha256'] and digest(P/'ds-native-game-v0.1.2/run-0001'/n) == f['sha256'] for n, f in archive['files'].items())
    log = (H/'native-game.log').read_text()
    trace = [(int(f), c) for f, c in re.findall(r'^FRAMECRC frame=(\d+) crc565=([0-9a-f]+)', log, re.M)]
    memory = [json.loads(l[8:]) for l in log.splitlines() if l.startswith('MEMJSON ')]
    captures = [json.loads(l[12:]) for l in log.splitlines() if l.startswith('CAPTUREJSON ')]
    inputs = [json.loads(l[10:]) for l in log.splitlines() if l.startswith('INPUTJSON ')]
    software_captures = [json.loads(l[12:]) for l in (S/'native-game.log').read_text().splitlines() if l.startswith('CAPTUREJSON ')]
    result = {'hardware_tested': True, 'executed_by': 'user', 'overall_result': 'FAIL_frame_and_cleanup',
              'expected_CIA_sha256': '8bc86b29d023211d6469f903ba4eed343b3abbb83a901576e8ba096c424e6226',
              'installed_CIA_identity_independently_measured': False,
              'guest_result': json.loads((H/'result.json').read_text()),
              'validation': json.loads((H/'validation.json').read_text()),
              'frame_CRC_samples': len(trace), 'first_four_texture_callback': captures[0]['frame'],
              'first_final_hardware_CRC_callback': next(f for f, c in trace if c == 'bf2a6bfd'),
              'exact_baseline_gate_ever_matched': any(c == 'ea733050' for _, c in trace),
              'final_raw_equal_to_previous_hardware_v011': digest(H/'comparison-miss.raw') == digest(P/'analysis/hardware/native-game-target-init-v0.1.1-user-run-0001/comparison-miss.raw'),
              'all_double_readbacks_stable_and_CRC_independently_validated': json.loads((A/'capture-audit.json').read_text())['all_capture_checks'],
              'loader_timeout_errno': 110, 'loader_wait_limit_ms': 30000,
              'shutdown_pause_and_stop_returned': 'RETURN MainActivity_NativeOnPause' in log and 'RETURN MainActivity_NativeOnStop' in log,
              'shutdown_stopped_before_job_audio_periodic_signals': not any(x in log for x in ['JOB ', 'AUDIO ', 'PERIODIC ']),
              'resource_cleanup_not_reached': 'RESOURCES JNI=' not in log,
              'exit_marker_absent': not (H/'exit.txt').exists(),
              'START_seen_in_retained_loop': 'START: cleanup incomplete; live resources retained' in log,
              'hardware_generic_workers': generic_workers(H/'threads-after_loader_wait.json'),
              'software_generic_workers': generic_workers(S/'threads-before_pause.json'),
              'process_commit_bytes': max(m['commit'] for m in memory),
              'normal_allocator_footprint_peak': max(m['normal_allocator_arena'] for m in memory),
              'memory_refusals': max(m['donor_refusals'] for m in memory),
              'runtime_failures': max(m['runtime_failures'] for m in memory),
              'source_folder_unchanged': True, 'new_hardware_run_authorized': False}
    pairs = []
    for hf, sf in [(75, 298), (76, 299), (351, 351), (352, 352), (400, 400)]:
        name_h, name_s = f'checkpoint-{hf:04d}.raw.gx', f'checkpoint-{sf:04d}.raw.gx'
        hw, sw = writes(H/name_h), writes(S/name_s)
        assert len(hw) == len(sw)
        assert all((a['reg'], a['mask']) == (b['reg'], b['mask']) for a, b in zip(hw, sw))
        diffs = [{'write': i, 'register': a['reg'], 'hardware': a['value'], 'software': b['value']}
                 for i, (a, b) in enumerate(zip(hw, sw)) if a['value'] != b['value']]
        assert len(diffs) == 2 and all(d['register'] == 0x85 for d in diffs)
        hb, sb = pica_bytes(H/name_h), pica_bytes(S/name_s)
        assert len(hb) == len(sb)
        hwords = struct.unpack('<'+'I'*(len(hb)//4), hb)
        swords = struct.unpack('<'+'I'*(len(sb)//4), sb)
        raw_differences = [4*i for i, (a, b) in enumerate(zip(hwords, swords)) if a != b]
        assert len(raw_differences) == 2
        hc = next(c for c in captures if c['frame'] == hf)
        sc = next(c for c in software_captures if c['frame'] == sf)
        assert hc['texture_digest'] == sc['texture_digest']
        tex_filter = [w['value'] for w in hw if w['reg'] == 0x83]
        assert tex_filter and all((p & 6) == 6 for p in tex_filter)
        pairs.append({'hardware_callback': hf, 'software_callback': sf, 'PICA_register_writes': len(hw),
                      'only_differences': diffs, 'different_register_name': 'GPUREG_TEXUNIT0_ADDR1',
                      'all_nonaddress_PICA_values_and_masks_equal': True,
                      'PICA_raw_word_difference_byte_offsets': raw_differences,
                      'texture0_min_and_mag_LINEAR': True, 'texture0_param_values': tex_filter,
                      'texture_FNV_equal': hc['texture_digest'] == sc['texture_digest'],
                      'vertex_input_FNV_hardware': next(i['draw_input_digest'] for i in inputs if i['frame'] == hf),
                      'texture_hashes_are_noncryptographic_not_full_content_proof': True})
    result['PICA_comparison_pairs'] = pairs
    result['known_incompatible_oracle_factor'] = 'Captured min/mag LINEAR state; previously saved Azahar Software evidence shows filtering acts as NEAREST. This does not prove attribution of every one of the9231 pixels.'
    result['HOME_close_explanation'] = 'fatal main loop calls aptMainLoop but ignores false; it never reaches process teardown while resources are retained. Suspending to HOME is not process exit.'
    observation_path = A/'user-observations.json'
    if observation_path.exists():
        result['user_clarification'] = json.loads(observation_path.read_text(encoding='utf-8'))
    result['unusual_POWER_behavior_cause_proven'] = False
    (A/'hardware-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ['overall_result', 'first_final_hardware_CRC_callback', 'loader_timeout_errno', 'hardware_generic_workers', 'software_generic_workers', 'all_double_readbacks_stable_and_CRC_independently_validated', 'final_raw_equal_to_previous_hardware_v011']}, indent=2))


if __name__ == '__main__':
    main()
