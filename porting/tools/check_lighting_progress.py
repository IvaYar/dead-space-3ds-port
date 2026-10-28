"""Validate completed early engine frames; distinguish black output from visible gameplay."""
import json,re,struct,zlib
from check_first_frame import P,read,sha,png
FOLDER='analysis/lighting-frame/'
def validate():
    build=read('3ds/build-emulator/build-manifest.json');native=read(FOLDER+'run-result.json');log=(P/FOLDER/'run.log').read_text(encoding='utf-8')
    assert native['capture_frame']==2605 and native['first_game_frame_rendered'] and native['exploratory'] and not native['hardware_tested']
    for key in ('lighting','default_depth','fog','combine','framebuffers','font_subset','allocator_compat','private_files','apk_assets','shared_arena'):assert native[key],key
    assert native['cpu_percent']==400 and native['memory_mib']==178 and native['donor_arena_mib']==[128]
    assert native['cxi_sha256']==build['outputs_sha256']['engine-audit-178.cxi'] and native['log_sha256']==sha(FOLDER+'run.log')
    returned=list(map(int,re.findall(r'^Frame (\d+) returned$',log,re.M)));assert returned==list(range(1,2606))
    for marker in ('Default depth attached: depth16/stencil8; 288000 owned bytes;',
        'Default surface: depth=16 stencil=8 bytes=288000','Lighting bridge attached: 18 operations;',
        'LIT GAME DRAW: frame=2604 vertices=','GLES error at stop: 00000000','Completed game frame saved.',
        'JNI checkpoint: pending=0 failures=2 refs=11 frame-depth=0 string-loans=1'):
        assert marker in log,marker
    for bad in ('STOP unsupported:','STOP GLES state:','STOP CPU exception','STOP arena refusal:','DIAGNOSTIC WATCHDOG STOPPED','Thread event: 5','CLOCK failure:'):assert bad not in log,bad
    for name,count in (('lighting',28),('default-surface',12)):
        t=read('analysis/'+name+'-tests.json');assert t['tests_run']==count and not t['errors'] and not t['failures'] and t['core_sha256']==build['outputs_sha256']['core-test.elf']
    state=re.search(r'Lighting state: enabled=(\d+) lights=([0-9a-f]+) two-side=(\d+) setters=(\d+) vertices=(\d+)',log);assert state
    enabled,mask,two_side,setters,vertices=state.groups();assert int(setters)>0 and int(vertices)>0
    resident,limit,saves,loads,failures=map(int,re.search(r'Texture pages: resident=(\d+) limit=(\d+) saves=(\d+) loads=(\d+) failures=(\d+)',log).groups());assert resident<=limit==6291456 and not failures
    brk,peak,pages,refusals=map(int,re.search(r'Donor arenas: break=(\d+) peak=(\d+) mapped-pages=(\d+)(?: map-peak=\d+)? refusals=(\d+)',log).groups());assert not refusals and brk+pages*4096<=128*1024*1024
    meta=read(FOLDER+'first-game-frame.json');raw=(P/FOLDER/'first-game-frame.raw').read_bytes();assert meta['frame']==2605 and len(raw)==meta['bytes']==192000 and f'{zlib.crc32(raw):08x}'==meta['crc32']
    w,h,pixels=png(FOLDER+'first-game-frame.png');assert (w,h)==(400,240)
    expected=bytearray()
    for y in range(239,-1,-1):
        for x in range(400):
            v=struct.unpack_from('<H',raw,(x*240+y)*2)[0];expected.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    assert pixels==expected
    lw,lh,lcd=png(FOLDER+'azahar-screen.png');assert (lw,lh)==(400,480)
    assert any(max(abs(a-b) for a,b in zip(pixels[:(240-dy)*400*3],lcd[dy*400*3:240*400*3]))<=1 for dy in (0,1))
    files=['run.log','run-result.json','first-game-frame.raw','first-game-frame.json','first-game-frame.png','azahar-screen.png']
    intermediate='SCENE INTERMEDIATE SAVED: frame=2604' in log
    if intermediate:
        partial=read(FOLDER+'scene-intermediate.json');partial_raw=(P/FOLDER/'scene-intermediate.raw').read_bytes()
        assert partial['frame']==2604 and partial['caller_offset']=='003244e0' and len(partial_raw)==partial['bytes']==192000 and any(partial_raw)
        assert f'{zlib.crc32(partial_raw):08x}'==partial['crc32']
        pw,ph,partial_pixels=png(FOLDER+'scene-intermediate.png');assert (pw,ph)==(400,240)
        decoded=bytearray()
        for y in range(239,-1,-1):
            for x in range(400):
                v=struct.unpack_from('<H',partial_raw,(x*240+y)*2)[0];decoded.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
        assert partial_pixels==decoded
        inspection=read(FOLDER+'visual-inspection.json');assert inspection['geometry_visible_in_intermediate'] and not inspection['final_scene_visible']
        assert inspection['intermediate_png_sha256']==sha(FOLDER+'scene-intermediate.png')
        files+=['scene-intermediate.json','scene-intermediate.raw','scene-intermediate.png','visual-inspection.json']
    report={'passed':True,'completed_engine_frame':True,'frame':2605,'frames_returned':2605,'output_is_black':not any(raw),
        'visible_scene_confirmed':False,'gameplay':False,'hardware_tested':False,'new_cia_produced':False,
        'geometry_visible_in_intermediate':intermediate,'intermediate_is_completed_frame':False,
        'lighting_setters':int(setters),'lighting_vertices':int(vertices),'default_depth_bits':16,'default_stencil_bits':8,'default_storage_bytes':288000,
        'gles_error':0,'arena_refusals':0,'paging_failures':0,'resident_texture_bytes':resident,'arena_bytes_in_use':brk+pages*4096,
        'cpu_percent':400,'application_memory_mib':178,'core_sha256':build['outputs_sha256']['core-test.elf'],'cxi_sha256':native['cxi_sha256'],
        'next_investigation':'Final surface visibility and later render passes; a completed frame alone is not a visible gameplay checkpoint',
        'witnesses_sha256':{FOLDER+n:sha(FOLDER+n) for n in files}}
    (P/'analysis/lighting-result.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':print(json.dumps(validate(),indent=2))
