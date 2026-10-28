"""Build the computer-only engine experiment; never produces an installable CIA."""
import hashlib,json,zlib,shutil
from pathlib import Path
import build_stage1 as base
import verify_asset_directories
PORTING=base.PORTING
BUILD=PORTING/'3ds/build-emulator'
def main():
    BUILD.mkdir(exist_ok=True);base.BUILD=BUILD
    asset_contract=verify_asset_directories.write()
    apk=json.loads((PORTING/'analysis/android-abi/apk-asset-namespace-contract.json').read_text())
    stored=[item['path'] for item in apk['manifest'] if item['zip_method']==0]
    (BUILD/'apk_fd_contract.h').write_text('static const char *const apk_stored_assets[]={'+','.join(json.dumps(x) for x in stored)+'};\n')
    font=json.loads((PORTING/'analysis/font-subset-contract.json').read_text())
    (BUILD/'font_subset_config.h').write_text(f'#define DS28_FONT_SIZE {font["subset_bytes"]}u\n#define DS28_FONT_CRC 0x{font["subset_crc32"]}u\n')
    (BUILD/'assets_contract.h').write_text(''.join(f'#define ASSET_COUNT_{i} {d["count"]}u\n#define ASSET_CRC_{i} 0x{d["names_crc32"]}u\n' for i,d in enumerate(asset_contract['directories'].values())))
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
    base.run(base.GCC,*soft,'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_graphics.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-graphics.so')
    base.run(base.GCC,*soft,'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_arrays.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-arrays.so')
    base.run(base.GCC,*soft,'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_textures.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-textures.so')
    base.run(base.GCC,*soft,'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_pipeline.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-pipeline.so')
    for suffix,extra in (('',[]),('-thumb',['-mthumb','-fvisibility=hidden','-DDS17_THUMB_FIXTURE'])):
        fixtures=[PORTING/'tests/fixture_jump.c',PORTING/'tests/fixture_jump_regs.s']
        if suffix:fixtures.append(PORTING/'tests/fixture_jump_thumb.s')
        base.run(base.GCC,*soft,*extra,'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
            *fixtures,'-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/f'fixture-jump{suffix}.so')
    embedded=[]
    for label,suffix in (('arm',''),('thumb','-thumb')):
        blob=(BUILD/f'fixture-jump{suffix}.so').read_bytes()
        embedded.append(f'static const unsigned char jump_{label}_fixture[]={{\n'+
            '\n'.join(','.join(str(b) for b in blob[i:i+32])+',' for i in range(0,len(blob),32))+'\n};\n')
    (BUILD/'jump_fixture.h').write_text(''.join(embedded))
    base.run(base.GCC,*soft,'-I'+str(PORTING/'3ds/include'),'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_strings.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-strings.so')
    blob=(BUILD/'fixture-strings.so').read_bytes()
    (BUILD/'strings_fixture.h').write_text('static const unsigned char strings_fixture[]={\n'+
        '\n'.join(','.join(str(b) for b in blob[i:i+32])+',' for i in range(0,len(blob),32))+'\n};\n')
    base.run(base.GCC,*soft,'-I'+str(PORTING/'3ds/include'),'-I'+str(BUILD),'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_assets.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-assets.so')
    blob=(BUILD/'fixture-assets.so').read_bytes()
    (BUILD/'assets_fixture.h').write_text('static const unsigned char assets_fixture[]={\n'+
        '\n'.join(','.join(str(b) for b in blob[i:i+32])+',' for i in range(0,len(blob),32))+'\n};\n')
    names=('ds_elf.c','ds_io.c','ds_io_sd.c','ds_runtime_libc.c','ds_runtime_math.c','ds6_basics.c','ds6_stdio.c','ds6_time.c',
           'ds6_all.c','ds7_threads.c','ds8_cpp.c','ds_init.c','ds_jni.c','ds_bootstrap.c','ds9_memory.c','ds10_jni.c','ds11_platform.c','ds12_sensor.c','ds13_gles.c','ds14_arrays.c','ds15_textures.c','ds16_pipeline.c','ds17_jump.c','ds17_jump.s','ds18_strings.c','ds19_assets.c','ds20_dirs.c','ds21_matrices.c','ds22_draw.c','ds23_touch.c','ds24_files.c','ds26_framebuffer.c','ds28_font.c','ds29_allocator.c','ds30_fog.c','ds31_combine.c')
    sources=[PORTING/'3ds/source'/n for n in names]
    base.run(base.GCC,*base.FLAGS,'-DDS7_SEMAPHORE_COUNT=64','-I'+str(PORTING/'3ds/include'),'-ffreestanding','-fno-builtin','-fno-unwind-tables','-nostdlib',
        *sources,PORTING/'tests/runtime_heap.c',PORTING/'tests/runtime_os.c',PORTING/'tests/stage6_stat_fixture.c',PORTING/'tests/ds7_platform_model.c',PORTING/'tests/jni10_callbacks.c',PORTING/'tests/ds11_platform_model.c',PORTING/'tests/sensor_jni_model.c',PORTING/'tests/arrays_model.c',PORTING/'tests/textures_model.c',PORTING/'tests/pipeline_model.c',
        '-Wl,-Ttext=0x00100000','-Wl,-e,ds_elf_inspect','-Wl,--start-group','-lm','-lc','-lnosys','-lgcc','-Wl,--end-group','-o',BUILD/'core-test.elf')
    donor=base.DONOR.read_bytes()
    (BUILD/'donor_config.h').write_text(f'#define DS_DONOR_SIZE {len(donor)}u\n#define DS_DONOR_CRC32 0x{zlib.crc32(donor):08x}u\n')
    include=['-I'+str(PORTING/'3ds/include'),'-I'+str(BUILD),'-I'+str(base.DKP/'libctru/include')]
    for suffix,extra in (('',[]),('-178',['-DDS_NEW3DS_178'])):
        base.run(base.GCC,*base.FLAGS,*extra,'-DDS7_SEMAPHORE_COUNT=64',*include,'-fno-builtin','-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',
            *sources,PORTING/'3ds/source/ds_exec.c',PORTING/'3ds/source/ds_cache.s',PORTING/'3ds/source/ds6_platform_3ds.c',
            PORTING/'3ds/source/ds7_platform_3ds.c',PORTING/'3ds/source/ds11_platform_3ds.c',PORTING/'3ds/source/ds12_sensor_3ds.c',PORTING/'3ds/source/ds19_assets_3ds.c',PORTING/'3ds/source/ds20_dirs_3ds.c',PORTING/'3ds/source/ds24_files_3ds.c',PORTING/'3ds/source/ds25_assets_3ds.c',PORTING/'3ds/source/ds27_pages_3ds.c',PORTING/'tests/engine_trap.s',PORTING/'tests/engine_azahar.c',PORTING/'tests/jni10_callbacks.c',
            '-L'+str(base.DKP/'libctru/lib'),'-lctru','-lm','-Wl,--gc-sections','-o',BUILD/('engine-audit'+suffix+'.elf'))
    base.run(base.DKP/'tools/bin/smdhtool.exe','--create','DS Emulator Audit','Computer only - not a playable port','Homebrew research',
        PORTING/'3ds/build-stage8/icon.png',BUILD/'audit.smdh')
    rsf=(PORTING/'3ds/build-stage8/stage8.rsf').read_text().replace('0xFDE57','0xFDE5E').replace('TST8','AUDT').replace('DSL8','DSEA')
    rsf=rsf.replace('SystemModeExt: Legacy','SystemModeExt: 124MB')
    (BUILD/'audit.rsf').write_text(rsf)
    base.run(PORTING/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',BUILD/'engine-audit.cxi','-rsf',BUILD/'audit.rsf','-target','t','-exefslogo',
        '-elf',BUILD/'engine-audit.elf','-icon',BUILD/'audit.smdh','-banner',PORTING/'3ds/build-stage8/stage8.bnr')
    (BUILD/'audit-178.rsf').write_text(rsf.replace('SystemModeExt: 124MB','SystemModeExt: 178MB').replace('ReleaseKernelMinor: "33"','ReleaseKernelMinor: "44"'))
    base.run(PORTING/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',BUILD/'engine-audit-178.cxi','-rsf',BUILD/'audit-178.rsf','-target','t','-exefslogo',
        '-elf',BUILD/'engine-audit-178.elf','-icon',BUILD/'audit.smdh','-banner',PORTING/'3ds/build-stage8/stage8.bnr')
    inputs=sources+[PORTING/'tests'/n for n in ('engine_azahar.c','engine_trap.s','runtime_heap.c','runtime_os.c','stage6_stat_fixture.c','ds7_platform_model.c','fixture_memory.c','fixture_jni10.c','jni10_callbacks.c','ds11_platform_model.c','fixture_platform.c','sensor_jni_model.c')]
    inputs+=[PORTING/'analysis/android-abi/candidate-sd-package.json',PORTING/'tests/fixture_graphics.c',PORTING/'tests/fixture_arrays.c',PORTING/'tests/arrays_model.c',PORTING/'tests/textures_model.c',PORTING/'tests/fixture_textures.c',PORTING/'tests/pipeline_model.c',PORTING/'tests/fixture_pipeline.c',PORTING/'tests/fixture_jump.c',PORTING/'tests/fixture_jump_regs.s',PORTING/'tests/fixture_jump_thumb.s',PORTING/'analysis/android-abi/jump-abi-contract.json',PORTING/'tests/fixture_strings.c']
    inputs+=[PORTING/'3ds/source'/n for n in ('ds_exec.c','ds_cache.s','ds6_platform_3ds.c','ds7_platform_3ds.c','ds11_platform_3ds.c','ds12_sensor_3ds.c','ds19_assets_3ds.c','ds20_dirs_3ds.c','ds24_files_3ds.c','ds25_assets_3ds.c','ds27_pages_3ds.c')]
    inputs+=list((PORTING/'3ds/include').glob('*.h'))
    inputs+=[PORTING/'tests/fixture_assets.c',PORTING/'analysis/asset-directory-contract.json',PORTING/'tools/verify_asset_directories.py',PORTING/'analysis/android-abi/apk-asset-namespace-contract.json']
    inputs+=[Path(__file__).resolve(),PORTING/'tools/build_stage1.py',PORTING/'3ds/build-stage8/stage8.rsf']
    inputs+=[PORTING/'analysis/font-subset-contract.json',PORTING/'tools/prepare_font_subset.py']
    backend={n:hashlib.sha256((PORTING/'3ds/source'/n).read_bytes()).hexdigest() for n in ('ds_exec.c','ds_cache.s')}
    previous=json.loads((PORTING/'dist/stage8/build-manifest.json').read_text())
    assert backend==previous['backend_sha256'],'Passed hardware backend changed'
    (BUILD/'build-manifest.json').write_text(json.dumps({'computer_only':True,'hardware_tested':False,'cia_produced':False,
        'hardware_execution_refused':True,'backend_matches_stage8':True,'backend_sha256':backend,'title_id':'000400000FDE5E00','semaphore_capacity':64,
        'sources_sha256':{str(f.relative_to(PORTING)):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs},
        'outputs_sha256':{n:hashlib.sha256((BUILD/n).read_bytes()).hexdigest() for n in ('core-test.elf','engine-audit.elf','engine-audit-178.elf','engine-audit.cxi','engine-audit-178.cxi','fixture-graphics.so','fixture-arrays.so','fixture-textures.so','fixture-pipeline.so','fixture-jump.so','fixture-jump-thumb.so','fixture-strings.so','fixture-assets.so')}},indent=2)+'\n')
    print('Built emulator-only runtime:',BUILD/'core-test.elf')
if __name__=='__main__':main()
