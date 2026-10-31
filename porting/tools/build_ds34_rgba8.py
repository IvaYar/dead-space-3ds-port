"""Isolated DS34 RGBA8->RGB8 diagnostic. Never edit/rebuild an old backend/build."""
import ast
import difflib
import json
import struct
import subprocess

import build_stage1 as b
import build_official_simple_tri as stock

P = b.PORTING
D = P / '3ds/build-ds34-rgba8-v0.1.0'
A = P / 'analysis/ds34-rgba8-rgb8'
TITLE = '000400000FDE6D00'
sha = stock.sha
EDITS = [
    ('c->layout!=DS13_RGB565_CTR', 'c->layout!=DS13_BGR8_CTR || gfxGetScreenFormat(GFX_TOP)!=GSP_BGR8_OES'),
    ('GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB565)', 'GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB8)'),
    ('c->capacity=(uint32_t)w*h*2', 'c->capacity=(uint32_t)w*h*3'),
    ('/* RGB565 destination has implicit alpha one. */', '/* RGB8 LCD has implicit alpha one. */'),
]


def main():
    if D.exists():
        raise SystemExit(f'Refusing to overwrite existing build: {D}')
    # Match the SDK already used by hardware-successful stock simple_tri.
    stock_manifest = json.loads((stock.D / 'build-manifest.json').read_text())
    for name in ['toolchain/citro3d/lib/libcitro3d.a', 'toolchain/devkitpro/libctru/lib/libctru.a']:
        assert sha(P / name) == stock_manifest['inputs_sha256'][name], name
    original_path = P / '3ds/source/ds34_gpu_3ds.c'
    original = original_path.read_text()
    modified = original
    for before, after in EDITS:
        assert modified.count(before) == 1, before
        modified = modified.replace(before, after)
    D.mkdir(parents=True)
    A.mkdir(parents=True, exist_ok=True)
    overlay = D / 'ds34_gpu_rgba8_rgb8.c'
    overlay.write_text(modified)
    (A / 'backend.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), modified.splitlines(True),
        fromfile='baseline/ds34_gpu_3ds.c', tofile='isolated/ds34_gpu_rgba8_rgb8.c')))
    tree = ast.parse((P / 'tools/build_gpu_gles.py').read_text())
    names = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets))
    sources = [P / '3ds/source' / n for n in names if n != 'ds34_gpu_3ds.c']
    sources += [overlay, P / 'tests/ds34_rgba8_probe.c']
    commands = []

    def run(*args):
        commands.append(list(map(str, args)))
        subprocess.run(commands[-1], cwd=D, check=True)

    # Keep the exact DS34 shader object semantics, not the stock triangle shader.
    run(b.DKP / 'tools/bin/picasso.exe', '-o', D / 'ds34.shbin', P / '3ds/source/ds34_gpu.v.pica')
    blob = (D / 'ds34.shbin').read_bytes()
    (D / 'ds34_shader.h').write_text('static const unsigned char ds34_shader[] __attribute__((aligned(4)))={' + ','.join(map(str, blob)) + '};\n')
    defines = ['-DDS34_CAPTURE_RGBA', '-DDS34_SEQUENCE_AUDIT', '-DDS34_FRAME_DIAGNOSTICS']
    includes = ['-I' + str(q) for q in [b.DKP / 'libctru/include', stock.LIB / 'include', P / '3ds/include', D]]
    run(b.GCC, *b.FLAGS, *defines, '-D__3DS__', '-mword-relocations', '-specs=3dsx.specs', '-Wl,-z,noexecstack',
        *includes, *sources, '-Wl,--wrap=gxCmdQueueRun,--wrap=gxCmdQueueClear',
        '-L' + str(stock.LIB / 'lib'), '-L' + str(b.DKP / 'libctru/lib'),
        '-lcitro3d', '-lctru', '-lm', '-Wl,--gc-sections', '-o', D / 'ds34-rgba8.elf')
    run(b.DKP / 'tools/bin/smdhtool.exe', '--create', 'DS34 RGBA8 v0.1.0',
        'Synthetic DS34 draw and present', 'Homebrew port research', b.DKP / 'libctru/default_icon.png', D / 'ds34-rgba8.smdh')
    old_rsf = (stock.D / 'simple_tri.rsf').read_text()
    rsf = old_rsf.replace('SIMPLE-TRI', 'DS34-RGBA8').replace('CTR-H-C3DT', 'CTR-H-D3RA').replace('0xFDE6A', '0xFDE6D')
    assert rsf[rsf.index('AccessControlInfo:'):] == old_rsf[old_rsf.index('AccessControlInfo:'):]
    (D / 'ds34-rgba8.rsf').write_text(rsf)
    run(P / 'toolchain/extras/makerom/makerom.exe', '-f', 'cia', '-o', D / 'ds34-rgba8.cia',
        '-rsf', D / 'ds34-rgba8.rsf', '-target', 't', '-exefslogo', '-elf', D / 'ds34-rgba8.elf',
        '-icon', D / 'ds34-rgba8.smdh', '-banner', stock.D / 'simple_tri.bnr', '-ver', '1')
    payload = stock.payload((D / 'ds34-rgba8.cia').read_bytes())
    previous = stock.payload((stock.D / 'simple_tri-profile.cia').read_bytes())
    for start, end in [(0x408, 0x600), (0x20d, 0x210), (0x21c, 0x220)]:
        assert payload[start:end] == previous[start:end]
    assert struct.unpack_from('<Q', payload, 0x108)[0] == int(TITLE, 16)
    (D / 'cia-payload.cxi').write_bytes(payload)
    inputs = sources + [original_path, P / 'tools/build_ds34_rgba8.py', P / 'tools/build_gpu_gles.py',
        P / '3ds/source/ds34_gpu.v.pica', D / 'ds34_shader.h', D / 'ds34-rgba8.rsf',
        stock.LIB / 'lib/libcitro3d.a', b.DKP / 'libctru/lib/libctru.a', b.GCC,
        stock.D / 'simple_tri.bnr', stock.D / 'build-manifest.json'] + list((P / '3ds/include').glob('*.h'))
    manifest = {
        'version': '0.1.0', 'title_id': TITLE, 'hardware_tested': False, 'hardware_run_authorized': False,
        'native_capable': True, 'game_called': False, 'new3ds_required': True,
        'hypothesis': 'DS34 draw/present completes with stock hardware-successful RGBA8/32-bit fill -> RGB8 chain',
        'render_target': '240x400 GPU_RB_RGBA8 / D24S8', 'TOP_format': 'GSP_BGR8_OES',
        'context_layout': 1, 'capture_bytes': 288000, 'color_bytes': 384000, 'depth_bytes': 384000,
        'clear_word': '68b0d8ff', 'fill_controls': [0x201, 0x201], 'transfer_flags': 0x1000,
        'sd_directory': '3ds/ds34-rgba8-v0.1.0', 'frame_count': 9,
        'SDK_waits_unchanged': True, 'GPU_IRQ_callbacks_unchanged': True,
        'unbounded_operations': ['C3D_FrameBegin(SYNCDRAW)', 'C3D_FrameSync', 'white texture upload', 'GSP/SD/APT', 'C3D_FrameEnd', 'C3D_Fini'],
        'observer': 'Run/Clear linker wrappers; bounded atomic memory records only, main-thread SD persistence',
        'backend_source_unchanged': sha(original_path), 'backend_overlay_edits': EDITS,
        'compiler_flags': b.FLAGS, 'defines': defines, 'commands': commands,
        'inputs_sha256': {q.relative_to(P).as_posix(): sha(q) for q in inputs},
        'outputs_sha256': {n: sha(D / n) for n in ['ds34-rgba8.elf', 'ds34-rgba8.cia', 'cia-payload.cxi', 'ds34.shbin']},
    }
    (D / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Built isolated DS34 RGBA8->RGB8 CIA:', D / 'ds34-rgba8.cia')


if __name__ == '__main__':
    main()
