"""Build the second, separate execution/softfp ABI diagnostic."""

import hashlib
import json
from pathlib import Path
import shutil
import zlib
import build_stage1 as base

PORTING = base.PORTING
BUILD = PORTING / "3ds/build-stage2"
DIST = PORTING / "dist/stage2"


def main():
    BUILD.mkdir(parents=True, exist_ok=True); DIST.mkdir(parents=True, exist_ok=True)
    base.BUILD = BUILD
    run = base.run
    donor = base.DONOR.read_bytes()
    if hashlib.sha1(donor).hexdigest() != "3c4a1b844eddbf3b9f0d2d946433bc429cc64b2e": raise ValueError("Unexpected donor")
    (BUILD / "donor_config.h").write_text(
        f'#define DS_DONOR_SIZE {len(donor)}u\n#define DS_DONOR_CRC32 0x{zlib.crc32(donor):08x}u\n', encoding="ascii")
    soft = [flag for flag in base.FLAGS if not flag.startswith("-mfloat-abi=")] + ["-mfloat-abi=softfp", "-mfpu=vfp"]
    run(base.GCC, *soft, "-fPIC", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-nostdlib", "-shared",
        PORTING / "tests/fixture_stage2.c", "-Wl,--hash-style=sysv", "-Wl,-z,max-page-size=4096", "-o", BUILD / "fixture-stage2.so")
    run(base.GCC, *base.FLAGS, "-fPIC", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-nostdlib", "-shared",
        PORTING / "tests/fixture.c", "-Wl,--hash-style=sysv", "-Wl,-z,max-page-size=4096", "-o", BUILD / "fixture-regression.so")
    blob = (BUILD / "fixture-stage2.so").read_bytes()
    (BUILD / "stage2_fixture.h").write_text('static const unsigned char stage2_fixture[] = {\n' +
        '\n'.join(','.join(str(b) for b in blob[i:i+32]) + ',' for i in range(0, len(blob), 32)) + '\n};\n', encoding="ascii")
    include = ["-I" + str(PORTING / "3ds/include"), "-I" + str(BUILD)]
    core = PORTING / "3ds/source/ds_elf.c"
    run(base.GCC, *base.FLAGS, *include, "-ffreestanding", "-fno-builtin", "-fno-unwind-tables",
        "-fno-asynchronous-unwind-tables", "-nostdlib", core, "-Wl,-Ttext=0x00100000", "-Wl,-e,ds_elf_inspect",
        "-o", BUILD / "core-test.elf")
    # Native-backend witness tests use actual libctru wrappers with a simulated
    # kernel boundary that reproduces QueryMemory's missing execute bit.
    old_cache = PORTING / "analysis/stage2-v0.2.1-ds_cache.s"
    for name, source, cache in [("exec-native-test", PORTING / "3ds/source/ds_exec.c", PORTING / "3ds/source/ds_cache.s"),
                               ("exec-before-fix-test", PORTING / "analysis/stage2-v0.2.0-ds_exec.c", old_cache),
                               ("exec-before-cache-fix-test", PORTING / "analysis/stage2-v0.2.1-ds_exec.c", old_cache)]:
        run(base.GCC, *base.FLAGS, *include, "-I" + str(base.DKP / "libctru/include"), "-D__3DS__",
            "-ffreestanding", "-fno-builtin", "-nostdlib", "-Wl,-z,noexecstack", source,
            cache, PORTING / "tests/exec_test_runtime.c",
            "-L" + str(base.DKP / "libctru/lib"), "-lctru", "-Wl,-Ttext=0x00100000", "-Wl,-e,ds_exec_open",
            "-o", BUILD / (name + ".elf"))
    run(base.GCC, *base.FLAGS, *include, "-I" + str(base.DKP / "libctru/include"), "-D__3DS__", "-mword-relocations",
        "-specs=3dsx.specs", "-Wl,-z,noexecstack", core, PORTING / "3ds/source/ds_exec.c", PORTING / "3ds/source/ds_cache.s",
        PORTING / "3ds/source/main_stage2.c", "-L" + str(base.DKP / "libctru/lib"), "-lctru", "-lm",
        "-Wl,--gc-sections", "-Wl,-Map=" + str(BUILD / "stage2.map"), "-o", BUILD / "deadspace-loader-stage2.elf")
    base.make_assets(stage=2)
    run(base.DKP / "tools/bin/smdhtool.exe", "--create", "DS Loader Test 2", "Stage 2 execution and ABI diagnostics",
        "Homebrew port research", BUILD / "icon.png", BUILD / "stage2.smdh")
    run(base.DKP / "tools/bin/3dsxtool.exe", BUILD / "deadspace-loader-stage2.elf", BUILD / "deadspace-loader-stage2.3dsx",
        "--smdh=" + str(BUILD / "stage2.smdh"))
    run(PORTING / "toolchain/extras/bannertool/bannertool.exe", "makebanner", "-i", BUILD / "banner.png", "-a",
        BUILD / "silence.wav", "-o", BUILD / "stage2.bnr")
    # Preserve the first diagnostic's application ID and source configuration.
    rsf = (PORTING / "3ds/stage1.rsf").read_text(encoding="utf-8")
    rsf = rsf.replace('"DS-LOADER-TEST"', '"DS-LOADER-TST2"').replace('"CTR-H-DSLT"', '"CTR-H-DSL2"').replace('0xFDE50', '0xFDE51')
    rsf = rsf.replace('    ControlMemory: 1', '    ControlProcessMemory: 112\n    FlushProcessDataCache: 84\n    ControlMemory: 1')
    rsf = rsf.replace('    QueryMemory: 2', '    QueryMemory: 2\n    QueryProcessMemory: 125')
    (BUILD / "stage2.rsf").write_text(rsf, encoding="utf-8")
    run(PORTING / "toolchain/extras/makerom/makerom.exe", "-f", "cia", "-o", BUILD / "deadspace-loader-stage2.cia",
        "-rsf", BUILD / "stage2.rsf", "-target", "t", "-exefslogo", "-elf", BUILD / "deadspace-loader-stage2.elf",
        "-icon", BUILD / "stage2.smdh", "-banner", BUILD / "stage2.bnr", "-ver", "34")
    card = DIST / "SD_CARD"
    (card / "3ds/deadspace").mkdir(parents=True, exist_ok=True)
    app = card / "3ds/deadspace2"; app.mkdir(parents=True, exist_ok=True)
    (card / "CIA").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base.DONOR, card / "3ds/deadspace" / base.DONOR.name)
    shutil.copyfile(BUILD / "deadspace-loader-stage2.3dsx", app / "deadspace2.3dsx")
    shutil.copyfile(BUILD / "stage2.smdh", app / "deadspace2.smdh")
    for target in (DIST / "deadspace-loader-stage2.cia", card / "CIA/deadspace-loader-stage2.cia"):
        shutil.copyfile(BUILD / "deadspace-loader-stage2.cia", target)
    manifest = {"stage": 2, "version": "0.2.2", "title_id": "000400000FDE5100", "gameplay": False,
                "start_requires_A": True, "instruction_cache_operation": "Luma SVC 0x94 entire instruction cache",
                "game_probe_scope": "Three instruction-verified constant getters only",
                "hardware_tested": False, "donor_sha256": hashlib.sha256(donor).hexdigest(),
                "fixture_sha256": hashlib.sha256(blob).hexdigest()}
    (DIST / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + '\n', encoding="utf-8")
    print("Stage 2 built:", DIST)


if __name__ == "__main__": main()
