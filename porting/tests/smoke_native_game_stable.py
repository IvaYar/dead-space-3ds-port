"""Native entry-point PASS, CRC_FAIL and incomplete-cleanup checks in Azahar."""
import argparse
import ctypes as C
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
import zlib

P = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--container', choices=['cxi', 'cia'], default='cxi')
parser.add_argument('--variant', choices=['normal', 'poison', 'crc', 'retain'], default='normal')
parser.add_argument('--cycles', type=int, default=3)
parser.add_argument('--attempt', default='')
args = parser.parse_args()
assert 1 <= args.cycles <= 5 and (not args.attempt or args.attempt.isalnum())
assert args.container == 'cxi' or args.variant == 'normal'
assert args.variant != 'retain' or args.cycles == 1
ROOT = P/('analysis/azahar-native-game-v0.1.2-'+args.variant+'-'+args.container+('-'+args.attempt if args.attempt else ''))
assert not ROOT.exists(), 'Preserve prior evidence'
os.environ['DEADSPACE_EMULATOR_ROOT'] = str(ROOT)
import smoke_azahar as f
f.OPTIONS[b'citra_cpu_clock_percentage'] = b'400'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def finish(code):
    sys.stdout.flush()
    sys.stderr.flush()
    kernel = C.WinDLL('kernel32')
    kernel.GetCurrentProcess.restype = C.c_void_p
    kernel.TerminateProcess.argtypes = [C.c_void_p, C.c_uint]
    kernel.TerminateProcess(kernel.GetCurrentProcess(), code)


def read_json(p):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def packed(raw):
    out = bytearray()
    for b, g, r in zip(raw[0::3], raw[1::3], raw[2::3]):
        v = (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)
        out.extend((v & 255, v >> 8))
    return bytes(out)


