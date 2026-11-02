"""Isolated native Prod124 exploration. Safety and menu evidence are separate."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'tools'))
from azahar_resource_store import ensure_dataset,prepare_card,sha

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--revision',required=True)
ap.add_argument('--attempt',required=True)
ap.add_argument('--cpu',type=int,default=400,choices=[100,400])
ap.add_argument('--opengl',action='store_true',help='Existing hidden OpenGL frontend; separate renderer evidence')
ap.add_argument('--sequence',default='',help='Guest checkpoint:button,...; held until next checkpoint')
ap.add_argument('--missing-down',action='store_true')
ap.add_argument('--circle-check',action='store_true')
ap.add_argument('--raw-only',action='store_true')
ap.add_argument('--pulse',action='store_true',help='Short host pulses at menu checkpoints')
ap.add_argument('--container',default='cxi',choices=['cxi','cia'])
args=ap.parse_args()
assert args.revision.isalnum() and args.attempt.isalnum()
ROOT=P/('analysis/azahar-native-menu-v0.1.7-'+args.revision+'-'+args.attempt)
assert not ROOT.exists(),'Preserve prior evidence'
os.environ['DEADSPACE_EMULATOR_ROOT']=str(ROOT)
import smoke_azahar as f
f.OPTIONS[b'citra_cpu_clock_percentage']=str(args.cpu).encode()
KEYS={'B':0,'START':3,'UP':4,'DOWN':5,'LEFT':6,'RIGHT':7,'A':8,'X':9,'L':10,'R':11}
schedule=[]
for item in filter(None,args.sequence.split(',')):
    frame,button=item.split(':');assert button in KEYS or button in ['CDOWN','CUP','NONE']
    schedule.append((int(frame),button))
assert schedule==sorted(schedule)

def read(p):
    try:return json.loads(p.read_text())
    except (OSError,ValueError):return {}

def finish(code):
    sys.stdout.flush();sys.stderr.flush()
    k=C.WinDLL('kernel32');k.GetCurrentProcess.restype=C.c_void_p
    k.TerminateProcess.argtypes=[C.c_void_p,C.c_uint]
    k.TerminateProcess(k.GetCurrentProcess(),code)

def main():
    build=P/('3ds/build-native-game-v0.1.7-'+args.revision)
    m=read(build/'build-manifest.json')
    for name,digest in m['outputs_sha256'].items():assert sha(build/name)==digest
    app=build/'native-game.cxi'
    if args.container=='cia':
        from build_native_startup_legacy import payload
        data=payload((build/'native-game.cia').read_bytes());assert data==app.read_bytes()
        app=ROOT/'tested-CIA-payload.cxi';app.write_bytes(data)
    dataset=ensure_dataset(P/'private/native-game-v0.1.0-sd/3ds/deadspace')
    prepare_card(ROOT/'Azahar/sdmc/3ds/deadspace',dataset)
    gl=None
    if args.opengl:
        from azahar_opengl import Frontend
        gl=Frontend(f)
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    controls={'buttons':[]}
    @C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
    def input_state(port,device,index,key):
        if (port,device,index)==(0,5,0):
            if key==1:return 32767 if 'CDOWN' in controls['buttons'] else -32767 if 'CUP' in controls['buttons'] else 0
            return 0
        if (port,device,index)==(0,1,0):
            return int(key in [KEYS[b] for b in controls['buttons'] if b in KEYS])
        return 0
    for name,cb in [('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',input_state)]:
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(cb)];setter(cb)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();game=f.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(game))
    if gl:gl.reset()
    started=time.monotonic()
    def timeout():
        (ROOT/'timeout.json').write_text(json.dumps({'safety_passed':False,'reason':'host deadline 900s'})+'\n');finish(124)
    timer=threading.Timer(900,timeout);timer.daemon=True;timer.start()
    run=ROOT/'Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001'
    checkpoint=0;safe=False;pulse_at={};last_guest_frame=0
    for host_frame in range(150000):
        controls['buttons']=[]
        preflight_steps=[(80,'UP'),(120,'DOWN'),(160,'LEFT'),(200,'RIGHT'),(240,'A'),(280,'B'),(340,'START' if args.raw_only else 'X')]
        if args.circle_check:preflight_steps=preflight_steps[:-1]+[(320,'CDOWN'),(360,'CUP'),(420,'START' if args.raw_only else 'X')]
        if args.missing_down:preflight_steps=[v for v in preflight_steps if v[1]!='DOWN'];preflight_steps=preflight_steps[:-1]+[(340,'X'),(400,'START')]
        for at,button in preflight_steps:
            if at<=host_frame<at+8:controls['buttons']=[button]
        state=read(run/'result.json');frame=state.get('frame',0)
        if state.get('status')=='exploring':
            for at,button in schedule:
                if frame>=at:controls['buttons']=[] if button=='NONE' else [button]
            if args.pulse:
                controls['buttons']=[]
                for at,button in schedule:
                    if button=='NONE':continue
                    if frame>=at and at not in pulse_at:pulse_at[at]=host_frame
                    if at in pulse_at and 0<=host_frame-pulse_at[at]<2:controls['buttons']=[button]
        live=read(ROOT/'control.json')
        if live.get('buttons') is not None:
            assert all(b in KEYS for b in live['buttons']);controls['buttons']=live['buttons']
        core.retro_run()
        if host_frame%10:continue
        if frame>checkpoint:
            checkpoint=frame;f.save_frame(ROOT/('screen-%04d.png'%frame))
            print('guest',frame,'host seconds',round(time.monotonic()-started,1),flush=True)
        if (run/'exit.txt').exists() or (args.raw_only and (run/'hid-preflight.json').exists() and read(run/'hid-preflight.json').get('state')=='START_exit'):
            host=(ROOT/'azahar-host.log').read_text(errors='replace')
            if 'ReleaseRight:999: called' in host and all('operation=0x00000001, addr0='+a in host for a in ['0x08000000','0x30000000']):
                safe=True;break
        if state.get('status')=='blocked':
            print('blocked guest; retaining resources until host process ends',flush=True);break
    timer.cancel()
    host=(ROOT/'azahar-host.log').read_text(errors='replace')
    log=(run/'native-game.log').read_text()
    collector_ok='HID_COLLECTOR join result=00000000' in log and 'HID_COLLECTOR freed before donor shutdown and gfxExit' in log
    if args.raw_only:
        preflight=read(run/'hid-preflight.json');proof=bool(safe and collector_ok and (not preflight.get('raw_buttons_passed') if args.missing_down else preflight.get('raw_buttons_passed')) and preflight.get('overflow')==0 and 'HID_PREFLIGHT START exit engine_loaded=0' in log and not (run/'validation.json').exists() and (not args.missing_down or 'HID_PREFLIGHT X blocked missing=00000080' in log))
        (ROOT/'result.json').write_text(json.dumps({'safety_passed':proof,'raw_only':True,'preflight':preflight,'collector_joined':collector_ok,'elapsed_host_seconds':round(time.monotonic()-started,3),'CXI_sha256':sha(app)},indent=2)+'\n');print('RAW preflight safety',proof,preflight,flush=True)
        if proof:core.retro_unload_game();core.retro_deinit()
        finish(0 if proof else 1)
    close=read(run/'close-state.json');attempt=close.get('shutdown_attempts',1)
    quiesce=read(run/('threads-a%d-after_quiesce.json'%attempt))
    joined=read(run/('threads-a%d-after_join.json'%attempt))
    workers=[w for w in quiesce.get('workers',[]) if w['token']&255]
    before=read(run/('threads-a%d-before_pause.json'%attempt))
    before_tokens={w['token'] for w in before.get('workers',[]) if w['token']&255}
    remaining=[w for w in joined.get('workers',[{'token':1}]) if w['token']&255]
    resources=re.search(r'RESOURCES JNI=(\d+) stdio=(\d+) appdata=(\d+) IOactive=(\d+) opens/closes=(\d+)/(\d+) dirs=(\d+)',log)
    balanced=bool(resources and int(resources[4])==0 and resources[5]==resources[6] and int(resources[7])==0)
    bad=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo|Memory permission|Assertion failed|Exception Type:|LogException:).*',host)
    # Original game reaps the detached loader when it finishes normally.
    # Require every handle present at shutdown to reach kernel completion.
    safety=bool(safe and collector_ok and len(workers)>=5 and before_tokens=={w['token'] for w in workers} and all(w['done']==1 and w['kernel_wait']==0 for w in workers) and not remaining and balanced and close.get('cleanup_complete') and not bad)
    perf=[json.loads(l[9:]) for l in log.splitlines() if l.startswith('PERFJSON ')]
    result={'safety_passed':safety,'exploratory':True,'guest_result':read(run/'result.json'),
        'validation':read(run/'validation.json'),'close_state':close,'invalid_memory_accesses':bad,
        'kernel_joins':sum(w['done']==1 and w['kernel_wait']==0 for w in workers),'handles_at_shutdown':len(before_tokens),'worker_handles_remaining':len(remaining),
        'files_balanced':balanced,'collector_joined':collector_ok,'host_pulses':args.pulse,'timing_windows':perf,'cpu_percent':args.cpu,'host_renderer':'OpenGL' if gl else 'Software','sequence':schedule,
        'elapsed_host_seconds':round(time.monotonic()-started,3),'CXI_sha256':sha(app),
        'CIA_sha256':sha(build/'native-game.cia') if args.container=='cia' else None,
        'runner_sha256':sha(Path(__file__)),'hardware_tested':False,'menu_confirmed':False,'gameplay_confirmed':False}
    if gl:result['opengl']=gl.info
    (ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if safety:core.retro_unload_game();core.retro_deinit()
    print('Safety',safety,'guest',result['guest_result'],flush=True)
    finish(0 if safety else 1)

if __name__=='__main__':
    try:main()
    except BaseException:
        import traceback
        (ROOT/'host-error.txt').write_text(traceback.format_exc());print(traceback.format_exc(),flush=True);finish(2)
