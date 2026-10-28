"""Verify the opt-in input/save run without declaring a menu or playable build."""
import json,re,struct,zlib
from check_first_frame import P,read,sha,png
def validate(folder='analysis/input-save-frame/',frames=240,apk=False,shared=False):
    build=read('3ds/build-emulator/build-manifest.json')
    for path,digest in build['sources_sha256'].items():assert sha(path)==digest,path
    for name,digest in build['outputs_sha256'].items():assert sha('3ds/build-emulator/'+name)==digest,name
    for path,n in (('analysis/touch-tests.json',14),('analysis/private-files-tests.json',19)):
        t=read(path);assert t['tests_run']==n and not t['failures'] and not t['errors']
        assert t['core_sha256']==build['outputs_sha256']['core-test.elf']
    native=read(folder+'run-result.json');log=(P/folder/'run.log').read_text(encoding='utf-8')
    assert native['exploratory'] and not native['checkpoint_validated'] and native['first_game_frame_rendered']
    assert native['cpu_percent']==100 and native['resume_focus'] and native['touch_attached'] and native['private_files']
    assert native['capture_frame']==frames and native['tap_frame']==160
    assert native.get('apk_assets',False)==apk and native.get('shared_arena',False)==shared
    assert native['donor_arena_mib']==([100] if shared else [20,80])
    assert native['cxi_sha256']==build['outputs_sha256']['engine-audit.cxi'] and native['log_sha256']==sha(folder+'run.log')
    for i in range(1,frames+1):assert f'Frame {i} returned\n' in log
    for marker in ('Private fd probe: OK read/write/reopen/append/exclusive/fstat; asset writes refused',
        'Private file bridge: appdata mounted at test-output/save-bridge; 5 bindings',
        'JNI PropertyValue: com/ea/blast/SystemAndroidDelegate.GetTouchScreenCount 1',
        'JNI CallMethod: com/ea/blast/TouchSurfaceAndroid.IsTouchScreenMultiTouch ()Z',
        'NativeOnResume returned','NativeOnWindowFocusChanged returned',
        'Touch event returned: frame=160 pressed=1 x=160 y=120 events=1',
        'Touch event returned: frame=161 pressed=0 x=160 y=120 events=2',
        'Touch shutdown: result=0 events=2',f'Sensor shutdown: result=0 active=0 events={frames-2} delay=1',
        'GLES error at stop: 00000000','Completed game frame saved.'):
        assert marker in log,marker
    for bad in ('STOP unsupported:','STOP CPU exception','DIAGNOSTIC WATCHDOG STOPPED','Thread event: 5','CLOCK failure:'):
        assert bad not in log,bad
    assert re.search(r'JNI checkpoint: pending=0 failures='+('2' if apk else '3')+r' refs=\d+ frame-depth=0 string-loans=1',log)
    # Snapshot is local and excluded from Git; later emulator runs may update
    # the working save-bridge tree without invalidating this capture.
    receipt=read(folder+'save-receipt.json');save_root=P/('analysis/apk-assets-state' if apk else 'analysis/input-save-state')
    required={'var/settings.sb','var/AchievementsSave.sb','var/00_LevelSave.sb'}
    # Confirmation in the extended menu run creates a genuine checkpoint; it
    # may persist into later legacy adapter checks in this isolated namespace.
    assert required<=set(receipt)<=required|{'var/00_CheckpointSave.sb'}
    for name,info in receipt.items():
        path=save_root/name;assert path.stat().st_size==info['bytes'] and sha(path)==info['sha256']
    assert receipt['var/settings.sb']['bytes']>0 and receipt['var/AchievementsSave.sb']['bytes']>0
    meta=read(folder+'first-game-frame.json');raw=(P/folder/'first-game-frame.raw').read_bytes()
    assert (meta['width'],meta['height'],meta['layout'],meta['frame'])==(400,240,2,frames)
    assert len(raw)==meta['bytes']==192000 and f'{zlib.crc32(raw):08x}'==meta['crc32']
    assert f"FIRST GAME FRAME CAPTURED: frame={frames} draws={meta['draws']} fragments={meta['fragments']} samples={meta['samples']}" in log
    w,h,pixels=png(folder+'first-game-frame.png');assert (w,h)==(400,240)
    expected=bytearray()
    for y in range(239,-1,-1):
        for x in range(400):
            v=struct.unpack_from('<H',raw,(x*240+y)*2)[0];expected.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    assert pixels==expected
    lw,lh,lcd=png(folder+'azahar-screen.png');assert (lw,lh)==(400,480)
    offsets=[]
    for dy in (0,1):
        n=(240-dy)*400*3
        if max(abs(a-b) for a,b in zip(pixels[:n],lcd[dy*400*3:dy*400*3+n]))<=1:offsets.append(dy)
    assert offsets
    report={'passed':True,'frames_returned':frames,'cpu_percent':100,'touch_tests_passed':14,'private_file_tests_passed':19,
        'native_pointer_events_returned':2,'native_private_file_probe_passed':True,'save_receipt':receipt,
        'gles_error':0,'local_frames_closed':True,'frame':meta,'lcd_vertical_offset_pixels':offsets[0],
        'menu_confirmed':False,'gameplay':False,'hardware_tested':False,'new_cia_produced':False,
        'core_sha256':build['outputs_sha256']['core-test.elf'],'cxi_sha256':native['cxi_sha256'],
        'witnesses_sha256':{folder+n:sha(folder+n) for n in ('run.log','run-result.json','save-receipt.json',
            'first-game-frame.raw','first-game-frame.json','first-game-frame.png','azahar-screen.png')}}
    if not apk:(P/'analysis/input-save-result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':print(json.dumps(validate(),indent=2))
