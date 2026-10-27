"""Build, validate and package the Bionic libc integration milestone."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PORTING=Path(__file__).resolve().parents[1]
DIST=PORTING/'dist/stage6'

def run(script,*args):
    subprocess.run([sys.executable,str(PORTING/script),*args],check=True,cwd=PORTING.parent)

def main():
    run('tools/build_stage6.py')
    run('tests/test_stage6_regression.py')
    run('tests/test_stage6_libc.py')
    run('tools/verify_stage1.py','--stage','6')
    for format_ in ('3dsx','cxi'):
        for case in ('ready','missing','wrong','asset-missing','asset-wrong','present','repeat'):
            run('tests/smoke_azahar.py','--stage','6','--format',format_,'--case',case)
    shutil.copyfile(PORTING/'3ds/README-stage6.ru.md',DIST/'README.ru.md')
    validation=DIST/'validation'; validation.mkdir(exist_ok=True)
    for filename in ('stage6-regression.json','stage6-libc-tests.json','stage6-import-audit.json','stage6-package-check.json'):
        shutil.copyfile(PORTING/'analysis'/filename,validation/filename)
    for suffix in ('result.json','user.log'):
        name=f'stage5-v0.5.0-{suffix}'
        shutil.copyfile(PORTING/'analysis/hardware'/name,validation/name)
    for path in (PORTING/'analysis/azahar-smoke').iterdir():
        if path.name.startswith(('result-stage6-','stage6-3dsx-','stage6-cxi-')):
            shutil.copyfile(path,validation/path.name)
    shutil.copyfile(PORTING/'analysis/android-abi/stage6-sources.json',validation/'android-abi-sources.json')
    manifest_path=DIST/'build-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    previous=json.loads((PORTING/'dist/stage5/build-manifest.json').read_text(encoding='utf-8'))
    assert manifest['backend_sha256']==previous['backend_sha256'],'RX backend changed'
    regression=json.loads((validation/'stage6-regression.json').read_text(encoding='utf-8'))
    libc=json.loads((validation/'stage6-libc-tests.json').read_text(encoding='utf-8'))
    manifest['validation']={'arm_regression_tests':regression['tests_run'],'arm_libc_tests':libc['tests_run'],
        'azahar_cases':14,'includes_repeated_run_in_one_process':True,'cia_hashes_verified':True,
        'stage6_hardware_tested':False,'game_functions_called':False,'constructors_called':False,
        'donor_preflight_expected_refusal':True,'backend_matches_stage5_passed_build':True}
    manifest['files']={}
    for path in sorted(DIST.rglob('*')):
        if path.is_file() and path!=manifest_path:
            manifest['files'][path.relative_to(DIST).as_posix()]={
                'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    version=manifest['version']
    archive_path=PORTING/f'dist/deadspace-3ds-stage6-v{version}-local.zip'
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(DIST.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(DIST).as_posix())
    with zipfile.ZipFile(archive_path) as archive: assert archive.testzip() is None
    cia_path=PORTING/f'dist/deadspace-loader-stage6-v{version}.cia'
    shutil.copyfile(DIST/'deadspace-loader-stage6.cia',cia_path)
    print('Stage 6 package:',archive_path,'bytes:',archive_path.stat().st_size)
    print('SHA256:',hashlib.sha256(archive_path.read_bytes()).hexdigest())
    print('CIA:',cia_path)

if __name__=='__main__': main()
