"""Actual-CIA Azahar validation of the observer and its bounded timeout path."""
import argparse
import ctypes as C
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
from pathlib import Path
from PIL import Image

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / 'tools'))
from gx_watch_report import classify
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fault', action='store_true')
args = parser.parse_args()
SUFFIX = '-fault' if args.fault else ''
ROOT = P / ('analysis/azahar-ds34-gx-watch-v0.2.0' + SUFFIX)
if ROOT.exists():
    raise SystemExit(f'Refusing to overwrite emulator evidence: {ROOT}')
os.environ['DEADSPACE_EMULATOR_ROOT'] = str(ROOT)
import smoke_azahar as f


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    build = P / ('3ds/build-ds34-gx-watch-v0.2.0' + SUFFIX)
    cia = build / 'ds34-gx-watch.cia'
    app = build / 'cia-payload.cxi'
    raw = cia.read_bytes();header, _, _, cert, ticket, tmd, _, size = struct.unpack_from('<IHHIIIIQ', raw)
    offset = sum((n + 63) & ~63 for n in [header, cert, ticket, tmd])
    assert raw[offset:offset + size] == app.read_bytes()
    assert struct.unpack_from('<Q', app.read_bytes(), 0x108)[0] == 0x000400000FDE6E00
    parent = ROOT / 'Azahar/sdmc/3ds/ds34-gx-watch-v0.2.0'
    stale = parent / 'run-0001';stale.mkdir(parents=True)
    (stale / 'result.json').write_text('{"stale":true}\n');stale_hash = sha(stale / 'result.json')
    card = parent / 'run-0002'
    core = C.CDLL(str((P / 'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    press_start = False

    @C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
    def input_state(port, device, index, key):
        if (port, device, index) == (0, 1, 0):
            return int(press_start) if key == 3 else int(f.button_a) if key == 8 else 0
        return 0

    for name, cb in [('environment', f.environment), ('video_refresh', f.video), ('audio_sample', f.audio),
                     ('audio_sample_batch', f.audio_batch), ('input_poll', f.poll), ('input_state', input_state)]:
        setter = getattr(core, 'retro_set_' + name);setter.argtypes = [type(cb)];setter(cb)
    core.retro_load_game.argtypes = [C.POINTER(f.GameInfo)];core.retro_load_game.restype = C.c_bool
    core.retro_init();info = f.GameInfo(str(app.resolve()).encode(), None, 0, None)
    assert core.retro_load_game(C.byref(info))
    started = time.monotonic();ready = sent = None
    try:
        for frame in range(5400):
            if (card / 'ready.txt').exists() and ready is None:
                ready = frame
            if ready is not None and sent is None and frame >= ready + 30:
                assert not (card / 'observation.json').exists() and not (card / 'frame.raw').exists()
                sent = frame
            f.button_a = sent is not None and sent <= frame < sent + 10
            core.retro_run()
            result = card / 'result.json'
            if result.exists() and result.stat().st_size:
                break
            assert time.monotonic() - started < 90, 'Host deadline'
        assert (card / 'result.json').exists()
        for _ in range(3):
            core.retro_run()
        f.save_frame(ROOT / 'screen.png')
        native = json.loads((card / 'result.json').read_text())
        assert native['observation_saved'] and native['pica_saved'], native
        before_start = (ROOT / 'azahar-host.log').stat().st_size
        f.button_a = False;press_start = True;cleaned = False
        for _ in range(180):
            core.retro_run()
            exit_file = card / 'exit.txt'
            segment = (ROOT / 'azahar-host.log').read_bytes()[before_start:].decode(errors='replace')
            if (exit_file.exists() and exit_file.read_text() == 'GPU drained; returning to HOME\n'
                    and 'ReleaseRight:999: called' in segment and 'operation=0x00000001, addr0=0x08000000' in segment):
                cleaned = True;(ROOT / 'START-cleanup.log').write_text(segment);break
        assert cleaned, 'Guest cleanup not completed before host unload'
    finally:
        core.retro_unload_game();core.retro_deinit()
        for source in card.glob('*'):
            if source.is_file() and source.suffix in ['.json', '.log', '.pica', '.txt']:
                shutil.copyfile(source, ROOT / ('guest-result.json' if source.name == 'result.json' else source.name))
    assert sha(stale / 'result.json') == stale_hash
    obs = json.loads((ROOT / 'observation.json').read_text())
    assert obs['armed'] and obs['fault'] is args.fault and not obs['overflow'] and obs['critical_io_blocked'] == 0
    assert obs['pica_bytes'] == 1168 and not obs['pica_rejected']
    assert len(obs['submits']) == 3 and all(s['returned'] and s['result'] == 0 for s in obs['submits'])
    pre = [r for r in obs['queue_records'] if r['kind'] == 0 and r['queue']['total'] == 3]
    post = [r for r in obs['queue_records'] if r['kind'] == 1 and r['queue']['total'] == 3]
    assert len(pre) == len(post) == 1
    assert post[0]['queue']['submitted'] == 3
    fill, pica, transfer = pre[0]['entries']
    assert [e[0] & 255 for e in pre[0]['entries']] == [2, 1, 3]
    assert fill[2] == 0x68b0d8ff and fill[3] - fill[1] == fill[6] - fill[4] == 384000 and fill[7] == 0x02010201
    assert transfer[3:] == [0x019000f0, 0x019000f0, 0x1000, 0, 0]
    assert [s['words'] for s in obs['submits']] == pre[0]['entries']
    decision = obs['samples'][obs['decision_index']]
    assert decision['phase'] == 8 and decision['queue'] == dict(total=3, submitted=3, completed=3, capacity=32)
    assert decision['queue_stable'] and decision['events_consistent'] and decision['idle']
    assert decision['counts']['PSC0'] == decision['counts']['P3D'] == decision['counts']['PPF'] == 1
    assert decision['counts']['DMA'] == 0 and obs['vblank_phases'] == 2
    assert all(s['phase'] != 11 for s in obs['samples'][:obs['decision_index'] + 1])
    assert native['initial_error_before_End'] == native['cpu_fragments'] == native['cpu_samples'] == 0
    assert native['gpu_draws'] == 1 and native['gpu_triangles'] == 2 and native['game_called'] is False
    blob = (ROOT / 'first-frame.pica').read_bytes();assert len(blob) == pica[2] == 1168
    words = struct.unpack('<' + 'I' * (len(blob) // 4), blob);cursor = packets = 0;registers = {}
    while cursor < len(words):
        assert cursor + 1 < len(words)
        header = words[cursor + 1];extra = (header >> 20) & 0x7ff;reg = header & 65535
        assert cursor + 2 + extra <= len(words)
        values = [words[cursor], *words[cursor + 2:cursor + 2 + extra]]
        for i, value in enumerate(values):registers[reg + (i if header >> 31 else 0)] = value
        cursor += extra + 2;cursor += cursor & 1;packets += 1
    assert cursor == len(words) and registers[0x117] == 2  # Actual PICA RGBA8 color-buffer configuration.
    if args.fault:
        assert obs['window_timeout'] and 1900 <= obs['elapsed_ms'] <= 2300
        assert not obs['nonblock_attempted'] and not native['render_verified']
        assert native['GL_error_after_diagnostic_wait'] == 0x500
    else:
        assert not obs['window_timeout'] and 100 <= obs['elapsed_ms'] < 500
        assert obs['nonblock_attempted'] and obs['nonblock_result'] and native['render_verified']
        raw = (card / 'frame.raw').read_bytes();assert len(raw) == 288000
        rgb = bytearray()
        for y in range(239, -1, -1):
            for x in range(400):
                i = (x * 240 + y) * 3;rgb.extend(raw[i:i + 3][::-1])
        image = Image.frombytes('RGB', (400, 240), bytes(rgb));image.save(ROOT / 'frame.png')
        assert image.tobytes() == Image.open(P / 'analysis/azahar-ds34-rgba8-v0.1.0/frame-00.png').convert('RGB').tobytes()
        assert native['GL_error_after_diagnostic_wait'] == 0
    host = (ROOT / 'azahar-host.log').read_text(errors='replace')
    bad = re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo|Memory permission|Assertion failed).*', host)
    assert not bad and (ROOT / 'azahar-host.log').stat().st_size < 524288
    interpretation = classify(obs)
    assert interpretation['classification'] == ('emulator_diagnostic_fault' if args.fault else 'queue_retired')
    (ROOT / 'interpretation.json').write_text(json.dumps(interpretation, indent=2) + '\n')
    report = {'passed': True, 'fault_test': args.fault, 'hardware_tested': False, 'CIA_sha256': sha(cia),
              'payload_sha256': sha(app), 'post_Run_live_snapshot_verified': True,
              'three_submission_Results_verified': True, 'PSC0_P3D_PPF_deltas': [1, 1, 1],
              'decision_before_NONBLOCK_and_Clear': True, 'window_elapsed_ms': obs['elapsed_ms'],
              'critical_io_attempts': 0, 'PICA_payload_bounds_verified': True, 'PICA_packets': packets,
              'actual_PICA_RGBA8_configuration_verified': True, 'RGBA8_RGB8_draw_path_unchanged': True,
              'BGR8_whole_frame_verified': not args.fault, 'A_gate_and_preservation_of_old_run_verified': True,
              'START_guest_cleanup_before_host_unload': True, 'invalid_memory_accesses': 0,
              'diagnostic_fault_changes_real_GPU_queue': False,
              'interpretation': interpretation['classification'], 'elapsed_host_seconds': round(time.monotonic() - started, 3)}
    (ROOT / 'result.json').write_text(json.dumps(report, indent=2) + '\n');print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
