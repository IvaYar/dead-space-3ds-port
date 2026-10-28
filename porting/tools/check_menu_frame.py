"""Verify real donor menu captures and JNI input; never infer gameplay from a draw."""
import json,re,struct,zlib
from check_first_frame import P,read,sha,png

FOLDER='analysis/menu-frame/'

def surface(stem,frame):
    meta=read(FOLDER+stem+'.json');raw=(P/FOLDER/(stem+'.raw')).read_bytes()
    assert (meta['width'],meta['height'],meta['layout'],meta['frame'])==(400,240,2,frame)
    assert len(raw)==meta['bytes']==192000 and f'{zlib.crc32(raw):08x}'==meta['crc32']
    w,h,pixels=png(FOLDER+stem+'.png');assert (w,h)==(400,240)
    decoded=bytearray()
    for y in range(239,-1,-1):
        for x in range(400):
            v=struct.unpack_from('<H',raw,(x*240+y)*2)[0]
            decoded.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    assert pixels==decoded
    return meta,pixels

def validate():
    build=read(FOLDER+'build-manifest.json');current=read('3ds/build-emulator/build-manifest.json');native=read(FOLDER+'run-result.json')
    assert native['exploratory'] and not native['hardware_tested'] and not native['gameplay']
    assert native['memory_mib']==178 and native['donor_arena_mib']==[128] and native['cpu_percent']==400
    for key in ('resume_focus','touch_attached','private_files','apk_assets','shared_arena','framebuffers','font_subset','allocator_compat'):assert native[key],key
    assert native['tap_events']==[[2300,160,134],[2600,284,225]]
    assert native['cxi_sha256']==build['outputs_sha256']['engine-audit-178.cxi']
    assert native['log_sha256']==sha(FOLDER+'run.log')
    log=(P/FOLDER/'run.log').read_text()
    for marker in ('EA allocator compatibility: verified growth-call new-break result; other sbrk callers unchanged',
        'FBO bridge attached: 15 operations;',
        'Texture paging attached: 128 names; 96MiB logical; 6MiB resident; exact RGBA8 + CRC',
        'Touch event returned: frame=2300 pressed=1 x=160 y=134 events=1',
        'Touch event returned: frame=2301 pressed=0 x=160 y=134 events=2',
        'Touch event returned: frame=2600 pressed=1 x=284 y=225 events=3',
        'Touch event returned: frame=2601 pressed=0 x=284 y=225 events=4',
        'PROGRESS FRAME SAVED: frame=2160','PROGRESS FRAME SAVED: frame=2400'):
        assert marker in log,marker
    for bad in ('STOP arena refusal:','STOP CPU exception','DIAGNOSTIC WATCHDOG STOPPED','Thread event: 5','CLOCK failure:'):
        assert bad not in log,bad
    assert 'GLES error at stop: 00000000' in log
    scene_adapters=native.get('fog',False) and native.get('combine',False)
    completed_lighting=native.get('lighting',False) and native.get('default_depth',False)
    stop_api,stop_caller=('glLightModelfv','00325e84') if scene_adapters else ('glFogx','003257ec')
    if completed_lighting:
        assert native['first_game_frame_rendered'] and native['capture_frame']==2605 and 'Frame 2605 returned\n' in log and 'Completed game frame saved.' in log
        assert 'STOP unsupported:' not in log and 'Default surface: depth=16 stencil=8 bytes=288000' in log
        stop_api=stop_caller=None
    else:assert f'STOP unsupported: {stop_api}\n' in log and f'Caller offset: {stop_caller}\n' in log
    if scene_adapters:
        for text in ('Fog bridge attached: 4 operations;',
            'Combine bridge attached: 2 units;',
            'FOG GAME DRAW: frame=2604 mode=2601 start=10 end=25',
            f'Fog state: enabled={0 if completed_lighting else 1} mode=2601 density=1 start=10 end=25 color=0,0,0,0'):
            assert text in log,text
        assert 'texture environment mode unsupported' not in log
        for name,count in [('fog',21),('combine',21)]+([('lighting',28),('default-surface',12)] if completed_lighting else []):
            test=read('analysis/'+name+'-tests.json');assert test['tests_run']==count and not test['errors'] and not test['failures']
            assert test['core_sha256']==build['outputs_sha256']['core-test.elf']
    returned=[int(n) for n in re.findall(r'^Frame (\d+) returned$',log,re.M)]
    assert returned==list(range(1,len(returned)+1)) and len(returned)>=2601
    normal,normal_pixels=surface('normal',2160);easy,easy_pixels=surface('easy',2400)
    # Fixed UI pixels reviewed in the matching witness; source font and renderer
    # are deterministic. A different screen cannot silently become "menu".
    inspection=read(FOLDER+'visual-inspection.json')
    assert inspection['screen']=='Select Difficulty' and inspection['selection_changed_from']=='Normal' and inspection['selection_changed_to']=='Easy'
    assert inspection['normal_png_sha256']==sha(FOLDER+'normal.png')
    assert inspection['easy_png_sha256']==sha(FOLDER+'easy.png')
    changed=sum(normal_pixels[i:i+3]!=easy_pixels[i:i+3] for i in range(0,len(normal_pixels),3))
    assert changed>1000 and normal['crc32']!=easy['crc32']
    resident,limit,saves,loads,failures=map(int,re.search(r'Texture pages: resident=(\d+) limit=(\d+) saves=(\d+) loads=(\d+) failures=(\d+)',log).groups())
    assert 0<resident<=limit==6*1024*1024 and saves>0 and loads>0 and not failures
    brk,peak,pages,refusals=map(int,re.search(r'Donor arenas: break=(\d+) peak=(\d+) mapped-pages=(\d+)(?: map-peak=\d+)? refusals=(\d+)',log).groups())
    assert brk<=peak and brk+pages*4096<=128*1024*1024 and not refusals
    files=['run.log','run-result.json','visual-inspection.json']+[n+'.'+ext for n in ('normal','easy') for ext in ('raw','json','png')]
    report={'passed':True,'screen':'Select Difficulty','normal_selection_rendered':True,'easy_selection_rendered':True,
        'menu_confirmed':True,'selection_change_verified':True,'confirmation_pointer_events_returned':True,
        'frames_returned':len(returned),'cpu_percent':400,'application_memory_mib':178,'donor_arena_mib':128,
        'texture_resident_bytes':resident,'texture_resident_limit_bytes':limit,'texture_backing_failures':0,
        'arena_bytes_in_use':brk+pages*4096,'arena_refusals':0,'gles_error':0,'changed_menu_pixels':changed,
        'normal_frame':normal,'easy_frame':easy,'post_confirmation_capture_complete':native['first_game_frame_rendered'],
        'next_stop':{'kind':'visibility_investigation' if completed_lighting else 'unimplemented_import','api':stop_api,'caller_offset':stop_caller,'frame':2605 if completed_lighting else 2604,'phase':'Completed early frame visibility' if completed_lighting else 'NativeOnDrawFrame after confirmation'},
        'native_fog_used':scene_adapters,'texture_combiner_mode_accepted':scene_adapters,'completed_3d_scene_frame':False,
        'lighting_profile_frame_completed':completed_lighting,'visible_gameplay_confirmed':False,
        'hardware_tested':False,'gameplay':False,'new_cia_produced':False,
        'core_sha256':build['outputs_sha256']['core-test.elf'],'cxi_sha256':native['cxi_sha256'],
        'matches_current_build':native['cxi_sha256']==current['outputs_sha256']['engine-audit-178.cxi'],
        'historical_checkpoint':native['cxi_sha256']!=current['outputs_sha256']['engine-audit-178.cxi'],
        'witnesses_sha256':{FOLDER+n:sha(FOLDER+n) for n in files+['build-manifest.json']}}
    (P/'analysis/menu-result.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':print(json.dumps(validate(),indent=2))
