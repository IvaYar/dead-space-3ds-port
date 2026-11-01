"""Isolated target-initialization hypothesis. Does not edit any GPU baseline."""
import argparse
import difflib
import json
import shutil
import subprocess
from pathlib import Path
from build_native_startup_legacy import payload,sha

P=Path(__file__).resolve().parents[1]
BASE=P/'3ds/build-native-game-v0.1.0-p124p'
A=P/'analysis/native-game-target-init-v0.1.1'
RUNTIME=['ds7_threads_probe.c','ds7_platform_probe.c','ds6_time_probe.c','ds8_cpp_probe.c','ds34_gpu_native.c','ds34_shader.h','ds34.shbin']

HOOK=r'''
C3D_RenderTarget *__real_C3D_RenderTargetCreate(int,int,GPU_COLORBUF,C3D_DEPTHTYPE);
C3D_RenderTarget *__wrap_C3D_RenderTargetCreate(int width,int height,GPU_COLORBUF color,C3D_DEPTHTYPE depth){
    C3D_RenderTarget *target=__real_C3D_RenderTargetCreate(width,height,color,depth);
    if(!target)return NULL;
    if(color!=GPU_RB_RGBA8 || width!=240 || height!=400)fatal("unexpected target format for initialization");
    u32 bytes=C3D_CalcColorBufSize(width,height,color);
    report("TARGET INIT color=%08lx bytes=%lu before original draw\n",(unsigned long)TARGET_INITIAL_RGBA,(unsigned long)bytes);
    /* GPU MemoryFill, not a CPU write to read-only VRAM; complete before use.
     * Initialize COLOR ONLY once. No game pixels or shader state supplied. */
    C3D_SyncMemoryFill(target->frameBuf.colorBuf,TARGET_INITIAL_RGBA,
        (u32 *)((u8 *)target->frameBuf.colorBuf+bytes),0x0201,NULL,0,NULL,0);
    return target;
}
'''

MISS=r'''
    if(current_frame>MAX_CALLBACKS){
        char missed[192];path(missed,"comparison-miss.raw");
        GSPGPU_InvalidateDataCache(graphics.pixels,BYTES);
        FILE *dump=fopen(missed,"wb");if(dump){fwrite(graphics.pixels,1,BYTES,dump);fclose(dump);}
        report("FULL FRAME CRC GATE NOT REACHED after %lu original callbacks\n",(unsigned long)MAX_CALLBACKS);
        return -1;
    }
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=['poison','black'],required=True)
    parser.add_argument('--cia',action='store_true');args=parser.parse_args()
    d=P/('3ds/build-native-game-v0.1.1-'+args.variant)
    if args.cia:
        assert args.variant=='black'
        proof=P/'analysis/azahar-native-game-v0.1.1-black-cxi/result.json'
        r=json.loads(proof.read_text());assert r['passed'] and r['sequential_cycles']>=3 and r['safe_exit']
        assert r['CXI_sha256']==sha(d/'native-game.cxi') and not (d/'native-game.cia').exists()
        subprocess.run(makerom('cia',d),cwd=d,check=True)
        raw=payload((d/'native-game.cia').read_bytes());assert raw==(d/'native-game.cxi').read_bytes()
        (d/'cia-payload.cxi').write_bytes(raw)
        (d/'cia-manifest.json').write_text(json.dumps({'title_id':'000400000FDE7400','CIA_sha256':sha(d/'native-game.cia'),'CIA_bytes':(d/'native-game.cia').stat().st_size,'payload_sha256':sha(d/'cia-payload.cxi'),'hardware_tested':False,'hardware_run_authorized':False},indent=2)+'\n')
        return
    assert not d.exists(),'Preserve existing evidence';d.mkdir();A.mkdir(exist_ok=True)
    if args.variant=='black':
        expected=json.loads((A/'poison-result.json').read_text());assert expected['unwritten_target_color_persists']
    old=json.loads((BASE/'build-manifest.json').read_text())
    for n,h in old['outputs_sha256'].items():assert sha(BASE/n)==h,n
    src=(BASE/'native-game-memory.c').read_text()
    before='free(quantized);if(current_frame>MAX_CALLBACKS)return -1;'
    assert src.count(before)==1
    text=src.replace(before,'free(quantized);'+MISS)
    assert text.count('static int graphics_setup(void){')==1
    text=text.replace('static int graphics_setup(void){',HOOK+'\nstatic int graphics_setup(void){')
    text=text.replace('ds-native-game-prod124-v0.1.0/','ds-native-game-v0.1.1/')
    text=text.replace('native-game-prod124-v010','native-game-init-v011').replace('DS Game Prod124 0.1.0','DS Game Init 0.1.1')
    color='0x7f11abffu' if args.variant=='poison' else '0x000000ffu'
    text='#define TARGET_INITIAL_RGBA '+color+'\n'+text
    (d/'native-game-memory.c').write_text(text)
    (d/'entry.diff').write_text(''.join(difflib.unified_diff(src.splitlines(True),text.splitlines(True),fromfile='Prod124 baseline',tofile=args.variant)))
    for n in RUNTIME+['native-game.bnr']:shutil.copyfile(BASE/n,d/n)
    rsf=(BASE/'native-game.rsf').read_text().replace('DS-GAME-P124','DS-GAME-INIT').replace('CTR-H-DG24','CTR-H-DGIN').replace('0xFDE73','0xFDE74')
    (d/'native-game.rsf').write_text(rsf)
    # Original compile command retained; add only the target-allocation wrapper.
    origin=P/'3ds/build-native-game-v0.1.0-p124g'
    m=json.loads((origin/'build-manifest.json').read_text())
    cmd=next(q for q in m['commands'] if q[0].endswith('arm-none-eabi-gcc.exe'))
    cmd=[q.replace(str(origin),str(d)) for q in cmd]
    cmd.insert(-2,'-Wl,--wrap=C3D_RenderTargetCreate')
    commands=[cmd];subprocess.run(cmd,cwd=d,check=True)
    cmd=[str(P/'toolchain/devkitpro/tools/bin/smdhtool.exe'),'--create','DS Game Init 0.1.1','Original frame; initial target clear','Dead Space port research',str(P/'toolchain/devkitpro/libctru/default_icon.png'),str(d/'native-game.smdh')]
    commands.append(cmd);subprocess.run(cmd,cwd=d,check=True)
    cmd=makerom('cxi',d);commands.append(cmd);subprocess.run(cmd,cwd=d,check=True)
    result={'variant':args.variant,'initial_RGBA':color,'only_behavior_difference_between_variants':'one initial target COLOR value','memory_MiB':{'normal':20,'linear':100,'arena':92},'depth_initialization_changed':False,'backend_and_shader_unchanged':True,'hardware_run_authorized':False,'CIA_created':False,'commands':commands,'inputs_sha256':{'baseline_entry':sha(BASE/'native-game-memory.c'),'builder':sha(Path(__file__).resolve())},'outputs_sha256':{n:sha(d/n) for n in ['native-game.elf','native-game.cxi','native-game-memory.c','native-game.rsf']}}
    (d/'build-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Built isolated',args.variant,'CXI. Existing GPU/shader/budget/shutdown preserved.')


def makerom(kind,d):
    return [str(P/'toolchain/extras/makerom/makerom.exe'),'-f',kind,'-o',str(d/('native-game.'+kind)),'-rsf',str(d/'native-game.rsf'),'-target','t','-exefslogo','-elf',str(d/'native-game.elf'),'-icon',str(d/'native-game.smdh'),'-banner',str(d/'native-game.bnr'),'-ver','1']


if __name__=='__main__':main()
