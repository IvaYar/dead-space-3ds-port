"""Headless Horizon/SD smoke test using the official Azahar 2126.2 libretro core.

No emulator UI is opened; the test uses software rendering and its own local SD directory.
"""

import ctypes as C
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import time
import zlib

PORTING = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('DEADSPACE_EMULATOR_ROOT',str(PORTING / 'analysis/azahar-smoke'))).resolve()
if (PORTING/'analysis').resolve() not in ROOT.parents:raise ValueError('Emulator output must be inside workspace analysis')
ROOT.mkdir(parents=True, exist_ok=True)
OPTIONS = {
    b"citra_graphics_api": b"Software", b"citra_is_new_3ds": b"New 3DS",
    b"citra_use_virtual_sd": b"enabled", b"citra_use_libretro_save_path": b"LibRetro Default",
    b"citra_audio_emulation": b"hle", b"citra_use_cpu_jit": b"enabled",
}
DEFAULTS = {}
PATH_BYTES = str(ROOT.resolve()).encode()
frame = None
shutdown = False
button_a = False
pointer_pressed = False
pointer_x = 0
pointer_y = 0
_host_bytes=0
(ROOT/'azahar-host.log').write_bytes(b'')
@C.CFUNCTYPE(None,C.c_int,C.c_char_p,C.c_void_p)
def host_log(level,fmt,arg):
    global _host_bytes
    if not fmt:return
    message=C.string_at(arg) if fmt in (b'%s',b'%s\n') and arg else fmt
    if _host_bytes>=524288 or (level<2 and b'ControlMemory' not in message and b'HeapAllocate' not in message):return
    line=str(level).encode()+b' '+message[:2048]+b'\n';_host_bytes+=len(line)
    with (ROOT/'azahar-host.log').open('ab') as f:f.write(line)


class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


@C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
def environment(command, data):
    global shutdown
    command &= ~0x10000
    if command == 27:
        C.cast(data,C.POINTER(C.c_void_p))[0]=C.cast(host_log,C.c_void_p).value
        return True
    if command in (9, 31):
        C.cast(data, C.POINTER(C.c_char_p))[0] = PATH_BYTES
        return True
    if command == 15:
        var = C.cast(data, C.POINTER(Variable)).contents
        value = OPTIONS.get(var.key, DEFAULTS.get(var.key))
        if value is not None: var.value = value; return True
        return False
    if command == 16:
        values = C.cast(data, C.POINTER(Variable))
        i = 0
        while values[i].key:
            desc = values[i].value or b""
            DEFAULTS[values[i].key] = desc.split(b"; ")[-1].split(b"|")[0]
            i += 1
        return True
    if command == 52: C.cast(data, C.POINTER(C.c_uint))[0] = 0; return True
    if command == 10: return C.cast(data, C.POINTER(C.c_int))[0] == 1
    if command == 17: C.cast(data, C.POINTER(C.c_bool))[0] = False; return True
    if command == 3: C.cast(data, C.POINTER(C.c_bool))[0] = True; return True
    if command == 39: C.cast(data, C.POINTER(C.c_uint))[0] = 0; return True
    if command == 47: C.cast(data, C.POINTER(C.c_int))[0] = 3; return True
    if command == 7: shutdown = True; return True
    if command in (1, 11, 18, 32, 35, 36, 37, 55): return True
    return False


@C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
def video(data, width, height, pitch):
    global frame
    if data and data != C.c_void_p(-1).value:
        frame = (width, height, pitch, C.string_at(data, pitch * height))


@C.CFUNCTYPE(None, C.c_int16, C.c_int16)
def audio(left, right): pass


@C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
def audio_batch(data, frames): return frames


@C.CFUNCTYPE(None)
def poll(): pass


@C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
def input_state(port, device, index, identifier):
    if port!=0 or index!=0:return 0
    if device==1 and identifier==8:return int(button_a)
    if device==2 and identifier==2:return int(pointer_pressed)
    if device==6:return pointer_x if identifier==0 else pointer_y if identifier==1 else int(pointer_pressed) if identifier==2 else 0
    return 0

def set_touch(pressed,x=160,y=120):
    """Real libretro pointer on the lower LCD of the fixed 400x480 layout."""
    global pointer_pressed,pointer_x,pointer_y
    if type(pressed) is not bool or type(x) is not int or type(y) is not int or not 0<=x<320 or not 0<=y<240:
        raise ValueError('Touch requires bool pressed and integer coordinates within 320x240')
    # Match Azahar2126.2 MouseTracker's +/-0x7fff canvas conversion. Aim at
    # pixel centers so the core's integer conversion lands inside each pixel.
    pointer_x=round((40+x+.5)/400*65534-32767)
    pointer_y=round((240+y+.5)/480*65534-32767)
    pointer_pressed=pressed


