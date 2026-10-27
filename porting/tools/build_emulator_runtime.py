"""Build the computer-only engine experiment; never produces an installable CIA."""
import hashlib,json,zlib,shutil
from pathlib import Path
import build_stage1 as base
PORTING=base.PORTING
BUILD=PORTING/'3ds/build-emulator'
def main():
    BUILD.mkdir(exist_ok=True);base.BUILD=BUILD
    for path in (PORTING/'3ds/build-stage8').glob('fixture-*.so'):shutil.copyfile(path,BUILD/path.name)
    soft=[f for f in base.FLAGS if not f.startswith('-mfloat-abi=')]+['-mfloat-abi=softfp','-mfpu=vfp']
    base.run(base.GCC,*soft,'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_memory.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-memory.so')
    base.run(base.GCC,*soft,'-I'+str(PORTING/'3ds/include'),'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_jni10.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-jni10.so')
    blob=(BUILD/'fixture-jni10.so').read_bytes()
    (BUILD/'jni10_fixture.h').write_text('static const unsigned char jni10_fixture[]={\n'+
        '\n'.join(','.join(str(b) for b in blob[i:i+32])+',' for i in range(0,len(blob),32))+'\n};\n')
    base.run(base.GCC,*soft,'-I'+str(PORTING/'3ds/include'),'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_platform.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-platform.so')
    blob=(BUILD/'fixture-platform.so').read_bytes()
    (BUILD/'platform_fixture.h').write_text('static const unsigned char platform_fixture[]={\n'+
        '\n'.join(','.join(str(b) for b in blob[i:i+32])+',' for i in range(0,len(blob),32))+'\n};\n')
    names=('ds_elf.c','ds_io.c','ds_io_sd.c','ds_runtime_libc.c','ds_runtime_math.c','ds6_basics.c','ds6_stdio.c','ds6_time.c',
           'ds6_all.c','ds7_threads.c','ds8_cpp.c','ds_init.c','ds_jni.c','ds_bootstrap.c','ds9_memory.c','ds10_jni.c','ds11_platform.c')
    sources=[PORTING/'3ds/source'/n for n in names]
    base.run(base.GCC,*base.FLAGS,'-I'+str(PORTING/'3ds/include'),'-ffreestanding','-fno-builtin','-fno-unwind-tables','-nostdlib',
        *sources,PORTING/'tests/runtime_heap.c',PORTING/'tests/runtime_os.c',PORTING/'tests/stage6_stat_fixture.c',PORTING/'tests/ds7_platform_model.c',PORTING/'tests/jni10_callbacks.c',PORTING/'tests/ds11_platform_model.c',
        '-Wl,-Ttext=0x00100000','-Wl,-e,ds_elf_inspect','-Wl,--start-group','-lm','-lc','-lnosys','-lgcc','-Wl,--end-group','-o',BUILD/'core-test.elf')
    donor=base.DONOR.read_bytes()
    (BUILD/'donor_config.h').write_text(f'#define DS_DONOR_SIZE {len(donor)}u\n#define DS_DONOR_CRC32 0x{zlib.crc32(donor):08x}u\n')
    include=['-I'+str(PORTING/'3ds/include'),'-I'+str(BUILD),'-I'+str(base.DKP/'libctru/include')]
    base.run(base.GCC,*base.FLAGS,*include,'-fno-builtin','-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',
        *sources,PORTING/'3ds/source/ds_exec.c',PORTING/'3ds/source/ds_cache.s',PORTING/'3ds/source/ds6_platform_3ds.c',
        PORTING/'3ds/source/ds7_platform_3ds.c',PORTING/'3ds/source/ds11_platform_3ds.c',PORTING/'tests/engine_trap.s',PORTING/'tests/engine_azahar.c',PORTING/'tests/jni10_callbacks.c',
        '-L'+str(base.DKP/'libctru/lib'),'-lctru','-lm','-Wl,--gc-sections','-o',BUILD/'engine-audit.elf')
    base.run(base.DKP/'tools/bin/smdhtool.exe','--create','DS Emulator Audit','Computer only - not a playable port','Homebrew research',
        PORTING/'3ds/build-stage8/icon.png',BUILD/'audit.smdh')
    rsf=(PORTING/'3ds/build-stage8/stage8.rsf').read_text().replace('0xFDE57','0xFDE5E').replace('TST8','AUDT').replace('DSL8','DSEA')
    (BUILD/'audit.rsf').write_text(rsf)
    base.run(PORTING/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',BUILD/'engine-audit.cxi','-rsf',BUILD/'audit.rsf','-target','t','-exefslogo',
        '-elf',BUILD/'engine-audit.elf','-icon',BUILD/'audit.smdh','-banner',PORTING/'3ds/build-stage8/stage8.bnr')
    inputs=sources+[PORTING/'tests'/n for n in ('engine_azahar.c','engine_trap.s','runtime_heap.c','runtime_os.c','stage6_stat_fixture.c','ds7_platform_model.c','fixture_memory.c','fixture_jni10.c','jni10_callbacks.c','ds11_platform_model.c','fixture_platform.c')]
    inputs+=[PORTING/'analysis/android-abi/candidate-sd-package.json']
    inputs+=[PORTING/'3ds/source'/n for n in ('ds_exec.c','ds_cache.s','ds6_platform_3ds.c','ds7_platform_3ds.c','ds11_platform_3ds.c')]
    inputs+=list((PORTING/'3ds/include').glob('*.h'))
    inputs+=[Path(__file__).resolve(),PORTING/'tools/build_stage1.py',PORTING/'3ds/build-stage8/stage8.rsf']
    backend={n:hashlib.sha256((PORTING/'3ds/source'/n).read_bytes()).hexdigest() for n in ('ds_exec.c','ds_cache.s')}
    previous=json.loads((PORTING/'dist/stage8/build-manifest.json').read_text())
    assert backend==previous['backend_sha256'],'Passed hardware backend changed'
    (BUILD/'build-manifest.json').write_text(json.dumps({'computer_only':True,'hardware_tested':False,'cia_produced':False,
        'hardware_execution_refused':True,'backend_matches_stage8':True,'backend_sha256':backend,'title_id':'000400000FDE5E00',
        'sources_sha256':{str(f.relative_to(PORTING)):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs},
        'outputs_sha256':{n:hashlib.sha256((BUILD/n).read_bytes()).hexdigest() for n in ('core-test.elf','engine-audit.elf','engine-audit.cxi')}},indent=2)+'\n')
    print('Built emulator-only runtime:',BUILD/'core-test.elf')
if __name__=='__main__':main()
