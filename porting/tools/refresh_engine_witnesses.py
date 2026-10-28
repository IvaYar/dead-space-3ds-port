"""Refresh legacy emulator witnesses sequentially, after extended runs finish.

The emulator SD is shared: never run this beside another native smoke process.
Commercial resources and private saves stay in ignored local directories.
"""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
P=Path(__file__).resolve().parents[1];ROOT=P/'analysis/azahar-smoke'
CARD=ROOT/'Azahar/sdmc/3ds/deadspace'

def run(name,*args):
    result=subprocess.run([sys.executable,*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=P.parent)
    (P/'analysis'/('refresh-'+name+'-console.txt')).write_bytes(result.stdout)
    if result.returncode:raise RuntimeError(f'{name} failed; inspect analysis/refresh-{name}-console.txt')
    print(name+' OK',flush=True)

def smoke(name,*args):run(name,P/'tests/smoke_engine_azahar.py',*args)

def snapshot(folder,logname='run'):
    folder=P/'analysis'/folder;folder.mkdir(exist_ok=True)
    run('export-'+folder.name,P/'tools/export_native_frame.py','--output-directory',folder)
    shutil.copyfile(ROOT/'engine-graphics-explore.log',folder/(logname+'.log'))
    shutil.copyfile(ROOT/'engine-graphics-explore-result.json',folder/(logname+'-result.json'))
    shutil.copyfile(ROOT/'engine-graphics-screen.png',folder/'azahar-screen.png')

def saves(folder,state):
    root=CARD/'test-output/save-bridge';dest=P/'analysis'/state;receipt={}
    for file in root.rglob('*'):
        if not file.is_file():continue
        name=file.relative_to(root).as_posix();target=dest/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(file,target);receipt[name]={'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (P/'analysis'/folder/'save-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

def main():
    for case in ('ready','missing','wrong','present','asset-missing','asset-wrong','content-unverified','sensor','graphics'):
        smoke('case-'+case,'--case',case)
    run('export-first-frame',P/'tools/export_native_frame.py')
    shutil.copyfile(ROOT/'engine-graphics-screen.png',P/'analysis/first-frame/azahar-screen.png')
    smoke('headphones','--case','graphics','--explore','--capture-frame',120)
    snapshot('headphone-frame','engine-frame120')
    common=['--case','graphics','--explore','--resume-focus','--touch','--tap-frame',160,'--private-files']
    smoke('private-files',*common,'--timeout-seconds',120,'--capture-frame',240)
    snapshot('input-save-frame');saves('input-save-frame','input-save-state')
    smoke('apk-assets',*common,'--timeout-seconds',120,'--capture-frame',180,'--apk-assets','--shared-arena')
    snapshot('apk-assets-frame');saves('apk-assets-frame','apk-assets-state')
    smoke('legacy-fbo-barrier',*common,'--timeout-seconds',300,'--capture-frame',600,'--apk-assets','--shared-arena')
    prefix='engine-apk600-shared100'
    shutil.copyfile(ROOT/'engine-graphics-explore.log',ROOT/(prefix+'.log'))
    report=json.loads((ROOT/'engine-graphics-explore-result.json').read_text());report['log']='analysis/azahar-smoke/'+prefix+'.log'
    (ROOT/(prefix+'-result.json')).write_text(json.dumps(report,indent=2)+'\n')
    for name in ('check_first_frame','check_headphone_frame','check_input_save','check_apk_assets'):
        run(name,P/'tools'/(name+'.py'))

if __name__=='__main__':main()