def save_frame(path):
    width, height, pitch, data = frame
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            offset = y * pitch + x * 4
            raw.extend((data[offset + 2], data[offset + 1], data[offset]))
    def chunk(name, value):
        return struct.pack(">I", len(value)) + name + value + struct.pack(">I", zlib.crc32(name + value))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def main():
    global button_a
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("3dsx", "cxi"), default="3dsx")
    parser.add_argument("--stage", type=int, choices=(1, 2, 3, 4, 5, 6, 7, 8), default=1)
    parser.add_argument("--case", choices=("present", "missing", "wrong", "ready", "asset-missing", "asset-wrong", "repeat", "stalled", "bad-ctor"), default="present")
    args = parser.parse_args()
    if args.case.startswith("asset-") and args.stage not in (4,6): parser.error("Asset cases belong to stages 4/6")
    if args.case == "repeat" and args.stage not in (5,6,7,8): parser.error("Repeat case belongs to stages 5/6/7")
    if args.case == "stalled" and args.stage not in (7,8): parser.error("Stalled case belongs to stage 7")
    if args.case == "bad-ctor" and args.stage!=8: parser.error("Bad constructor case belongs to stage 8")
    library = PORTING / "toolchain/azahar-libretro/azahar_libretro.dll"
    if not library.exists():
        candidates = list(library.parent.glob("*.dll"))
        library = candidates[0]
    core = C.CDLL(str(library.resolve()))
    for name, callback in (("environment", environment), ("video_refresh", video), ("audio_sample", audio),
                           ("audio_sample_batch", audio_batch), ("input_poll", poll), ("input_state", input_state)):
        setter = getattr(core, "retro_set_" + name); setter.argtypes = [type(callback)]; setter(callback)
    core.retro_load_game.argtypes = [C.POINTER(GameInfo)]; core.retro_load_game.restype = C.c_bool
    core.retro_init()
    for base in (ROOT / "Azahar/sdmc",):
        target = base / "3ds/deadspace"; target.mkdir(parents=True, exist_ok=True)
        donor_path = target / "libEAMGameDeadSpace_orig.so"
        if args.case == "missing":
            if donor_path.exists(): donor_path.unlink()
        else:
            shutil.copyfile(PORTING / "analysis/candidate-sd/libEAMGameDeadSpace_orig.so", donor_path)
            if args.case == "wrong":
                data = bytearray(donor_path.read_bytes()); data[-1] ^= 1; donor_path.write_bytes(data)
        if args.stage in (4,6):
            asset = target / "assets/published/data/achievements.sb"
            asset.parent.mkdir(parents=True, exist_ok=True)
            if args.case == "asset-missing":
                if asset.exists(): asset.unlink()
            else:
                data = bytearray((PORTING / "analysis/candidate-sd/assets/published/data/achievements.sb").read_bytes())
                if args.case == "asset-wrong": data[-1] ^= 1
                asset.write_bytes(data)
        log_name = {1: "stage1-log.txt", 2: "stage2-v0.2.2-log.txt", 3: "stage3-v0.3.0-log.txt", 4: "stage4-v0.4.0-log.txt", 5: "stage5-v0.5.0-log.txt", 6:"stage6-v0.6.0-log.txt", 7:"stage7-v0.7.0-log.txt",8:"stage8-v0.8.0-log.txt"}[args.stage]
        log = target / log_name
        if log.exists(): log.unlink()
    build_dir = "build" if args.stage == 1 else f"build-stage{args.stage}"
    variant="-stall" if args.case=="stalled" else "-bad-ctor" if args.case=="bad-ctor" else ""
    app = (PORTING / f"3ds/{build_dir}/deadspace-loader-stage{args.stage}{variant}.{args.format}").resolve()
    info = GameInfo(str(app).encode(), None, 0, None)
    if not core.retro_load_game(C.byref(info)):
        raise RuntimeError("Azahar failed to load the diagnostic application")
    started = time.monotonic()
    expected = {"present": f"STAGE {args.stage} PASSED", "missing": "Missing library",
                "wrong": "Mapping skipped: unexpected donor" if args.stage == 1 else "Donor CRC mismatch",
                "ready": f"STAGE {args.stage} READY - press A",
                "repeat": f"STAGE {args.stage} PASSED",
                "stalled": f"STAGE {args.stage} STOPPED",
                "bad-ctor": "STAGE 8 STOPPED",
                "asset-missing": f"STAGE {args.stage} STOPPED", "asset-wrong": f"STAGE {args.stage} STOPPED"}[args.case]
    found = None
    repeat_at = None
    for iteration in range(1800):
        button_a = args.stage >= 2 and args.case != "ready" and (iteration == 60 or iteration == repeat_at)
        core.retro_run()
        if iteration % 30 == 0:
            for log in ROOT.rglob(log_name):
                contents = log.read_text(encoding="utf-8", errors="replace")
                if expected in contents:
                    if args.case == "repeat" and "Run: 2\n" not in contents:
                        if repeat_at is None: repeat_at = iteration + 60
                    else:
                        found = log
            if found:
                for _ in range(30): core.retro_run()
                break
        if shutdown or time.monotonic() - started > 45: break
    suffix = args.format + "-" + args.case
    if frame: save_frame(ROOT / (f"stage{args.stage}-" + suffix + "-screen.png"))
    core.retro_unload_game(); core.retro_deinit()
    if not found: raise RuntimeError(f"Expected stage-{args.stage} SD log was not produced; inspect emulator logs/frame")
    log_text = found.read_text(encoding="utf-8", errors="replace")
    if args.case != "ready": assert "New 3DS: yes" in log_text
    if args.case not in ("present", "repeat"): assert f"STAGE {args.stage} PASSED" not in log_text
    if args.stage == 2 and args.case != "ready":
        assert "Backend: emulator (RX not tested)" in log_text
        assert "Float softfp bridge: 4.25 (expected 4.25)" in log_text
        assert "I-cache=entire (0x94)" in log_text
    if args.stage == 3 and args.case == "present":
        for line in ("Backend: emulator (RX not tested)", "I-cache=entire (0x94)",
                     "JNI code + writable VM slot: OK", "JavaVM.GetEnv: 0, env matches: yes",
                     "JNI_OnLoad: 00010004 (expected 00010004)", "Game stored JavaVM pointer: MATCH",
                     "Game -> JNI callback -> game: MATCH", "Callbacks: get=1 release=1 errors=0",
                     "String released: yes", "No constructors or engine entry point called."):
            assert line in log_text, line
    if args.stage == 3 and args.case in ("wrong", "missing"):
        assert "Calling verified JNI_OnLoad" not in log_text and "Backend:" not in log_text
    if args.stage == 4 and args.case != "ready":
        assert "Bridge cleanup: OK, active=0" in log_text
        if args.case in ("missing", "wrong"):
            assert "Calling original Android-ABI" not in log_text and "Backend:" not in log_text
        else:
            for line in ("Backend: emulator (RX not tested)", "I-cache=entire (0x94)",
                         "Donor imports: bound=5 missing=383 weak-null=4", "Incomplete donor binding: REFUSED, image unchanged",
                         "I/O probe bindings: OK (5/5)", "Constructor marker: 42 (expected 42)",
                         "Bridge handles before cleanup: 0", "No game functions or constructors called."):
                assert line in log_text, line
            if args.case == "present":
                for line in ("Probe result: 0 (expected 0)", "Asset bytes: 3568 (expected 3568)", "Seek/EOF: MATCH",
                             "Android errno: badfd=9 missing=2 readonly=30"):
                    assert line in log_text, line
            if args.case == "asset-missing": assert "Probe result: 1 (expected 0)" in log_text
            if args.case == "asset-wrong": assert "Probe result: 4 (expected 0)" in log_text
    if args.stage == 5 and args.case != "ready":
        assert "Cleanup: leaked-blocks=0 active-files=0" in log_text
        if args.case in ("missing", "wrong"):
            assert "Calling original softfp" not in log_text and "Backend:" not in log_text
        else:
            for line in ("Backend: emulator (RX not tested)", "I-cache=entire (0x94)",
                         "Donor imports: bound=53 missing=335 weak-null=4", "Incomplete donor binding: REFUSED, image unchanged",
                         "Runtime probe bindings: OK (49/49)", "Memory/string probe: 0 (expected 0)",
                         "Allocation overflow errno: 12/12 (expected 12/12)", "Constructor marker: 42 (expected 42)",
                         "Heap: live=0 bytes=0", "Heap refusals=2 invalid-free=0", "Float/double math: 35 checks, failure=0",
                         "Math errno: domain=33 range=34 (expected 33/34)", "No game functions or constructors called."):
                assert line in log_text, line
            if args.case == "repeat": assert "Run: 2\n" in log_text
    if args.stage == 6 and args.case != "ready":
        assert "Cleanup: leaked-blocks=0 active-files=0" in log_text
        assert "Runtime heap before cleanup: live=0 bytes=0" in log_text
        if args.case in ("missing","wrong"):
            assert "Calling original softfp" not in log_text and "Backend:" not in log_text
        else:
            for line in ("Backend: emulator (RX not tested)","I-cache=entire (0x94)",
                         "Donor imports: bound=108 missing=280 weak-null=4","Incomplete donor binding: REFUSED, image unchanged",
                         "Bionic probe bindings: OK (57/57)","Formatting/numeric/env/atomic: 0",
                         "Android log callbacks: 3 (expected 3)","Constructor marker: 42 (expected 42)"):
                assert line in log_text,line
            if args.case in ("present","repeat"):
                for line in ("Bionic FILE/stat + SD roundtrip: 0","Asset bytes=3568 CRC32=4a8d9499","Time/calendar/sleep: 0"):
                    assert line in log_text,line
            else:
                assert "Time/calendar/sleep:" not in log_text
            if args.case=="repeat": assert "Run: 2\n" in log_text
            scratch=target/"test-output"
            assert not (scratch/"stage6-roundtrip.txt").exists()
            assert not (scratch/"stage6-renamed.txt").exists()
    if args.stage==7 and args.case=="stalled":
        assert "Thread shutdown: live=1" in log_text
        assert "Active workers: module retained; exit before retry." in log_text
        assert "Cleanup: leaked-blocks=" not in log_text
    if args.stage == 7 and args.case not in ("ready","stalled"):
        assert "Thread shutdown: live=0" in log_text
        assert "Cleanup: leaked-blocks=0 active-files=0" in log_text
        assert "Runtime heap before cleanup: live=0 bytes=0" in log_text
        if args.case in ("missing","wrong"):
            assert "Calling original softfp thread" not in log_text and "Backend:" not in log_text
        else:
            for line in ("Backend: emulator (RX not tested)","I-cache=entire (0x94)",
                         "Donor imports: bound=145 missing=243 weak-null=4","Thread probe bindings: OK (47/47)",
                         "Thread probe: 0", "Mutex counter: 1000 (expected 1000)","TLS destructor calls: 4 (expected 4)",
                         "Worker error flags: 0 (expected 0)","Constructor marker: 42 (expected 42)",
                         "Threads: active=0 finished=0","Pools: mutex=0 cond=0 sem=0 keys=0"):
                assert line in log_text,line
            if args.case=="repeat": assert "Run: 2\n" in log_text
    if args.stage==8 and args.case!="ready":
        if args.case=="stalled":
            assert "Thread shutdown: live=1" in log_text
            assert "Active workers: module retained; exit before retry." in log_text
            assert "Finalizing test module" not in log_text and "Cleanup: leaked-blocks=" not in log_text
        else:
            for line in ("Thread shutdown: live=0","C++ registry: pending=0 active-guards=0 failures=0",
                         "Runtime heap before cleanup: live=0 bytes=0","Cleanup: leaked-blocks=0 active-files=0"):
                assert line in log_text,line
        if args.case in ("missing","wrong","bad-ctor"):
            assert "Running verified test-module constructors" not in log_text and "Backend:" not in log_text
            if args.case=="bad-ctor": assert "Constructor plan: REFUSED, entries=0" in log_text
        else:
            for line in ("Backend: emulator (RX not tested)","I-cache=entire (0x94)",
                         "Donor imports: bound=149 missing=239 weak-null=4","C++ probe bindings: OK (18/18)",
                         "Constructor plan: OK, entries=2","Before constructors: objects=0 order=0",
                         "After constructors: objects=2 order=912 (expected 2/912)","Repeated constructor run: REFUSED"):
                assert line in log_text,line
            if args.case!="stalled":
                for line in ("C++ probe: 0", "Static objects: 3 order=9123 (expected 3/9123)",
                             "Filtered/reentrant destructor calls: 6 (expected 6)","Guards: release=2 abort=1 waits=",
                             "Destruction: objects=3 order=321 (expected 3/321)","No game functions or game constructors called."):
                    assert line in log_text,line
        if args.case=="repeat": assert "Run: 2\n" in log_text
    if args.case == "ready":
        assert args.stage >= 2 and "Backend:" not in log_text and "Calling verified JNI_OnLoad" not in log_text
        assert "Fixture bindings:" not in log_text and "Donor imports:" not in log_text
        assert not button_a
    shutil.copyfile(found, ROOT / (f"stage{args.stage}-" + suffix + ".log"))
    report = {"emulator": "Azahar libretro 2126.2", "renderer": "Software", "game_runtime": False,
              "hardware_tested": False, "stage": args.stage, "format": args.format, "case": args.case, "expected_status_found": True,
              "log": str(found.relative_to(PORTING)), "frames": iteration + 1,
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    result_prefix = "result-" if args.stage == 1 else f"result-stage{args.stage}-"
    (ROOT / (result_prefix + suffix + ".json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__": main()
