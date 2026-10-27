"""Build, validate and package Android-ABI read-only asset I/O diagnostics."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PORTING=Path(__file__).resolve().parents[1]
DIST=PORTING/'dist/stage4'


def run(script,*args):
    subprocess.run([sys.executable,str(PORTING/script),*args],check=True,cwd=PORTING.parent)


def main():
    run('tools/build_stage4.py')
    run('tests/test_stage4_regression.py')
    run('tests/test_stage4_io.py')
    run('tools/verify_stage1.py','--stage','4')
    for format_ in ('3dsx','cxi'):
        for case in ('ready','missing','wrong','asset-missing','asset-wrong','present'):
            run('tests/smoke_azahar.py','--stage','4','--format',format_,'--case',case)
    shutil.copyfile(PORTING/'3ds/README-stage4.ru.md',DIST/'README.ru.md')
    validation=DIST/'validation'; validation.mkdir(exist_ok=True)
    for filename in ('stage4-regression.json','stage4-io-tests.json','stage4-import-audit.json','stage4-package-check.json'):
        shutil.copyfile(PORTING/'analysis'/filename,validation/filename)
    for version,stage in (('0.2.2',2),('0.3.0',3)):
        for suffix in ('result.json','user.log'):
            name=f'stage{stage}-v{version}-{suffix}'
            shutil.copyfile(PORTING/'analysis/hardware'/name,validation/name)
    for path in (PORTING/'analysis/azahar-smoke').iterdir():
        if path.name.startswith(('result-stage4-','stage4-3dsx-','stage4-cxi-')):
            shutil.copyfile(path,validation/path.name)
    shutil.copyfile(PORTING/'analysis/android-abi/sources.json',validation/'android-abi-sources.json')
    manifest_path=DIST/'build-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    # The backend must match the sources archived in stage 3's passed build.
    previous=json.loads((PORTING/'dist/stage3/build-manifest.json').read_text(encoding='utf-8'))
    assert manifest['backend_sha256']==previous['backend_sha256'],'RX backend changed'
    regression=json.loads((validation/'stage4-regression.json').read_text(encoding='utf-8'))
    io=json.loads((validation/'stage4-io-tests.json').read_text(encoding='utf-8'))
    manifest['validation']={'arm_regression_tests':regression['tests_run'],'arm_io_tests':io['tests_run'],
        'azahar_cases':12,'cia_hashes_verified':True,'stage4_hardware_tested':False,
        'game_functions_called':False,'constructors_called':False,'donor_preflight_expected_refusal':True,
        'backend_matches_stage3_passed_build':True}
    manifest['files']={}
    for path in sorted(DIST.rglob('*')):
        if path.is_file() and path!=manifest_path:
            manifest['files'][path.relative_to(DIST).as_posix()]={
                'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    version=manifest['version']
    archive_path=PORTING/f'dist/deadspace-3ds-stage4-v{version}-local.zip'
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(DIST.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(DIST).as_posix())
    with zipfile.ZipFile(archive_path) as archive: assert archive.testzip() is None
    cia_path=PORTING/f'dist/deadspace-loader-stage4-v{version}.cia'
    shutil.copyfile(DIST/'deadspace-loader-stage4.cia',cia_path)
    print('Stage 4 package:',archive_path,'bytes:',archive_path.stat().st_size)
    print('SHA256:',hashlib.sha256(archive_path.read_bytes()).hexdigest())
    print('CIA:',cia_path)


if __name__=='__main__': main()
