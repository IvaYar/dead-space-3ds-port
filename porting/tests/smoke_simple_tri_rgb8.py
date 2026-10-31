"""One short actual-CIA-payload run; software LCD pixels and guest START cleanup."""
import ctypes as C,hashlib,json,os,re,struct,time
from pathlib import Path
from PIL import Image
P=Path(__file__).resolve().parents[1]
os.environ['DEADSPACE_EMULATOR_ROOT']=str(P/'analysis/azahar-simple-tri-rgb8')
import smoke_azahar as f

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    build=P/'3ds/build-simple-tri-rgb8';app=build/'cia-payload.cxi'
    data=(build/'simple-tri-rgb8.cia').read_bytes()
    h,_,_,c,t,m,_,size=struct.unpack_from('<IHHIIIIQ',data)
    offset=sum((n+63)&~63 for n in [h,c,t,m]);payload=data[offset:offset+size]
    assert payload==app.read_bytes() and struct.unpack_from('<Q',payload,0x108)[0]==0x000400000FDE6C00
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    press_start=False
    @C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
    def input_state(port,device,index,key):
        return int(press_start) if port==0 and device==1 and index==0 and key==3 else 0
    for name,cb in [('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),
        ('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',input_state)]:
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(cb)];setter(cb)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();info=f.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(info))
    observations=[];started=time.monotonic();cleanup_segment=''
    try:
        for frame in range(121):
            core.retro_run()
            if frame in [60,90,120]:
                assert f.frame is not None
                path=f.ROOT/f'frame-{frame}.png';f.save_frame(path)
                image=Image.open(path).convert('RGB');assert image.size==(400,480)
                top=image.crop((0,0,400,240));top.save(f.ROOT/f'top-{frame}.png')
                pixels=list(top.get_flattened_data());background=top.getpixel((20,20))
                white=pixels.count((255,255,255));bg_count=pixels.count(background)
                anomalies=[(x,y,top.getpixel((x,y))) for y in range(240) for x in range(400)
                    if top.getpixel((x,y)) not in [background,(255,255,255)]]
                observation={'frontend_frame':frame,'background_RGB':background,'white_pixels':white,
                    'background_pixels':bg_count,'corner_anomalies':anomalies,
                    'top_pixels_sha256':hashlib.sha256(top.tobytes()).hexdigest(),'image':path.name}
                observations.append(observation)
                (f.ROOT/'observations.json').write_text(json.dumps(observations,indent=2)+'\n')
                expected=(104,176,216)  # RGB8 output retains the original channels.
                assert background==expected,(background,expected)
                assert anomalies in [[],[(399,0,(0,0,0))]],anomalies[:10]
                assert white==16000 and white+bg_count+len(anomalies)==96000
                assert top.getpixel((200,120))==(255,255,255)
            assert time.monotonic()-started<40,'Host deadline'
        before_START=(f.ROOT/'azahar-host.log').stat().st_size
        press_start=True
        for _ in range(90):core.retro_run()
        cleanup_segment=(f.ROOT/'azahar-host.log').read_bytes()[before_START:].decode(errors='replace')
        assert 'ReleaseRight:999: called' in cleanup_segment
        assert 'operation=0x00000001, addr0=0x08000000' in cleanup_segment
    finally:
        core.retro_unload_game();core.retro_deinit()
    host=(f.ROOT/'azahar-host.log').read_text(errors='replace')
    invalid=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo).*',host)
    assert not invalid,invalid[:5]
    assert len({o['top_pixels_sha256'] for o in observations})==1
    report={'passed':True,'hardware_tested':False,'diagnostic_cycle':1,
        'tested_payload':'NCCH extracted from actual CIA; FBI installation not emulated',
        'CIA_sha256':sha(build/'simple-tri-rgb8.cia'),'payload_sha256':sha(app),'ELF_sha256':sha(build/'triangle.elf'),
        'capture':'Azahar2126.2 software LCD libretro video callback; no OpenGL',
        'observations':observations,'invalid_accesses_in_host_log':0,'START_guest_GSP_release_and_heap_free':True,
        'frontend_shutdown_signal':f.shutdown,'elapsed_seconds':round(time.monotonic()-started,3),
        'limitations':['No native queue/IRQ instrumentation; frontend observations are not a native frame count',
            'Stock-style rendering starts immediately and has no native timeout or SD log',
            'Azahar PASS does not establish hardware success; expected service stubs remain']}
    (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
