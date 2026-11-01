"""Package only the verified experimental CIA and port sources; never original files."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

P=Path(__file__).resolve().parents[1]
B=P/'3ds/build-native-game-v0.1.0-h2'
A=P/'analysis/native-game-cia-v0.1.0'
D=P/'dist/native-game-v0.1.0'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert not D.exists() and not D.with_suffix('.zip').exists(),'Preserve existing package'
    build=json.loads((B/'build-manifest.json').read_text());cia=json.loads((B/'cia-manifest.json').read_text())
    for name,digest in build['inputs_sha256'].items():assert sha(P/name)==digest,name
    for name,digest in build['outputs_sha256'].items():assert sha(B/name)==digest,name
    assert sha(B/'native-game.cia')==cia['CIA_sha256']
    proofs={}
    for name in ['cxi','cia','cia-installed']:
        report=json.loads((P/('analysis/azahar-native-game-v0.1.0-h2-'+name)/'result.json').read_text())
        assert report['passed'] and report['safe_exit'] and report['sequential_cycles']==3
        assert report['CXI_sha256']==cia['payload_sha256']
        assert report['runner_sha256']==sha(P/'tests/smoke_native_game.py')
        if name!='cxi':assert report['CIA_sha256']==cia['CIA_sha256']
        assert all(c['passed'] and c['baseline_RGB565_exact'] and c['both_heaps_released'] and not c['invalid_memory_accesses'] and c['shutdown_proof']['kernel_joins']==6 and c['shutdown_proof']['worker_handles_remaining']==0 and c['shutdown_proof']['files_balanced'] for c in report['cycles'])
        if name=='cia-installed':assert all(c['loaded_installed_content'] for c in report['cycles'])
        proofs[name]=report
    audit=json.loads((A/'preflight.json').read_text());install=json.loads((A/'CIA-install.json').read_text())
    assert audit['static_preflight_passed'] and not audit['RomFS_present'] and install['passed']
    assert install['installed_content_sha256']==cia['payload_sha256']
    copies={B/'native-game.cia':'native-game.cia',P/'3ds/README-native-game.ru.md':'README.ru.md',P/'toolchain/citro3d/LICENSE':'LICENSE-citro3d.md',B/'build-manifest.json':'validation/build-manifest.json',B/'cia-manifest.json':'validation/cia-manifest.json'}
    for name in ['preflight.json','CIA-install.json','CIA-install.log','CIA-container-audit.txt','report.ru.md','SD-summary.json','initial-host-crash.json']:
        copies[A/name]='validation/'+name
    for name in ['cxi','cia','cia-installed']:
        copies[P/('analysis/azahar-native-game-v0.1.0-h2-'+name)/'result.json']='validation/'+name+'-result.json'
    for name in ['build_native_game.py','package_native_game.py']:copies[P/'tools'/name]='source/'+name
    for name in ['native_game.c','native_thread_probe.h','smoke_native_game.py','smoke_installed_native_game.py']:copies[P/'tests'/name]='source/'+name
    for name in ['ds7_threads_probe.c','ds7_platform_probe.c','ds6_time_probe.c','ds8_cpp_probe.c','ds34_gpu_native.c','ds34_shader.h']:copies[B/name]='source/runtime/'+name
    copies[P/'3ds/source/ds34_gpu.v.pica']='source/ds34_gpu.v.pica'
    D.mkdir(parents=True)
    for source,name in copies.items():
        target=D/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    manifest={'version':'0.1.0','revision':'h2','experimental':True,'title_id':cia['title_id'],'CIA_sha256':cia['CIA_sha256'],'hardware_tested':False,'hardware_run_authorized':False,'original_code_frame':True,'software_passed':True,'successful_final_cycles':9,'installed_CIA_content_tested':True,'original_resources_included':False,'known_earlier_host_crash':'h1 Azahar DLL 0xc0000005, not reproduced in final nine h2 cycles; cause unproven','files':{name:{'bytes':(D/name).stat().st_size,'sha256':sha(D/name)} for name in sorted(copies.values())}}
    (D/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=D.parent/(D.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as out:
        for name in [*sorted(copies.values()),'manifest.json']:out.write(D/name,name)
    with zipfile.ZipFile(archive) as check:
        assert check.testzip() is None
        assert set(check.namelist())==set(copies.values())|{'manifest.json'}
        assert not any(Path(n).suffix.lower() in ['.apk','.so','.ttf','.raw','.png'] for n in check.namelist())
        for name,entry in manifest['files'].items():assert hashlib.sha256(check.read(name)).hexdigest()==entry['sha256']
    (A/'package.json').write_text(json.dumps({'archive':archive.relative_to(P).as_posix(),'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'CIA_sha256':cia['CIA_sha256'],'files':len(copies)+1,'original_resources_included':False,'hardware_run_authorized':False},indent=2)+'\n')
    print((A/'package.json').read_text())

if __name__=='__main__':main()
