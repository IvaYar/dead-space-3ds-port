"""Build isolated sensor tests; leaves the 158-test engine checkpoint untouched."""
import hashlib,json
from pathlib import Path
import build_stage1 as base
PORTING=base.PORTING;BUILD=PORTING/'3ds/build-sensor'
def main():
    BUILD.mkdir(exist_ok=True);base.BUILD=BUILD
    include=['-I'+str(PORTING/'3ds/include')]
    core=[PORTING/'3ds/source/ds12_sensor.c',PORTING/'tests/sensor_model.c']
    base.run(base.GCC,*base.FLAGS,*include,'-ffreestanding','-fno-builtin','-nostdlib',*core,
        '-Wl,-Ttext=0x00100000','-Wl,-e,ds12_sensor_init','-Wl,--start-group','-lm','-lc','-lnosys','-lgcc','-Wl,--end-group','-o',BUILD/'sensor-test.elf')
    soft=[f for f in base.FLAGS if not f.startswith('-mfloat-abi=')]+['-mfloat-abi=softfp','-mfpu=vfp']
    base.run(base.GCC,*soft,*include,'-fPIC','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-shared',
        PORTING/'tests/fixture_sensor.c','-Wl,--hash-style=sysv','-Wl,-z,max-page-size=4096','-o',BUILD/'fixture-sensor.so')
    native=[PORTING/'3ds/source'/n for n in ('ds12_sensor.c','ds12_sensor_3ds.c','ds_exec.c','ds_cache.s')]+[PORTING/'tests/sensor_azahar.c']
    base.run(base.GCC,*base.FLAGS,*include,'-I'+str(base.DKP/'libctru/include'),'-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',
        *native,'-L'+str(base.DKP/'libctru/lib'),'-lctru','-lm','-Wl,--gc-sections','-o',BUILD/'sensor-audit.elf')
    rsf=(PORTING/'3ds/build-stage8/stage8.rsf').read_text().replace('0xFDE57','0xFDE5F').replace('TST8','SENS').replace('DSL8','DSSN')
    (BUILD/'sensor.rsf').write_text(rsf)
    base.run(PORTING/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',BUILD/'sensor-audit.cxi','-rsf',BUILD/'sensor.rsf','-target','t','-exefslogo',
        '-elf',BUILD/'sensor-audit.elf','-icon',PORTING/'3ds/build-emulator/audit.smdh','-banner',PORTING/'3ds/build-stage8/stage8.bnr')
    backend={n:hashlib.sha256((PORTING/'3ds/source'/n).read_bytes()).hexdigest() for n in ('ds_exec.c','ds_cache.s')}
    assert backend==json.loads((PORTING/'dist/stage8/build-manifest.json').read_text())['backend_sha256']
    sources=list(dict.fromkeys(core+native+[PORTING/'tests/fixture_sensor.c',PORTING/'3ds/include/ds12_sensor.h',PORTING/'3ds/include/ds_jni.h',PORTING/'3ds/include/ds_exec.h',PORTING/'tools/build_stage1.py',Path(__file__).resolve(),
        PORTING/'tests/test_sensor.py',PORTING/'tests/smoke_sensor_azahar.py',PORTING/'3ds/build-stage8/stage8.rsf',PORTING/'3ds/build-stage8/stage8.bnr',PORTING/'3ds/build-emulator/audit.smdh']))
    report={'hardware_tested':False,'game_adapter_enabled':False,'cia_produced':False,'backend_sha256':backend,
        'sources_sha256':{str(p.relative_to(PORTING)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'outputs_sha256':{n:hashlib.sha256((BUILD/n).read_bytes()).hexdigest() for n in ('sensor-test.elf','fixture-sensor.so','sensor-audit.elf','sensor-audit.cxi')}}
    (BUILD/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Built isolated sensor CPU and native CXI tests; no CIA.')
if __name__=='__main__':main()
