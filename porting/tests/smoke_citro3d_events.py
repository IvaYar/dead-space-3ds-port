"""Verify passive event counters, checkpoints and unchanged CLEAR packets."""
import argparse,ctypes as C,hashlib,json,os,re,struct,time
from pathlib import Path
from PIL import Image
P=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fault-test',action='store_true');args=parser.parse_args()
os.environ['DEADSPACE_EMULATOR_ROOT']=str(P/('analysis/azahar-citro3d-events'+('-fault' if args.fault_test else '')))
import smoke_azahar as f
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    build=P/('3ds/build-citro3d-events'+('-fault' if args.fault_test else ''))
    data=(build/'control.cia').read_bytes();h,k,v,c,t,m,_,size=struct.unpack_from('<IHHIIIIQ',data)
    align=lambda n:(n+63)&~63
    off=align(h)+align(c)+align(t)+align(m);payload=data[off:off+size]
    assert h==0x2020 and k==v==0 and payload[0x100:0x104]==b'NCCH'
    assert struct.unpack_from('<Q',payload,0x108)[0]==0x000400000FDE6900
    app=build/'cia-payload.cxi';app.write_bytes(payload)
    card=f.ROOT/'Azahar/sdmc/3ds/citro3d-control-v0.1.1';card.mkdir(parents=True,exist_ok=True)
    for name in [*[f.name for f in card.glob('events-*.json')],'ready.txt','result.json','control.log','clear.raw','triangle.raw','triangle-vertices.bin','stage-0-queue.json','stage-1-queue.json','stage-1-1.pica']:
        q=card/name
        if q.exists():q.unlink()
    result=card/'result.json';result.write_text('{"stale":true,"passed":true}')
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    original=f.input_state;press_start=False
    @C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
    def input_state(port,device,index,key):
        if port==0 and device==1 and index==0 and key==3:return int(press_start)
        return original(port,device,index,key)
    for name,cb in [('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',input_state)]:
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(cb)];setter(cb)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();info=f.GameInfo(str(app.resolve()).encode(),None,0,None);assert core.retro_load_game(C.byref(info))
    ready=None;sent=None;started=time.monotonic()
    for frame in range(3000):
        if (card/'ready.txt').exists() and ready is None:
            ready=frame;assert not result.exists(),'Stale PASS not removed'
        if ready is not None and sent is None and frame>=ready+30:
            assert not result.exists() and not list(card.glob('events-*.json')),'Test ran without A'
            assert 'C3D INIT BEGIN' not in (card/'control.log').read_text();sent=frame
        f.button_a=sent is not None and sent<=frame<sent+8
        core.retro_run()
        if sent is not None and result.exists() and result.stat().st_size:break
        if time.monotonic()-started>45:break
    for _ in range(3):core.retro_run()
    if f.frame:f.save_frame(f.ROOT/'screen.png')
    f.button_a=False;press_start=True;drained=False
    if result.exists():
        for _ in range(90):
            core.retro_run()
            if 'EXIT GPU DRAINED' in (card/'control.log').read_text():drained=True;break
    core.retro_unload_game();core.retro_deinit()
    assert result.exists(),'Control did not return; inspect isolated log'
    native=json.loads(result.read_text());log=(card/'control.log').read_text()
    assert native['environment']=='emulator' and native['ds34_linked'] is False and native['triangle_called'] is False
    assert native['passed'] is (not args.fault_test) and drained,native
    host=(f.ROOT/'azahar-host.log').read_text(errors='replace')
    errors=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo).*',host);assert not errors,errors[:5]
    submits=re.findall(r'SUBMIT \d+ result=([0-9a-f]{8})',log)
    assert len(submits)==2 and all(x=='00000000' for x in submits)
    snapshots=[json.loads(q.read_text()) for q in sorted(card.glob('events-*.json'))]
    assert snapshots and all(q['version']=='0.1.1' for q in snapshots)
    before=next(q for q in snapshots if q['label']=='before-submit')
    after=next(q for q in snapshots if q['label']=='after-submit')
    expected=json.loads((P/'analysis/hardware/citro3d-control-v0.1.0-user/stage-0-queue.json').read_text())
    assert before['commands']==after['commands']==[e['words'] for e in expected['entries']]
    assert before['queue']=={'total':2,'submitted':0,'completed':0}
    assert before['events_consistent'] and all(v['count']==0 for v in before['events'].values())
    last=next(q for q in reversed(snapshots) if q['events_consistent'])
    assert {name:v['count'] for name,v in last['events'].items()}=={'PSC0':1,'PSC1':0,'PPF':1},last
    # Azahar 2126.2 sends only PSC0 for a dual-buffer MemoryFill command.
    assert last['serial']==2 and last['tick_hz']==268111856
    assert {v['first_order'] for v in last['events'].values() if v['count']}=={1,2}
    for sample in snapshots:
        if not sample['events_consistent']:continue
        assert sum(v['count'] for v in sample['events'].values())==sample['serial']
        for name,v in sample['events'].items():
            assert v['stable']
            if not v['count']:continue
            assert v['first_run']==v['last_run']==1
            assert sample['origin_tick']<=v['first_tick']<=v['last_tick']<=sample['sample_tick']
            assert v['first_us']==(v['first_tick']-sample['origin_tick'])*1000000//sample['tick_hz']
            assert v['last_us']==(v['last_tick']-sample['origin_tick'])*1000000//sample['tick_hz']
    assert native['triangle_called'] is False and not native['checkpoint_io_failed']
    assert native['version']=='0.1.1' and not list(card.glob('*.pica'))
    if args.fault_test:
        timeout=next(q for q in snapshots if q['label']=='timeout')
        assert timeout['queue']=={'total':2,'submitted':2,'completed':2}
        assert timeout['events_consistent'] and timeout['events']['PSC0']['count']==timeout['events']['PPF']['count']==1
        assert timeout['events']['PSC1']['count']==0
        assert 'OBSERVER SOFTWARE SELFTEST PASS; not GPU events' in log
        assert native['stages_completed']==0 and native['timeout'] and native['failure']=='GX QUEUE TIMEOUT'
        assert not (card/'clear.raw').exists()
        stamps=re.findall(r'PHASE ms=(\d+) vb=\d+,\d+ (GX WAIT BEGIN|GX QUEUE TIMEOUT)',log)
        elapsed=int(stamps[-1][0])-int(stamps[-2][0]);assert 1900<=elapsed<=4000
    else:
        assert native['stages_completed']==1 and not native['timeout'] and native['passed']
        raw=(card/'clear.raw').read_bytes();assert len(raw)==192000
        values=struct.unpack('<96000H',raw);assert len(set(values))==1
        value=values[0];rgb=(((value>>11)&31)*255//31,((value>>5)&63)*255//63,(value&31)*255//31)
        assert max(abs(a-b) for a,b in zip(rgb,(16,32,48)))<=8
        Image.new('RGB',(400,240),rgb).save(f.ROOT/'clear.png')
        assert hashlib.sha256(raw).hexdigest()==json.loads((P/'analysis/azahar-citro3d-control/result.json').read_text())['pixel_checks']['clear']['raw_sha256']
    for q in [card/'control.log',card/'result.json',*card.glob('events-*.json')]:
        (f.ROOT/('native-result.json' if q.name=='result.json' else q.name)).write_bytes(q.read_bytes())
    report={'passed':True,'intentional_fault':args.fault_test,'hardware_tested':False,
        'tested_payload':'NCCH extracted from actual CIA','cia_sha256':sha(build/'control.cia'),'payload_sha256':sha(app),
        'native_result':native,'A_gate_verified':True,'stale_result_cleared':True,'START_exit_drained':drained,
        'invalid_accesses':len(errors),'exact_native_v0_1_0_GPU_packets_unchanged':True,
        'delivered_event_counts':{n:v['count'] for n,v in last['events'].items()},
        'event_timestamp_and_snapshot_consistency_verified':True,'checkpoint_count':len(snapshots),
        'timeout_checkpoint_verified':args.fault_test,'elapsed_seconds':round(time.monotonic()-started,3)}
    (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
