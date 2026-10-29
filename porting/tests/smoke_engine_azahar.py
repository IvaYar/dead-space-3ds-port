"""Run the emulator-only native runtime and original game to its first stop trap."""
import argparse,ctypes as C,hashlib,json,shutil,time,os,threading,re
from pathlib import Path
import smoke_azahar as frontend
PORTING=frontend.PORTING;ROOT=frontend.ROOT
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',choices=('present','missing','wrong','ready','asset-missing','asset-wrong','content-unverified','sensor','graphics'),default='present')
    parser.add_argument('--explore',action='store_true',help='Capture the next stop without claiming the checkpoint regression passed')
    parser.add_argument('--gpu',action='store_true',help='Isolated experimental PICA engine build; requires exploratory graphics and separate SD')
    parser.add_argument('--gpu-sequence-start',type=int,default=0,help='First native callback saved by the separate GPU sequence audit build')
    parser.add_argument('--gpu-sequence-count',type=int,default=0,help='Consecutive GPU captures, 2..10; end must equal capture-frame')
    parser.add_argument('--capture-frame',type=int,default=8,help='Graphics capture callback/auto-menu ceiling (2..12000); custom values require --explore')
    parser.add_argument('--timeout-seconds',type=int,default=60,help='Wall time budget, 1..3600; over 60 requires --explore')
    parser.add_argument('--resume-focus',action='store_true',help='Exploratory resume/focus lifecycle after donor initialization')
    parser.add_argument('--touch',action='store_true',help='Attach real HID to the donor touchscreen callback (exploratory)')
    parser.add_argument('--tap-frame',type=int,default=0,help='One scripted down/up at the screen center, native callback 2..598')
    parser.add_argument('--private-files',action='store_true',help='Opt-in appdata descriptor read/write in isolated save-bridge directory')
    parser.add_argument('--cpu-percent',type=int,default=100,help='Exploratory emulator CPU clock percentage, 25..400 in steps of 25')
    parser.add_argument('--apk-assets',action='store_true',help='Use the genuine extracted APK AssetManager namespace')
    parser.add_argument('--brk-mib',type=int,choices=(20,33),default=20,help='Exploratory split of the same 100MiB donor budget: 20+80 or 33+67')
    parser.add_argument('--shared-arena',action='store_true',help='Exploratory shared 100MiB pool for brk and mmap; no budget increase')
    parser.add_argument('--framebuffers',action='store_true',help='Exploratory OES framebuffer/renderbuffer backend')
    parser.add_argument('--memory-mib',type=int,choices=(124,178),default=124,help='New3DS application memory profile; 178 requires --explore graphics')
    parser.add_argument('--font-subset',action='store_true',help='Use the verified private font subset; source font remains unchanged')
    parser.add_argument('--allocator-compat',action='store_true',help='Verified EA allocator growth-call result compatibility')
    parser.add_argument('--tap-events',default='',help='Up to 16 ordered frame:x:y taps, comma separated; source screen 320x240')
    parser.add_argument('--fog',action='store_true',help='Opt-in ES1.1 fog state and actual RGB fog rasterization')
    parser.add_argument('--combine',action='store_true',help='Opt-in ES1.1 texture RGB/alpha combiners')
    parser.add_argument('--lighting',action='store_true',help='Opt-in ES1.1 lights, materials and actual vertex lighting')
    parser.add_argument('--default-depth',action='store_true',help='Owned depth16/stencil8 for the default LCD surface')
    parser.add_argument('--auto-menu',action='store_true',help='Tap Easy/confirm only when their exact original menu CRCs are visible')
    parser.add_argument('--scene-frames',type=int,default=240,help='Initial callbacks after confirmation (2..3600); auto-menu-test.txt may update the live stop target')
    parser.add_argument('--save-checkpoint',type=Path,help='Private savestate directory inside analysis/emulator-checkpoints; saved once after automatic menu confirmation')
    parser.add_argument('--restore-checkpoint',type=Path,help='Resume the same CXI/DLL/profile and its private SD snapshot')
    parser.add_argument('--stop-after-checkpoint',action='store_true',help='Finish after saving a private emulator checkpoint, without claiming a game-frame checkpoint')
    parser.add_argument('--control-file',type=Path,help='Live JSON pressed/x/y input, optional scene_frames and screenshot sequence; exploratory fixed 400x480 layout')
    args=parser.parse_args()
    if (args.gpu_sequence_start or args.gpu_sequence_count) and (not args.gpu or args.gpu_sequence_start<2 or not 2<=args.gpu_sequence_count<=10 or args.gpu_sequence_start+args.gpu_sequence_count-1!=args.capture_frame or args.auto_menu):
        parser.error('GPU sequence requires --gpu, start>=2, count2..10, matching capture-frame and no auto-menu')
    if args.gpu and (not args.explore or args.case!='graphics' or args.memory_mib!=178 or ROOT==PORTING/'analysis/azahar-smoke' or args.save_checkpoint or args.restore_checkpoint):
        parser.error('--gpu requires exploratory graphics, 178MiB and an isolated SD; CPU checkpoints are incompatible')
    if args.cpu_percent not in range(25,401,25) or (args.cpu_percent!=100 and not args.explore):
        parser.error('nondefault CPU clock requires --explore; supported range 25..400, step 25')
    frontend.OPTIONS[b'citra_cpu_clock_percentage']=str(args.cpu_percent).encode('ascii')
    if not 2<=args.capture_frame<=12000 or (args.capture_frame!=8 and (not args.explore or args.case!='graphics')):
        parser.error('custom capture frames require --case graphics --explore and range 2..12000')
    if args.auto_menu and (not args.explore or args.case!='graphics' or args.tap_events or args.tap_frame or not 2<=args.scene_frames<=3600):
        parser.error('--auto-menu requires exploratory graphics, no scripted taps, and scene-frames 2..3600')
    if (args.save_checkpoint or args.restore_checkpoint) and (not args.auto_menu or not args.explore or args.case!='graphics'):
        parser.error('Private checkpoints require exploratory graphics with --auto-menu')
    if args.stop_after_checkpoint and not args.save_checkpoint:parser.error('--stop-after-checkpoint requires --save-checkpoint')
    if args.control_file and (not args.explore or args.case!='graphics' or not (args.touch or args.auto_menu) or args.tap_frame or args.tap_events):
        parser.error('--control-file requires exploratory graphics and live touch or auto-menu, without scripted taps')
    if not 1<=args.timeout_seconds<=3600 or (args.timeout_seconds>60 and not args.explore):
        parser.error('timeout must be 1..3600; values over 60 require --explore')
    if args.resume_focus and (not args.explore or args.case!='graphics'):
        parser.error('--resume-focus requires --case graphics --explore')
    if args.shared_arena and args.brk_mib!=20:parser.error('--shared-arena cannot combine with --brk-mib 33')
    if (args.touch or args.tap_frame or args.tap_events or args.private_files or args.apk_assets or args.brk_mib!=20 or args.shared_arena or args.framebuffers or args.memory_mib!=124 or args.font_subset or args.allocator_compat or args.fog or args.combine or args.lighting or args.default_depth) and (not args.explore or args.case!='graphics'):
        parser.error('touch options require --case graphics --explore')
    if args.tap_frame and not 2<=args.tap_frame<=min(3598,args.capture_frame-2):
        parser.error('tap-frame must be 2..3598 and at least two callbacks before capture')
    taps=[]
    if args.tap_events:
        if args.tap_frame:parser.error('--tap-events and --tap-frame are mutually exclusive')
        try:taps=[tuple(map(int,item.split(':'))) for item in args.tap_events.split(',')]
        except ValueError:parser.error('tap events must be frame:x:y, comma separated')
        if not 1<=len(taps)<=16 or any(len(t)!=3 for t in taps):parser.error('expected 1..16 frame:x:y taps')
        if any(not 2<=f<=args.capture_frame-2 or not 0<=x<320 or not 0<=y<240 for f,x,y in taps):parser.error('tap frame or coordinate out of range')
        if any(b[0]<=a[0]+1 for a,b in zip(taps,taps[1:])):parser.error('tap frames must increase with a release frame between taps')
    elif args.tap_frame:taps=[(args.tap_frame,160,120)]
    card=ROOT/'Azahar/sdmc/3ds/deadspace';card.mkdir(parents=True,exist_ok=True)
    donor=card/'libEAMGameDeadSpace_orig.so';log=card/'engine-azahar-log.txt'
    receipt=card/'assets-verified.txt';receipt_backup=receipt.read_bytes() if receipt.exists() else None
    marker=card/'sensor-bridge-test.txt';marker_backup=marker.read_bytes() if marker.exists() else None
    if args.case in ('sensor','graphics'):marker.write_bytes(b'DS12_SENSOR_TEST_V1\n')
    elif marker.exists():marker.unlink()
    gl_marker=card/'graphics-bridge-test.txt';gl_backup=gl_marker.read_bytes() if gl_marker.exists() else None
    capture=card/'capture-frame.txt';capture_backup=capture.read_bytes() if capture.exists() else None
    if args.case=='graphics':capture.write_text(str(args.capture_frame)+'\n',encoding='ascii')
    sequence=card/'gpu-sequence-test.txt';sequence_backup=sequence.read_bytes() if sequence.exists() else None
    if args.gpu_sequence_count:sequence.write_text(f'{args.gpu_sequence_start} {args.gpu_sequence_count}\n',encoding='ascii')
    elif sequence.exists():sequence.unlink()
    if args.case=='graphics':gl_marker.write_bytes(b'1\n')
    elif gl_marker.exists():gl_marker.unlink()
    lifecycle=card/'lifecycle-bridge-test.txt';lifecycle_backup=lifecycle.read_bytes() if lifecycle.exists() else None
    if args.resume_focus:lifecycle.write_bytes(b'1\n')
    elif lifecycle.exists():lifecycle.unlink()
    touch=card/'touch-bridge-test.txt';touch_backup=touch.read_bytes() if touch.exists() else None
    if args.touch or taps or args.auto_menu:touch.write_text(''.join(f'{f} {x} {y}\n' for f,x,y in (taps or [(0,160,120)])),encoding='ascii')
    elif touch.exists():touch.unlink()
    private=card/'private-files-test.txt';private_backup=private.read_bytes() if private.exists() else None
    if args.private_files:private.write_bytes(b'1\n')
    elif private.exists():private.unlink()
    apk=card/'apk-assets-test.txt';apk_backup=apk.read_bytes() if apk.exists() else None
    if args.apk_assets:apk.write_bytes(b'1\n')
    elif apk.exists():apk.unlink()
    arena=card/'arena-split-test.txt';arena_backup=arena.read_bytes() if arena.exists() else None
    if args.shared_arena or args.brk_mib!=20:arena.write_bytes(f'{100 if args.shared_arena else args.brk_mib}\n'.encode('ascii'))
    elif arena.exists():arena.unlink()
    fbo=card/'framebuffer-test.txt';fbo_backup=fbo.read_bytes() if fbo.exists() else None
    if args.framebuffers:fbo.write_bytes(b'1\n')
    elif fbo.exists():fbo.unlink()
    font=card/'font-subset-test.txt';font_backup=font.read_bytes() if font.exists() else None
    if args.font_subset:font.write_bytes(b'1\n')
    elif font.exists():font.unlink()
    allocator=card/'allocator-compat-test.txt';allocator_backup=allocator.read_bytes() if allocator.exists() else None
    if args.allocator_compat:allocator.write_bytes(b'1\n')
    elif allocator.exists():allocator.unlink()
    fog=card/'fog-test.txt';fog_backup=fog.read_bytes() if fog.exists() else None
    if args.fog:fog.write_bytes(b'1\n')
    elif fog.exists():fog.unlink()
    combine=card/'combine-test.txt';combine_backup=combine.read_bytes() if combine.exists() else None
    if args.combine:combine.write_bytes(b'1\n')
    elif combine.exists():combine.unlink()
    lighting=card/'lighting-test.txt';lighting_backup=lighting.read_bytes() if lighting.exists() else None
    if args.lighting:lighting.write_bytes(b'1\n')
    elif lighting.exists():lighting.unlink()
    depth=card/'default-depth-test.txt';depth_backup=depth.read_bytes() if depth.exists() else None
    if args.default_depth:depth.write_bytes(b'1\n')
    elif depth.exists():depth.unlink()
    auto=card/'auto-menu-test.txt';auto_backup=auto.read_bytes() if auto.exists() else None
    if args.auto_menu:auto.write_text(str(args.scene_frames)+'\n',encoding='ascii')
    elif auto.exists():auto.unlink()
    def restore_markers():
        for path,backup in ((marker,marker_backup),(gl_marker,gl_backup),(capture,capture_backup),(lifecycle,lifecycle_backup),
            (touch,touch_backup),(private,private_backup),(apk,apk_backup),(arena,arena_backup),(fbo,fbo_backup),(font,font_backup),
            (allocator,allocator_backup),(fog,fog_backup),(combine,combine_backup),(lighting,lighting_backup),(depth,depth_backup),(auto,auto_backup),(sequence,sequence_backup)):
            if backup is not None:path.write_bytes(backup)
            elif path.exists():path.unlink()
        if args.case=='content-unverified' and receipt_backup is not None:receipt.write_bytes(receipt_backup)
    def exit_host(code):
        # Avoid DLL detach under running guest workers; this is this isolated
        # runner's own process, with its SD flags already restored.
        kernel=C.WinDLL('kernel32');kernel.GetCurrentProcess.restype=C.c_void_p
        kernel.TerminateProcess.argtypes=[C.c_void_p,C.c_uint]
        kernel.TerminateProcess(kernel.GetCurrentProcess(),code)
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
    app=PORTING/('3ds/build-emulator/engine-audit-178.cxi' if args.memory_mib==178 else '3ds/build-emulator/engine-audit.cxi')
    if args.gpu:app=PORTING/'3ds/build-gpu-engine/engine-gpu.cxi'
    if args.gpu_sequence_count:app=PORTING/'3ds/build-gpu-sequence/engine-gpu.cxi'
    def wall_timeout():
        failed=ROOT/f'engine-{args.case}-wall-timeout.log'
        if log.exists():shutil.copyfile(log,failed)
        if frontend.frame:frontend.save_frame(ROOT/f'engine-{args.case}-wall-timeout-screen.png')
        report={'passed':False,'checkpoint_validated':False,'host_wall_timeout':True,'memory_mib':args.memory_mib,
            'wall_limit_seconds':args.timeout_seconds+15,'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),'hardware_tested':False}
        (ROOT/f'engine-{args.case}-wall-timeout-result.json').write_text(json.dumps(report,indent=2)+'\n')
        restore_markers()
        print(json.dumps(report,indent=2),flush=True)
        # ExitProcess can deadlock in a host DLL detach routine. This watchdog
        # is already recording failure and must end its own emulator process.
        exit_host(124)
    timer=threading.Timer(args.timeout_seconds+15,wall_timeout);timer.daemon=True;timer.start()
    core=C.CDLL(str((PORTING/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    for name,callback in (('environment',frontend.environment),('video_refresh',frontend.video),('audio_sample',frontend.audio),
                         ('audio_sample_batch',frontend.audio_batch),('input_poll',frontend.poll),('input_state',frontend.input_state)):
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(callback)];setter(callback)
    core.retro_load_game.argtypes=[C.POINTER(frontend.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();game=frontend.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(game))
    checkpoint_saved=None;checkpoint_restored=None
    profile={k:v for k,v in vars(args).items() if k not in ('save_checkpoint','restore_checkpoint','timeout_seconds','stop_after_checkpoint','control_file','gpu_sequence_start','gpu_sequence_count')}
    if args.restore_checkpoint:
        # The core advertises RETRO_SERIALIZATION_QUIRK_MUST_INITIALIZE.
        # Initialize its core-loop thread and services with no launch input
        # before replacing emulated state. This is not game progression.
        frontend.button_a=False
        for _ in range(60):core.retro_run()
        import sys;sys.path.insert(0,str(PORTING/'tools'))
        import emulator_checkpoint as checkpoint
        try:checkpoint_restored=checkpoint.load(core,args.restore_checkpoint,card,profile,app,PORTING/'toolchain/azahar-libretro/azahar_libretro.dll')
        except Exception as error:
            timer.cancel();restore_markers();print('CHECKPOINT RESTORE FAILED '+str(error),flush=True);exit_host(2)
        print('CHECKPOINT RESTORED '+json.dumps(checkpoint_restored),flush=True)
    expected={'present':'ENGINE EXPERIMENT STOPPED','missing':'Missing library','wrong':'Wrong donor CRC','ready':'READY - press A',
        'asset-missing':'JNI I/O PROBE STOPPED','asset-wrong':'JNI I/O PROBE STOPPED','content-unverified':'FRAME BUDGET STOPPED','sensor':'ENGINE EXPERIMENT STOPPED','graphics':'ENGINE EXPERIMENT STOPPED'}[args.case]
    start=time.monotonic();found=None;control_screenshot=None
    for frame in range(max(18000,args.capture_frame*300) if args.case=='graphics' else 2400):
        frontend.button_a=not checkpoint_restored and args.case!='ready' and frame==60
        try:core.retro_run()
        except OSError as error:
            # A host DLL exception is a failed emulator run, even if the
            # native journal reached a checkpoint. Never hang in DLL unload.
            if frontend.frame:frontend.save_frame(ROOT/f'engine-{args.case}-host-failure-screen.png')
            failed=ROOT/f'engine-{args.case}-host-failure.log'
            if log.exists():shutil.copyfile(log,failed)
            report={'passed':False,'checkpoint_validated':False,'host_exception':str(error),'case':args.case,
                'cpu_percent':args.cpu_percent,'frames':frame+1,'hardware_tested':False,'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),
                'log_sha256':hashlib.sha256(failed.read_bytes()).hexdigest() if failed.exists() else None}
            (ROOT/f'engine-{args.case}-host-failure-result.json').write_text(json.dumps(report,indent=2)+'\n')
            restore_markers()
            print(json.dumps(report,indent=2),flush=True);exit_host(2)
        if frame%15==0 or frontend.shutdown:
            if args.control_file:
                try:
                    control=json.loads(args.control_file.read_text()) if args.control_file.exists() else {'pressed':False}
                    if not isinstance(control,dict):raise ValueError('Live control must be a JSON object')
                    if frontend.frame and frontend.frame[:2]!=(400,480):raise ValueError('Live pointer requires 400x480 emulator layout')
                    frontend.set_touch(control.get('pressed',False),control.get('x',160),control.get('y',120))
                    if args.auto_menu and 'scene_frames' in control:
                        value=control['scene_frames']
                        if type(value) is not int or not 2<=value<=3600:raise ValueError('Live scene_frames must be 2..3600')
                        desired=str(value)+'\n'
                        if auto.read_text()!=desired:auto.write_text(desired,encoding='ascii')
                    if 'screenshot' in control and control['screenshot']!=control_screenshot and frontend.frame:
                        frontend.save_frame(ROOT/'engine-live-screen.png');control_screenshot=control['screenshot']
                        (ROOT/'live-control-response.json').write_text(json.dumps({'screenshot':control_screenshot,'host_frame':frame,'elapsed_seconds':round(time.monotonic()-start,3)})+'\n')
                except (OSError,ValueError,TypeError):frontend.set_touch(False)
            for candidate in ROOT.rglob('engine-azahar-log.txt'):
                text=candidate.read_text(encoding='utf-8',errors='replace')
                if args.save_checkpoint and not checkpoint_saved and 'AUTO MENU confirm released:' in text and 'Completed game frame saved.' not in text:
                    import sys;sys.path.insert(0,str(PORTING/'tools'))
                    import emulator_checkpoint as checkpoint
                    try:checkpoint_saved=checkpoint.save(core,args.save_checkpoint,card,profile,app,PORTING/'toolchain/azahar-libretro/azahar_libretro.dll')
                    except Exception as error:
                        timer.cancel();restore_markers();print('CHECKPOINT SAVE FAILED '+str(error),flush=True);exit_host(2)
                    print('CHECKPOINT SAVED '+json.dumps(checkpoint_saved),flush=True)
                if expected in text:found=candidate;break
            if found:break
            if args.stop_after_checkpoint and checkpoint_saved:break
        if frontend.shutdown or time.monotonic()-start>args.timeout_seconds:break
    if frontend.frame:frontend.save_frame(ROOT/f'engine-{args.case}-screen.png')
    if args.stop_after_checkpoint and checkpoint_saved:
        timer.cancel();restore_markers()
        report={'passed':True,'scope':'Private emulator checkpoint saved only; engine capture not completed',
            'checkpoint':checkpoint_saved,'gameplay':False,'hardware_tested':False,'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest()}
        (ROOT/'engine-private-checkpoint-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2),flush=True);exit_host(0)
    core.retro_unload_game();core.retro_deinit()
    timer.cancel()
    restore_markers()
    if found is None:
        failed=ROOT/f'engine-{args.case}-incomplete.log'
        if log.exists():shutil.copyfile(log,failed)
        report={'passed':False,'checkpoint_validated':False,'completed_expected_stop':False,
            'case':args.case,'capture_frame':args.capture_frame,'auto_menu':args.auto_menu,
            'scene_frames':args.scene_frames if args.auto_menu else None,'wall_limit_seconds':args.timeout_seconds,
            'elapsed_seconds':round(time.monotonic()-start,3),'hardware_tested':False,
            'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),
            'log_sha256':hashlib.sha256(failed.read_bytes()).hexdigest() if failed.exists() else None}
        (ROOT/f'engine-{args.case}-incomplete-result.json').write_text(json.dumps(report,indent=2)+'\n')
        raise RuntimeError(f'Expected {expected}; incomplete run saved separately')
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
            assert 'FIRST GAME FRAME CAPTURED: frame=8 draws=' in text
            assert 'Frame 8 returned' in text and 'Completed game frame saved.' in text
            assert 'GAME DRAW: caller-offset=003244e0' in text and 'DIAGNOSTIC WATCHDOG STOPPED' not in text
            assert 'JNI assets: lists=1 names=12 gets=12 sets=0 strings=0 arrays=0' in text
            assert 'JNI strings: new16=1 newUTF=34 get16=12 getUTF=31 regions=0 errors=0' in text
            assert 'Jump contexts: saves=601 restores=0 refusals=0' in text
            texture=re.search(r'GLES texture stores: names=(\d+) bytes=(\d+) uploads=(\d+) patches=(\d+)',text)
            assert texture and 2<=int(texture[1])<=32 and 1048580<=int(texture[2])<=6*1024*1024 and int(texture[3])>=3 and int(texture[4])==0
            assert 'JNI checkpoint: pending=0 failures=3 refs=11 frame-depth=0 string-loans=1' in text
            assert 'JNI PopLocalFrame pinned string:' not in text
            assert 'GLES error at stop: 00000000' in text
            assert 'STOP unsupported: glGetIntegerv\n' not in text
            assert 'Sensor shutdown: result=0 active=0 events=6 delay=1' in text
            metadata=json.loads((card/'first-game-frame.json').read_text());raw=(card/'first-game-frame.raw').read_bytes()
            import zlib
            assert metadata['frame']==8 and metadata['width']==400 and metadata['height']==240 and metadata['layout']==2
            # Asynchronous donor texture workers can finish a callback later.
            # Verify real completed draws rather than pinning their schedule.
            assert 12<=metadata['draws']<=32 and metadata['triangles']==metadata['draws']*2
            assert metadata['fragments']>=400000 and metadata['samples']>=100000
            assert f"FIRST GAME FRAME CAPTURED: frame=8 draws={metadata['draws']} fragments={metadata['fragments']} samples={metadata['samples']}" in text
            assert len(raw)==metadata['bytes']==192000 and f'{zlib.crc32(raw):08x}'==metadata['crc32']
    elif args.case=='content-unverified':
        assert 'Frame 120 returned' in text and 'reference capacity' not in text and 'accelerometer backend missing' not in text
        assert int(re.search(r'Frame budget refs=(\d+)',text)[1])<16
    elif args.case.startswith('asset-'):
        assert 'Running 209 donor constructors' not in text and 'JNI I/O cleanup: files=0 heap=0' in text
        assert 'JNI I/O probe: 0' not in text
    else:assert 'Running 209 donor constructors' not in text
    suffix='-explore' if args.explore else ''
    target=ROOT/f'engine-{args.case}{suffix}.log';shutil.copyfile(found,target)
    report={'emulator':'Azahar libretro 2126.2','gpu_backend':args.gpu,'case':args.case,'expected_status_found':True,'hardware_tested':False,'gameplay':False,
        'first_game_frame_rendered':'Completed game frame saved.' in text,
        'exploratory':args.explore,'checkpoint_validated':not args.explore,
        'cpu_percent':args.cpu_percent,'resume_focus':args.resume_focus,'touch_attached':args.touch or bool(taps) or args.auto_menu,
        'auto_menu':args.auto_menu,'scene_frames':args.scene_frames if args.auto_menu else None,
        'saved_checkpoint':checkpoint_saved,'restored_checkpoint':checkpoint_restored,
        'actual_capture_frame':json.loads((card/'first-game-frame.json').read_text())['frame'] if 'Completed game frame saved.' in text else None,
        'actual_scene_frames':int(re.search(r'FIRST GAME FRAME CAPTURED: frame=(\d+)',text)[1])-int(re.search(r'AUTO MENU confirm: frame=(\d+)',text)[1]) if args.auto_menu and 'Completed game frame saved.' in text else None,
        'tap_events':taps,
        'tap_frame':args.tap_frame,'private_files':args.private_files,'capture_frame':args.capture_frame,
        'apk_assets':args.apk_assets,'donor_arena_mib':[128 if args.memory_mib==178 else 100] if args.shared_arena else [args.brk_mib,100-args.brk_mib],
        'shared_arena':args.shared_arena,
        'framebuffers':args.framebuffers,
        'memory_mib':args.memory_mib,
        'font_subset':args.font_subset,
        'allocator_compat':args.allocator_compat,
        'fog':args.fog,
        'combine':args.combine,
        'lighting':args.lighting,
        'default_depth':args.default_depth,
        'frames':frame+1,'elapsed_seconds':round(time.monotonic()-start,3),'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),
        'log_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'log':str(target.relative_to(PORTING))}
    (ROOT/f'engine-{args.case}{suffix}-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
