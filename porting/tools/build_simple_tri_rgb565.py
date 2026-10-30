"""Isolate RGB8 -> RGB565 in the hardware-working official simple_tri CIA.

Preserve SYNCDRAW, draw, SDK and queue handlers. No diagnostic runtime hooks.
"""
import difflib,json,shutil,struct,subprocess
from pathlib import Path
import build_official_simple_tri as stock
import build_stage1 as b
P=stock.P
A=P/'analysis/simple-tri-rgb565'
D=P/'3ds/build-simple-tri-rgb565'
TITLE='000400000FDE6B00'
VERSION='0.1.0'
sha=stock.sha

def main():
    A.mkdir(parents=True,exist_ok=True);D.mkdir(parents=True,exist_ok=True)
    reference=json.loads((stock.D/'build-manifest.json').read_text())
    for key,root in [('inputs_sha256',P),('outputs_sha256',stock.D)]:
        for name,h in reference[key].items():assert sha(root/name)==h,name
    # Capture current old evidence, including the already successful stock CIA.
    if not (A/'preservation.json').exists():
        paths=set(json.loads((stock.A/'preservation.json').read_text())['before'])
        for base in [stock.D,stock.A,P/'dist/official-simple-tri-v0.1.0']:
            paths.update(q.relative_to(P).as_posix() for q in base.rglob('*') if q.is_file())
        paths.update(['dist/official-simple-tri-v0.1.0.zip',
            'analysis/hardware/official-simple-tri-v0.1.0-user-result.json',
            'analysis/hardware/official-simple-tri-profile-cia-v0.1.0-user-result.json'])
        (A/'preservation.json').write_text(json.dumps({'before':{n:sha(P/n) for n in sorted(paths)}},indent=2)+'\n')
    upstream=stock.A/'upstream/graphics/gpu/simple_tri/source/main.c'
    original=upstream.read_text()
    edits=[('#define CLEAR_COLOR 0x68B0D8FF','#define CLEAR_COLOR 0x0068B0D8'),
        ('GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGBA8) | GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB8)',
         'GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGB8) | GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB565)'),
        ('\tgfxInitDefault();','\tgfxInitDefault();\n\tgfxSetScreenFormat(GFX_TOP, GSP_RGB565_OES);'),
        ('C3D_RenderTargetCreate(240, 400, GPU_RB_RGBA8, GPU_RB_DEPTH24_STENCIL8)',
         'C3D_RenderTargetCreate(240, 400, GPU_RB_RGB8, GPU_RB_DEPTH24_STENCIL8)')]
    modified=original
    for before,after in edits:
        assert modified.count(before)==1,before
        modified=modified.replace(before,after)
    # Invert the exact whitelist: any other source difference must fail build.
    restored=modified
    for before,after in reversed(edits):restored=restored.replace(after,before)
    assert restored==original
    source=D/'main.c';source.write_text(modified)
    diff=''.join(difflib.unified_diff(original.splitlines(True),modified.splitlines(True),
        fromfile='hardware-working-stock/main.c',tofile='rgb565-only/main.c'))
    (A/'source.diff').write_text(diff)
    commands=[]
    def run(*cmd):
        commands.append(list(map(str,cmd)))
        subprocess.run(list(map(str,cmd)),check=True,cwd=D)
    # Reuse the exact shader object and binary: no shader rebuild or code change.
    for name in ['vshader_shbin.h','vshader.shbin.o','vshader.shbin']:
        shutil.copyfile(stock.D/name,D/name)
    flags=reference['compiler_flags']
    includes=['-I'+str(x) for x in [stock.LIB/'include',b.DKP/'libctru/include',D]]
    run(b.GCC,*flags,*includes,'-c',source,'-o','main.o')
    run(b.GCC,'-specs=3dsx.specs','-g',*b.ARCH,'-Wl,-Map,triangle.map',
        'vshader.shbin.o','main.o','-L'+str(stock.LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),
        '-lcitro3d','-lctru','-lm','-o','triangle.elf')
    # Separate application identity avoids replacing either working stock build.
    run(b.DKP/'tools/bin/smdhtool.exe','--create','tri RGB565 v0.1.0','Format-only Citro3D control',
        'Homebrew port research',b.DKP/'libctru/default_icon.png','triangle.smdh')
    stock_rsf=(stock.D/'simple_tri.rsf').read_text()
    rsf=stock_rsf.replace('SIMPLE-TRI','TRI-RGB565').replace('CTR-H-C3DT','CTR-H-C3DF').replace('0xFDE6A','0xFDE6B')
    (D/'triangle.rsf').write_text(rsf)
    assert rsf[rsf.index('AccessControlInfo:'):]==stock_rsf[stock_rsf.index('AccessControlInfo:'):]
    run(P/'toolchain/extras/makerom/makerom.exe','-f','cia','-o','simple-tri-rgb565.cia','-rsf','triangle.rsf',
        '-target','t','-exefslogo','-elf','triangle.elf','-icon','triangle.smdh','-banner',stock.D/'simple_tri.bnr','-ver','1')
    current=stock.payload((D/'simple-tri-rgb565.cia').read_bytes())
    previous=stock.payload((stock.D/'simple_tri-profile.cia').read_bytes())
    assert current[0x408:0x600]==previous[0x408:0x600],'CIA capabilities changed'
    assert current[0x20d:0x210]==previous[0x20d:0x210],'System-control flags changed'
    assert current[0x21c:0x220]==previous[0x21c:0x220],'Stack size changed'
    assert struct.unpack_from('<Q',current,0x108)[0]==int(TITLE,16)
    (D/'cia-payload.cxi').write_bytes(current)
    inputs=[Path(__file__).resolve(),source,upstream,D/'triangle.rsf',stock.D/'simple_tri.bnr',
        stock.D/'vshader.shbin.o',stock.LIB/'lib/libcitro3d.a',b.DKP/'libctru/lib/libctru.a',b.GCC]
    report={'version':VERSION,'title_id':TITLE,'title_version':1,'hardware_tested':False,'hardware_run_authorized':False,
        'hypothesis':'Does the RGB8 render target / RGB565 LCD / 0x2100 display transfer combination reproduce the native failure?',
        'source_whitelist_verified':True,'source_edits':edits,'clear_color_repacked_to_preserve_RGB':True,
        'unchanged_shader_object':sha(D/'vshader.shbin.o')==sha(stock.D/'vshader.shbin.o'),
        'unchanged_SDK_compiler_flags_and_CIA_capabilities_except_identity':True,
        'unchanged_SYNCDRAW_draw_FrameEnd_and_handlers':True,'runtime_instrumentation':False,'DS34_linked':False,
        'render_target':'240x400 RGB8 / D24S8','TOP_format':'RGB565','transfer_flags':0x2100,
        'color_bytes':288000,'depth_bytes':384000,'fill_controls':[0x101,0x201],
        'gfx_allocation':'gfxInitDefault retains original TOP allocation; RGB565 switch does not shrink/reallocate it',
        'CIA_profile':reference['CIA_profile'],'stock_ELF_sha256':sha(stock.D/'simple_tri.elf'),
        'compiler_flags':flags,'commands':commands,'inputs_sha256':{x.relative_to(P).as_posix():sha(x) for x in inputs},
        'outputs_sha256':{n:sha(D/n) for n in ['triangle.elf','simple-tri-rgb565.cia','cia-payload.cxi','vshader.shbin']}}
    (D/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(diff)
    print('Built format-only CIA:',D/'simple-tri-rgb565.cia')
if __name__=='__main__':main()
