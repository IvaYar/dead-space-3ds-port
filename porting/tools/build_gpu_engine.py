"""Separate emulator engine variant: never overwrites the CPU baseline CXI."""
import ast,hashlib,json,subprocess
from pathlib import Path
import build_stage1 as b
P=b.PORTING;D=P/'3ds/build-gpu-engine';CPU=P/'3ds/build-emulator';LIB=P/'toolchain/citro3d'
def run(*args):subprocess.run(list(map(str,args)),check=True,cwd=D)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    D.mkdir(exist_ok=True);library=json.loads((LIB/'build-manifest.json').read_text());assert sha(LIB/'lib/libcitro3d.a')==library['library_sha256']
    # Share the existing source inventory, not generated or patched game code.
    tree=ast.parse((P/'tools/build_emulator_runtime.py').read_text())
    names=next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='names' for t in n.targets))
    extra=('ds_exec.c','ds_cache.s','ds6_platform_3ds.c','ds7_platform_3ds.c','ds11_platform_3ds.c','ds12_sensor_3ds.c','ds19_assets_3ds.c','ds20_dirs_3ds.c','ds24_files_3ds.c','ds25_assets_3ds.c','ds27_pages_3ds.c','ds34_gpu_3ds.c')
    sources=[P/'3ds/source'/n for n in (*names,*extra)]+[P/'tests'/n for n in ('engine_trap.s','engine_azahar.c','jni10_callbacks.c')]
    run(b.DKP/'tools/bin/picasso.exe','-o',D/'ds34.shbin',P/'3ds/source/ds34_gpu.v.pica')
    (D/'ds34_shader.h').write_text('static const unsigned char ds34_shader[] __attribute__((aligned(4)))={'+','.join(map(str,(D/'ds34.shbin').read_bytes()))+'};\n')
    includes=['-I'+str(p) for p in (D,P/'3ds/include',CPU,b.DKP/'libctru/include',LIB/'include')]
    run(b.GCC,*b.FLAGS,'-DDS_PICA_BACKEND','-DDS_NEW3DS_178','-DDS7_SEMAPHORE_COUNT=64',*includes,'-fno-builtin','-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',*sources,
        '-L'+str(LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),'-lcitro3d','-lctru','-lm','-Wl,--gc-sections','-o',D/'engine-gpu.elf')
    rsf=(CPU/'audit-178.rsf').read_text().replace('0xFDE5E','0xFDE66').replace('AUDT','GPUE').replace('DSEA','DSGE');(D/'engine-gpu.rsf').write_text(rsf)
    run(P/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',D/'engine-gpu.cxi','-rsf',D/'engine-gpu.rsf','-target','t','-exefslogo',
        '-elf',D/'engine-gpu.elf','-icon',CPU/'audit.smdh','-banner',P/'3ds/build-stage8/stage8.bnr')
    inputs=sources+list((P/'3ds/include').glob('*.h'))+list(CPU.glob('*.h'))+[Path(__file__).resolve(),P/'3ds/source/ds34_gpu.v.pica',LIB/'lib/libcitro3d.a']
    manifest={'emulator_only':True,'cia_produced':False,'hardware_tested':False,'title_id':'000400000FDE6600','citro3d_commit':library['commit'],
        'sources_sha256':{str(p.relative_to(P)):sha(p) for p in inputs},'outputs_sha256':{n:sha(D/n) for n in ('engine-gpu.elf','engine-gpu.cxi','ds34.shbin')}}
    (D/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Built isolated GPU engine',manifest['outputs_sha256']['engine-gpu.cxi'])
if __name__=='__main__':main()
