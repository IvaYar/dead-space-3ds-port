"""Build Android-ABI file I/O diagnostics with the device-verified RX backend."""
import hashlib
import json
import shutil
import struct
import zlib
import build_stage1 as base
from inspect_packages import inspect_elf

PORTING = base.PORTING
BUILD = PORTING / "3ds/build-stage4"
DIST = PORTING / "dist/stage4"
ASSET = PORTING / "analysis/candidate-sd/assets/published/data/achievements.sb"


def main():
    BUILD.mkdir(parents=True, exist_ok=True); DIST.mkdir(parents=True, exist_ok=True)
    base.BUILD = BUILD; run = base.run
    donor = base.DONOR.read_bytes(); asset = ASSET.read_bytes()
    if hashlib.sha1(donor).hexdigest() != "3c4a1b844eddbf3b9f0d2d946433bc429cc64b2e": raise ValueError("Unexpected donor")
    (BUILD / "donor_config.h").write_text(
        f'#define DS_DONOR_SIZE {len(donor)}u\n#define DS_DONOR_CRC32 0x{zlib.crc32(donor):08x}u\n'
        f'#define DS_ASSET_SIZE {len(asset)}u\n#define DS_ASSET_CRC32 0x{zlib.crc32(asset):08x}u\n', encoding="ascii")
    include = ["-I" + str(PORTING / "3ds/include"), "-I" + str(BUILD)]
    soft = [flag for flag in base.FLAGS if not flag.startswith("-mfloat-abi=")] + ["-mfloat-abi=softfp", "-mfpu=vfp"]
    for name, flags in (("fixture-regression", base.FLAGS), ("fixture-stage4", soft)):
        source = PORTING / "tests" / ("fixture.c" if name == "fixture-regression" else "fixture_stage4.c")
        run(base.GCC, *flags, "-fPIC", "-fno-builtin", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-nostdlib", "-shared",
            source, "-Wl,--hash-style=sysv", "-Wl,-z,max-page-size=4096", "-o", BUILD / (name + ".so"))
    blob = (BUILD / "fixture-stage4.so").read_bytes()
    # Read the fixture's .plt VA independently of the C loader (test module only).
    shoff = struct.unpack_from('<I', blob, 32)[0]; shnum, shstr = struct.unpack_from('<HH', blob, 48)
    sections = [struct.unpack_from('<10I', blob, shoff + i * 40) for i in range(shnum)]
    names = blob[sections[shstr][4]:sections[shstr][4] + sections[shstr][5]]
    plt = next(s for s in sections if names[s[0]:names.index(0, s[0])] == b'.plt')
    assert plt[2] & 4 and plt[5] <= 4096 and (plt[3] & 4095) + plt[5] <= 4096
    fixture_info = inspect_elf(blob)
    assert fixture_info['imports'] == ['__errno', 'close', 'lseek', 'open', 'read'], fixture_info['imports']
    (BUILD / "stage4_fixture.h").write_text(f'#define DS_FIXTURE_PLT_VA 0x{plt[3]:08x}u\nstatic const unsigned char stage4_fixture[] = {{\n' +
        '\n'.join(','.join(str(b) for b in blob[i:i+32]) + ',' for i in range(0, len(blob), 32)) + '\n};\n', encoding="ascii")
    sources = [PORTING / "3ds/source" / name for name in ("ds_elf.c", "ds_io.c")]
    run(base.GCC, *base.FLAGS, *include, "-ffreestanding", "-fno-builtin", "-fno-unwind-tables", "-nostdlib",
        *sources, "-Wl,-Ttext=0x00100000", "-Wl,-e,ds_elf_inspect", "-o", BUILD / "core-test.elf")
    run(base.GCC, *base.FLAGS, *include, "-I" + str(base.DKP / "libctru/include"), "-D__3DS__", "-mword-relocations",
        "-specs=3dsx.specs", "-Wl,-z,noexecstack", *sources, PORTING / "3ds/source/ds_io_sd.c",
        PORTING / "3ds/source/ds_exec.c", PORTING / "3ds/source/ds_cache.s", PORTING / "3ds/source/main_stage4.c",
        "-L" + str(base.DKP / "libctru/lib"), "-lctru", "-lm", "-Wl,--gc-sections",
        "-Wl,-Map=" + str(BUILD / "stage4.map"), "-o", BUILD / "deadspace-loader-stage4.elf")
    base.make_assets(stage=4)
    run(base.DKP / "tools/bin/smdhtool.exe", "--create", "DS Loader Test 4", "Stage 4 Android file I/O diagnostics",
        "Homebrew port research", BUILD / "icon.png", BUILD / "stage4.smdh")
    run(base.DKP / "tools/bin/3dsxtool.exe", BUILD / "deadspace-loader-stage4.elf", BUILD / "deadspace-loader-stage4.3dsx",
        "--smdh=" + str(BUILD / "stage4.smdh"))
    run(PORTING / "toolchain/extras/bannertool/bannertool.exe", "makebanner", "-i", BUILD / "banner.png", "-a", BUILD / "silence.wav", "-o", BUILD / "stage4.bnr")
    rsf = (PORTING / "3ds/stage1.rsf").read_text(encoding="utf-8")
    rsf = rsf.replace('"DS-LOADER-TEST"','"DS-LOADER-TST4"').replace('"CTR-H-DSLT"','"CTR-H-DSL4"').replace('0xFDE50','0xFDE53')
    rsf = rsf.replace('    ControlMemory: 1','    ControlProcessMemory: 112\n    FlushProcessDataCache: 84\n    QueryProcessMemory: 125\n    ControlMemory: 1')
    (BUILD / "stage4.rsf").write_text(rsf, encoding="utf-8")
    run(PORTING / "toolchain/extras/makerom/makerom.exe", "-f", "cia", "-o", BUILD / "deadspace-loader-stage4.cia",
        "-rsf", BUILD / "stage4.rsf", "-target", "t", "-exefslogo", "-elf", BUILD / "deadspace-loader-stage4.elf",
        "-icon", BUILD / "stage4.smdh", "-banner", BUILD / "stage4.bnr", "-ver", "64")
    card = DIST / "SD_CARD"; app = card / "3ds/deadspace4"
    app.mkdir(parents=True, exist_ok=True); (card / "3ds/deadspace/assets/published/data").mkdir(parents=True, exist_ok=True)
    (card / "CIA").mkdir(exist_ok=True)
    shutil.copyfile(base.DONOR, card / "3ds/deadspace" / base.DONOR.name)
    shutil.copyfile(ASSET, card / "3ds/deadspace/assets/published/data/achievements.sb")
    shutil.copyfile(BUILD / "deadspace-loader-stage4.3dsx", app / "deadspace4.3dsx")
    shutil.copyfile(BUILD / "stage4.smdh", app / "deadspace4.smdh")
    for target in (DIST / "deadspace-loader-stage4.cia", card / "CIA/deadspace-loader-stage4.cia"):
        shutil.copyfile(BUILD / "deadspace-loader-stage4.cia", target)
    imports = inspect_elf(donor)['imports']; supported = ['__errno', 'close', 'lseek', 'open', 'read']
    audit = {"donor_imports":len(imports), "io_bindings":supported,
             "remaining_imports": [name for name in imports if name not in supported],
             "game_engine_started":False, "notes":"Other imports remain unresolved; no dummy success implementations"}
    (PORTING / "analysis/stage4-import-audit.json").write_text(json.dumps(audit,indent=2)+'\n',encoding="utf-8")
    manifest = {"stage":4,"version":"0.4.0","title_id":"000400000FDE5300","gameplay":False,"hardware_tested":False,
                "start_requires_A":True,"probe_scope":"Original softfp I/O module reads donor asset; donor import preflight only; no game functions",
                "backend_basis":"Unchanged stage-2 v0.2.2 backend, also passed with stage-3 v0.3.0 on user's console",
                "backend_sha256":{n:hashlib.sha256((PORTING / '3ds/source' / n).read_bytes()).hexdigest() for n in ('ds_exec.c','ds_cache.s')},
                "donor_sha256":hashlib.sha256(donor).hexdigest(),"asset_sha256":hashlib.sha256(asset).hexdigest(),
                "asset_bytes":len(asset),"asset_crc32":f'{zlib.crc32(asset):08x}',"fixture_sha256":hashlib.sha256(blob).hexdigest()}
    (DIST / "build-manifest.json").write_text(json.dumps(manifest,indent=2)+'\n',encoding="utf-8")
    print("Stage 4 built:", DIST)


if __name__ == "__main__": main()
