"""One output-format experiment from the failed RGB8->RGB565 stock variant.

No old build is regenerated; no hardware is run. Keep source/fill/draw unchanged.
"""
import difflib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import build_simple_tri_rgb565 as previous

P = previous.P
D = P / '3ds/build-simple-tri-rgb8'
A = P / 'analysis/simple-tri-rgb8'
TITLE = '000400000FDE6C00'
sha = previous.sha
EDITS = [
    ('GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB565)',
     'GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB8)'),
    ('\tgfxSetScreenFormat(GFX_TOP, GSP_RGB565_OES);\n', ''),
]


def main():
    # Refuse to silently replace evidence from an earlier run.
    if D.exists():
        raise SystemExit(f'Build directory already exists: {D}')
    reference = json.loads((previous.D / 'build-manifest.json').read_text())
    for key, root in [('inputs_sha256', P), ('outputs_sha256', previous.D)]:
        for name, expected in reference[key].items():
            assert sha(root / name) == expected, name
    original = (previous.D / 'main.c').read_text()
    modified = original
    for before, after in EDITS:
        assert modified.count(before) == 1, before
        modified = modified.replace(before, after)
    # Exact forward reconstruction also checks the deletion of the LCD switch.
    assert modified == original.replace(EDITS[0][0], EDITS[0][1]).replace(EDITS[1][0], '')
    D.mkdir(parents=True)
    A.mkdir(parents=True, exist_ok=True)
    source = D / 'main.c'
    source.write_text(modified)
    (A / 'source.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), modified.splitlines(True),
        fromfile='failed-rgb8-to-rgb565/main.c', tofile='rgb8-to-rgb8/main.c')))
    for name in ['vshader_shbin.h', 'vshader.shbin.o', 'vshader.shbin']:
        assert sha(previous.D / name) == sha(previous.stock.D / name), name
        shutil.copyfile(previous.D / name, D / name)
    commands = []

    def run(*cmd):
        commands.append(list(map(str, cmd)))
        subprocess.run(commands[-1], check=True, cwd=D)

    b = previous.b
    stock = previous.stock
    flags = reference['compiler_flags']
    includes = ['-I' + str(x) for x in [stock.LIB / 'include', b.DKP / 'libctru/include', D]]
    run(b.GCC, *flags, *includes, '-c', source, '-o', 'main.o')
    run(b.GCC, '-specs=3dsx.specs', '-g', *b.ARCH, '-Wl,-Map,triangle.map',
        'vshader.shbin.o', 'main.o', '-L' + str(stock.LIB / 'lib'),
        '-L' + str(b.DKP / 'libctru/lib'), '-lcitro3d', '-lctru', '-lm', '-o', 'triangle.elf')
    run(b.DKP / 'tools/bin/smdhtool.exe', '--create', 'tri RGB8 v0.1.0',
        'RGB8 source / RGB8 output', 'Homebrew port research',
        b.DKP / 'libctru/default_icon.png', 'triangle.smdh')
    old_rsf = (previous.D / 'triangle.rsf').read_text()
    rsf = old_rsf.replace('TRI-RGB565', 'TRI-RGB8').replace('CTR-H-C3DF', 'CTR-H-C3DR').replace('0xFDE6B', '0xFDE6C')
    assert rsf[rsf.index('AccessControlInfo:'):] == old_rsf[old_rsf.index('AccessControlInfo:'):]
    (D / 'triangle.rsf').write_text(rsf)
    run(P / 'toolchain/extras/makerom/makerom.exe', '-f', 'cia', '-o', 'simple-tri-rgb8.cia',
        '-rsf', 'triangle.rsf', '-target', 't', '-exefslogo', '-elf', 'triangle.elf',
        '-icon', 'triangle.smdh', '-banner', stock.D / 'simple_tri.bnr', '-ver', '1')
    current = stock.payload((D / 'simple-tri-rgb8.cia').read_bytes())
    old = stock.payload((previous.D / 'simple-tri-rgb565.cia').read_bytes())
    for start, end in [(0x408, 0x600), (0x20d, 0x210), (0x21c, 0x220)]:
        assert current[start:end] == old[start:end]
    assert struct.unpack_from('<Q', current, 0x108)[0] == int(TITLE, 16)
    (D / 'cia-payload.cxi').write_bytes(current)
    inputs = [source, previous.D / 'main.c', previous.D / 'build-manifest.json',
              D / 'triangle.rsf', stock.D / 'simple_tri.bnr', previous.D / 'vshader.shbin.o',
              stock.LIB / 'lib/libcitro3d.a', b.DKP / 'libctru/lib/libctru.a', b.GCC,
              __file__]
    inputs = [Path(x).resolve() for x in inputs]
    report = {
        'title_id': TITLE, 'version': '0.1.0', 'hardware_tested': False,
        'hardware_run_authorized': False, 'source_edits': EDITS,
        'hypothesis': 'RGB8 source/fill works when output uses default RGB8 LCD instead of RGB565 plus TOP switch',
        'changed_logical_parameter': 'output format; two consistent source sites, not a one-line edit',
        'render_target': '240x400 RGB8 / D24S8', 'TOP_format': 'RGB8', 'transfer_flags': 0x1100,
        'color_bytes': 288000, 'depth_bytes': 384000, 'fill_controls': [0x101, 0x201],
        'unchanged_clear_color': '0x0068B0D8', 'unchanged_shader_object': True,
        'unchanged_SYNCDRAW_draw_FrameEnd_and_handlers': True, 'runtime_instrumentation': False,
        'CIA_capabilities_unchanged_except_identity': True, 'compiler_flags': flags, 'commands': commands,
        'inputs_sha256': {x.relative_to(P).as_posix(): sha(x) for x in inputs},
        'outputs_sha256': {n: sha(D / n) for n in ['triangle.elf', 'simple-tri-rgb8.cia', 'cia-payload.cxi', 'vshader.shbin']},
    }
    (D / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Built isolated RGB8->RGB8 CIA:', D / 'simple-tri-rgb8.cia')


if __name__ == '__main__':
    main()
