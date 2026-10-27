"""Build, validate and package the Bionic libc integration milestone."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PORTING=Path(__file__).resolve().parents[1]
DIST=PORTING/'dist/stage7'

def run(script,*args):
    subprocess.run([sys.executable,str(PORTING/script),*args],check=True,cwd=PORTING.parent)

def main():
    run('tools/build_stage7.py')
    run('tests/test_stage7_regression.py')
    run('tests/test_stage7_threads.py')
    run('tools/verify_stage1.py','--stage','7')
    for format_ in ('3dsx','cxi'):
        for case in ('ready','missing','wrong','present','repeat'):
            run('tests/smoke_azahar.py','--stage','7','--format',format_,'--case',case)
    run('tests/smoke_azahar.py','--stage','7','--format','cxi','--case','stalled')
    shutil.copyfile(PORTING/'3ds/README-stage7.ru.md',DIST/'README.ru.md')
    validation=DIST/'validation'; validation.mkdir(exist_ok=True)
    for filename in ('stage7-regression.json','stage7-thread-tests.json','stage7-import-audit.json','stage7-package-check.json'):
        shutil.copyfile(PORTING/'analysis'/filename,validation/filename)
    for suffix in ('result.json','user.log'):
        name=f'stage6-v0.6.0-{suffix}'
        shutil.copyfile(PORTING/'analysis/hardware'/name,validation/name)
    for path in (PORTING/'analysis/azahar-smoke').iterdir():
        if path.name.startswith(('result-stage7-','stage7-3dsx-','stage7-cxi-')):
            shutil.copyfile(path,validation/path.name)
    shutil.copyfile(PORTING/'analysis/android-abi/stage7-sources.json',validation/'android-abi-sources.json')
    manifest_path=DIST/'build-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    previous=json.loads((PORTING/'dist/stage6/build-manifest.json').read_text(encoding='utf-8'))
    assert manifest['backend_sha256']==previous['backend_sha256'],'RX backend changed'
    regression=json.loads((validation/'stage7-regression.json').read_text(encoding='utf-8'))
    libc=json.loads((validation/'stage7-thread-tests.json').read_text(encoding='utf-8'))
    manifest['validation']={'arm_regression_tests':regression['tests_run'],'arm_thread_api_tests':libc['tests_run'],
        'azahar_cases':11,'includes_retained_image_timeout':True,'includes_repeated_run_in_one_process':True,'cia_hashes_verified':True,
        'stage7_hardware_tested':False,'game_functions_called':False,'constructors_called':False,
        'donor_preflight_expected_refusal':True,'backend_matches_stage6_passed_build':True}
    manifest['files']={}
    for path in sorted(DIST.rglob('*')):
        if path.is_file() and path!=manifest_path:
            manifest['files'][path.relative_to(DIST).as_posix()]={
                'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    version=manifest['version']
    archive_path=PORTING/f'dist/deadspace-3ds-stage7-v{version}-local.zip'
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(DIST.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(DIST).as_posix())
    with zipfile.ZipFile(archive_path) as archive: assert archive.testzip() is None
    cia_path=PORTING/f'dist/deadspace-loader-stage7-v{version}.cia'
    shutil.copyfile(DIST/'deadspace-loader-stage7.cia',cia_path)
    print('Stage 7 package:',archive_path,'bytes:',archive_path.stat().st_size)
    print('SHA256:',hashlib.sha256(archive_path.read_bytes()).hexdigest())
    print('CIA:',cia_path)

if __name__=='__main__': main()