def run_cycle(core, app, source, controls, cycle):
    evidence = ROOT/('cycle-%04d' % cycle)
    evidence.mkdir()
    run_dir = ROOT/('Azahar/sdmc/3ds/ds-native-game-v0.1.2/run-%04d' % cycle)
    host_start = len((ROOT/'azahar-host.log').read_text(errors='replace'))
    controls['start'] = False
    f.button_a = False
    f.shutdown = False
    f.frame = None
    game = f.GameInfo(str(app.resolve()).encode(), None, 0, None)
    assert core.retro_load_game(C.byref(game))
    started = time.monotonic()

    def timeout():
        (ROOT/'timeout.json').write_text(json.dumps({'passed': False, 'reason': 'host deadline', 'CXI_sha256': sha(app)})+'\n')
        finish(124)

    timer = threading.Timer(180, timeout)
    timer.daemon = True
    timer.start()
    cleaned = False
    final = validation = None
    frame_report = None
    for host_frame in range(40000):
        f.button_a = 60 <= host_frame < 70
        core.retro_run()
        if host_frame % 5:
            continue
        final = read_json(run_dir/'result.json')
        validation = read_json(run_dir/'validation.json')
        if not final or not validation:
            continue
        if final['frame_saved'] and args.variant in ['normal', 'retain'] and not controls['start']:
            frame_report = final
            (evidence/'frame-before-exit.json').write_text(json.dumps(final, indent=2)+'\n')
            f.save_frame(evidence/'screen.png')
            controls['start'] = True
            f.button_a = False
        host = (ROOT/'azahar-host.log').read_text(errors='replace')[host_start:]
        if final['status'] == 'blocked':
            # Capture retention before any host destruction of the guest.
            for _ in range(30):
                core.retro_run()
            break
        exit_file = run_dir/'exit.txt'
        marker = exit_file.exists() and 'Workers stopped; GPU drained;' in exit_file.read_text()
        cleaned = marker and 'ReleaseRight:999: called' in host and all('operation=0x00000001, addr0='+a in host for a in ['0x08000000', '0x30000000'])
        if cleaned:
            break
    timer.cancel()
    final = read_json(run_dir/'result.json')
    validation = read_json(run_dir/'validation.json')
    for q in run_dir.iterdir():
        if q.is_file() and q.suffix in ['.log', '.json', '.txt']:
            shutil.copyfile(q, evidence/('guest-result.json' if q.name == 'result.json' else q.name))
    host = (ROOT/'azahar-host.log').read_text(errors='replace')[host_start:]
    bad = re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo|Memory permission|Assertion failed|Exception Type:|LogException:).*', host)
    baseline = (source/'first-game-frame.raw').read_bytes()
    assert len(baseline) == 192000 and zlib.crc32(baseline) == 0xea733050
    different = None
    if (run_dir/'frame.raw').exists():
        raw = (run_dir/'frame.raw').read_bytes()
        assert len(raw) == 288000
        quantized = packed(raw)
        different = sum(quantized[i:i+2] != baseline[i:i+2] for i in range(0, len(baseline), 2))
    sequence = sorted(run_dir.glob('sequence-*.raw'))
    sequence_exact = all(len(q.read_bytes()) == 288000 and packed(q.read_bytes()) == baseline for q in sequence)
    log = (evidence/'native-game.log').read_text()
    captures = [json.loads(l[12:]) for l in log.splitlines() if l.startswith('CAPTUREJSON ')]
    capture_checks = bool(captures) and all(c['raw_crc_a'] == c['raw_crc_b'] and c['crc565_a'] == c['crc565_b'] and c['bytes'] == 288000 and c['column_stride'] == 720 for c in captures)
    for c in captures:
        raw = (run_dir/c['file']).read_bytes()
        capture_checks &= len(raw) == 288000 and f'{zlib.crc32(raw):08x}' == c['raw_crc_a'] and f'{zlib.crc32(packed(raw)):08x}' == c['crc565_a']
    inputs = [json.loads(l[10:]) for l in log.splitlines() if l.startswith('INPUTJSON ')]
    capture_checks &= len(inputs) == len(captures) and all(not c['capture_truncated'] and c['draw_input_count'] > 0 and (run_dir/c['file']).stat().st_size == c['command_bytes'] > 0 for c in inputs)
    quiesce = read_json(evidence/'threads-after_quiesce.json')
    joined = read_json(evidence/'threads-after_join.json')
    workers = [w for w in quiesce['workers'] if w['token'] & 255] if quiesce else []
    remaining = [w for w in joined['workers'] if w['token'] & 255] if joined else [None]
    resources = re.search(r'RESOURCES JNI=(\d+) stdio=(\d+) appdata=(\d+) IOactive=(\d+) opens/closes=(\d+)/(\d+) dirs=(\d+)', log)
    balanced = bool(resources and int(resources[4]) == 0 and resources[5] == resources[6] and int(resources[7]) == 0)
    proof = {'kernel_joins': sum(w['done'] == 1 and w['kernel_wait'] == 0 for w in workers),
             'worker_handles_remaining': len(remaining), 'files_balanced': balanced,
             'io_opens': int(resources[5]) if resources else None, 'io_closes': int(resources[6]) if resources else None}
    shutdown_exact = len(workers) == 6 and proof['kernel_joins'] == 6 and not remaining and balanced
    safe = bool(cleaned and shutdown_exact and final and final['safe_exit'] and validation and validation['cleanup_complete'])
    if args.variant == 'normal':
        expected = safe and final['status'] == 'passed' and validation['frame_status'] == 'PASS' and different == 0 and len(sequence) == validation['sequence_completed'] == 8 and sequence_exact
    elif args.variant == 'retain':
        expected = not cleaned and not final['safe_exit'] and not validation['cleanup_complete'] and final['status'] == 'blocked' and not (run_dir/'exit.txt').exists() and 'RESOURCES JNI=' not in log and 'ReleaseRight:999: called' not in host and 'operation=0x00000001, addr0=0x30000000' not in host
    else:
        expected = safe and final['status'] == 'failed' and not final['frame_saved'] and validation['frame_status'] == 'FAIL' and validation['callbacks_completed'] == 600 and (run_dir/'comparison-miss.raw').stat().st_size == 288000
    report = {'passed': bool(expected and capture_checks and not bad), 'variant': args.variant,
              'guest_frame_pass': bool(validation and validation['frame_status'] == 'PASS'),
              'safe_exit': safe, 'both_heaps_released': bool(cleaned), 'different_pixels': different,
              'sequence_frames': len(sequence), 'sequence_exact': sequence_exact, 'readback_and_independent_CRC_checks': bool(capture_checks),
              'invalid_memory_accesses': bad, 'shutdown_proof': proof, 'frame_guest_result': frame_report,
              'final_guest_result': final, 'validation': validation, 'cycle': cycle,
              'CXI_sha256': sha(app), 'hardware_tested': False, 'elapsed_host_seconds': round(time.monotonic()-started, 3)}
    (evidence/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Cycle', cycle, 'expectation PASS' if report['passed'] else 'FAIL', 'guest', final['status'] if final else None, 'safe_exit', safe, flush=True)
    return report


def main():
    build = P/('3ds/build-native-game-v0.1.2-'+args.variant)
    app = build/'native-game.cxi'
    if args.container == 'cia':
        sys.path.insert(0, str(P/'tools'))
        from build_native_startup_legacy import payload
        import struct
        data = payload((build/'native-game.cia').read_bytes())
        assert data == app.read_bytes() and struct.unpack_from('<Q', data, 0x108)[0] == 0x000400000FDE7500
        ROOT.mkdir(exist_ok=True)
        app = ROOT/'tested-CIA-payload.cxi'
        app.write_bytes(data)
    source = P/'analysis/azahar-gpu-engine/Azahar/sdmc/3ds/deadspace'
    card = ROOT/'Azahar/sdmc/3ds/deadspace'
    card.mkdir(parents=True)
    for name in ['assets', 'apk-assets']:
        shutil.copytree(source/name, card/name)
    shutil.copytree(source/'test-output/font-subset', card/'test-output/font-subset')
    for name in ['assets-verified.txt', 'apk-assets-verified.txt']:
        shutil.copyfile(source/name, card/name)
    shutil.copyfile(P/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so', card/'libEAMGameDeadSpace_orig.so')
    core = C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    controls = {'start': False}

    @C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
    def input_state(port, device, index, key):
        if (port, device, index) == (0, 1, 0):
            return int(controls['start']) if key == 3 else int(f.button_a) if key == 8 else 0
        return 0

    for name, cb in [('environment', f.environment), ('video_refresh', f.video), ('audio_sample', f.audio), ('audio_sample_batch', f.audio_batch), ('input_poll', f.poll), ('input_state', input_state)]:
        setter = getattr(core, 'retro_set_'+name)
        setter.argtypes = [type(cb)]
        setter(cb)
    core.retro_load_game.argtypes = [C.POINTER(f.GameInfo)]
    core.retro_load_game.restype = C.c_bool
    core.retro_init()
    reports = []
    for cycle in range(1, args.cycles+1):
        r = run_cycle(core, app, source, controls, cycle)
        reports.append(r)
        if not r['passed'] or args.variant == 'retain':
            break
        core.retro_unload_game()
    if args.variant != 'retain':
        core.retro_deinit()
    report = {**reports[-1], 'passed': len(reports) == args.cycles and all(q['passed'] for q in reports),
              'sequential_cycles': len(reports), 'cycles': reports, 'same_core_and_SD': True,
              'runner_sha256': sha(Path(__file__)), 'container': args.container,
              'CIA_sha256': sha(build/'native-game.cia') if args.container == 'cia' else None,
              'CIA_payload_verified': args.container == 'cia', 'title_id': '000400000FDE7500'}
    (ROOT/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    finish(0 if report['passed'] else 1)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        import traceback
        text = traceback.format_exc()
        ROOT.mkdir(exist_ok=True, parents=True)
        (ROOT/'host-error.txt').write_text(text)
        print(text, flush=True)
        finish(2)
