"""Build CLEAR-only public event observation; preserve the v0.1.0 packets."""
import argparse,hashlib,json,struct,subprocess,wave
from pathlib import Path
from PIL import Image,ImageDraw
import build_stage1 as b
P=b.PORTING
LIB=P/'toolchain/citro3d'
VERSION='0.1.1'
TITLE='000400000FDE6900'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def payload(data):
    h,_,_,c,t,m,_,size=struct.unpack_from('<IHHIIIIQ',data)
    align=lambda n:(n+63)&~63
    off=align(h)+align(c)+align(t)+align(m)
    result=data[off:off+size];assert result[0x100:0x104]==b'NCCH';return result
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fault-test',action='store_true');args=parser.parse_args()
    d=P/('3ds/build-citro3d-events'+('-fault' if args.fault_test else ''));d.mkdir(exist_ok=True)
    reference=P/'3ds/build-gpu-hardware-v0.1.3'
    old=json.loads((reference/'build-manifest.json').read_text())
    old_hashes={n.replace('\\','/'):h for n,h in old['sources_sha256'].items()}
    for name in ['toolchain/citro3d/lib/libcitro3d.a','toolchain/devkitpro/libctru/lib/libctru.a']:
        assert sha(P/name)==old_hashes[name],name
    def run(*cmd):subprocess.run(list(map(str,cmd)),check=True,cwd=d)
    source=P/'tests/citro3d_events.c';observer=P/'tests/citro3d_event_observer.c';header=P/'tests/citro3d_event_observer.h'
    flags=b.FLAGS+['-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack','-Wl,--wrap=gxCmdQueueRun,--wrap=gspSubmitGxCommand']
    run(b.GCC,*flags,*(['-DCLEAR_EVENTS_FAULT'] if args.fault_test else []),
        *['-I'+str(x) for x in [b.DKP/'libctru/include',LIB/'include',d]],source,observer,
        '-L'+str(LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),'-lcitro3d','-lctru','-lm','-Wl,--gc-sections','-o',d/'control.elf')
    image=Image.new('RGB',(48,48),(16,32,48));draw=ImageDraw.Draw(image);draw.polygon([(24,4),(6,42),(42,42)],fill='white');image.save(d/'icon.png')
    image=Image.new('RGB',(256,128),(16,32,48));ImageDraw.Draw(image).text((36,50),'CITRO3D CLEAR IRQ',fill='white');image.save(d/'banner.png')
    with wave.open(str(d/'silence.wav'),'wb') as w:w.setparams((1,2,22050,0,'NONE','not compressed'));w.writeframes(b'\0\0'*22050)
    run(b.DKP/'tools/bin/smdhtool.exe','--create','Citro3D CLEAR IRQ','Passive PSC0 PSC1 PPF observation','Homebrew port research',d/'icon.png',d/'control.smdh')
    run(P/'toolchain/extras/bannertool/bannertool.exe','makebanner','-i',d/'banner.png','-a',d/'silence.wav','-o',d/'control.bnr')
    rsf=(P/'3ds/stage1.rsf').read_text().replace('DS-LOADER-TEST','CITRO3D-CONTROL').replace('CTR-H-DSLT','CTR-H-C3DC').replace('0xFDE50','0xFDE69')
    old_rsf=(reference/'ds34-gpu-test.rsf').read_text()
    assert rsf[rsf.index('AccessControlInfo:'):]==old_rsf[old_rsf.index('AccessControlInfo:'):]
    (d/'control.rsf').write_text(rsf)
    for kind in ['cia','cxi']:
        run(P/'toolchain/extras/makerom/makerom.exe','-f',kind,'-o',d/('control.'+kind),'-rsf',d/'control.rsf','-target','t','-exefslogo',
            '-elf',d/'control.elf','-icon',d/'control.smdh','-banner',d/'control.bnr',*(['-ver','2'] if kind=='cia' else []))
    current=payload((d/'control.cia').read_bytes());previous=payload((reference/'ds34-gpu-test.cia').read_bytes())
    # NCCH exheader starts at 0x200; ARM11 local/kernel/ARM9 caps at exheader
    # 0x200..0x400. Ignore only the program ID (first 8 bytes of local caps).
    same_caps=current[0x408:0x600]==previous[0x408:0x600];assert same_caps,'CIA capability/memory profile differs'
    control_reference=payload((P/'3ds/build-citro3d-control/control.cia').read_bytes())
    assert current[0x400:0x600]==control_reference[0x400:0x600],'Control v0.1.0 capability profile differs'
    inputs=[source,observer,header,Path(__file__).resolve(),P/'3ds/stage1.rsf',reference/'ds34-gpu-test.rsf',
        LIB/'lib/libcitro3d.a',b.DKP/'libctru/lib/libctru.a',b.GCC]
    report={'version':VERSION,'title_id':TITLE,'hardware_tested':False,'hardware_run_authorized':False,'ds34_linked':False,
        'game_resources_used':False,'fault_injection_compiled':args.fault_test,'sources':[source.relative_to(P).as_posix(),observer.relative_to(P).as_posix()],
        'clear_only':True,'same_v0.1.0_binary_capabilities':True,'passive_event_slots':['PSC0','PSC1','PPF'],
        'callback_IO_allocation_waits':False,'SDK_handlers_replaced':False,'IRQ_linker_wrap':False,
        'compiler_flags':flags,'same_SDK_library_hashes':True,'same_RSF_access_and_system_control':True,'same_binary_capabilities_except_program_id':same_caps,
        'profile':'Legacy 64MB / application / CPU read-only VRAM / 256KiB stack',
        'render_target':'240x400 RGB8 / D24S8 / TOP RGB565, identical formats and transfer flags to DS34',
        'reference_example':'https://github.com/devkitPro/3ds-examples/tree/master/graphics/gpu/simple_tri',
        'adaptations':['RGB8/RGB565 to match DS34 rather than example RGBA8/RGB8','one CLEAR only; public PSC0 PSC1 PPF callbacks with no SDK handler replacement','A gate; bounded waits; diagnostics and CPU pixel reads'],
        'sdk_commit':old['citro3d_commit'],'inputs_sha256':{x.relative_to(P).as_posix():sha(x) for x in inputs},
        'outputs_sha256':{n:sha(d/n) for n in ['control.elf','control.cia','control.cxi']}}
    (d/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print('CLEAR event observer built:',d/'control.cia')
if __name__=='__main__':main()
