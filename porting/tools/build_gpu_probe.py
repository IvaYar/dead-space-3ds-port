"""Build an isolated emulator GPU experiment; never replaces engine binaries."""
import hashlib,json,subprocess
from pathlib import Path
import build_stage1 as b
P=b.PORTING;D=P/'3ds/build-gpu-probe';LIB=P/'toolchain/citro3d'
def run(*args):subprocess.run(list(map(str,args)),check=True,cwd=D)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    D.mkdir(exist_ok=True);library=json.loads((LIB/'build-manifest.json').read_text())
    assert sha(LIB/'lib/libcitro3d.a')==library['library_sha256']
    run(b.DKP/'tools/bin/picasso.exe','-o',D/'gpu_probe.shbin',P/'tests/gpu_probe.v.pica')
    blob=(D/'gpu_probe.shbin').read_bytes()
    (D/'gpu_probe_shader.h').write_text('static const unsigned char gpu_probe_shader[] __attribute__((aligned(4)))={'+','.join(map(str,blob))+'};\n')
    run(b.GCC,*b.FLAGS,'-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',
        '-I'+str(b.DKP/'libctru/include'),'-I'+str(LIB/'include'),'-I'+str(D),P/'tests/gpu_probe.c',
        '-L'+str(LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),'-lcitro3d','-lctru','-lm','-Wl,--gc-sections','-o',D/'gpu-probe.elf')
    run(b.DKP/'tools/bin/smdhtool.exe','--create','DS PICA probe','GPU experiment; no game','Homebrew research',P/'3ds/build-stage8/icon.png',D/'gpu-probe.smdh')
    rsf=(P/'3ds/build-stage8/stage8.rsf').read_text().replace('0xFDE57','0xFDE63').replace('TST8','GPU0').replace('DSL8','DSGP')
    (D/'gpu-probe.rsf').write_text(rsf)
    run(P/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',D/'gpu-probe.cxi','-rsf',D/'gpu-probe.rsf','-target','t','-exefslogo',
        '-elf',D/'gpu-probe.elf','-icon',D/'gpu-probe.smdh','-banner',P/'3ds/build-stage8/stage8.bnr')
    inputs=[P/'tests/gpu_probe.c',P/'tests/gpu_probe.v.pica',Path(__file__).resolve(),LIB/'lib/libcitro3d.a',LIB/'build-manifest.json',P/'3ds/build-stage8/stage8.rsf']
    manifest={'emulator_only':True,'game_called':False,'cia_produced':False,'title_id':'000400000FDE6300',
        'citro3d_commit':library['commit'],'sources_sha256':{str(p.relative_to(P)):sha(p) for p in inputs},
        'outputs_sha256':{n:sha(D/n) for n in ('gpu-probe.elf','gpu-probe.cxi','gpu_probe.shbin')}}
    (D/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Built isolated PICA probe',manifest['outputs_sha256']['gpu-probe.cxi'])
if __name__=='__main__':main()
