"""Build an independent stock-API Citro3D control, not a DS34 fix."""
import argparse,hashlib,json,struct,subprocess,wave
from pathlib import Path
from PIL import Image,ImageDraw
import build_stage1 as b
P=b.PORTING
LIB=P/'toolchain/citro3d'
VERSION='0.1.0'
TITLE='000400000FDE6900'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def payload(data):
    h,_,_,c,t,m,_,size=struct.unpack_from('<IHHIIIIQ',data)
    align=lambda n:(n+63)&~63
    off=align(h)+align(c)+align(t)+align(m)
    result=data[off:off+size];assert result[0x100:0x104]==b'NCCH';return result
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fault-test',action='store_true');args=parser.parse_args()
    d=P/('3ds/build-citro3d-control'+('-fault' if args.fault_test else ''));d.mkdir(exist_ok=True)
    reference=P/'3ds/build-gpu-hardware-v0.1.3'
    old=json.loads((reference/'build-manifest.json').read_text())
    old_hashes={n.replace('\\','/'):h for n,h in old['sources_sha256'].items()}
    for name in ['toolchain/citro3d/lib/libcitro3d.a','toolchain/devkitpro/libctru/lib/libctru.a']:
        assert sha(P/name)==old_hashes[name],name
    def run(*cmd):subprocess.run(list(map(str,cmd)),check=True,cwd=d)
    source=P/'tests/citro3d_control.c';shader=P/'tests/citro3d_control.v.pica'
    run(b.DKP/'tools/bin/picasso.exe','-o',d/'control.shbin',shader)
    (d/'control_shader.h').write_text('static const unsigned char control_shader[] __attribute__((aligned(4)))={'+','.join(map(str,(d/'control.shbin').read_bytes()))+'};\n')
    flags=b.FLAGS+['-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack','-Wl,--wrap=gxCmdQueueRun,--wrap=gspSubmitGxCommand']
    run(b.GCC,*flags,*(['-DCONTROL_FAULT_TEST'] if args.fault_test else []),
        *['-I'+str(x) for x in [b.DKP/'libctru/include',LIB/'include',d]],source,
        '-L'+str(LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),'-lcitro3d','-lctru','-lm','-Wl,--gc-sections','-o',d/'control.elf')
    image=Image.new('RGB',(48,48),(16,32,48));draw=ImageDraw.Draw(image);draw.polygon([(24,4),(6,42),(42,42)],fill='white');image.save(d/'icon.png')
    image=Image.new('RGB',(256,128),(16,32,48));ImageDraw.Draw(image).text((36,50),'CITRO3D CONTROL',fill='white');image.save(d/'banner.png')
    with wave.open(str(d/'silence.wav'),'wb') as w:w.setparams((1,2,22050,0,'NONE','not compressed'));w.writeframes(b'\0\0'*22050)
    run(b.DKP/'tools/bin/smdhtool.exe','--create','Citro3D Control','Independent clear and triangle diagnostics','Homebrew port research',d/'icon.png',d/'control.smdh')
    run(P/'toolchain/extras/bannertool/bannertool.exe','makebanner','-i',d/'banner.png','-a',d/'silence.wav','-o',d/'control.bnr')
    rsf=(P/'3ds/stage1.rsf').read_text().replace('DS-LOADER-TEST','CITRO3D-CONTROL').replace('CTR-H-DSLT','CTR-H-C3DC').replace('0xFDE50','0xFDE69')
    old_rsf=(reference/'ds34-gpu-test.rsf').read_text()
    assert rsf[rsf.index('AccessControlInfo:'):]==old_rsf[old_rsf.index('AccessControlInfo:'):]
    (d/'control.rsf').write_text(rsf)
    for kind in ['cia','cxi']:
        run(P/'toolchain/extras/makerom/makerom.exe','-f',kind,'-o',d/('control.'+kind),'-rsf',d/'control.rsf','-target','t','-exefslogo',
            '-elf',d/'control.elf','-icon',d/'control.smdh','-banner',d/'control.bnr',*(['-ver','1'] if kind=='cia' else []))
    current=payload((d/'control.cia').read_bytes());previous=payload((reference/'ds34-gpu-test.cia').read_bytes())
    # NCCH exheader starts at 0x200; ARM11 local/kernel/ARM9 caps at exheader
    # 0x200..0x400. Ignore only the program ID (first 8 bytes of local caps).
    same_caps=current[0x408:0x600]==previous[0x408:0x600];assert same_caps,'CIA capability/memory profile differs'
    inputs=[source,shader,Path(__file__).resolve(),P/'3ds/stage1.rsf',reference/'ds34-gpu-test.rsf',
        LIB/'lib/libcitro3d.a',b.DKP/'libctru/lib/libctru.a',b.GCC]
    report={'version':VERSION,'title_id':TITLE,'hardware_tested':False,'hardware_run_authorized':False,'ds34_linked':False,
        'game_resources_used':False,'fault_injection_compiled':args.fault_test,'sources':[source.relative_to(P).as_posix()],
        'compiler_flags':flags,'same_SDK_library_hashes':True,'same_RSF_access_and_system_control':True,'same_binary_capabilities_except_program_id':same_caps,
        'profile':'Legacy 64MB / application / CPU read-only VRAM / 256KiB stack',
        'render_target':'240x400 RGB8 / D24S8 / TOP RGB565, identical formats and transfer flags to DS34',
        'reference_example':'https://github.com/devkitPro/3ds-examples/tree/master/graphics/gpu/simple_tri',
        'adaptations':['RGB8/RGB565 to match DS34 rather than example RGBA8/RGB8','two finite phases: clear then triangle','A gate; bounded waits; diagnostics and CPU pixel reads'],
        'sdk_commit':old['citro3d_commit'],'inputs_sha256':{x.relative_to(P).as_posix():sha(x) for x in inputs},
        'outputs_sha256':{n:sha(d/n) for n in ['control.elf','control.cia','control.cxi','control.shbin']}}
    (d/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print('Independent control built:',d/'control.cia')
if __name__=='__main__':main()
