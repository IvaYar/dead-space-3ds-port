"""Compare synthetic PICA pixels with the actual DS22 renderer in Azahar."""
import ctypes as C,hashlib,json,os,re,struct,time,zlib,sys
from pathlib import Path
P=Path(__file__).resolve().parents[1]
OPENGL='--opengl' in sys.argv[1:]
RGBA='--rgba-target' in sys.argv[1:]
os.environ['DEADSPACE_EMULATOR_ROOT']=str(P/('analysis/azahar-gpu-sampling-gl-rgba' if OPENGL and RGBA else 'analysis/azahar-gpu-sampling-gl' if OPENGL else 'analysis/azahar-gpu-sampling-rgba' if RGBA else 'analysis/azahar-gpu-sampling'))
import smoke_azahar as f

def rgb565(raw):
    out=bytearray()
    for y in range(239,-1,-1):
        for x in range(400):
            off=(x*240+y)*2;v=raw[off]|raw[off+1]<<8
            out.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    return out

def png(rgb):
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v))
    scan=b''.join(b'\0'+rgb[y*1200:(y+1)*1200] for y in range(240))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',400,240,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')

def main():
    gl=None
    if OPENGL:
        from azahar_opengl import Frontend
        gl=Frontend(f)
    card=f.ROOT/'Azahar/sdmc/3ds/deadspace';card.mkdir(parents=True,exist_ok=True)
    meta=card/'sampling-result.json';error=card/'sampling-error.txt'
    for path in (meta,error,*card.glob('sampling-*.raw')):
        if path.exists():path.unlink()
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    for name,callback in (('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',f.input_state)):
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(callback)];setter(callback)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();app=P/('3ds/build-gpu-sampling-rgba/gpu-gles.cxi' if RGBA else '3ds/build-gpu-sampling/gpu-gles.cxi');info=f.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(info));start=time.monotonic()
    if gl:gl.reset()
    host_captures=set()
    for frame in range(3600):
        core.retro_run()
        if gl and f.frame:
            for test in (8,*range(8)):
                path=card/f'sampling-gpu-{test}.raw'
                if test not in host_captures and path.exists() and path.stat().st_size==192000:
                    f.save_frame(f.ROOT/f'host-{test}.png');host_captures.add(test)
        if frame%10==0 and ((meta.exists() and meta.stat().st_size) or (error.exists() and error.stat().st_size)):break
        if time.monotonic()-start>90:break
    core.retro_unload_game();core.retro_deinit()
    assert not error.exists(),error.read_text() if error.exists() else ''
    assert meta.exists(),'No paired sampling result'
    memory_errors=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address).*',(f.ROOT/'azahar-host.log').read_text(errors='replace'))
    cases=[]
    for test in (*range(8),8):
        images=[]
        for backend in ('cpu','gpu'):
            raw=(card/f'sampling-{backend}-{test}.raw').read_bytes();assert len(raw)==192000
            rgb=rgb565(raw);(f.ROOT/f'{backend}-{test}.png').write_bytes(png(rgb));images.append(rgb)
        diffs=[max(abs(images[0][i+j]-images[1][i+j]) for j in range(3)) for i in range(0,len(images[0]),3)]
        bad=[i for i,v in enumerate(diffs) if v>8]
        cases.append({'case':test,'filter':'untextured' if test==8 else 'LINEAR' if test&1 else 'NEAREST','pattern':'asymmetric RGB control' if test==8 else ('magnified lines/checker','fractional UV','exact texel boundary','fractional alpha atlas')[test//2],
            'pixels_over_tolerance':len(bad),'max_channel_error':max(diffs),'first_mismatches':[[i%400,i//400] for i in bad[:8]],'passed':not bad})
    m=json.loads(meta.read_text());report={**m,'render_target':'RGBA8' if RGBA else 'RGB8','graphics_api':'OpenGL' if OPENGL else 'Software','passed':not memory_errors and all(c['passed'] for c in cases),'cases':cases,'unmapped_accesses':len(memory_errors),
        'hardware_tested':False,'cpu_baseline_modified':False,'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-start,3)}
    report['capture_control_passed']=not memory_errors and cases[0]['passed'] and cases[8]['passed']
    report['text_comparison_valid']=report['capture_control_passed']
    if not report['text_comparison_valid']:report['limitation']='Control framebuffer is incorrect; text differences cannot identify a backend UV/filter defect.'
    if gl:report['opengl_capture']=gl.info
    (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    assert report['passed'],'Sampling differs; inspect saved case diagnostics'
if __name__=='__main__':main()
