"""Check the independent control's actual CIA payload in isolated Azahar."""
import argparse,ctypes as C,hashlib,json,os,re,struct,time
from pathlib import Path
from PIL import Image
P=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fault-test',action='store_true');args=parser.parse_args()
os.environ['DEADSPACE_EMULATOR_ROOT']=str(P/('analysis/azahar-citro3d-control'+('-fault' if args.fault_test else '')))
import smoke_azahar as f
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    build=P/('3ds/build-citro3d-control'+('-fault' if args.fault_test else ''))
    data=(build/'control.cia').read_bytes();h,k,v,c,t,m,_,size=struct.unpack_from('<IHHIIIIQ',data)
    align=lambda n:(n+63)&~63
    off=align(h)+align(c)+align(t)+align(m);payload=data[off:off+size]
    assert h==0x2020 and k==v==0 and payload[0x100:0x104]==b'NCCH'
    assert struct.unpack_from('<Q',payload,0x108)[0]==0x000400000FDE6900
    app=build/'cia-payload.cxi';app.write_bytes(payload)
    card=f.ROOT/'Azahar/sdmc/3ds/citro3d-control-v0.1.0';card.mkdir(parents=True,exist_ok=True)
    for name in ['ready.txt','result.json','control.log','clear.raw','triangle.raw','triangle-vertices.bin','stage-0-queue.json','stage-1-queue.json','stage-1-1.pica']:
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
            assert not result.exists() and not (card/'stage-0-queue.json').exists(),'Test ran without A'
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
    assert native['environment']=='emulator' and native['ds34_linked'] is False and native['game_called'] is False
    assert native['passed'] is (not args.fault_test) and drained,native
    host=(f.ROOT/'azahar-host.log').read_text(errors='replace')
    errors=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo).*',host);assert not errors,errors[:5]
    submits=re.findall(r'SUBMIT \d+ result=([0-9a-f]{8})',log);assert submits and all(v=='00000000' for v in submits)
    clear=json.loads((card/'stage-0-queue.json').read_text());assert [e['type'] for e in clear['entries']]==[2,3],clear
    queues={'clear':[e['type'] for e in clear['entries']]};images={}
    if args.fault_test:
        assert native['stages_completed']==0 and native['timeout'] and native['failure']=='GX QUEUE TIMEOUT',native
        assert not (card/'stage-1-queue.json').exists() and 'SCENE INIT BEGIN' not in log
        assert not (card/'clear.raw').exists(),'Readback ran without retirement'
    else:
        assert native['stages_completed']==2 and native['failure']=='none' and not native['timeout']
        triangle=json.loads((card/'stage-1-queue.json').read_text());assert [e['type'] for e in triangle['entries']]==[2,1,3],triangle
        queues['triangle']=[e['type'] for e in triangle['entries']]
        assert (card/'triangle-vertices.bin').read_bytes()==struct.pack('<9f',200,200,.5,100,40,.5,300,40,.5)
        for name in ['clear','triangle']:
            raw=(card/(name+'.raw')).read_bytes();assert len(raw)==192000
            pixels=[struct.unpack_from('<H',raw,(x*240+239-y)*2)[0] for y in range(240) for x in range(400)]
            background=pixels[20*400+20];assert len(set(pixels))==(1 if name=='clear' else 2)
            if name=='triangle':assert pixels[120*400+200]==65535 and 15000<=pixels.count(65535)<=17000
            assert background!=65535
            image=Image.new('RGB',(400,240));image.putdata([(((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31) for v in pixels]);image.save(f.ROOT/(name+'.png'))
            images[name]={'raw_sha256':hashlib.sha256(raw).hexdigest(),'png_sha256':sha(f.ROOT/(name+'.png')),'distinct_colors':len(set(pixels))}
    for name in ['control.log','stage-0-queue.json','stage-1-queue.json','stage-1-1.pica','triangle-vertices.bin']:
        if (card/name).exists():(f.ROOT/name).write_bytes((card/name).read_bytes())
    report={'passed':True,'intentional_fault':args.fault_test,'hardware_tested':False,'tested_payload':'NCCH extracted from actual CIA',
        'cia_sha256':sha(build/'control.cia'),'payload_sha256':sha(app),'stale_result_cleared':True,'A_gate_verified':True,'START_exit_drained':drained,
        'invalid_accesses':len(errors),'submit_results_success':True,'queue_types':queues,'pixel_checks':images,'native_result':native,'elapsed_seconds':round(time.monotonic()-started,3)}
    (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
