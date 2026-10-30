"""Package the tested independent control; never runs hardware or edits DS34."""
import hashlib,json,re,shutil,subprocess,zipfile
from pathlib import Path
P=Path(__file__).resolve().parents[1]
B=P/'3ds/build-citro3d-control';E=P/'analysis/azahar-citro3d-control'
D=P/'dist/citro3d-control-v0.1.0'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((B/'build-manifest.json').read_text());test=json.loads((E/'result.json').read_text())
    fault=json.loads((P/'analysis/azahar-citro3d-control-fault/result.json').read_text())
    assert test['passed'] and test['START_exit_drained'] and test['invalid_accesses']==0
    assert fault['passed'] and fault['intentional_fault'] and fault['native_result']['timeout'] and fault['START_exit_drained']
    assert not manifest['fault_injection_compiled'] and manifest['ds34_linked'] is False
    assert manifest['same_binary_capabilities_except_program_id'] and manifest['same_SDK_library_hashes']
    assert sha(B/'control.cia')==test['cia_sha256']
    for name,h in manifest['inputs_sha256'].items():assert sha(P/name)==h,name
    for name,h in manifest['outputs_sha256'].items():assert sha(B/name)==h,name
    symbols=subprocess.check_output([str(P/'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-nm.exe'),'-g','--defined-only',str(B/'control.elf')],text=True)
    assert not re.search(r'\b(?:ds34_|ds13_|ds22_|ds_runtime_|ds_exec_|ds_elf_|NativeOnDrawFrame)\w*',symbols)
    assert b'Emulator-only fault build' not in (B/'control.elf').read_bytes()
    result=subprocess.run([str(P/'toolchain/extras/ctrtool/ctrtool.exe'),'--verify',str(B/'control.cia')],capture_output=True,text=True)
    output=result.stdout+result.stderr
    errors=[x for x in output.splitlines() if ' ERROR]' in x]
    expected=['Signature for Ticket was invalid','Signature for TitleMetaData was invalid','Signature for AccessDescriptor was invalid']
    assert len(errors)==3 and all(any(e in x for e in expected) for x in errors),errors
    hashes=[x.strip() for x in output.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)',x)]
    assert len(hashes)>=3 and all('(GOOD)' in x for x in hashes)
    D.mkdir(exist_ok=True);v=D/'validation';v.mkdir(exist_ok=True)
    shutil.copyfile(B/'control.cia',D/'citro3d-control-v0.1.0.cia')
    shutil.copyfile(P/'3ds/README-citro3d-control.ru.md',D/'README.ru.md')
    shutil.copyfile(P/'toolchain/citro3d/LICENSE',D/'LICENSE-citro3d.md')
    for name in ['result.json','control.log','clear.png','triangle.png','stage-0-queue.json','stage-1-queue.json','stage-1-1.pica','triangle-vertices.bin']:
        shutil.copyfile(E/name,v/name)
    shutil.copyfile(P/'analysis/azahar-citro3d-control-fault/result.json',v/'fault-test.json')
    shutil.copyfile(P/'analysis/citro3d-control/comparison.json',v/'comparison.json')
    release={**manifest,'emulator_tested':True,'hardware_tested':False,'hardware_run_authorized':False,'not_a_DS34_fix':True,
        'symbols_check_no_DS34_GLES_engine':True,'hash_checks':hashes,'game_resources_included':False}
    release['files']={f.relative_to(D).as_posix():{'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(D.rglob('*')) if f.is_file() and f.name!='build-manifest.json'}
    assert set(release['files'])=={'citro3d-control-v0.1.0.cia','README.ru.md','LICENSE-citro3d.md',*[f'validation/{n}' for n in ['result.json','control.log','clear.png','triangle.png','stage-0-queue.json','stage-1-queue.json','stage-1-1.pica','triangle-vertices.bin','fault-test.json','comparison.json']]}
    (D/'build-manifest.json').write_text(json.dumps(release,indent=2)+'\n')
    archive=P/'dist/citro3d-control-v0.1.0.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(D.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(D).as_posix())
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None and set(z.namelist())==set(release['files'])|{'build-manifest.json'}
    check={'passed':True,'hardware_tested':False,'hardware_run_authorized':False,'not_a_DS34_fix':True,
        'cia_sha256':sha(B/'control.cia'),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'symbols_check_no_DS34_GLES_engine':True,
        'original_game_resources_included':False,'hash_checks':hashes,'CIA_title_id':manifest['title_id']}
    (P/'analysis/citro3d-control/package.json').write_text(json.dumps(check,indent=2)+'\n');print(json.dumps(check,indent=2))
if __name__=='__main__':main()
