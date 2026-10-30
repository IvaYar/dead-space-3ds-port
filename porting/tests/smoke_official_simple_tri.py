"""Check unmodified upstream simple_tri in Azahar; software LCD output, no GL capture."""
import argparse,ctypes as C,hashlib,json,os,re,time
from pathlib import Path
from PIL import Image
P=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--format',choices=['3dsx','cia'],required=True)
args=parser.parse_args()
os.environ['DEADSPACE_EMULATOR_ROOT']=str(P/('analysis/azahar-official-simple-tri-'+args.format))
import smoke_azahar as f

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    build=P/'3ds/build-official-simple-tri'
    app=build/('simple_tri.3dsx' if args.format=='3dsx' else 'cia-payload.cxi')
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    press_start=False
    @C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
    def input_state(port,device,index,key):
        if port==0 and device==1 and index==0 and key==3:return int(press_start)
        return 0
    for name,cb in [('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),
        ('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',input_state)]:
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(cb)];setter(cb)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();info=f.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(info)),'Load failed'
    observations=[];started=time.monotonic()
    try:
        for frame in range(180):
            core.retro_run()
            if frame in [60,90,120]:
                assert f.frame is not None
                path=f.ROOT/f'frame-{frame}.png';f.save_frame(path)
                image=Image.open(path).convert('RGB');assert image.size==(400,480),image.size
                top=image.crop((0,0,400,240));top.save(f.ROOT/f'top-{frame}.png')
                pixels=list(top.get_flattened_data())
                white=pixels.count((255,255,255));background=pixels.count((104,176,216))
                # Preserve and report the observed one-pixel LCD corner anomaly.
                # Accept only this exact location/color; do not hide other errors.
                anomalies=[(x,y,top.getpixel((x,y))) for y in range(240) for x in range(400)
                    if top.getpixel((x,y)) not in [(255,255,255),(104,176,216)]]
                assert anomalies in [[],[(399,0,(0,0,0))]],anomalies[:10]
                assert 15000<=white<=17000 and white+background+len(anomalies)==96000,(white,background)
                assert top.getpixel((200,120))==(255,255,255) and top.getpixel((20,20))==(104,176,216)
                observations.append({'frontend_frame':frame,'white_pixels':white,'background_pixels':background,
                    'corner_anomalies':anomalies,'top_pixels_sha256':hashlib.sha256(top.tobytes()).hexdigest(),'image':path.name})
            if frame==120:break
            assert time.monotonic()-started<40,'Host deadline'
        press_start=True
        for _ in range(90):
            core.retro_run()
            if f.shutdown:break
    finally:
        core.retro_unload_game();core.retro_deinit()
    host=(f.ROOT/'azahar-host.log').read_text(errors='replace')
    invalid=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo).*',host)
    assert not invalid,invalid[:5]
    assert len({o['top_pixels_sha256'] for o in observations})==1,'Image unstable'
    report={'passed':True,'format':args.format,'hardware_tested':False,'app_sha256':sha(app),
        'cia_sha256':sha(build/'simple_tri-profile.cia') if args.format=='cia' else None,
        'ELF_sha256':sha(build/'simple_tri.elf'),'unmodified_upstream_source':True,
        'capture':'Azahar software renderer LCD libretro video callback; no OpenGL',
        'observations':observations,'invalid_accesses_in_host_log':len(invalid),'START_requested':True,
        'frontend_shutdown_signal':f.shutdown,'elapsed_seconds':round(time.monotonic()-started,3),
        'limitations':['Frontend observations are not an instrumented native frame count',
            'CIA tested as extracted NCCH payload; FBI installation not emulated',
            'No native SD log, observer, timeout or safety gate added to upstream source']}
    (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
