"""Verify completed donor draws, current build hashes, CPU buffer and LCD image."""
import hashlib,json,re,struct,zlib
from pathlib import Path
P=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256((P/path).read_bytes()).hexdigest()
def read(path):return json.loads((P/path).read_text(encoding='utf-8'))
def png(path):
    data=(P/path).read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n';offset=8;compressed=bytearray();size=None
    while offset<len(data):
        n=struct.unpack_from('>I',data,offset)[0];kind=data[offset+4:offset+8];body=data[offset+8:offset+8+n]
        assert zlib.crc32(kind+body)==struct.unpack_from('>I',data,offset+8+n)[0]
        if kind==b'IHDR':
            w,h,depth,color,compression,filter_,interlace=struct.unpack('>IIBBBBB',body);assert (depth,color,compression,filter_,interlace)==(8,2,0,0,0);size=(w,h)
        if kind==b'IDAT':compressed.extend(body)
        offset+=12+n
    assert size;w,h=size;scan=zlib.decompress(compressed);assert len(scan)==h*(1+w*3)
    rows=[]
    for y in range(h):
        row=scan[y*(1+w*3):(y+1)*(1+w*3)];assert row[0]==0;rows.append(row[1:])
    return w,h,b''.join(rows)
def validate():
    build=read('3ds/build-emulator/build-manifest.json');tests=read('analysis/first-frame-tests.json')
    for path,digest in build['sources_sha256'].items():assert sha(path)==digest,path
    for name,digest in build['outputs_sha256'].items():assert sha('3ds/build-emulator/'+name)==digest,name
    assert tests['tests_run']==31 and not tests['errors'] and not tests['failures']
    assert tests['core_sha256']==build['outputs_sha256']['core-test.elf']
    native=read('analysis/azahar-smoke/engine-graphics-result.json')
    assert native['checkpoint_validated'] and native['first_game_frame_rendered'] and not native['exploratory']
    assert native['cxi_sha256']==build['outputs_sha256']['engine-audit.cxi']
    assert native['log_sha256']==sha('analysis/azahar-smoke/engine-graphics.log')
    log=(P/'analysis/azahar-smoke/engine-graphics.log').read_text(encoding='utf-8')
    for marker in ('Donor constructors completed: 209','GLES context bindings: 99','Application memory: bytes=130023424; donor arenas=20+80MiB',
        'Frame 2 returned','Frame 8 returned','GAME DRAW: caller-offset=003244e0',
        'FIRST GAME FRAME CAPTURED: frame=8 draws=','Completed game frame saved.',
        'GLES error at stop: 00000000','Sensor shutdown: result=0 active=0 events=6 delay=1'):
        assert marker in log,marker
    assert 'STOP unsupported:' not in log and 'DIAGNOSTIC WATCHDOG STOPPED' not in log and 'STOP CPU exception' not in log
    assert log.count('Thread event: 3 ')==6
    jni=re.search(r'JNI checkpoint: pending=(\d+) failures=(\d+) refs=(\d+) frame-depth=(\d+) string-loans=(\d+)',log);assert jni
    jni=dict(zip(('pending','failures','refs','frame_depth','string_loans'),map(int,jni.groups())))
    assert jni=={'pending':0,'failures':3,'refs':11,'frame_depth':0,'string_loans':1}
    assert 'JNI PopLocalFrame pinned string:' not in log
    assert 'JNI retained string: slot=2 text=1.1.33 Universal SD (Default) loans=1 refs=0' in log
    jumps=re.search(r'Jump contexts: saves=(\d+) restores=(\d+) refusals=(\d+)',log);assert jumps
    jumps=dict(zip(('saves','restores','refusals'),map(int,jumps.groups())));assert jumps['saves']>=601 and not jumps['restores'] and not jumps['refusals']
    texture=re.search(r'GLES texture stores: names=(\d+) bytes=(\d+) uploads=(\d+) patches=(\d+)',log);assert texture
    texture=dict(zip(('names','bytes','uploads','patches'),map(int,texture.groups())))
    assert 2<=texture['names']<=32 and 1048580<=texture['bytes']<=6*1024*1024 and texture['uploads']>=3 and not texture['patches']
    arena=re.search(r'Donor arenas: break=(\d+) peak=(\d+) mapped-pages=(\d+) map-peak=(\d+) refusals=(\d+)',log);assert arena
    arena=dict(zip(('break_bytes','break_peak','mapped_pages','map_peak_pages','refusals'),map(int,arena.groups())))
    assert arena['break_bytes']==16781312 and arena['mapped_pages']==8908 and 12116<=arena['map_peak_pages']<=20480 and not arena['refusals']
    meta=read('analysis/first-frame/first-game-frame.json');raw=(P/'analysis/first-frame/first-game-frame.raw').read_bytes()
    assert meta['width']==400 and meta['height']==240 and meta['layout']==2 and meta['frame']==8
    # Worker completion changes the first textured callback; counters must
    # agree with the journal and represent substantial real, textured draws.
    assert 12<=meta['draws']<=32 and meta['triangles']==meta['draws']*2
    assert meta['fragments']>=400000 and meta['samples']>=100000
    assert f"FIRST GAME FRAME CAPTURED: frame=8 draws={meta['draws']} fragments={meta['fragments']} samples={meta['samples']}" in log
    assert len(raw)==meta['bytes']==192000 and f'{zlib.crc32(raw):08x}'==meta['crc32']
    w,h,pixels=png('analysis/first-frame/first-game-frame.png');assert (w,h)==(400,240)
    expected=bytearray()
    for y in range(239,-1,-1):
        for x in range(400):
            value=struct.unpack_from('<H',raw,(x*240+y)*2)[0];expected.extend((((value>>11)&31)*255//31,((value>>5)&63)*255//63,(value&31)*255//31))
    assert pixels==expected and len(set(struct.iter_unpack('3B',pixels)))>16 and max(pixels)>96
    lw,lh,lcd=png('analysis/first-frame/azahar-screen.png');assert (lw,lh)==(400,480)
    # The software libretro LCD path can place the top image one scanline below
    # the decoded buffer. Verify both alignments without modifying either PNG.
    alignments=[]
    for dy in (0,1):
        count=(240-dy)*400*3
        if max(abs(a-b) for a,b in zip(pixels[:count],lcd[dy*400*3:dy*400*3+count]))<=1:alignments.append(dy)
    assert alignments
    assert not any(lcd[400*240*3:])
    report={'passed':True,'emulator':'Azahar libretro 2126.2','hardware_tested':False,'gameplay':False,'menu_confirmed':False,
        'first_game_frame_rendered':True,'presented_to_emulated_lcd':True,'lcd_vertical_offset_pixels':alignments[0],
        'frame':meta,'renderer':'bounded unlit CPU triangles; no PICA200 acceleration',
        'original_draw_caller_offset':'003244e0','donor_workers_started':6,'native_acceleration_callbacks_returned':6,
        'opt_in_gl_bindings':99,'opt_in_filesystem_bindings':4,'application_memory_bytes':130023424,
        'arena_capacity_bytes':{'break':20*1024*1024,'anonymous_mappings':80*1024*1024},'arena_stats':arena,
        'texture_stores_at_capture':texture,'jump_contexts':jumps,'jni_checkpoint':jni,'retained_string_loan':'version text has one native borrow and no JNI references; storage retained until context cleanup; local frames close normally',
        'core_sha256':tests['core_sha256'],'cxi_sha256':native['cxi_sha256'],
        'witnesses_sha256':{p:sha(p) for p in ('analysis/first-frame-tests.json','analysis/azahar-smoke/engine-graphics.log','analysis/azahar-smoke/engine-graphics-result.json',
            'analysis/first-frame/first-game-frame.raw','analysis/first-frame/first-game-frame.json','analysis/first-frame/first-game-frame.png','analysis/first-frame/azahar-screen.png')}}
    (P/'analysis/first-frame-result.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':print(json.dumps(validate(),indent=2))
