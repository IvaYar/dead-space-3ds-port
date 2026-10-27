"""Build a bounded JNI-bootstrap milestone using the device-verified stage-2 backend."""
import hashlib
import json
import shutil
import zlib
import build_stage1 as base

PORTING = base.PORTING
BUILD = PORTING / "3ds/build-stage3"
DIST = PORTING / "dist/stage3"


def main():
    BUILD.mkdir(parents=True, exist_ok=True); DIST.mkdir(parents=True, exist_ok=True)
    base.BUILD = BUILD; run = base.run
    donor = base.DONOR.read_bytes()
    if hashlib.sha1(donor).hexdigest() != "3c4a1b844eddbf3b9f0d2d946433bc429cc64b2e": raise ValueError("Unexpected donor")
    (BUILD / "donor_config.h").write_text(f'#define DS_DONOR_SIZE {len(donor)}u\n#define DS_DONOR_CRC32 0x{zlib.crc32(donor):08x}u\n', encoding="ascii")
    include = ["-I" + str(PORTING / "3ds/include"), "-I" + str(BUILD)]
    run(base.GCC, *base.FLAGS, "-fPIC", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-nostdlib", "-shared",
        PORTING / "tests/fixture.c", "-Wl,--hash-style=sysv", "-Wl,-z,max-page-size=4096", "-o", BUILD / "fixture-regression.so")
    sources = [PORTING / "3ds/source" / name for name in ("ds_elf.c", "ds_jni.c", "ds_bootstrap.c")]
    run(base.GCC, *base.FLAGS, *include, "-ffreestanding", "-fno-builtin", "-fno-unwind-tables", "-nostdlib",
        *sources, "-Wl,-Ttext=0x00100000", "-Wl,-e,ds_elf_inspect", "-o", BUILD / "core-test.elf")
    run(base.GCC, *base.FLAGS, *include, "-I" + str(base.DKP / "libctru/include"), "-D__3DS__", "-mword-relocations",
        "-specs=3dsx.specs", "-Wl,-z,noexecstack", *sources, PORTING / "3ds/source/ds_exec.c",
        PORTING / "3ds/source/ds_cache.s", PORTING / "3ds/source/main_stage3.c",
        "-L" + str(base.DKP / "libctru/lib"), "-lctru", "-lm", "-Wl,--gc-sections",
        "-Wl,-Map=" + str(BUILD / "stage3.map"), "-o", BUILD / "deadspace-loader-stage3.elf")
    base.make_assets(stage=3)
    run(base.DKP / "tools/bin/smdhtool.exe", "--create", "DS Loader Test 3", "Stage 3 JNI bootstrap diagnostics",
        "Homebrew port research", BUILD / "icon.png", BUILD / "stage3.smdh")
    run(base.DKP / "tools/bin/3dsxtool.exe", BUILD / "deadspace-loader-stage3.elf", BUILD / "deadspace-loader-stage3.3dsx",
        "--smdh=" + str(BUILD / "stage3.smdh"))
    run(PORTING / "toolchain/extras/bannertool/bannertool.exe", "makebanner", "-i", BUILD / "banner.png", "-a", BUILD / "silence.wav", "-o", BUILD / "stage3.bnr")
    rsf = (PORTING / "3ds/stage1.rsf").read_text(encoding="utf-8")
    rsf = rsf.replace('"DS-LOADER-TEST"','"DS-LOADER-TST3"').replace('"CTR-H-DSLT"','"CTR-H-DSL3"').replace('0xFDE50','0xFDE52')
    rsf = rsf.replace('    ControlMemory: 1','    ControlProcessMemory: 112\n    FlushProcessDataCache: 84\n    QueryProcessMemory: 125\n    ControlMemory: 1')
    (BUILD / "stage3.rsf").write_text(rsf, encoding="utf-8")
    run(PORTING / "toolchain/extras/makerom/makerom.exe", "-f", "cia", "-o", BUILD / "deadspace-loader-stage3.cia",
        "-rsf", BUILD / "stage3.rsf", "-target", "t", "-exefslogo", "-elf", BUILD / "deadspace-loader-stage3.elf",
        "-icon", BUILD / "stage3.smdh", "-banner", BUILD / "stage3.bnr", "-ver", "48")
    card = DIST / "SD_CARD"; app = card / "3ds/deadspace3"
    app.mkdir(parents=True, exist_ok=True); (card / "3ds/deadspace").mkdir(exist_ok=True); (card / "CIA").mkdir(exist_ok=True)
    shutil.copyfile(base.DONOR, card / "3ds/deadspace" / base.DONOR.name)
    shutil.copyfile(BUILD / "deadspace-loader-stage3.3dsx", app / "deadspace3.3dsx")
    shutil.copyfile(BUILD / "stage3.smdh", app / "deadspace3.smdh")
    for target in (DIST / "deadspace-loader-stage3.cia", card / "CIA/deadspace-loader-stage3.cia"):
        shutil.copyfile(BUILD / "deadspace-loader-stage3.cia", target)
    manifest = {"stage":3,"version":"0.3.0","title_id":"000400000FDE5200","gameplay":False,"hardware_tested":False,
                "start_requires_A":True,"game_probe_scope":"Verified JNI_OnLoad and two string wrappers; no constructors or engine entry point",
                "backend_basis":"Stage 2 v0.2.2 passed on the user's console; unchanged ds_exec.c and ds_cache.s",
                "backend_sha256":{n:hashlib.sha256((PORTING / '3ds/source' / n).read_bytes()).hexdigest() for n in ('ds_exec.c','ds_cache.s')},
                "donor_sha256":hashlib.sha256(donor).hexdigest()}
    (DIST / "build-manifest.json").write_text(json.dumps(manifest,indent=2)+'\n',encoding="utf-8")
    print("Stage 3 built:", DIST)


if __name__ == "__main__": main()
