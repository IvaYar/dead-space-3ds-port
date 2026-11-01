"""Original donor callback 180 through the separate native entry point in Azahar."""
import argparse
import ctypes as C
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from PIL import Image
P=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--revision',default='');parser.add_argument('--cycles',type=int,default=3);args=parser.parse_args()
assert 1<=args.cycles<=5
assert not args.revision or args.revision.isalnum()
SUFFIX='-'+args.revision if args.revision else ''
ROOT=P/('analysis/azahar-native-frame-v0.1.0'+SUFFIX)
if ROOT.exists():raise SystemExit('Do not overwrite checkpoint evidence')
os.environ['DEADSPACE_EMULATOR_ROOT']=str(ROOT)
import smoke_azahar as f
f.OPTIONS[b'citra_cpu_clock_percentage']=b'400'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def finish(code):
    sys.stdout.flush();sys.stderr.flush()
    kernel=C.WinDLL('kernel32');kernel.GetCurrentProcess.restype=C.c_void_p
    kernel.TerminateProcess.argtypes=[C.c_void_p,C.c_uint]
    kernel.TerminateProcess(kernel.GetCurrentProcess(),code)

def main():
    build=P/('3ds/build-native-frame-v0.1.0'+SUFFIX);app=build/'native-frame.cxi'
    assert app.exists(), 'Build must complete before starting emulator validation'
    source=P/'analysis/azahar-gpu-engine/Azahar/sdmc/3ds/deadspace'
    card=ROOT/'Azahar/sdmc/3ds/deadspace';card.mkdir(parents=True)
    for name in ['assets','apk-assets','test-output']:shutil.copytree(source/name,card/name)
    # Only derived font is needed from baseline writable data. A new appdata
    # namespace starts empty; original resources remain private ignored files.
    for name in ['assets-verified.txt','apk-assets-verified.txt']:shutil.copyfile(source/name,card/name)
    shutil.copyfile(P/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so',card/'libEAMGameDeadSpace_orig.so')
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    controls={'start':False}
    @C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
    def input_state(port,device,index,key):
        if (port,device,index)==(0,1,0):return int(controls['start']) if key==3 else int(f.button_a) if key==8 else 0
        return 0
    for name,cb in [('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',input_state)]:
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(cb)];setter(cb)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();reports=[]
    for cycle in range(1,args.cycles+1):
        evidence=ROOT/('cycle-%04d'%cycle);evidence.mkdir()
        controls['start']=False;f.button_a=False;f.shutdown=False;f.frame=None
        report=run_cycle(core,app,source,controls,cycle,evidence);reports.append(report)
        if not report['passed']:break
        core.retro_unload_game()
    core.retro_deinit()
    report={**reports[-1],'passed':len(reports)==args.cycles and all(q['passed'] for q in reports),
            'sequential_cycles':len(reports),'sequential_passed':len(reports)==args.cycles and all(q['passed'] for q in reports),
            'same_core_and_SD':True,'cycles':reports,'runner_sha256':sha(Path(__file__))}
    (ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['cycles','frame_guest_result','final_guest_result']},indent=2),flush=True)
    finish(0 if report['passed'] else 1)

