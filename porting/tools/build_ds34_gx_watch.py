"""Build separate one-frame DS34 RGBA8 observer. Never rebuild the old backend."""
import argparse
import ast
import json
import shutil
import struct
import subprocess

import build_ds34_rgba8 as prior

P = prior.P
A = P / 'analysis/ds34-gx-watch-v0.2.0'
D = P / '3ds/build-ds34-gx-watch-v0.2.0'
TITLE = '000400000FDE6E00'
sha = prior.sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fault', action='store_true', help='Separate emulator-only forced-timeout fixture; never distribute')
    args = parser.parse_args()
    dest = D.with_name(D.name + '-fault') if args.fault else D
    if (dest / 'build-manifest.json').exists():
        raise SystemExit(f'Refusing to overwrite a build: {dest}')
    old = json.loads((prior.D / 'build-manifest.json').read_text())
    for key, root in [('inputs_sha256', P), ('outputs_sha256', prior.D)]:
        for name, expected in old[key].items():
            assert sha(root / name) == expected, name
    dest.mkdir(parents=True, exist_ok=True)
    # Exact prior RGBA8/RGB8 renderer and compiled shader, unchanged.
    for name in ['ds34_gpu_rgba8_rgb8.c', 'ds34_shader.h', 'ds34.shbin']:
        shutil.copyfile(prior.D / name, dest / name)
        assert sha(dest / name) == sha(prior.D / name)
    tree = ast.parse((P / 'tools/build_gpu_gles.py').read_text())
    names = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets))
    sources = [P / '3ds/source' / n for n in names if n != 'ds34_gpu_3ds.c']
    sources += [dest / 'ds34_gpu_rgba8_rgb8.c'] + [P / 'tests' / n for n in
               ['gx_watch.c', 'gx_watch_save.c', 'ds34_gx_watch_probe.c']]
    flags = prior.b.FLAGS
    defines = ['-DDS34_CAPTURE_RGBA', '-DDS34_SEQUENCE_AUDIT', '-DDS34_FRAME_DIAGNOSTICS']
    if args.fault:
        defines.append('-DGX_WATCH_FAULT')
    wrappers = ['gxCmdQueueRun', 'gxCmdQueueClear', 'gspSubmitGxCommand',
                'fopen', 'fwrite', 'fprintf', 'fflush', 'fclose', 'fputs']
    commands = []

    def run(*cmd):
        commands.append(list(map(str, cmd)))
        subprocess.run(commands[-1], cwd=dest, check=True)

    b = prior.b
    stock = prior.stock
    includes = ['-I' + str(q) for q in [b.DKP / 'libctru/include', stock.LIB / 'include', P / '3ds/include', dest]]
    run(b.GCC, *flags, *defines, '-D__3DS__', '-mword-relocations', '-specs=3dsx.specs', '-Wl,-z,noexecstack',
        *includes, *sources, '-Wl,' + ','.join('--wrap=' + n for n in wrappers),
        '-L' + str(stock.LIB / 'lib'), '-L' + str(b.DKP / 'libctru/lib'), '-lcitro3d', '-lctru', '-lm',
        '-Wl,--gc-sections', '-o', dest / 'ds34-gx-watch.elf')
    run(b.DKP / 'tools/bin/smdhtool.exe', '--create', 'DS34 GX Watch 0.2.0',
        'One frame, passive GX completion watch', 'Homebrew port research', b.DKP / 'libctru/default_icon.png', dest / 'ds34-gx-watch.smdh')
    old_rsf = (stock.D / 'simple_tri.rsf').read_text()
    rsf = old_rsf.replace('SIMPLE-TRI', 'DS34-GX-WATCH').replace('CTR-H-C3DT', 'CTR-H-GXW2').replace('0xFDE6A', '0xFDE6E')
    assert rsf[rsf.index('AccessControlInfo:'):] == old_rsf[old_rsf.index('AccessControlInfo:'):]
    (dest / 'ds34-gx-watch.rsf').write_text(rsf)
    run(P / 'toolchain/extras/makerom/makerom.exe', '-f', 'cia', '-o', dest / 'ds34-gx-watch.cia',
        '-rsf', dest / 'ds34-gx-watch.rsf', '-target', 't', '-exefslogo', '-elf', dest / 'ds34-gx-watch.elf',
        '-icon', dest / 'ds34-gx-watch.smdh', '-banner', stock.D / 'simple_tri.bnr', '-ver', '1')
    payload = stock.payload((dest / 'ds34-gx-watch.cia').read_bytes())
    reference = stock.payload((prior.D / 'ds34-rgba8.cia').read_bytes())
    for start, end in [(0x408, 0x600), (0x20d, 0x210), (0x21c, 0x220)]:
        assert payload[start:end] == reference[start:end]
    assert struct.unpack_from('<Q', payload, 0x108)[0] == int(TITLE, 16)
    (dest / 'cia-payload.cxi').write_bytes(payload)
    inputs = sources + [P / 'tests/gx_watch.h', P / 'tools/build_ds34_gx_watch.py',
        P / 'tools/build_ds34_rgba8.py', prior.D / 'build-manifest.json', prior.D / 'ds34_gpu_rgba8_rgb8.c',
        dest / 'ds34_shader.h', dest / 'ds34-gx-watch.rsf', stock.LIB / 'lib/libcitro3d.a',
        b.DKP / 'libctru/lib/libctru.a', b.GCC, stock.D / 'simple_tri.bnr'] + list((P / '3ds/include').glob('*.h'))
    report = {'version': '0.2.0', 'title_id': TITLE, 'fault_build': args.fault, 'hardware_tested': False,
        'hardware_run_authorized': False, 'game_called': False, 'frames': 1,
        'unchanged_renderer_and_shader': True, 'renderer_sha256': sha(dest / 'ds34_gpu_rgba8_rgb8.c'),
        'RGBA8_RGB8_flags': 0x1000, 'layout': 1, 'capture_bytes': 288000,
        'GPU_IRQ_VBlank_queue_handlers_preserved': True,
        'public_event_observers': ['PSC0', 'P3D', 'PPF', 'PSC1 auxiliary', 'DMA auxiliary'],
        'SDK_wait_semantics_changed_only_for_diagnostics': True, 'NONBLOCK_is_not_GPU_fix': True,
        'window_ms': 2000, 'no_SD_in_window': True, 'stdio_guard_wrappers': wrappers[3:],
        'sd_root': '3ds/ds34-gx-watch-v0.2.0/run-NNNN', 'old_logs_overwritten': False,
        'wrappers': wrappers, 'compiler_flags': flags, 'defines': defines, 'commands': commands,
        'inputs_sha256': {q.relative_to(P).as_posix(): sha(q) for q in inputs},
        'outputs_sha256': {n: sha(dest / n) for n in ['ds34-gx-watch.elf', 'ds34-gx-watch.cia', 'cia-payload.cxi', 'ds34.shbin']}}
    (dest / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Built separate GX observer:', dest / 'ds34-gx-watch.cia')


if __name__ == '__main__':
    main()
