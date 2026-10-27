"""Build, validate and package the Android memory/string/math milestone."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PORTING=Path(__file__).resolve().parents[1]
DIST=PORTING/'dist/stage5'


def run(script,*args):
    subprocess.run([sys.executable,str(PORTING/script),*args],check=True,cwd=PORTING.parent)


def main():
    run('tools/build_stage5.py')
    run('tests/test_stage5_regression.py')
    run('tests/test_stage5_runtime.py')
    run('tools/verify_stage1.py','--stage','5')
    for format_ in ('3dsx','cxi'):
        for case in ('ready','missing','wrong','present','repeat'):
            run('tests/smoke_azahar.py','--stage','5','--format',format_,'--case',case)
    shutil.copyfile(PORTING/'3ds/README-stage5.ru.md',DIST/'README.ru.md')
    validation=DIST/'validation'; validation.mkdir(exist_ok=True)
    for filename in ('stage5-regression.json','stage5-runtime-tests.json','stage5-import-audit.json','stage5-package-check.json'):
        shutil.copyfile(PORTING/'analysis'/filename,validation/filename)
    for suffix in ('result.json','user.log'):
        name=f'stage4-v0.4.0-{suffix}'
        shutil.copyfile(PORTING/'analysis/hardware'/name,validation/name)
    for path in (PORTING/'analysis/azahar-smoke').iterdir():
        if path.name.startswith(('result-stage5-','stage5-3dsx-','stage5-cxi-')):
            shutil.copyfile(path,validation/path.name)
    manifest_path=DIST/'build-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    previous=json.loads((PORTING/'dist/stage4/build-manifest.json').read_text(encoding='utf-8'))
    assert manifest['backend_sha256']==previous['backend_sha256'],'RX backend changed'
    regression=json.loads((validation/'stage5-regression.json').read_text(encoding='utf-8'))
    runtime=json.loads((validation/'stage5-runtime-tests.json').read_text(encoding='utf-8'))
    manifest['validation']={'arm_regression_tests':regression['tests_run'],'arm_runtime_tests':runtime['tests_run'],
        'azahar_cases':10,'includes_repeated_run_in_one_process':True,'cia_hashes_verified':True,
        'stage5_hardware_tested':False,'game_functions_called':False,'constructors_called':False,
        'donor_preflight_expected_refusal':True,'backend_matches_stage4_passed_build':True}
    manifest['files']={}
    for path in sorted(DIST.rglob('*')):
        if path.is_file() and path!=manifest_path:
            manifest['files'][path.relative_to(DIST).as_posix()]={
                'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    version=manifest['version']
    archive_path=PORTING/f'dist/deadspace-3ds-stage5-v{version}-local.zip'
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(DIST.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(DIST).as_posix())
    with zipfile.ZipFile(archive_path) as archive: assert archive.testzip() is None
    cia_path=PORTING/f'dist/deadspace-loader-stage5-v{version}.cia'
    shutil.copyfile(DIST/'deadspace-loader-stage5.cia',cia_path)
    print('Stage 5 package:',archive_path,'bytes:',archive_path.stat().st_size)
    print('SHA256:',hashlib.sha256(archive_path.read_bytes()).hexdigest())
    print('CIA:',cia_path)


if __name__=='__main__': main()
