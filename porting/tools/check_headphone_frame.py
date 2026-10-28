"""Verify the longer donor run and its real CPU/LCD headphone-screen images."""
import json,re,struct,zlib
from check_first_frame import P,read,sha,png

def validate():
    folder='analysis/headphone-frame/'
    build=read('3ds/build-emulator/build-manifest.json')
    for path,digest in build['sources_sha256'].items():assert sha(path)==digest,path
    for name,digest in build['outputs_sha256'].items():assert sha('3ds/build-emulator/'+name)==digest,name
    native=read(folder+'engine-frame120-result.json');log=(P/folder/'engine-frame120.log').read_text(encoding='utf-8')
    assert native['exploratory'] and not native['checkpoint_validated'] and native['first_game_frame_rendered']
    assert native['cxi_sha256']==build['outputs_sha256']['engine-audit.cxi']
    assert native['log_sha256']==sha(folder+'engine-frame120.log')
    for frame in range(1,121):assert f'Frame {frame} returned\n' in log
    for marker in ('Donor constructors completed: 209','Completed game frame saved.','GLES error at stop: 00000000',
        'JNI checkpoint: pending=0 failures=3 refs=11 frame-depth=0 string-loans=1',
        'JNI retained string: slot=2 text=1.1.33 Universal SD (Default) loans=1 refs=0',
        'Sensor shutdown: result=0 active=0 events=118 delay=1',
        'GLES upload: 256x256 format=1906 required=2097156 limit=6291456 result=0'):
        assert marker in log,marker
    assert log.count('Thread event: 3 ')==6
    for bad in ('STOP unsupported:','STOP CPU exception','DIAGNOSTIC WATCHDOG STOPPED','PopLocalFrame pinned','GLES state:'):
        assert bad not in log,bad
    assert not re.search(r'GLES upload: .*result=[12]',log)
    meta=read(folder+'first-game-frame.json');raw=(P/folder/'first-game-frame.raw').read_bytes()
    assert (meta['width'],meta['height'],meta['layout'],meta['frame'])==(400,240,2,120)
    assert meta['draws']>=250 and meta['triangles']>=1000 and meta['samples']>=1_000_000
    assert len(raw)==meta['bytes']==192000 and f'{zlib.crc32(raw):08x}'==meta['crc32']
    assert f"FIRST GAME FRAME CAPTURED: frame=120 draws={meta['draws']} fragments={meta['fragments']} samples={meta['samples']}" in log
    width,height,pixels=png(folder+'first-game-frame.png');assert (width,height)==(400,240)
    expected=bytearray()
    for y in range(239,-1,-1):
        for x in range(400):
            v=struct.unpack_from('<H',raw,(x*240+y)*2)[0]
            expected.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    assert pixels==expected and len(set(struct.iter_unpack('3B',pixels)))>100 and max(pixels)>200
    lw,lh,lcd=png(folder+'azahar-screen.png');assert (lw,lh)==(400,480)
    offsets=[]
    for dy in (0,1):
        n=(240-dy)*400*3
        if max(abs(a-b) for a,b in zip(pixels[:n],lcd[dy*400*3:dy*400*3+n]))<=1:offsets.append(dy)
    assert offsets and not any(lcd[400*240*3:])
    report={'passed':True,'runner_exploratory':True,'verified_by':'check_headphone_frame.py',
        'screen':'character and headphones; advice text visually inspected','frames_returned':120,
        'gles_error':0,'pending_jni_exception':False,'local_frame_depth':0,'retained_version_string_loans':1,
        'native_acceleration_callbacks_returned':118,'donor_workers_started':6,'frame':meta,
        'lcd_vertical_offset_pixels':offsets[0],'texture_budget_bytes':6*1024*1024,'runtime_heap_budget_bytes':8*1024*1024,
        'hardware_tested':False,'menu_confirmed':False,'gameplay':False,'audio_confirmed':False,
        'core_sha256':build['outputs_sha256']['core-test.elf'],'cxi_sha256':native['cxi_sha256'],
        'witnesses_sha256':{folder+n:sha(folder+n) for n in ('engine-frame120.log','engine-frame120-result.json',
            'first-game-frame.json','first-game-frame.raw','first-game-frame.png','azahar-screen.png')}}
    (P/'analysis/headphone-frame-result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':print(json.dumps(validate(),indent=2))
