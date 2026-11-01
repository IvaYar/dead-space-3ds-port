"""One isolated software-Azahar run of the actual DS34 RGBA8 CIA payload."""
import ctypes as C
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import time
import zlib
from pathlib import Path

from PIL import Image, ImageDraw

P = Path(__file__).resolve().parents[1]
ROOT = P / 'analysis/azahar-ds34-rgba8-v0.1.0'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verify-existing', action='store_true', help='Offline validation only; never load the emulator')
parser.add_argument('--cycle', type=int, default=1)
args = parser.parse_args()
if ROOT.exists() and not args.verify_existing:
    raise SystemExit(f'Refusing to overwrite previous emulator evidence: {ROOT}')
if not args.verify_existing:
    os.environ['DEADSPACE_EMULATOR_ROOT'] = str(ROOT)
    import smoke_azahar as f


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if args.verify_existing:
        verify_existing()
        return
    build = P / '3ds/build-ds34-rgba8-v0.1.0'
    cia = build / 'ds34-rgba8.cia'
    app = build / 'cia-payload.cxi'
    data = cia.read_bytes()
    header, _, _, cert, ticket, tmd, _, size = struct.unpack_from('<IHHIIIIQ', data)
    offset = sum((n + 63) & ~63 for n in [header, cert, ticket, tmd])
    assert data[offset:offset + size] == app.read_bytes()
    assert struct.unpack_from('<Q', app.read_bytes(), 0x108)[0] == 0x000400000FDE6D00
    card = ROOT / 'Azahar/sdmc/3ds/ds34-rgba8-v0.1.0'
    card.mkdir(parents=True, exist_ok=True)
    (card / 'result.json').write_text('{"passed":true,"stale":true}\n')
    (card / 'exit.txt').write_text('STALE EXIT\n')
    core = C.CDLL(str((P / 'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    (ROOT / 'run-context.json').write_text(json.dumps({'cycle': args.cycle}) + '\n')
    press_start = False

    @C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
    def input_state(port, device, index, key):
        if port == 0 and device == 1 and index == 0:
            return int(press_start) if key == 3 else int(f.button_a) if key == 8 else 0
        return 0

    for name, callback in [('environment', f.environment), ('video_refresh', f.video),
            ('audio_sample', f.audio), ('audio_sample_batch', f.audio_batch),
            ('input_poll', f.poll), ('input_state', input_state)]:
        setter = getattr(core, 'retro_set_' + name)
        setter.argtypes = [type(callback)]
        setter(callback)
    core.retro_load_game.argtypes = [C.POINTER(f.GameInfo)]
    core.retro_load_game.restype = C.c_bool
    core.retro_init()
    info = f.GameInfo(str(app.resolve()).encode(), None, 0, None)
    assert core.retro_load_game(C.byref(info))
    started = time.monotonic()
    ready_frame = sent = None
    result = card / 'result.json'
    exit_ok = False
    try:
        for frame in range(5400):
            if (card / 'ready.txt').exists() and ready_frame is None:
                assert not result.exists() and not (card / 'exit.txt').exists()
                ready_frame = frame
            if ready_frame is not None and sent is None and frame >= ready_frame + 30:
                assert not (card / 'frame-00.raw').exists(), 'GPU ran before A'
                sent = frame
            f.button_a = sent is not None and sent <= frame < sent + 10
            core.retro_run()
            if sent is not None and result.exists() and result.stat().st_size:
                break
            assert time.monotonic() - started < 90, 'Host deadline; inspect last phase'
        assert result.exists(), 'No result'
        for _ in range(3):
            core.retro_run()
        f.save_frame(ROOT / 'screen.png')
        native = json.loads(result.read_text())
        # Save even a failure so the diagnostic cycle remains reviewable.
        shutil.copyfile(result, ROOT / 'guest-result.json')
        assert native['passed'], native
        before_start = (ROOT / 'azahar-host.log').stat().st_size
        f.button_a = False
        press_start = True
        for _ in range(180):
            core.retro_run()
            exit_file = card / 'exit.txt'
            cleanup = (ROOT / 'azahar-host.log').read_bytes()[before_start:].decode(errors='replace')
            if (exit_file.exists() and exit_file.read_text() == 'GPU drained; returning to HOME\n'
                    and 'ReleaseRight:999: called' in cleanup
                    and 'operation=0x00000001, addr0=0x08000000' in cleanup):
                exit_ok = True
                (ROOT / 'START-cleanup.log').write_text(cleanup)
                break
        assert exit_ok, 'No guest START cleanup marker'
    finally:
        core.retro_unload_game()
        core.retro_deinit()
        for source in card.glob('*.json'):
            shutil.copyfile(source, ROOT / ('guest-result.json' if source.name == 'result.json' else source.name))
        if (card / 'gpu-test.log').exists():
            shutil.copyfile(card / 'gpu-test.log', ROOT / 'gpu-test.log')
    verify_existing(round(time.monotonic() - started, 3))


def verify_existing(elapsed_seconds=None):
    build = P / '3ds/build-ds34-rgba8-v0.1.0'
    cia = build / 'ds34-rgba8.cia'
    app = build / 'cia-payload.cxi'
    card = ROOT / 'Azahar/sdmc/3ds/ds34-rgba8-v0.1.0'
    native = json.loads((ROOT / 'guest-result.json').read_text())
    assert native['passed']
    assert (card / 'exit.txt').read_text() == 'GPU drained; returning to HOME\n'
    cleanup = (ROOT / 'START-cleanup.log').read_text()
    assert 'ReleaseRight:999: called' in cleanup and 'operation=0x00000001, addr0=0x08000000' in cleanup
    assert native['frames'] == 9 and native['gpu_draws'] == 9 and native['gpu_triangles'] == 18
    assert native['bytes'] == 288000 and native['layout'] == 1
    for key in ['gl_error', 'cpu_fragments', 'cpu_samples', 'bad_retirement', 'vertex_mismatches', 'texture_mismatches']:
        assert native[key] == 0, (key, native[key])
    assert native['retired_runs'] >= 9 and native['environment'] == 'emulator'
    host = (ROOT / 'azahar-host.log').read_text(errors='replace')
    errors = re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo|Memory permission|Assertion failed).*', host)
    assert not errors, errors[:8]
    assert (ROOT / 'azahar-host.log').stat().st_size < 524288, 'Host log truncated'
    log = (ROOT / 'gpu-test.log').read_text()
    for marker in ['ATTACH OK', 'PRESENT OK', 'FRAME PIXELS AND CAPTURE PASS', 'TEST PASS', 'EXIT GPU DRAINED']:
        assert marker in log, marker
    observations = []
    for frame in range(9):
        raw = (card / f'frame-{frame:02}.raw').read_bytes()
        meta = json.loads((card / f'frame-{frame:02}.json').read_text())
        assert len(raw) == meta['bytes'] == 288000 and meta['layout'] == 1
        assert f'{zlib.crc32(raw):08x}' == meta['crc32']
        # Independent decode, same established CTR BGR layout as export_native_frame.
        rgb = bytearray()
        for y in range(239, -1, -1):
            for x in range(400):
                offset = (x * 240 + y) * 3
                rgb.extend(raw[offset:offset + 3][::-1])
        image = Image.frombytes('RGB', (400, 240), bytes(rgb))
        step = min(frame, 6)
        left = 40 + 32 * step
        color = (255, 255, 255) if step == 0 else [(255, 0, 0), (0, 255, 0), (0, 0, 255)][(step - 1) % 3]
        expected = Image.new('RGB', (400, 240), (104, 176, 216))
        ImageDraw.Draw(expected).rectangle((left, 120, left + 63, 199), fill=color)
        image.save(ROOT / f'frame-{frame:02}.png')
        assert image.tobytes() == expected.tobytes(), f'Whole-frame color/layout mismatch {frame}'
        observations.append({'frame': frame, 'raw_sha256': hashlib.sha256(raw).hexdigest(),
                             'png_sha256': sha(ROOT / f'frame-{frame:02}.png'),
                             'foreground_RGB': color, 'rectangle_left': left, 'pixels_verified': 96000})
    assert len({o['raw_sha256'] for o in observations[:7]}) == 7
    assert len({o['raw_sha256'] for o in observations[6:]}) == 1, 'Repeated final frames unstable'
    queue = [json.loads(q.read_text()) for q in sorted((ROOT).glob('queue-*.json'))]
    runs = [q for q in queue if q['phase'] == 'before-run' and q['total']]
    retired = [q for q in queue if q['phase'] == 'before-clear' and q['total']]
    assert len(runs) == len(retired) == 10  # One attach texture copy plus nine frames.
    for run, done in zip(runs, retired):
        assert run['entries'] == done['entries']
        assert done['total'] == done['submitted'] == done['completed']
    assert [e[0] & 255 for e in runs[0]['entries']] == [4]
    for run in runs[1:]:
        assert [e[0] & 255 for e in run['entries']] == [2, 1, 3]
    report = {'passed': True, 'diagnostic_cycle': json.loads((ROOT / 'run-context.json').read_text())['cycle'], 'hardware_tested': False,
              'tested_payload': 'NCCH extracted from actual CIA; installation not emulated',
              'CIA_sha256': sha(cia), 'payload_sha256': sha(app), 'guest_result': native,
              'first_frame_verified': True, 'frames_verified': 9, 'unique_frames': 7,
              'identical_final_frames_verified': 3, 'all_pixels_verified_per_frame': 96000,
              'queue_runs_completed': len(retired) - 1, 'initial_texture_copy_runs_completed': 1,
              'queue_kinds': ['FILL', 'PICA', 'DISPLAY'],
              'SDK_SYNCDRAW_FrameSync_and_handlers_preserved': True,
              'A_gate_stale_result_and_START_cleanup_verified': True,
              'invalid_accesses': len(errors), 'observations': observations,
              'elapsed_seconds': elapsed_seconds,
              'offline_revalidation_without_runtime_rerun': args.verify_existing,
              'limitations': ['Software emulator success is not native success', 'Cache service stubs remain',
                             'SDK waits are unbounded; hardware can hang', 'No textures/game/high-memory stress covered']}
    (ROOT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ['observations', 'guest_result']}, indent=2))


if __name__ == '__main__':
    main()
