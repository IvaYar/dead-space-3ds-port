"""Build, validate and package the C++ lifecycle milestone."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PORTING=Path(__file__).resolve().parents[1]
DIST=PORTING/'dist/stage8'

def run(script,*args):
    subprocess.run([sys.executable,str(PORTING/script),*args],check=True,cwd=PORTING.parent)

def main():
    run('tools/build_stage8.py')
    run('tests/test_stage8_regression.py')
    run('tests/test_stage8_cpp.py')
    run('tools/verify_stage1.py','--stage','8')
    for format_ in ('3dsx','cxi'):
        for case in ('ready','missing','wrong','present','repeat'):
            run('tests/smoke_azahar.py','--stage','8','--format',format_,'--case',case)
    run('tests/smoke_azahar.py','--stage','8','--format','cxi','--case','stalled')
    run('tests/smoke_azahar.py','--stage','8','--format','cxi','--case','bad-ctor')
    shutil.copyfile(PORTING/'3ds/README-stage8.ru.md',DIST/'README.ru.md')
    validation=DIST/'validation'; validation.mkdir(exist_ok=True)
    for filename in ('stage8-regression.json','stage8-cpp-tests.json','stage8-import-audit.json','stage8-package-check.json'):
        shutil.copyfile(PORTING/'analysis'/filename,validation/filename)
    for suffix in ('result.json','user.log'):
        name=f'stage7-v0.7.0-{suffix}'
        shutil.copyfile(PORTING/'analysis/hardware'/name,validation/name)
    for path in (PORTING/'analysis/azahar-smoke').iterdir():
        if path.name.startswith(('result-stage8-','stage8-3dsx-','stage8-cxi-')):
            shutil.copyfile(path,validation/path.name)
    shutil.copyfile(PORTING/'analysis/android-abi/stage8-sources.json',validation/'android-abi-sources.json')
    manifest_path=DIST/'build-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    previous=json.loads((PORTING/'dist/stage7/build-manifest.json').read_text(encoding='utf-8'))
    assert manifest['backend_sha256']==previous['backend_sha256'],'RX backend changed'
    regression=json.loads((validation/'stage8-regression.json').read_text(encoding='utf-8'))
    libc=json.loads((validation/'stage8-cpp-tests.json').read_text(encoding='utf-8'))
    manifest['validation']={'arm_regression_tests':regression['tests_run'],'arm_cpp_lifecycle_tests':libc['tests_run'],
        'azahar_cases':12,'includes_retained_image_timeout':True,'includes_bad_constructor_refusal':True,'includes_repeated_run_in_one_process':True,'cia_hashes_verified':True,
        'stage8_hardware_tested':False,'game_functions_called':False,'game_constructors_called':False,'test_module_constructors_called':True,
        'donor_preflight_expected_refusal':True,'backend_matches_stage7_passed_build':True}
    manifest['files']={}
    for path in sorted(DIST.rglob('*')):
        if path.is_file() and path!=manifest_path:
            manifest['files'][path.relative_to(DIST).as_posix()]={
                'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    version=manifest['version']
    archive_path=PORTING/f'dist/deadspace-3ds-stage8-v{version}-local.zip'
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(DIST.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(DIST).as_posix())
    with zipfile.ZipFile(archive_path) as archive: assert archive.testzip() is None
    cia_path=PORTING/f'dist/deadspace-loader-stage8-v{version}.cia'
    shutil.copyfile(DIST/'deadspace-loader-stage8.cia',cia_path)
    print('Stage 8 package:',archive_path,'bytes:',archive_path.stat().st_size)
    print('SHA256:',hashlib.sha256(archive_path.read_bytes()).hexdigest())
    print('CIA:',cia_path)

if __name__=='__main__': main()
