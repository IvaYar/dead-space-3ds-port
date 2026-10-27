"""Run the emulator-only native runtime and original game to its first stop trap."""
import argparse,ctypes as C,hashlib,json,shutil,time
from pathlib import Path
import smoke_azahar as frontend
PORTING=frontend.PORTING;ROOT=frontend.ROOT
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',choices=('present','missing','wrong','ready','asset-missing','asset-wrong','content-unverified','sensor','graphics'),default='present')
    parser.add_argument('--explore',action='store_true',help='Capture the next stop without claiming the checkpoint regression passed')
    args=parser.parse_args()
    card=ROOT/'Azahar/sdmc/3ds/deadspace';card.mkdir(parents=True,exist_ok=True)
    donor=card/'libEAMGameDeadSpace_orig.so';log=card/'engine-azahar-log.txt'
    receipt=card/'assets-verified.txt';receipt_backup=receipt.read_bytes() if receipt.exists() else None
    marker=card/'sensor-bridge-test.txt';marker_backup=marker.read_bytes() if marker.exists() else None
    if args.case in ('sensor','graphics'):marker.write_bytes(b'DS12_SENSOR_TEST_V1\n')
    elif marker.exists():marker.unlink()
    gl_marker=card/'graphics-bridge-test.txt';gl_backup=gl_marker.read_bytes() if gl_marker.exists() else None
    capture=card/'capture-frame.txt';capture_backup=capture.read_bytes() if capture.exists() else None
    if args.case=='graphics' and capture_backup is None:capture.write_bytes(b'8\n')
    if args.case=='graphics':gl_marker.write_bytes(b'1\n')
    elif gl_marker.exists():gl_marker.unlink()
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
        'asset-missing':'JNI I/O PROBE STOPPED','asset-wrong':'JNI I/O PROBE STOPPED','content-unverified':'FRAME BUDGET STOPPED','sensor':'ENGINE EXPERIMENT STOPPED','graphics':'ENGINE EXPERIMENT STOPPED'}[args.case]
    start=time.monotonic();found=None
    for frame in range(18000 if args.case=='graphics' else 2400):
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
    if marker_backup is not None:marker.write_bytes(marker_backup)
    elif marker.exists():marker.unlink()
    if gl_backup is not None:gl_marker.write_bytes(gl_backup)
    elif gl_marker.exists():gl_marker.unlink()
    if capture_backup is not None:capture.write_bytes(capture_backup)
    elif capture.exists():capture.unlink()
    if args.case=='content-unverified' and receipt_backup is not None:receipt.write_bytes(receipt_backup)
    assert found is not None,f'Expected {expected}; inspect local log'
    text=found.read_text(encoding='utf-8')
    if args.explore:
        assert 'Backend: Azahar; native RX not tested' in text
    elif args.case=='present':
        for line in ('Backend: Azahar; native RX not tested','Production preflight: bound=154 missing=234 weak=4',
                     'Production guard: REFUSED; image unchanged','Donor constructors completed: 209','JNI_OnLoad: 00010004; stored VM: MATCH',
                     'NativeOnCreate returned','NativeOnSurfaceCreated returned','NativeOnSurfaceChanged returned',
                     'JNI I/O cleanup: files=0 heap=0','JNI NativeEAIOStartup returned: com/ea/EAIO/EAIO.Startup',
                     'Platform probe: 0','properties=29','Platform cleanup: files=0 heap=0','Frame 1 returned','Frame 2 begin',
                     'JNI accelerometer backend missing: com/ea/blast/DeviceOrientationHandlerAndroidDelegate.SetEnabled (Z)V MISSING',
                     'STOP Java adapter','Phase: NativeOnDrawFrame','No game frame rendered.'):
            assert line in text,line
        assert 'bytes=3568 CRC32=4a8d9499' in text and 'JNI I/O probe: 0' in text
    elif args.case in ('sensor','graphics'):
        assert 'Sensor bridge attached: native HID' in text
        assert 'Sensor shutdown: result=0 active=0' in text
        assert 'accelerometer backend missing' not in text and 'accelerometer constructor unavailable' not in text
        if args.case=='graphics':
            assert 'GLES surface probe: OK 400x240' in text and 'GLES context bindings: 99' in text
            assert 'GLES buffer probe: OK upload=24 sub=12 readback=12 active=0' in text
            assert 'GLES texture probe: OK upload=16 sub=4 readback=4 active=0' in text
            assert 'GLES pipeline probe: OK cull=2 alpha=2 blend=4 typed=1' in text
            assert 'String probe: 0' in text and 'units=7 bytes=17' in text and 'String cleanup: files=0 heap=0' in text
            assert 'JNI AssetManager.list returned: android/content/res/AssetManager. 12' in text
            assert 'Asset probe: 0' in text and 'names=176' in text and 'Asset cleanup: files=0 heap=0' in text
            assert 'FIRST GAME FRAME CAPTURED: frame=8 draws=15 fragments=629370 samples=251370' in text
            assert 'Frame 8 returned' in text and 'Completed game frame saved.' in text
            assert 'GAME DRAW: caller-offset=003244e0' in text and 'DIAGNOSTIC WATCHDOG STOPPED' not in text
            assert 'JNI assets: lists=1 names=12 gets=12 sets=0 strings=0 arrays=0' in text
            assert 'JNI strings: new16=1 newUTF=34 get16=12 getUTF=31 regions=0 errors=0' in text
            assert 'Jump contexts: saves=601 restores=0 refusals=0' in text
            import re
            texture=re.search(r'GLES texture stores: names=(\d+) bytes=(\d+) uploads=(\d+) patches=(\d+)',text)
            assert texture and 2<=int(texture[1])<=32 and 1048580<=int(texture[2])<=2097152 and int(texture[3])>=3 and int(texture[4])==0
            assert 'GLES error at stop: 00000000' in text
            assert 'STOP unsupported: glGetIntegerv\n' not in text
            assert 'Sensor shutdown: result=0 active=0 events=6 delay=1' in text
            metadata=json.loads((card/'first-game-frame.json').read_text());raw=(card/'first-game-frame.raw').read_bytes()
            import zlib
            assert metadata['frame']==8 and metadata['width']==400 and metadata['height']==240 and metadata['layout']==2
            assert len(raw)==metadata['bytes']==192000 and f'{zlib.crc32(raw):08x}'==metadata['crc32']
    elif args.case=='content-unverified':
        assert 'Frame 120 returned' in text and 'reference capacity' not in text and 'accelerometer backend missing' not in text
        import re
        assert int(re.search(r'Frame budget refs=(\d+)',text)[1])<16
    elif args.case.startswith('asset-'):
        assert 'Running 209 donor constructors' not in text and 'JNI I/O cleanup: files=0 heap=0' in text
        assert 'JNI I/O probe: 0' not in text
    else:assert 'Running 209 donor constructors' not in text
    suffix='-explore' if args.explore else ''
    target=ROOT/f'engine-{args.case}{suffix}.log';shutil.copyfile(found,target)
    report={'emulator':'Azahar libretro 2126.2','case':args.case,'expected_status_found':True,'hardware_tested':False,'gameplay':False,
        'first_game_frame_rendered':'Completed game frame saved.' in text,
        'exploratory':args.explore,'checkpoint_validated':not args.explore,
        'frames':frame+1,'elapsed_seconds':round(time.monotonic()-start,3),'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),
        'log_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'log':str(target.relative_to(PORTING))}
    (ROOT/f'engine-{args.case}{suffix}-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
