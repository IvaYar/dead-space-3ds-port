"""Build synthetic native New3DS GPU CIA/CXI, isolated from game builds."""
import argparse,ast,hashlib,json,subprocess,wave
from pathlib import Path
from PIL import Image,ImageDraw
import build_stage1 as b
VERSION='0.1.3'
P=b.PORTING;D=P/('3ds/build-gpu-hardware-v'+VERSION);LIB=P/'toolchain/citro3d'
TITLE='000400000FDE6800'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*args):subprocess.run(list(map(str,args)),check=True,cwd=D)
def main():
    global D
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fault-tests',action='store_true',help='Build separate emulator-only fault injection variant; never package it')
    args=parser.parse_args()
    if args.fault_tests:D=D.with_name(D.name+'-faults')
    D.mkdir(exist_ok=True);library=json.loads((LIB/'build-manifest.json').read_text());assert sha(LIB/'lib/libcitro3d.a')==library['library_sha256']
    tree=ast.parse((P/'tools/build_gpu_gles.py').read_text())
    names=next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='names' for t in n.targets))
    sources=[P/'3ds/source'/n for n in names]+[P/'tests/gpu_hardware_probe.c',P/'tests/gpu_hardware_diag.c',P/'tests/gpu_hardware_queue.c']
    assert all(p.name not in {'engine_azahar.c','ds_exec.c','ds_cache.s'} for p in sources)
    run(b.DKP/'tools/bin/picasso.exe','-o',D/'ds34.shbin',P/'3ds/source/ds34_gpu.v.pica')
    (D/'ds34_shader.h').write_text('static const unsigned char ds34_shader[] __attribute__((aligned(4)))={'+','.join(map(str,(D/'ds34.shbin').read_bytes()))+'};\n')
    run(b.GCC,*b.FLAGS,'-DGPU_TEST_VERSION="'+VERSION+'"','-DDS34_SEQUENCE_AUDIT','-DDS34_FRAME_DIAGNOSTICS',
        *(['-DDS34_DIAGNOSTIC_FAULTS'] if args.fault_tests else []),'-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',
        *['-I'+str(p) for p in (b.DKP/'libctru/include',LIB/'include',P/'3ds/include',D)],*sources,
        '-Wl,--wrap=gxCmdQueueRun,--wrap=gspSubmitGxCommand',
        '-L'+str(LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),'-lcitro3d','-lctru','-lm','-Wl,--gc-sections','-o',D/'ds34-gpu-test.elf')
    icon=Image.new('RGB',(48,48),(8,16,24));draw=ImageDraw.Draw(icon);draw.polygon([(24,4),(4,42),(44,42)],fill=(0,200,180));draw.text((15,23),'GPU',fill=(0,0,0));icon.save(D/'icon.png')
    banner=Image.new('RGB',(256,128),(8,16,24));draw=ImageDraw.Draw(banner);draw.text((38,36),'DS34 GPU TEST',fill=(0,220,200));draw.text((38,60),'SYNTHETIC DATA ONLY',fill=(230,230,230));banner.save(D/'banner.png')
    with wave.open(str(D/'silence.wav'),'wb') as w:w.setparams((1,2,22050,0,'NONE','not compressed'));w.writeframes(b'\0\0'*22050)
    run(b.DKP/'tools/bin/smdhtool.exe','--create','DS34 GPU Test','Synthetic GPU hardware diagnostics','Homebrew port research',D/'icon.png',D/'ds34-gpu-test.smdh')
    run(P/'toolchain/extras/bannertool/bannertool.exe','makebanner','-i',D/'banner.png','-a',D/'silence.wav','-o',D/'ds34-gpu-test.bnr')
    rsf=(P/'3ds/stage1.rsf').read_text().replace('DS-LOADER-TEST','DS34-GPU-TEST').replace('CTR-H-DSLT','CTR-H-DSHW').replace('0xFDE50','0xFDE68')
    # Standard libctru/GSP permissions only: no process RX/custom SVC backend.
    assert 'ControlProcessMemory:' not in rsf and 'FlushProcessDataCache:' not in rsf
    assert '1f000000-1f5fffff:r' in rsf # retain CPU read-only VRAM, do not widen permissions
    (D/'ds34-gpu-test.rsf').write_text(rsf)
    for fmt in ['cia','cxi']:
        run(P/'toolchain/extras/makerom/makerom.exe','-f',fmt,'-o',D/f'ds34-gpu-test.{fmt}','-rsf',D/'ds34-gpu-test.rsf','-target','t','-exefslogo',
            '-elf',D/'ds34-gpu-test.elf','-icon',D/'ds34-gpu-test.smdh','-banner',D/'ds34-gpu-test.bnr',*(['-ver','19'] if fmt=='cia' else []))
    inputs=sources+list((P/'3ds/include').glob('*.h'))+[P/'tests/gpu_hardware_diag.h',P/'3ds/source/ds34_gpu.v.pica',Path(__file__).resolve(),P/'tools/build_gpu_gles.py',P/'3ds/stage1.rsf',LIB/'lib/libcitro3d.a']
    inputs.extend([b.DKP/'libctru/lib/libctru.a',b.DKP/'libctru/include/3ds/gpu/gx.h',b.DKP/'libctru/include/3ds/services/gspgpu.h'])
    manifest={'version':VERSION,'title_id':TITLE,'native_capable':True,'hardware_tested':False,'game_called':False,'game_resources_included':False,'cia_produced':True,'new3ds_required':True,'start_requires_A':True,'cpu_vram_mapping':'read-only','inactive_texture_initialization':'blocking GPU transfer from linear staging outside frame',
        'scope':'Diagnostic synthetic DS34/GLES GPU tests; hardware hang cause still unknown; no original engine or RX backend',
        'sd_directory':'3ds/ds34-gpu-test-v'+VERSION,'phase_logging':True,'wait_timeout_ms':2000,
        'queue_observer':'linker wrappers: Run, SubmitGxCommand; original calls retained; aggregate completion counters only',
        'irq_observation_available':False,
        'first_frame_pica_capture':'CPU virtual ranges validated against linear heap and default command buffer size',
        'bounded_waits':['VBlank counters for both screens','GX queue via FrameBegin NONBLOCK'],
        'unbounded_operations_remaining':['initial white texture SDK transfer','GSP/SD calls','FrameEnd','Fini after idle check'],
        'fault_injection_compiled':args.fault_tests,'citro3d_commit':library['commit'],'sources_sha256':{str(p.relative_to(P)):sha(p) for p in inputs},
        'outputs_sha256':{n:sha(D/n) for n in ['ds34-gpu-test.elf','ds34-gpu-test.cia','ds34-gpu-test.cxi','ds34.shbin']}}
    (D/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Built native GPU fixture',D/'ds34-gpu-test.cia')
if __name__=='__main__':main()
