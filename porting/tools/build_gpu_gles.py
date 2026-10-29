"""Build the isolated GLES-to-PICA fixture without replacing CPU engine builds."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import build_stage1 as b
P=b.PORTING;D=P/'3ds/build-gpu-gles';LIB=P/'toolchain/citro3d'
def run(*args):subprocess.run(list(map(str,args)),check=True,cwd=D)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    global D
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group();mode.add_argument('--engine-memory',action='store_true');mode.add_argument('--sampling',action='store_true');parser.add_argument('--rgba-target',action='store_true');args=parser.parse_args()
    if args.rgba_target and not args.sampling:parser.error('--rgba-target requires --sampling; capture diagnostic only')
    if args.sampling:D=P/'3ds/build-gpu-sampling'
    if args.engine_memory:D=P/'3ds/build-gpu-gles-memory'
    if args.rgba_target:D=P/'3ds/build-gpu-sampling-rgba'
    D.mkdir(exist_ok=True);library=json.loads((LIB/'build-manifest.json').read_text())
    assert sha(LIB/'lib/libcitro3d.a')==library['library_sha256']
    run(b.DKP/'tools/bin/picasso.exe','-o',D/'ds34.shbin',P/'3ds/source/ds34_gpu.v.pica')
    blob=(D/'ds34.shbin').read_bytes()
    (D/'ds34_shader.h').write_text('static const unsigned char ds34_shader[] __attribute__((aligned(4)))={'+','.join(map(str,blob))+'};\n')
    names=('ds_elf.c','ds_io.c','ds_runtime_libc.c','ds13_gles.c','ds14_arrays.c','ds15_textures.c','ds16_pipeline.c','ds21_matrices.c','ds22_draw.c','ds26_framebuffer.c','ds30_fog.c','ds31_combine.c','ds32_lighting.c','ds33_surface.c','ds34_gpu_3ds.c')
    sources=[P/'3ds/source'/n for n in names]+[P/('tests/gpu_sampling_probe.c' if args.sampling else 'tests/gpu_gles_probe.c')]
    run(b.GCC,*b.FLAGS,*(['-DDS_GPU_ENGINE_MEMORY'] if args.engine_memory else []),*(['-DDS34_CAPTURE_RGBA'] if args.rgba_target else []),'-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',
        '-I'+str(b.DKP/'libctru/include'),'-I'+str(LIB/'include'),'-I'+str(P/'3ds/include'),'-I'+str(D),*sources,
        '-L'+str(LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),'-lcitro3d','-lctru','-lm','-Wl,--gc-sections','-o',D/'gpu-gles.elf')
    run(b.DKP/'tools/bin/smdhtool.exe','--create','DS GPU GLES','GLES GPU fixture; no game','Homebrew research',P/'3ds/build-stage8/icon.png',D/'gpu-gles.smdh')
    rsf=(P/'3ds/build-stage8/stage8.rsf').read_text().replace('0xFDE57','0xFDE65').replace('TST8','GLES').replace('DSL8','DSGG')
    if args.engine_memory:rsf=rsf.replace('SystemModeExt: Legacy','SystemModeExt: 178MB').replace('ReleaseKernelMinor: "33"','ReleaseKernelMinor: "44"')
    (D/'gpu-gles.rsf').write_text(rsf)
    run(P/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',D/'gpu-gles.cxi','-rsf',D/'gpu-gles.rsf','-target','t','-exefslogo',
        '-elf',D/'gpu-gles.elf','-icon',D/'gpu-gles.smdh','-banner',P/'3ds/build-stage8/stage8.bnr')
    inputs=sources+list((P/'3ds/include').glob('*.h'))+[P/'3ds/source/ds34_gpu.v.pica',Path(__file__).resolve(),LIB/'lib/libcitro3d.a',LIB/'build-manifest.json']
    manifest={'emulator_only':True,'rgba_target':args.rgba_target,'sampling':args.sampling,'engine_memory':args.engine_memory,'game_called':False,'cia_produced':False,'title_id':'000400000FDE6500','citro3d_commit':library['commit'],
        'sources_sha256':{str(p.relative_to(P)):sha(p) for p in inputs},'outputs_sha256':{n:sha(D/n) for n in ('gpu-gles.elf','gpu-gles.cxi','ds34.shbin')}}
    (D/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Built GPU GLES fixture',manifest['outputs_sha256']['gpu-gles.cxi'])
if __name__=='__main__':main()