def run_cycle(core,app,source,controls,cycle,evidence):
    run_dir=ROOT/('Azahar/sdmc/3ds/ds-native-frame-v0.1.0/run-%04d'%cycle)
    host_start=len((ROOT/'azahar-host.log').read_text(errors='replace'))
    game=f.GameInfo(str(app.resolve()).encode(),None,0,None);assert core.retro_load_game(C.byref(game))
    started=time.monotonic()
    def timeout():
        (ROOT/'timeout.json').write_text(json.dumps({'passed':False,'reason':'host deadline','CXI_sha256':sha(app)})+'\n');finish(124)
    timer=threading.Timer(120,timeout);timer.daemon=True;timer.start()
    frame_report=None;last_print=started
    for host_frame in range(30000):
        f.button_a=60<=host_frame<70
        core.retro_run()
        result=run_dir/'result.json'
        if host_frame%10==0 and result.exists() and result.stat().st_size:
            frame_report=json.loads(result.read_text())
            if frame_report['status']=='blocked':
                timer.cancel();print(json.dumps(frame_report,indent=2),flush=True);(ROOT/'blocked.json').write_text(json.dumps(frame_report,indent=2)+'\n');finish(1)
            if frame_report['frame_saved']:break
        if time.monotonic()-last_print>20:
            last_print=time.monotonic();print('Running original checkpoint:',host_frame,'host frames',flush=True)
    assert frame_report and frame_report['frame_saved']
    for _ in range(3):core.retro_run()
    f.save_frame(evidence/'screen.png')
    raw=(run_dir/'frame.raw').read_bytes();assert len(raw)==288000
    rgb=bytearray();packed=bytearray()
    for i in range(0,len(raw),3):
        blue,green,red=raw[i:i+3];value=(red>>3)<<11|(green>>2)<<5|(blue>>3);packed.extend((value&255,value>>8))
    baseline=(source/'first-game-frame.raw').read_bytes();assert len(baseline)==192000
    exact=bytes(packed)==baseline
    different=sum(packed[i:i+2]!=baseline[i:i+2] for i in range(0,len(baseline),2))
    for y in range(239,-1,-1):
        for x in range(400):
            i=(x*240+y)*3;rgb.extend(raw[i:i+3][::-1])
    Image.frombytes('RGB',(400,240),bytes(rgb)).save(evidence/'original-frame.png')
    (evidence/'frame-before-exit.json').write_text(json.dumps(frame_report,indent=2)+'\n')
    print('Original frame saved; baseline different pixels:',different,flush=True)
    f.button_a=False;controls['start']=True;final=None;cleaned=False
    for _ in range(2400):
        core.retro_run()
        if (run_dir/'result.json').exists():
            try:final=json.loads((run_dir/'result.json').read_text())
            except json.JSONDecodeError:continue
            if final['status']=='blocked':break
        host=(ROOT/'azahar-host.log').read_text(errors='replace')[host_start:]
        if (run_dir/'exit.txt').exists() and 'ReleaseRight:999: called' in host and all(('operation=0x00000001, addr0='+address) in host for address in ['0x08000000','0x30000000']):cleaned=True;break
    timer.cancel()
    for q in run_dir.iterdir():
        if q.is_file() and q.suffix in ['.log','.json','.txt']:shutil.copyfile(q,evidence/('guest-result.json' if q.name=='result.json' else q.name))
    host=(ROOT/'azahar-host.log').read_text(errors='replace')[host_start:]
    bad=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo|Memory permission|Assertion failed|Exception Type:|LogException:).*',host)
    quiesce=evidence/'threads-after_quiesce.json';joined=evidence/'threads-after_join.json'
    workers=[w for w in json.loads(quiesce.read_text())['workers'] if w['token']&255] if quiesce.exists() else []
    remaining=[w for w in json.loads(joined.read_text())['workers'] if w['token']&255] if joined.exists() else [None]
    resources=re.search(r'RESOURCES JNI=(\d+) stdio=(\d+) appdata=(\d+) IOactive=(\d+) opens/closes=(\d+)/(\d+) dirs=(\d+)',(evidence/'native-frame.log').read_text())
    balanced=bool(resources and int(resources[4])==0 and resources[5]==resources[6] and int(resources[7])==0)
    shutdown_proof={'kernel_joins':sum(w['done']==1 and w['kernel_wait']==0 for w in workers),'worker_handles_remaining':len(remaining),'files_balanced':balanced,
                    'io_opens':int(resources[5]) if resources else None,'io_closes':int(resources[6]) if resources else None,
                    'sleep_EINTR_returns':sum(w.get('sleep_EINTR',0) for w in workers)}
    shutdown_exact=len(workers)==6 and shutdown_proof['kernel_joins']==6 and not remaining and balanced
    report={'passed':bool(exact and cleaned and shutdown_exact and not bad and final and final['safe_exit']),
            'original_code_frame_saved':True,'reference_callback':180,'actual_callback':frame_report['frame'],'baseline_RGB565_exact':exact,'different_pixels':different,'safe_exit':bool(cleaned and final and final['safe_exit']),'both_heaps_released':cleaned,'cycle':cycle,
            'invalid_memory_accesses':bad,'shutdown_proof':shutdown_proof,'frame_guest_result':frame_report,'final_guest_result':final,'CXI_sha256':sha(app),'frame_BGR8_sha256':hashlib.sha256(raw).hexdigest(),
            'hardware_tested':False,'native_RX_not_emulated':True,'elapsed_host_seconds':round(time.monotonic()-started,3)}
    (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Cycle',cycle,'PASS' if report['passed'] else 'FAIL','safe_exit',report['safe_exit'],'memory errors',len(bad),flush=True)
    return report
if __name__=='__main__':
    try:main()
    except BaseException:
        import traceback
        text=traceback.format_exc();(ROOT/'host-error.txt').write_text(text);print(text,flush=True);finish(2)
