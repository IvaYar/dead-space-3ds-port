"""Verify a completed original scene capture without equating it with gameplay."""
import argparse,json,re,struct,zlib
from check_first_frame import P,read,sha,png

COHORT={
    'emulator-runtime':122,'jni10':20,'platform-jni':16,'sensor-jni':8,
    'gles':17,'arrays':17,'textures':22,'pipeline':18,'jump':13,'strings':24,
    'assets':28,'first-frame':32,'touch':14,'private-files':19,'apk-assets':23,
    'jni-monitors':12,'shared-memory':12,'emulator-threads':4,'framebuffer':24,
    'texture-pages':10,'font-profile':8,'allocator-compat':7,'fog':21,
    'combine':21,'lighting':28,'default-surface':12}

def image(folder,stem,log):
    meta=read(folder+stem+'.json');raw=(P/(folder+stem+'.raw')).read_bytes()
    assert (meta['width'],meta['height'],meta['layout'],meta['bytes'])==(400,240,2,192000)
    assert len(raw)==192000 and f'{zlib.crc32(raw):08x}'==meta['crc32']
    frame=meta['frame']
    marker=(f"FIRST GAME FRAME CAPTURED: frame={frame} draws={meta['draws']} fragments={meta['fragments']} samples={meta['samples']}"
        if stem=='first-game-frame' else f'PROGRESS FRAME SAVED: frame={frame}')
    assert marker in log,marker
    w,h,rgb=png(folder+stem+'.png');assert (w,h)==(400,240)
    expected=bytearray()
    for y in range(239,-1,-1):
        for x in range(400):
            v=struct.unpack_from('<H',raw,(x*240+y)*2)[0]
            expected.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    assert rgb==expected
    return meta,rgb

def validate(folder,historical=False):
    folder=folder.rstrip('/')+'/'
    build=read(folder+'build-manifest.json');native=read(folder+'run-result.json')
    core=build['outputs_sha256']['core-test.elf']
    assert native['log_sha256']==sha(folder+'run.log')
    assert native['cxi_sha256']==build['outputs_sha256']['engine-audit-178.cxi']
    current=read('3ds/build-emulator/build-manifest.json')
    matches=native['cxi_sha256']==current['outputs_sha256']['engine-audit-178.cxi'] and core==current['outputs_sha256']['core-test.elf']
    if not historical:
        assert matches,'Capture is historical; use --historical explicitly'
        for path,digest in current['sources_sha256'].items():assert sha(path)==digest,path
        for name,digest in current['outputs_sha256'].items():assert sha('3ds/build-emulator/'+name)==digest,name
        for name,count in COHORT.items():
            t=read('analysis/'+name+'-tests.json')
            assert t['tests_run']==count and t['errors']==t['failures']==0 and t['core_sha256']==core,name
    assert build['backend_matches_stage8'] and not build['cia_produced']
    assert native['exploratory'] and native['first_game_frame_rendered'] and not native['hardware_tested']
    for key in ('lighting','default_depth','fog','combine','framebuffers','font_subset','allocator_compat','private_files','apk_assets','shared_arena'):assert native[key],key
    assert native['cpu_percent']==400 and native['memory_mib']==178
    log=(P/(folder+'run.log')).read_text(encoding='utf-8')
    meta,rgb=image(folder,'first-game-frame',log);frame=meta['frame']
    assert list(map(int,re.findall(r'^Frame (\d+) returned$',log,re.M)))==list(range(1,frame+1))
    for text in ('Completed game frame saved.','GLES error at stop: 00000000','Default surface: depth=16 stencil=8 bytes=288000'):
        assert text in log,text
    for bad in ('STOP unsupported:','STOP GLES state:','STOP CPU exception','STOP arena refusal:','DIAGNOSTIC WATCHDOG STOPPED','Thread event: 5','CLOCK failure:'):assert bad not in log,bad
    resident,limit,saves,loads,failures=map(int,re.search(r'Texture pages: resident=(\d+) limit=(\d+) saves=(\d+) loads=(\d+) failures=(\d+)',log).groups())
    assert resident<=limit==6291456 and failures==0
    brk,peak,pages,refusals=map(int,re.search(r'Donor arenas: break=(\d+) peak=(\d+) mapped-pages=(\d+)(?: map-peak=\d+)? refusals=(\d+)',log).groups())
    assert refusals==0 and brk+pages*4096<=128*1024*1024
    lw,lh,lcd=png(folder+'azahar-screen.png');assert (lw,lh)==(400,480)
    assert any(max(abs(a-b) for a,b in zip(rgb[:(240-dy)*1200],lcd[dy*1200:240*1200]))<=1 for dy in (0,1))
    auto=native.get('auto_menu',False);menu_frames=[]
    if auto:
        for name,crc in (('select Easy','95a4497f'),('confirm','416337f3')):
            found=re.search(r'AUTO MENU '+name+r': frame=(\d+) crc='+crc,log);assert found,name
            f=int(found[1]);m,_=image(folder,'progress-frame-'+str(f),log);assert m['crc32']==crc
            assert f'Touch event returned: frame={f} pressed=1' in log and f'Touch event returned: frame={f+1} pressed=0' in log
            menu_frames.append(f)
        assert frame==menu_frames[1]+(native.get('actual_scene_frames') or native['scene_frames'])
        assert native['actual_capture_frame']==frame
    inspection=read(folder+'visual-inspection.json')
    assert inspection['final_png_sha256']==sha(folder+'first-game-frame.png')
    assert inspection['visible_scene'] and any(rgb)
    report={'passed':True,'matches_current_build':matches,'historical':historical,
        'computer_tests_passed':sum(COHORT.values()) if not historical else None,
        'completed_frame':frame,'visible_scene_confirmed':True,'scene_description':inspection['description'],
        'auto_menu_verified':auto,'menu_frames':menu_frames,'gameplay':False,'audio_verified':False,
        'hardware_tested':False,'new_cia_produced':False,'core_sha256':core,'cxi_sha256':native['cxi_sha256'],
        'gles_error':0,'arena_refusals':0,'paging_failures':0,
        'witnesses_sha256':{folder+n:sha(folder+n) for n in ('run.log','run-result.json','build-manifest.json','first-game-frame.raw','first-game-frame.json','first-game-frame.png','azahar-screen.png','visual-inspection.json')}}
    (P/(folder+'validation.json')).write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--folder',default='analysis/auto-scene-frame');parser.add_argument('--historical',action='store_true')
    args=parser.parse_args();print(json.dumps(validate(args.folder,args.historical),indent=2))
