"""Build the stage-1 3DS diagnostic and ARM tests with the local devkitARM toolchain."""

import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import wave
import zlib

PORTING = Path(__file__).resolve().parents[1]
DKP = PORTING / "toolchain/devkitpro"
BUILD = PORTING / "3ds/build"
DIST = PORTING / "dist/stage1"
DONOR = PORTING / "analysis/candidate-sd/libEAMGameDeadSpace_orig.so"
GCC = DKP / "devkitARM/bin/arm-none-eabi-gcc.exe"
ARCH = ["-march=armv6k", "-mtune=mpcore", "-mfloat-abi=hard", "-mtp=soft"]
FLAGS = ARCH + ["-std=c11", "-O2", "-g", "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections"]


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=BUILD)


def png(path, width, height, pixel):
    raw = b"".join(b"\0" + b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def make_assets(stage=1):
    # Original geometric diagnostic icon; no game art or commercial logo is used.
    def icon(x, y):
        if 10 <= x < 38 and 10 <= y < 38:
            if x in (10, 11, 36, 37) or y in (10, 11, 36, 37): return (90, 230, 222)
            if 16 <= x < 32 and 19 <= y < 23: return (190, 245, 240)
            if 16 <= x < 26 and 27 <= y < 30: return (90, 230, 222)
        return (8, 20 + y // 4, 30 + y // 3)
    png(BUILD / "icon.png", 48, 48, icon)
    font = {
        'A':[14,17,17,31,17,17,17], 'D':[30,17,17,17,17,17,30],
        'E':[31,16,16,30,16,16,31], 'S':[15,16,16,14,1,1,30],
        'P':[30,17,17,30,16,16,16], 'C':[15,16,16,16,16,16,15],
        'L':[16,16,16,16,16,16,31], 'O':[14,17,17,17,17,17,14],
        'R':[30,17,17,30,20,18,17], 'T':[31,4,4,4,4,4,4],
        'G':[15,16,16,23,17,17,15], '1':[4,12,4,4,4,4,14],
        '2':[14,17,1,2,4,8,31],
        '3':[30,1,1,14,1,1,30],
        '4':[2,6,10,18,31,2,2],
        '5':[31,16,16,30,1,1,30],
        '6':[14,16,16,30,17,17,14],
        '7':[31,1,2,4,8,8,8],
        '8':[14,17,17,14,17,17,14],
        ' ':[0]*7,
    }
    pixels = [[(7, 18 + y // 16, 29 + y // 12) for _ in range(256)] for y in range(128)]
    for text, y, scale, color in [("DEAD SPACE", 20, 3, (180, 240, 235)),
                                   ("LOADER TEST", 64, 2, (85, 222, 210)),
                                   (f"STAGE {stage}", 96, 2, (165, 180, 190))]:
        x0 = (256 - (len(text) * 6 - 1) * scale) // 2
        for index, char in enumerate(text):
            for row, bits in enumerate(font[char]):
                for col in range(5):
                    if bits & (1 << (4 - col)):
                        for dy in range(scale):
                            for dx in range(scale): pixels[y + row * scale + dy][x0 + (index * 6 + col) * scale + dx] = color
    png(BUILD / "banner.png", 256, 128, lambda x, y: pixels[y][x])
    with wave.open(str(BUILD / "silence.wav"), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(22050); out.writeframes(b"\0" * 4410)


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)
    donor = DONOR.read_bytes()
    digest = hashlib.sha256(donor).hexdigest()
    # Pin the researched SD variant rather than silently accepting another APK.
    if hashlib.sha1(donor).hexdigest() != "3c4a1b844eddbf3b9f0d2d946433bc429cc64b2e":
        raise ValueError("Unexpected donor library; inspect it before changing this pin")
    packages = json.loads((PORTING / "toolchain/manifest.json").read_text(encoding="utf-8"))
    libctru_version = next(p["version"] for p in packages if p["name"] == "libctru")
    (BUILD / "donor_config.h").write_text(
        f'#define DS_DONOR_SIZE {len(donor)}u\n#define DS_DONOR_CRC32 0x{zlib.crc32(donor):08x}u\n'
        f'#define DS_DONOR_SHA256 "{digest}"\n#define DS_LIBCTRU_VERSION "{libctru_version}"\n', encoding="ascii")
    include = ["-I" + str(PORTING / "3ds/include")]
    core = PORTING / "3ds/source/ds_elf.c"
    run(GCC, *FLAGS, *include, "-ffreestanding", "-fno-builtin", "-fno-unwind-tables",
        "-fno-asynchronous-unwind-tables", "-nostdlib", core, "-Wl,-Ttext=0x00100000",
        "-Wl,-e,ds_elf_inspect", "-o", BUILD / "core-test.elf")
    run(GCC, *FLAGS, "-fPIC", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-nostdlib", "-shared",
        PORTING / "tests/fixture.c", "-Wl,--hash-style=sysv", "-Wl,-z,max-page-size=4096",
        "-o", BUILD / "fixture.so")
    run(GCC, *FLAGS, *include, "-I" + str(BUILD), "-I" + str(DKP / "libctru/include"),
        "-D__3DS__", "-mword-relocations", "-specs=3dsx.specs", core, PORTING / "3ds/source/main.c",
        "-L" + str(DKP / "libctru/lib"), "-lctru", "-lm", "-Wl,--gc-sections",
        "-Wl,-Map=" + str(BUILD / "stage1.map"), "-o", BUILD / "deadspace-loader-stage1.elf")
    make_assets()
    run(DKP / "tools/bin/smdhtool.exe", "--create", "DS Loader Test", "Stage 1 diagnostics - not the game",
        "Homebrew port research", BUILD / "icon.png", BUILD / "stage1.smdh")
    run(DKP / "tools/bin/3dsxtool.exe", BUILD / "deadspace-loader-stage1.elf", BUILD / "deadspace-loader-stage1.3dsx",
        "--smdh=" + str(BUILD / "stage1.smdh"))
    run(PORTING / "toolchain/extras/bannertool/bannertool.exe", "makebanner", "-i", BUILD / "banner.png",
        "-a", BUILD / "silence.wav", "-o", BUILD / "stage1.bnr")
    run(PORTING / "toolchain/extras/makerom/makerom.exe", "-f", "cia", "-o", BUILD / "deadspace-loader-stage1.cia",
        "-rsf", PORTING / "3ds/stage1.rsf", "-target", "t", "-exefslogo", "-elf", BUILD / "deadspace-loader-stage1.elf",
        "-icon", BUILD / "stage1.smdh", "-banner", BUILD / "stage1.bnr", "-ver", "16")
    card = DIST / "SD_CARD/3ds/deadspace"
    card.mkdir(parents=True, exist_ok=True)
    for obsolete in ("deadspace-loader-stage1.3dsx", "deadspace-loader-stage1.smdh"):
        (card / obsolete).unlink(missing_ok=True)
    for name in ("deadspace-loader-stage1.3dsx", "stage1.smdh"):
        shutil.copyfile(BUILD / name, card / ("deadspace.smdh" if name == "stage1.smdh" else "deadspace.3dsx"))
    shutil.copyfile(DONOR, card / DONOR.name)
    shutil.copyfile(BUILD / "deadspace-loader-stage1.cia", DIST / "deadspace-loader-stage1.cia")
    cia_dir = DIST / "SD_CARD/cias"
    cia_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BUILD / "deadspace-loader-stage1.cia", cia_dir / "deadspace-loader-stage1.cia")
    manifest = {"stage": 1, "game_runtime": False, "hardware_tested": False, "title_id": "000400000FDE5000",
                "donor_sha256": digest, "files": {}}
    for path in sorted(DIST.rglob("*")):
        if path.is_file() and path.name != "build-manifest.json":
            manifest["files"][path.relative_to(DIST).as_posix()] = {
                "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (DIST / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Built stage-1 diagnostics:", DIST)


if __name__ == "__main__":
    main()
