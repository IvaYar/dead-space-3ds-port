"""Build unmodified devkitPro simple_tri, then wrap the SAME ELF in our CIA profile.

No runtime instrumentation, SDK wrappers, game code or hardware execution.
Native Python reproduces the pinned Makefile rules because GNU make is unavailable.
"""
import hashlib,json,struct,subprocess,urllib.request,wave
from pathlib import Path
from PIL import Image,ImageDraw
import build_stage1 as b

P=b.PORTING
COMMIT='be2001fee08cf8ec7d3366e095e83f6f75da8942'
A=P/'analysis/official-simple-tri'
D=P/'3ds/build-official-simple-tri'
LIB=P/'toolchain/citro3d'
TITLE='000400000FDE6A00'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def payload(data):
    h,_,_,c,t,m,_,size=struct.unpack_from('<IHHIIIIQ',data)
    align=lambda n:(n+63)&~63
    off=sum(map(align,[h,c,t,m]));result=data[off:off+size]
    assert result[0x100:0x104]==b'NCCH'
    return result

def main():
    A.mkdir(parents=True,exist_ok=True);D.mkdir(parents=True,exist_ok=True)
    files=['README.md','graphics/gpu/simple_tri/Makefile','graphics/gpu/simple_tri/source/main.c',
        'graphics/gpu/simple_tri/source/vshader.v.pica','graphics/gpu/immediate/source/main.c']
    ref={'repository':'https://github.com/devkitPro/3ds-examples','commit':COMMIT,'files':{}}
    for name in files:
        url=f'https://raw.githubusercontent.com/devkitPro/3ds-examples/{COMMIT}/{name}'
        dest=A/'upstream'/name
        if not dest.exists():
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(urllib.request.urlopen(url,timeout=30).read())
        ref['files'][name]={'url':url,'sha256':sha(dest)}
    if (A/'upstream.json').exists():assert ref==json.loads((A/'upstream.json').read_text())
    (A/'upstream.json').write_text(json.dumps(ref,indent=2)+'\n')
    source=A/'upstream/graphics/gpu/simple_tri/source/main.c'
    shader=source.with_name('vshader.v.pica')
    old=json.loads((P/'3ds/build-citro3d-control/build-manifest.json').read_text())
    for name in ['toolchain/citro3d/lib/libcitro3d.a','toolchain/devkitpro/libctru/lib/libctru.a']:
        assert sha(P/name)==old['inputs_sha256'][name]
    commands=[]
    def run(*cmd,**kwargs):
        commands.append(list(map(str,cmd)))
        return subprocess.run(list(map(str,cmd)),check=True,cwd=D,**kwargs)
    tools=b.DKP/'tools/bin'
    run(tools/'picasso.exe','-o','vshader.shbin',shader)
    asm=run(tools/'bin2s.exe','-a','4','-H','vshader_shbin.h','vshader.shbin',capture_output=True).stdout
    (D/'vshader.shbin.s').write_bytes(asm)
    # Exactly the upstream Makefile CFLAGS/ASFLAGS/LDFLAGS. The extra include/lib
    # directory selects our pinned Citro3D 1.7.1 rather than a different SDK copy.
    cflags=['-g','-Wall','-O2','-mword-relocations','-ffunction-sections',*b.ARCH,'-D__3DS__']
    includes=['-I'+str(x) for x in [LIB/'include',b.DKP/'libctru/include',D]]
    run(b.GCC,*cflags,*includes,'-c',source,'-o','main.o')
    run(b.GCC,'-x','assembler-with-cpp','-g',*b.ARCH,'-c','vshader.shbin.s','-o','vshader.shbin.o')
    run(b.GCC,'-specs=3dsx.specs','-g',*b.ARCH,'-Wl,-Map,simple_tri.map',
        'vshader.shbin.o','main.o','-L'+str(LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),
        '-lcitro3d','-lctru','-lm','-o','simple_tri.elf')
    icon=b.DKP/'libctru/default_icon.png'
    run(tools/'smdhtool.exe','--create','simple_tri','Built with devkitARM & libctru','Unspecified Author',icon,'simple_tri.smdh')
    run(tools/'3dsxtool.exe','simple_tri.elf','simple_tri.3dsx','--smdh=simple_tri.smdh')
    # Packaging only: retain the exact same linked ELF for CIA and 3DSX.
    image=Image.new('RGB',(256,128),(104,176,216))
    draw=ImageDraw.Draw(image);draw.polygon([(128,15),(75,95),(181,95)],fill='white')
    draw.text((45,108),'OFFICIAL SIMPLE_TRI',fill='black');image.save(D/'banner.png')
    with wave.open(str(D/'silence.wav'),'wb') as w:
        w.setparams((1,2,22050,0,'NONE','not compressed'));w.writeframes(b'\0\0'*22050)
    run(P/'toolchain/extras/bannertool/bannertool.exe','makebanner','-i','banner.png','-a','silence.wav','-o','simple_tri.bnr')
    rsf=(P/'3ds/stage1.rsf').read_text().replace('DS-LOADER-TEST','SIMPLE-TRI').replace('CTR-H-DSLT','CTR-H-C3DT').replace('0xFDE50','0xFDE6A')
    (D/'simple_tri.rsf').write_text(rsf)
    run(P/'toolchain/extras/makerom/makerom.exe','-f','cia','-o','simple_tri-profile.cia','-rsf','simple_tri.rsf',
        '-target','t','-exefslogo','-elf','simple_tri.elf','-icon','simple_tri.smdh','-banner','simple_tri.bnr','-ver','1')
    current=payload((D/'simple_tri-profile.cia').read_bytes())
    previous=payload((P/'3ds/build-citro3d-control/control.cia').read_bytes())
    assert current[0x408:0x600]==previous[0x408:0x600],'Changed capabilities'
    assert struct.unpack_from('<Q',current,0x108)[0]==int(TITLE,16)
    (D/'cia-payload.cxi').write_bytes(current)
    inputs=[Path(__file__).resolve(),source,shader,source.parent.parent/'Makefile',P/'3ds/stage1.rsf',
        LIB/'lib/libcitro3d.a',b.DKP/'libctru/lib/libctru.a',b.GCC,
        b.DKP/'devkitARM/3ds_rules',b.DKP/'devkitARM/base_tools',b.DKP/'devkitARM/arm-none-eabi/lib/3dsx.specs']
    report={'upstream_commit':COMMIT,'upstream_sources_unmodified':True,'runtime_instrumentation':False,
        'hardware_tested':False,'not_a_GPU_fix':True,'game_resources_used':False,'title_id':TITLE,'title_version':1,
        'same_ELF_for_3dsx_and_CIA':True,'same_SDK_as_failed_control':True,
        'same_CIA_capabilities_except_program_id':True,'CIA_profile':'Legacy64MB / stack256KiB / CPU VRAM read-only',
        'official_example_has_CIA_profile':False,'C3D_commit':old['sdk_commit'],'libctru_version':'2.7.0-1',
        'build_adaptations':['Native Python reproduces Makefile commands; GNU make unavailable',
            'Explicit separate include/library directory for pinned Citro3D 1.7.1',
            'Additional CIA wraps unchanged ELF with existing project profile and separate Title ID'],
        'compiler_flags':cflags,'commands':commands,'inputs_sha256':{x.relative_to(P).as_posix():sha(x) for x in inputs},
        'outputs_sha256':{n:sha(D/n) for n in ['simple_tri.elf','simple_tri.3dsx','simple_tri.smdh','simple_tri-profile.cia','cia-payload.cxi','vshader.shbin']}}
    (D/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Built unchanged official simple_tri: 3DSX + same-ELF CIA, Title ID',TITLE)
if __name__=='__main__':main()
