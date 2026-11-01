"""Read-only run audit; correlate captures by donor inputs rather than callback number."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib
import numpy as np
from analyze_native_game_image import P, unpack8, unpack565, quantize
from audit_pica_outputs import command_list


def gx_records(path):
    blob = path.read_bytes()
    offset, records = 0, []
    while offset < len(blob):
        assert len(blob)-offset >= 36, 'Truncated GX record'
        *words, count = struct.unpack_from('<9I', blob, offset)
        offset += 36
        assert count <= len(blob)-offset and count % 4 == 0
        payload = blob[offset:offset+count]
        offset += count
        kind = words[0] & 255
        assert kind == 1 or not count
        record = {'type': kind, 'words': words, 'PICA_bytes': count}
        if kind == 1:
            assert count == words[2] and count > 0
            decoded = command_list(payload)
            record |= {'PICA_sha256': hashlib.sha256(payload).hexdigest(),
                       'PICA_packets': len(decoded['packets']), 'PICA_writes': len(decoded['writes'])}
        if kind == 3:
            record['display_RGBA8_to_RGB8_240x400'] = words[3:6] == [0x019000f0, 0x019000f0, 0x1000]
        records.append(record)
    assert records and offset == len(blob)
    return records


def inspect(run):
    run = run.resolve()
    log = (run/'native-game.log').read_text()
    inputs = {r['file']: r for l in log.splitlines() if l.startswith('INPUTJSON ') for r in [json.loads(l[10:])]}
    baseline = unpack565((P/'analysis/gpu-safety/first-game-frame.raw').read_bytes())
    captures = []
    for line in log.splitlines():
        if not line.startswith('CAPTUREJSON '):
            continue
        r = json.loads(line[12:])
        raw = (run/r['file']).read_bytes()
        q = quantize(unpack8(raw))
        words = ((q[..., 0] << 11) | (q[..., 1] << 5) | q[..., 2]).T[:, ::-1].astype('<u2').tobytes()
        crc8, crc565 = f'{zlib.crc32(raw):08x}', f'{zlib.crc32(words):08x}'
        source = inputs[r['file']+'.gx']
        records = gx_records(run/source['file'])
        stable = r['raw_crc_a'] == r['raw_crc_b'] == crc8 and r['crc565_a'] == r['crc565_b'] == crc565
        complete = not source['capture_truncated'] and sum(c['type'] == 1 for c in records) > 0
        captures.append({**r, **source, 'raw_file': r['file'], 'readback_crc_independently_verified': stable,
                         'command_capture_complete': complete, 'GX': records,
                         'different_pixels_from_frozen_reference': int(np.any(q != baseline, axis=-1).sum()),
                         'state_key': [source['draw_input_digest'], source['draw_input_count'], r['texture_digest'], *r['viewport']]})
    return {'run': str(run), 'captures': captures, 'result': json.loads((run/'result.json').read_text()),
            'validation': json.loads((run/'validation.json').read_text()),
            'all_capture_checks': bool(captures) and all(c['readback_crc_independently_verified'] and c['command_capture_complete'] and all(r.get('display_RGBA8_to_RGB8_240x400', True) for r in c['GX']) for c in captures)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = inspect(args.run)
    if args.compare:
        reference = inspect(args.compare)
        pairs = []
        for c in result['captures']:
            candidates = [r for r in reference['captures'] if r['state_key'] == c['state_key']]
            pairs.append({'frame': c['frame'], 'raw_file': c['raw_file'], 'candidate_frames_with_same_input_digest': [r['frame'] for r in candidates],
                          'input_digest_is_noncryptographic_not_proof_of_identity': True,
                          'same_RGB565_CRC_found': any(r['crc565_a'] == c['crc565_a'] for r in candidates)})
        result['comparison'] = {'reference_run': reference['run'], 'pairs': pairs,
                                'note': 'Inspect GX/PICA and state as well: equal FNV digests alone do not prove equal inputs.'}
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        with args.output.open('x') as out:
            out.write(text)
    else:
        print(text)


if __name__ == '__main__':
    main()
