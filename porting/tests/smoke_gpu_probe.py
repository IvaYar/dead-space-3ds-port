"""Execute PICA commands in a separate emulator SD and inspect actual pixels."""
import os,ctypes as C,json,time,zlib,struct,hashlib
from pathlib import Path
P=Path(__file__).resolve().parents[1]
os.environ['DEADSPACE_EMULATOR_ROOT']=str(P/'analysis/azahar-gpu-probe')
import smoke_azahar as f
def main():
    card=f.ROOT/'Azahar/sdmc/3ds/deadspace';card.mkdir(parents=True,exist_ok=True)
    meta=card/'gpu-probe.json'
    if meta.exists():meta.unlink()
    library=P/'toolchain/azahar-libretro/azahar_libretro.dll';core=C.CDLL(str(library.resolve()))
    for name,callback in (('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',f.input_state)):
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(callback)];setter(callback)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();app=P/'3ds/build-gpu-probe/gpu-probe.cxi';info=f.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(info))
    start=time.monotonic()
    for frame in range(3600):
        core.retro_run()
        if meta.exists() and frame%10==0:break
        if time.monotonic()-start>90:break
    if f.frame:f.save_frame(f.ROOT/'gpu-probe-screen.png')
    core.retro_unload_game();core.retro_deinit()
    assert meta.exists(),'GPU capture missing; inspect isolated LCD/log'
    m=json.loads(meta.read_text());raw=(card/'gpu-probe.raw').read_bytes()
    assert m['frames']==16 and not m['game_called'] and not m['cpu_rasterizer_linked']
    assert m['layout']==1 and m['width']==400 and m['height']==240 and len(raw)==m['bytes']==288000
    assert f'{zlib.crc32(raw):08x}'==m['crc32']
    rgb=bytearray()
    for y in range(239,-1,-1):
        for x in range(400):rgb.extend(raw[(x*240+y)*3:(x*240+y)*3+3][::-1])
    def pixel(x,y):return tuple(rgb[(y*400+x)*3:(y*400+x+1)*3])
    # Background plus interior gradient: excludes an all-clear/all-white image.
    assert max(abs(a-b) for a,b in zip(pixel(10,10),(16,32,48)))<=1,pixel(10,10)
    center=pixel(200,120);assert min(center)>10 and max(center)-min(center)>10,center
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v))
    scan=b''.join(b'\0'+rgb[y*1200:(y+1)*1200] for y in range(240))
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',400,240,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')
    (f.ROOT/'gpu-probe.png').write_bytes(png)
    report={'passed':True,'scope':'PICA foundation only; original game not accelerated yet','hardware_tested':False,
        'frames':16,'center_rgb':center,'elapsed_seconds':round(time.monotonic()-start,3),
        'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),'raw_sha256':hashlib.sha256(raw).hexdigest(),
        'png_sha256':hashlib.sha256(png).hexdigest(),'emulator_sd_isolated':True}
    (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
