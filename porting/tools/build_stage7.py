"""Build Bionic stdio, metadata, formatting, time and atomic diagnostics."""
import hashlib
import json
import re
import shutil
import struct
import zlib
import build_stage1 as base
from inspect_packages import inspect_elf

PORTING=base.PORTING
BUILD=PORTING/'3ds/build-stage7'
DIST=PORTING/'dist/stage7'


def main():
    BUILD.mkdir(parents=True,exist_ok=True); DIST.mkdir(parents=True,exist_ok=True)
    base.BUILD=BUILD; run=base.run
    donor=base.DONOR.read_bytes()
    if hashlib.sha1(donor).hexdigest()!='3c4a1b844eddbf3b9f0d2d946433bc429cc64b2e': raise ValueError('Unexpected donor')
    (BUILD/'donor_config.h').write_text(f'#define DS_DONOR_SIZE {len(donor)}u\n#define DS_DONOR_CRC32 0x{zlib.crc32(donor):08x}u\n',encoding='ascii')
    include=['-I'+str(PORTING/'3ds/include'),'-I'+str(BUILD)]
    soft=[f for f in base.FLAGS if not f.startswith('-mfloat-abi=')]+['-mfloat-abi=softfp','-mfpu=vfp']
    for name,flags in (('fixture-regression',base.FLAGS),('fixture-stage4',soft),('fixture-stage5',soft),('fixture-stage6',soft),('fixture-stage7',soft)):
        source=PORTING/'tests'/('fixture.c' if name=='fixture-regression' else name.replace('-','_')+'.c')
        run(base.GCC,*flags,'-fPIC','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
            source,*include,'-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/(name+'.so'))
    blob=(BUILD/'fixture-stage7.so').read_bytes()
    fixture_info=inspect_elf(blob)
    supported=re.findall(r'DS_BIND\("([^"]+)"', (PORTING/'3ds/include/ds_runtime_bindings.def').read_text())
    assert len(supported)==len(set(supported))==48
    extra=[]
    for filename in ('ds6_basics.c','ds6_stdio.c','ds6_time.c'):
        extra+=re.findall(r'\{"([^"]+)",\(uint32_t\)', (PORTING/'3ds/source'/filename).read_text())
    assert len(extra)==55 and len(set(extra))==55,extra
    thread_names=re.findall(r'\{"([^"]+)",\(uint32_t\)', (PORTING/'3ds/source/ds7_threads.c').read_text())
    assert len(thread_names)==40 and len(set(thread_names))==40
    expected=set(thread_names+['__errno','malloc','free','memset','sqrtf','clock_gettime','usleep'])
    assert set(fixture_info['imports'])==expected, (set(fixture_info['imports'])-expected,expected-set(fixture_info['imports']))
    phoff=struct.unpack_from('<I',blob,28)[0]; phnum=struct.unpack_from('<H',blob,44)[0]
    pages=[]
    for i in range(phnum):
        ph=struct.unpack_from('<8I',blob,phoff+i*32)
        if ph[0]==1 and ph[6]&1:
            pages.extend(range(ph[2]&~4095,(ph[2]+ph[5]+4095)&~4095,4096))
    assert 0<len(pages)<=16
    (BUILD/'stage7_fixture.h').write_text('static const uint32_t stage7_exec_pages[] = {'+','.join(str(p) for p in pages)+'};\n'+
        'static const unsigned char stage7_fixture[] = {\n'+'\n'.join(','.join(str(b) for b in blob[i:i+32])+',' for i in range(0,len(blob),32))+'\n};\n',encoding='ascii')
    sources=[PORTING/'3ds/source'/n for n in ('ds_elf.c','ds_io.c','ds_runtime_libc.c','ds_runtime_math.c','ds6_basics.c','ds6_stdio.c','ds6_time.c','ds6_all.c','ds7_threads.c')]
    run(base.GCC,*base.FLAGS,*include,'-ffreestanding','-fno-builtin','-fno-unwind-tables','-nostdlib',
        *sources,PORTING/'3ds/source/ds_io_sd.c',PORTING/'tests/runtime_heap.c',PORTING/'tests/runtime_os.c',PORTING/'tests/stage6_stat_fixture.c',PORTING/'tests/ds7_platform_model.c','-Wl,-Ttext=0x00100000','-Wl,-e,ds_elf_inspect',
        '-Wl,--start-group','-lm','-lc','-lnosys','-lgcc','-Wl,--end-group','-o',BUILD/'core-test.elf')
    run(base.GCC,*base.FLAGS,*include,'-fno-builtin','-I'+str(base.DKP/'libctru/include'),'-D__3DS__','-mword-relocations',
        '-specs=3dsx.specs','-Wl,-z,noexecstack',*sources,PORTING/'3ds/source/ds_io_sd.c',PORTING/'3ds/source/ds_exec.c',
        PORTING/'3ds/source/ds_cache.s',PORTING/'3ds/source/ds6_platform_3ds.c',PORTING/'3ds/source/ds7_platform_3ds.c',PORTING/'3ds/source/main_stage7.c','-L'+str(base.DKP/'libctru/lib'),'-lctru','-lm',
        '-Wl,--gc-sections','-Wl,-Map='+str(BUILD/'stage7.map'),'-o',BUILD/'deadspace-loader-stage7.elf')
    run(base.GCC,'-DDS7_INJECT_STALL',*base.FLAGS,*include,'-fno-builtin','-I'+str(base.DKP/'libctru/include'),'-D__3DS__','-mword-relocations',
        '-specs=3dsx.specs','-Wl,-z,noexecstack',*sources,PORTING/'3ds/source/ds_io_sd.c',PORTING/'3ds/source/ds_exec.c',
        PORTING/'3ds/source/ds_cache.s',PORTING/'3ds/source/ds6_platform_3ds.c',PORTING/'3ds/source/ds7_platform_3ds.c',PORTING/'3ds/source/main_stage7.c','-L'+str(base.DKP/'libctru/lib'),'-lctru','-lm',
        '-Wl,--gc-sections','-Wl,-Map='+str(BUILD/'stage7-stall.map'),'-o',BUILD/'deadspace-loader-stage7-stall.elf')
    base.make_assets(stage=7)
    run(base.DKP/'tools/bin/smdhtool.exe','--create','DS Loader Test 7','Stage 7 Android threads diagnostics',
        'Homebrew port research',BUILD/'icon.png',BUILD/'stage7.smdh')
    run(base.DKP/'tools/bin/3dsxtool.exe',BUILD/'deadspace-loader-stage7.elf',BUILD/'deadspace-loader-stage7.3dsx','--smdh='+str(BUILD/'stage7.smdh'))
    run(PORTING/'toolchain/extras/bannertool/bannertool.exe','makebanner','-i',BUILD/'banner.png','-a',BUILD/'silence.wav','-o',BUILD/'stage7.bnr')
    rsf=(PORTING/'3ds/stage1.rsf').read_text(encoding='utf-8')
    rsf=rsf.replace('"DS-LOADER-TEST"','"DS-LOADER-TST7"').replace('"CTR-H-DSLT"','"CTR-H-DSL7"').replace('0xFDE50','0xFDE56')
    rsf=rsf.replace('    ControlMemory: 1','    ControlProcessMemory: 112\n    FlushProcessDataCache: 84\n    QueryProcessMemory: 125\n    ControlMemory: 1')
    (BUILD/'stage7.rsf').write_text(rsf,encoding='utf-8')
    run(PORTING/'toolchain/extras/makerom/makerom.exe','-f','cia','-o',BUILD/'deadspace-loader-stage7.cia','-rsf',BUILD/'stage7.rsf',
        '-target','t','-exefslogo','-elf',BUILD/'deadspace-loader-stage7.elf','-icon',BUILD/'stage7.smdh','-banner',BUILD/'stage7.bnr','-ver','112')
    # Test-only CXI selects a slow worker to exercise retained-image shutdown.
    run(PORTING/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',BUILD/'deadspace-loader-stage7-stall.cxi','-rsf',BUILD/'stage7.rsf',
        '-target','t','-exefslogo','-elf',BUILD/'deadspace-loader-stage7-stall.elf','-icon',BUILD/'stage7.smdh','-banner',BUILD/'stage7.bnr')
    card=DIST/'SD_CARD'; app=card/'3ds/deadspace7'
    app.mkdir(parents=True,exist_ok=True); (card/'3ds/deadspace/assets/published/data').mkdir(parents=True,exist_ok=True); (card/'CIA').mkdir(exist_ok=True)
    shutil.copyfile(base.DONOR,card/'3ds/deadspace'/base.DONOR.name)
    shutil.copyfile(PORTING/'analysis/candidate-sd/assets/published/data/achievements.sb',card/'3ds/deadspace/assets/published/data/achievements.sb')
    shutil.copyfile(BUILD/'deadspace-loader-stage7.3dsx',app/'deadspace7.3dsx'); shutil.copyfile(BUILD/'stage7.smdh',app/'deadspace7.smdh')
    for target in (DIST/'deadspace-loader-stage7.cia',card/'CIA/deadspace-loader-stage7.cia'): shutil.copyfile(BUILD/'deadspace-loader-stage7.cia',target)
    imports=inspect_elf(donor)['imports']; supported=sorted(set(supported+extra+thread_names+['open','read','lseek','close','__errno'])&set(imports))
    assert len(supported)==145 and set(supported)<=set(imports)
    audit={'donor_imports':392,'supported_imports':supported,'remaining_imports':[n for n in imports if n not in supported],
           'required_missing':243,'weak_zero':4,'game_engine_started':False,'constructors_called':False}
    (PORTING/'analysis/stage7-import-audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    manifest={'stage':7,'version':'0.7.0','title_id':'000400000FDE5600','gameplay':False,'hardware_tested':False,'start_requires_A':True,
        'probe_scope':'Original softfp multithread/sync/TLS probes; no donor code executed',
        'backend_sha256':{n:hashlib.sha256((PORTING/'3ds/source'/n).read_bytes()).hexdigest() for n in ('ds_exec.c','ds_cache.s')},
        'donor_sha256':hashlib.sha256(donor).hexdigest(),'fixture_sha256':hashlib.sha256(blob).hexdigest(),
        'supported_imports':145,'fixture_imports':len(fixture_info['imports']),'registry_entries':148,'thread_limits':{'workers':16,'keys':32,'mutexes':64,'conditions':32,'semaphores':32},'fixture_exec_pages':pages,'diagnostic_allocation_limit':1048576}
    (DIST/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('Stage 7 built:',DIST)


if __name__=='__main__': main()
