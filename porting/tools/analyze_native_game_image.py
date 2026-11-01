"""Exact offline comparison. Raw game pixels/derived PNGs remain private."""
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import zlib
import numpy as np
from PIL import Image, ImageDraw

P = Path(__file__).resolve().parents[1]
A = P/'analysis/native-game-stable-v0.1.2'


def crc(data):
    return f'{zlib.crc32(data):08x}'


def unpack565(raw):
    words = np.frombuffer(raw, '<u2').reshape(400, 240)[:, ::-1].T
    return np.stack((words >> 11, (words >> 5) & 63, words & 31), axis=-1).astype(np.int16)


def unpack8(raw):
    assert len(raw) == 288000
    return np.frombuffer(raw, np.uint8).reshape(400, 240, 3)[:, ::-1, ::-1].transpose(1, 0, 2).astype(np.int16)


def quantize(rgb):
    return rgb >> np.array([3, 2, 3])


def components(mask):
    seen = mask.copy()
    result = []
    for y, x in zip(*np.where(mask)):
        if not seen[y, x]:
            continue
        seen[y, x] = False
        pending = deque([(int(y), int(x))])
        points = []
        while pending:
            r, c = pending.popleft()
            points.append((r, c))
            for rr, cc in [(r-1, c), (r+1, c), (r, c-1), (r, c+1)]:
                if 0 <= rr < 240 and 0 <= cc < 400 and seen[rr, cc]:
                    seen[rr, cc] = False
                    pending.append((rr, cc))
        rows, cols = zip(*points)
        result.append({'pixels': len(points), 'bbox_xy': [min(cols), min(rows), max(cols), max(rows)]})
    return sorted(result, key=lambda c: -c['pixels'])


