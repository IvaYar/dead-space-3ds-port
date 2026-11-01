"""One-factor DS34 experiment: fill all declared vertex shader output components.

Assemble the two-line shader variant, then replace its unique embedded SHBIN in
the preserved ELF. This keeps CPU instructions, resource addresses and observer
identical. No old build is regenerated; no hardware is accessed.
"""
import difflib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import build_ds34_gx_watch as prior
from audit_pica_outputs import shader

P = prior.P
D = P / '3ds/build-ds34-uv-mask-v0.2.1'
A = P / 'analysis/ds34-uv-mask-v0.2.1'
TITLE = '000400000FDE6F00'
sha = prior.sha
EDITS = [('mul uv0_out.xy,', 'mul uv0_out,'), ('mul uv1_out.xy,', 'mul uv1_out,')]


def main():
    if (D / 'build-manifest.json').exists():
        raise SystemExit(f'Refusing to overwrite evidence: {D}')
    old = json.loads((prior.D / 'build-manifest.json').read_text())
    assert not old['fault_build']
    for key, root in [('inputs_sha256', P), ('outputs_sha256', prior.D)]:
        for name, expected in old[key].items():
            assert sha(root / name) == expected, name
    D.mkdir(parents=True, exist_ok=True)
    A.mkdir(parents=True, exist_ok=True)
    source = (P / '3ds/source/ds34_gpu.v.pica').read_text()
    modified = source
    for before, after in EDITS:
        assert modified.count(before) == 1
        modified = modified.replace(before, after)
    (D / 'baseline.v.pica').write_text(source)
    (D / 'ds34_gpu.v.pica').write_text(modified)
    (A / 'shader.diff').write_text(''.join(difflib.unified_diff(
        source.splitlines(True), modified.splitlines(True),
        fromfile='preserved-ds34/shader', tofile='full-output-mask/shader')))
    commands = []

    def run(*cmd):
        commands.append(list(map(str, cmd)))
        subprocess.run(commands[-1], cwd=D, check=True)

    picasso = prior.prior.b.DKP / 'tools/bin/picasso.exe'
    run(picasso, '-o', D / 'baseline.shbin', D / 'baseline.v.pica')
    run(picasso, '-o', D / 'ds34.shbin', D / 'ds34_gpu.v.pica')
    baseline = (prior.D / 'ds34.shbin').read_bytes()
    assert (D / 'baseline.shbin').read_bytes() == baseline
    candidate = (D / 'ds34.shbin').read_bytes()
    assert len(candidate) == len(baseline) == 280
    delta = [i for i, (x, y) in enumerate(zip(baseline, candidate)) if x != y]
    assert delta == [0x7c, 0x84]
    assert [(baseline[i], candidate[i]) for i in delta] == [(0xac, 0xaf), (0xec, 0xef)]
    before, after = shader(baseline), shader(candidate)
    assert before['code_words'] == after['code_words']
    assert [o['missing'] for o in before['outputs']] == ['', '', 'zw', 'zw']
    assert after['all_declared_components_once']
    # Patch only data in a loaded ELF segment. Everything else, including DWARF,
    # CPU code, allocation sizes, literal strings and all observer code, is kept.
    elf = (prior.D / 'ds34-gx-watch.elf').read_bytes()
    assert elf.count(baseline) == 1
    offset = elf.index(baseline)
    phoff = struct.unpack_from('<I', elf, 28)[0]
    phsize, phnum = struct.unpack_from('<HH', elf, 42)
    segments = [struct.unpack_from('<8I', elf, phoff + i * phsize) for i in range(phnum)]
    loaded = [s for s in segments if s[0] == 1 and s[1] <= offset and offset + len(baseline) <= s[1] + s[4]]
    assert len(loaded) == 1
    patched = elf[:offset] + candidate + elf[offset + len(baseline):]
    assert [i for i, (x, y) in enumerate(zip(elf, patched)) if x != y] == [offset + i for i in delta]
    (D / 'ds34-uv-mask.elf').write_bytes(patched)
    stock = prior.prior.stock
    old_rsf = (prior.D / 'ds34-gx-watch.rsf').read_text()
    rsf = old_rsf.replace('DS34-GX-WATCH', 'DS34-UV-MASK').replace('CTR-H-GXW2', 'CTR-H-D3UM').replace('0xFDE6E', '0xFDE6F')
    assert rsf[rsf.index('AccessControlInfo:'):] == old_rsf[old_rsf.index('AccessControlInfo:'):]
    (D / 'ds34-uv-mask.rsf').write_text(rsf)
    run(prior.prior.b.DKP / 'tools/bin/smdhtool.exe', '--create', 'DS34 UV Mask 0.2.1',
        'One factor: full UV output writes', 'Homebrew port research',
        prior.prior.b.DKP / 'libctru/default_icon.png', D / 'ds34-uv-mask.smdh')
    run(P / 'toolchain/extras/makerom/makerom.exe', '-f', 'cia', '-o', D / 'ds34-uv-mask.cia',
        '-rsf', D / 'ds34-uv-mask.rsf', '-target', 't', '-exefslogo', '-elf', D / 'ds34-uv-mask.elf',
        '-icon', D / 'ds34-uv-mask.smdh', '-banner', stock.D / 'simple_tri.bnr', '-ver', '1')
    payload = stock.payload((D / 'ds34-uv-mask.cia').read_bytes())
    reference = stock.payload((prior.D / 'ds34-gx-watch.cia').read_bytes())
    for start, end in [(0x408, 0x600), (0x20d, 0x210), (0x21c, 0x220)]:
        assert payload[start:end] == reference[start:end]
    assert struct.unpack_from('<Q', payload, 0x108)[0] == int(TITLE, 16)
    (D / 'cia-payload.cxi').write_bytes(payload)
    inputs = [Path(__file__).resolve(), P / 'tools/audit_pica_outputs.py',
              P / '3ds/source/ds34_gpu.v.pica', prior.D / 'ds34.shbin',
              prior.D / 'ds34-gx-watch.elf', prior.D / 'build-manifest.json', picasso,
              P / 'toolchain/extras/makerom/makerom.exe']
    report = dict(version='0.2.1', title_id=TITLE, hardware_tested=False,
                  hardware_run_authorized=False, game_called=False,
                  source_edits=EDITS, baseline_shader=before, candidate_shader=after,
                  SHBIN_changed_byte_offsets=delta, ELF_changed_byte_offsets=[offset + i for i in delta],
                  embedded_SHBIN_ELF_offset=offset, embedded_SHBIN_virtual_address=loaded[0][2] + offset - loaded[0][1],
                  CPU_code_and_resource_addresses_identical=True, old_builds_regenerated=False,
                  shader_instruction_words_and_DVLE_identical=True,
                  reused_observer='GX Watch 0.2.0, unchanged ELF; same version strings and SD root; fresh run-NNNN',
                  commands=commands, inputs_sha256={q.relative_to(P).as_posix(): sha(q) for q in inputs},
                  outputs_sha256={n: sha(D / n) for n in ['ds34-uv-mask.elf', 'ds34-uv-mask.cia', 'cia-payload.cxi', 'ds34.shbin']})
    (D / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['title_id', 'SHBIN_changed_byte_offsets', 'ELF_changed_byte_offsets']}, indent=2))


if __name__ == '__main__':
    main()
