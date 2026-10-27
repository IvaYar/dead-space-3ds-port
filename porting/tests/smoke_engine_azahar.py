"""Run the emulator-only native runtime and original game to its first stop trap."""
import argparse,ctypes as C,hashlib,json,shutil,time
from pathlib import Path
import smoke_azahar as frontend
PORTING=frontend.PORTING;ROOT=frontend.ROOT
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',choices=('present','missing','wrong','ready','asset-missing','asset-wrong','content-unverified'),default='present');args=parser.parse_args()
    card=ROOT/'Azahar/sdmc/3ds/deadspace';card.mkdir(parents=True,exist_ok=True)
    donor=card/'libEAMGameDeadSpace_orig.so';log=card/'engine-azahar-log.txt'
    receipt=card/'assets-verified.txt';receipt_backup=receipt.read_bytes() if receipt.exists() else None
    if args.case=='content-unverified' and receipt.exists():receipt.unlink()
    if log.exists():log.unlink()
    if args.case=='missing':
        if donor.exists():donor.unlink()
    else:
        data=bytearray((PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes())
        if args.case=='wrong':data[-1]^=1
        donor.write_bytes(data)
    asset=card/'assets/published/data/achievements.sb';asset.parent.mkdir(parents=True,exist_ok=True)
    if args.case=='asset-missing':
        if asset.exists():asset.unlink()
    else:
        data=bytearray((PORTING/'analysis/candidate-sd/assets/published/data/achievements.sb').read_bytes())
        if args.case=='asset-wrong':data[-1]^=1
        asset.write_bytes(data)
    core=C.CDLL(str((PORTING/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    for name,callback in (('environment',frontend.environment),('video_refresh',frontend.video),('audio_sample',frontend.audio),
                         ('audio_sample_batch',frontend.audio_batch),('input_poll',frontend.poll),('input_state',frontend.input_state)):
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(callback)];setter(callback)
    core.retro_load_game.argtypes=[C.POINTER(frontend.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();app=PORTING/'3ds/build-emulator/engine-audit.cxi';game=frontend.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(game))
    expected={'present':'ENGINE EXPERIMENT STOPPED','missing':'Missing library','wrong':'Wrong donor CRC','ready':'READY - press A',
        'asset-missing':'JNI I/O PROBE STOPPED','asset-wrong':'JNI I/O PROBE STOPPED','content-unverified':'FRAME BUDGET STOPPED'}[args.case]
    start=time.monotonic();found=None
    for frame in range(2400):
        frontend.button_a=args.case!='ready' and frame==60
        core.retro_run()
        if frame%15==0 or frontend.shutdown:
            for candidate in ROOT.rglob('engine-azahar-log.txt'):
                text=candidate.read_text(encoding='utf-8',errors='replace')
                if expected in text:found=candidate;break
            if found:break
        if frontend.shutdown or time.monotonic()-start>60:break
    if frontend.frame:frontend.save_frame(ROOT/f'engine-{args.case}-screen.png')
    core.retro_unload_game();core.retro_deinit()
    if args.case=='content-unverified' and receipt_backup is not None:receipt.write_bytes(receipt_backup)
    assert found is not None,f'Expected {expected}; inspect local log'
    text=found.read_text(encoding='utf-8')
    if args.case=='present':
        for line in ('Backend: Azahar; native RX not tested','Production preflight: bound=152 missing=236 weak=4',
                     'Production guard: REFUSED; image unchanged','Donor constructors completed: 209','JNI_OnLoad: 00010004; stored VM: MATCH',
                     'NativeOnCreate returned','NativeOnSurfaceCreated returned','NativeOnSurfaceChanged returned',
                     'JNI I/O cleanup: files=0 heap=0','JNI NativeEAIOStartup returned: com/ea/EAIO/EAIO.Startup',
                     'Platform probe: 0','properties=29','Platform cleanup: files=0 heap=0','Frame 1 returned','Frame 2 begin',
                     'JNI accelerometer backend missing: com/ea/blast/DeviceOrientationHandlerAndroidDelegate.SetEnabled (Z)V MISSING',
                     'STOP Java adapter','Phase: NativeOnDrawFrame','No game frame rendered.'):
            assert line in text,line
        assert 'bytes=3568 CRC32=4a8d9499' in text and 'JNI I/O probe: 0' in text
    elif args.case=='content-unverified':
        assert 'Frame 120 returned' in text and 'reference capacity' not in text and 'accelerometer backend missing' not in text
        import re
        assert int(re.search(r'Frame budget refs=(\d+)',text)[1])<16
    elif args.case.startswith('asset-'):
        assert 'Running 209 donor constructors' not in text and 'JNI I/O cleanup: files=0 heap=0' in text
        assert 'JNI I/O probe: 0' not in text
    else:assert 'Running 209 donor constructors' not in text
    target=ROOT/f'engine-{args.case}.log';shutil.copyfile(found,target)
    report={'emulator':'Azahar libretro 2126.2','case':args.case,'expected_status_found':True,'hardware_tested':False,'gameplay':False,
        'frames':frame+1,'elapsed_seconds':round(time.monotonic()-start,3),'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),
        'log_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'log':str(target.relative_to(PORTING))}
    (ROOT/f'engine-{args.case}-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