def stats(a, b):
    delta = a-b
    mask = np.any(delta, axis=-1)
    y, x = np.where(mask)
    nonblack_a, nonblack_b = np.any(a, axis=-1), np.any(b, axis=-1)
    c = components(mask)
    return {'different_pixels': int(mask.sum()), 'bbox_xy': [int(x.min()), int(y.min()), int(x.max()), int(y.max())] if len(x) else None,
            'different_channels': [int(np.count_nonzero(delta[..., k])) for k in range(3)],
            'signed_channel_delta_histograms': [{str(int(v)): int(n) for v, n in zip(*np.unique(delta[..., k][mask], return_counts=True))} for k in range(3)],
            'max_abs_channel_delta': np.abs(delta).max(axis=(0, 1)).tolist(),
            'all_deltas_at_most_one': int((mask & (np.abs(delta).max(axis=-1) <= 1)).sum()),
            'nonblack_a': int(nonblack_a.sum()), 'nonblack_b': int(nonblack_b.sum()),
            'a_nonblack_b_black': int((nonblack_a & ~nonblack_b).sum()),
            'a_black_b_nonblack': int((~nonblack_a & nonblack_b).sum()),
            'row_differences': mask.sum(axis=1).tolist(), 'column_differences': mask.sum(axis=0).tolist(),
            'grid_20x20': [[int(mask[y:y+20, x:x+20].sum()) for x in range(0, 400, 20)] for y in range(0, 240, 20)],
            'connected_component_count_4_neighbours': len(c), 'largest_components': c[:30],
            'delta_vectors_most_common': [{'delta': list(k), 'pixels': n} for k, n in Counter(map(tuple, delta[mask].tolist())).most_common(30)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extra', type=Path, help='Additional BGR8 capture for comparison with frozen reference')
    parser.add_argument('--tag', default='hardware')
    args = parser.parse_args()
    assert args.tag.isalnum()
    hardware = (args.extra or P/'analysis/hardware/native-game-target-init-v0.1.1-user-run-0001/comparison-miss.raw').resolve()
    reference = P/'analysis/gpu-safety/first-game-frame.raw'
    azahar = P/'analysis/azahar-native-game-v0.1.1-black-cxi/Azahar/sdmc/3ds/ds-native-game-v0.1.1/run-0001/frame.raw'
    raw, ref, azraw = hardware.read_bytes(), reference.read_bytes(), azahar.read_bytes()
    rgb, azrgb = unpack8(raw), unpack8(azraw)
    q, qref, qaz = quantize(rgb), unpack565(ref), quantize(azrgb)
    assert np.array_equal(qaz, qref) and crc(ref) == 'ea733050'
    little_words = ((q[..., 0] << 11) | (q[..., 1] << 5) | q[..., 2]).T[:, ::-1].astype('<u2').tobytes()
    result = {'input': str(hardware.relative_to(P)), 'reference': str(reference.relative_to(P)),
              'input_sha256': hashlib.sha256(raw).hexdigest(), 'reference_sha256': hashlib.sha256(ref).hexdigest(),
              'raw_BGR8_crc32': crc(raw), 'quantized_RGB565_crc32': crc(little_words),
              'reference_RGB565_crc32': crc(ref), 'RGB565': stats(q, qref), 'RGB8_vs_Azahar_RGB8': stats(rgb, azrgb)}
    transforms = {'BGR8_CTR': q, 'RGB8_channel_swap': q[..., ::-1], 'vertical_flip': q[::-1], 'horizontal_flip': q[:, ::-1],
                  'rotate_180': q[::-1, ::-1], 'row_major_BGR8': quantize(np.frombuffer(raw, np.uint8).reshape(240, 400, 3)[..., ::-1].astype(np.int16))}
    # Requantize after swapping RGB8 (R/B bit widths are both 5).
    result['layout_hypotheses_different_pixels'] = {n: int(np.any(t != qref, axis=-1).sum()) for n, t in transforms.items()}
    shifts = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            a, b = q[max(0, dy):240+min(0, dy), max(0, dx):400+min(0, dx)], qref[max(0, -dy):240-max(0, dy), max(0, -dx):400-max(0, dx)]
            shifts.append({'dx': dx, 'dy': dy, 'different_pixels_in_overlap': int(np.any(a != b, axis=-1).sum()), 'overlap_pixels': a.shape[0]*a.shape[1]})
    result['small_shift_hypotheses'] = shifts
    mask = np.any(q != qref, axis=-1)
    active = np.any(qref, axis=-1) | np.any(q, axis=-1)
    yy, xx = np.indices(mask.shape)
    result['periodicity'] = {str(n): {'x_differences': [int(mask[xx % n == i].sum()) for i in range(n)],
                                    'x_active_denominators': [int(active[xx % n == i].sum()) for i in range(n)],
                                    'y_differences': [int(mask[yy % n == i].sum()) for i in range(n)]} for n in [2, 4, 8, 16, 32, 64]}
    lower = slice(180, 220)
    result['lower_fragments_y180_219'] = {'reference_nonblack': int(np.any(qref[lower], axis=-1).sum()),
                                        'azahar_nonblack': int(np.any(qaz[lower], axis=-1).sum()),
                                        'input_nonblack': int(np.any(q[lower], axis=-1).sum()),
                                        'different_pixels': int(mask[lower].sum()),
                                        'reference_components': components(np.any(qref, axis=-1) & (yy >= 180) & (yy < 220))[:20]}
    # Existing early EA captures are independent evidence for possible stale
    # compositing; equality of black background alone is never evidence.
    early = []
    frag = np.any(qref, axis=-1) & (yy >= 180) & (yy < 220)
    for path in sorted((P/'analysis/gpu-sequence-8-17').glob('gpu-frame-*.raw')):
        e = unpack565(path.read_bytes())
        early.append({'frame': path.stem, 'equal_at_reference_nonblack_fragments': int((np.all(e == qref, axis=-1) & frag).sum()),
                      'total_reference_fragments': int(frag.sum()), 'early_nonblack_y180_219': int(np.any(e[lower], axis=-1).sum())})
    result['early_EA_comparison'] = early
    out = A/(args.tag+'-image-comparison.json')
    assert not out.exists(), 'Preserve existing image analysis'
    out.write_text(json.dumps(result, indent=2)+'\n')
    private = A/'private-images'
    private.mkdir(exist_ok=True)
    diff = np.zeros((240, 400, 3), np.uint8)
    diff[mask] = [255, 60, 20]
    diff[mask & (np.abs(q-qref).max(axis=-1) <= 1)] = [255, 220, 0]
    montage = Image.new('RGB', (800, 530))
    draw = ImageDraw.Draw(montage)
    for x, y, label, pixels in [(0, 0, 'Frozen Azahar RGB8', azrgb), (400, 0, 'Input RGB8', rgb),
                               (0, 265, 'RGB565 delta: yellow <=1, red >1', diff), (400, 265, 'Lower reference fragments, x1', np.where((yy >= 180)[..., None], azrgb, 0))]:
        draw.text((x+4, y+4), label, fill='white')
        montage.paste(Image.fromarray(pixels.astype(np.uint8)), (x, y+22))
    montage.save(private/(args.tag+'-comparison.png'))
    print(json.dumps({k: result[k] for k in ['raw_BGR8_crc32', 'quantized_RGB565_crc32', 'layout_hypotheses_different_pixels', 'lower_fragments_y180_219']}, indent=2))
    print('RGB565 different:', result['RGB565']['different_pixels'], 'RGB8 different:', result['RGB8_vs_Azahar_RGB8']['different_pixels'])


if __name__ == '__main__':
    main()
