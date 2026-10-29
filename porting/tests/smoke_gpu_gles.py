"""Check actual GPU pixels produced through the game's GLES binding layer."""
import os,ctypes as C,json,time,zlib,struct,hashlib,sys,re
from pathlib import Path
P=Path(__file__).resolve().parents[1]
ENGINE_MEMORY='--engine-memory' in sys.argv[1:]
os.environ['DEADSPACE_EMULATOR_ROOT']=str(P/('analysis/azahar-gpu-gles-memory' if ENGINE_MEMORY else 'analysis/azahar-gpu-gles'))
import smoke_azahar as f
def png(rgb):
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v))
    scan=b''.join(b'\0'+rgb[y*1200:(y+1)*1200] for y in range(240))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',400,240,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')
def main():
    card=f.ROOT/'Azahar/sdmc/3ds/deadspace';card.mkdir(parents=True,exist_ok=True)
    meta=card/'gpu-gles-result.json';error=card/'gpu-gles-error.txt'
    for path in (meta,error,*card.glob('gpu-gles-*.raw')):
        if path.exists():path.unlink()
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    for name,callback in (('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',f.input_state)):
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(callback)];setter(callback)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();app=P/('3ds/build-gpu-gles-memory/gpu-gles.cxi' if ENGINE_MEMORY else '3ds/build-gpu-gles/gpu-gles.cxi');info=f.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(info));start=time.monotonic()
    for frame in range(3600):
        core.retro_run()
        if frame%10==0 and (meta.exists() or error.exists()):break
        if time.monotonic()-start>90:break
    if f.frame:f.save_frame(f.ROOT/'gpu-gles-screen.png')
    core.retro_unload_game();core.retro_deinit()
    assert not error.exists(),error.read_text() if error.exists() else ''
    assert meta.exists(),'No GLES GPU result; inspect isolated screen and emulator log'
    memory_errors=re.findall(r'.*unmapped (?:Read|Write)\w*.*',(f.ROOT/'azahar-host.log').read_text(errors='replace'))
    assert not memory_errors,memory_errors[:8]
    m=json.loads(meta.read_text());images=[];pixels=[]
    for case in range(9):
        raw=(card/f'gpu-gles-{case}.raw').read_bytes();assert len(raw)==192000
        rgb=bytearray()
        for y in range(239,-1,-1):
            for x in range(400):
                off=(x*240+y)*2;v=raw[off]|raw[off+1]<<8
                rgb.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
        image=png(rgb);(f.ROOT/f'gpu-gles-{case}.png').write_bytes(image)
        images.append(hashlib.sha256(image).hexdigest())
        pixels.append(lambda x,y,data=rgb:tuple(data[(y*400+x)*3:(y*400+x+1)*3]))
    def near(case,x,y,expected):
        actual=pixels[case](x,y);assert max(abs(a-b) for a,b in zip(actual,expected))<=8,(case,x,y,actual,expected)
    near(0,200,120,(0,255,0));near(0,50,120,(16,32,48));near(0,200,20,(16,32,48))
    near(1,80,40,(0,0,255));near(1,320,40,(255,255,255));near(1,80,200,(255,0,0));near(1,320,200,(0,255,0))
    near(2,200,120,(128,0,127))
    near(3,200,30,(255,255,255));near(3,200,90,(0,0,255))
    near(3,200,150,(0,255,0));near(3,200,210,(255,0,0))
    near(4,200,30,(255,255,255));near(4,200,90,(0,0,255))
    near(4,200,150,(0,255,0));near(4,200,210,(255,0,0))
    near(5,100,120,(0,255,0));near(5,300,120,(0,255,0))
    near(6,100,120,(0,0,255));near(6,300,120,(255,0,0))
    near(7,80,40,(0,0,255));near(7,320,40,(255,255,255))
    near(7,80,200,(255,0,0));near(7,320,200,(0,255,0))
    near(8,100,120,(255,0,0));near(8,300,120,(255,0,0))
    assert m['passed'] and m['gpu_draws']==22 and m['gpu_triangles']==2772 and m['gpu_uploads']==5
    assert m['cpu_fragments']==m['cpu_samples']==0
    report={**m,'unmapped_accesses':len(memory_errors),'engine_memory':ENGINE_MEMORY,'scope':'GLES adapter GPU fragments; original game not called','hardware_tested':False,'emulator_sd_isolated':True,
        'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),'png_sha256':images,'elapsed_seconds':round(time.monotonic()-start,3)}
    (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
