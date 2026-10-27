"""Validate local homebrew packaging; Nintendo signature checks are expected to fail."""

import hashlib
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

PORTING = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=int, choices=(1, 2, 3, 4, 5, 6, 7, 8), default=1)
    args = parser.parse_args()
    stage = args.stage
    path = PORTING / f"dist/stage{stage}/deadspace-loader-stage{stage}.cia"
    data = path.read_bytes()
    header, kind, version, cert, ticket, tmd, footer, content = struct.unpack_from("<IHHIIIIQ", data)
    align = lambda value: (value + 63) & ~63
    offset = align(header) + align(cert) + align(ticket) + align(tmd)
    ncch = data[offset:offset + content]
    assert kind == 0 and version == 0 and header == 0x2020
    assert len(ncch) == content and ncch[0x100:0x104] == b"NCCH"
    title = 0x000400000FDE5000 + (stage - 1) * 0x100
    assert struct.unpack_from("<Q", ncch, 0x108)[0] == title
    assert struct.unpack_from("<I", ncch, 0x104)[0] * 0x200 == len(ncch)
    build_dir = "build" if stage == 1 else f"build-stage{stage}"
    (PORTING / f"3ds/{build_dir}/deadspace-loader-stage{stage}.cxi").write_bytes(ncch)
    process = subprocess.run([str(PORTING / "toolchain/extras/ctrtool/ctrtool.exe"), "--verify", str(path)],
                             capture_output=True, text=True)
    output = process.stdout + process.stderr
    errors = [line for line in output.splitlines() if " ERROR]" in line]
    expected = ("Signature for Ticket was invalid", "Signature for TitleMetaData was invalid",
                "Signature for AccessDescriptor was invalid")
    assert len(errors) == 3 and all(any(item in line for item in expected) for line in errors), errors
    hash_lines = [line.strip() for line in output.splitlines() if re.search(r"[Hh]ash.*\((?:GOOD|FAIL)\)", line)]
    assert len(hash_lines) >= 3 and all("(GOOD)" in line for line in hash_lines), hash_lines
    folder = "deadspace" if stage == 1 else f"deadspace{stage}"
    executable = PORTING / f"dist/stage{stage}/SD_CARD/3ds/{folder}/{folder}.3dsx"
    assert executable.read_bytes()[:4] == b"3DSX"
    result = {"cia_sha256": hashlib.sha256(data).hexdigest(), "title_id": f"{title:016X}",
              "hash_checks": hash_lines, "signature_status": "Homebrew test signatures; retail signatures not valid",
              "hardware_tested": False, "cia_bytes": len(data), "3dsx_bytes": executable.stat().st_size}
    if stage >= 2:
        elf_path = PORTING / f"3ds/{build_dir}/deadspace-loader-stage{stage}.elf"
        elf = elf_path.read_bytes()
        nm = subprocess.run([str(PORTING / "toolchain/devkitpro/devkitARM/bin/arm-none-eabi-nm.exe"),
                             "-g", "--defined-only", str(elf_path)], capture_output=True, text=True, check=True).stdout
        definitions = {parts[2]: int(parts[0], 16) for line in nm.splitlines()
                       if len(parts := line.split()) == 3}
        assert "ds_invalidate_instruction_cache" not in definitions
        address = definitions["ds_invalidate_entire_instruction_cache"]
        phoff = struct.unpack_from("<I", elf, 28)[0]
        phnum = struct.unpack_from("<H", elf, 44)[0]
        found = False
        for index in range(phnum):
            segment = struct.unpack_from("<8I", elf, phoff + index * 32)
            if segment[0] == 1 and segment[2] <= address and address + 16 <= segment[2] + segment[4]:
                instructions = struct.unpack_from("<4I", elf, segment[1] + address - segment[2])
                assert instructions == (0xe3a00000, 0xe3a01000, 0xef000094, 0xe12fff1e), instructions
                found = True
        assert found
        result["app_cache_wrapper_verified"] = "mov r0,0; mov r1,0; svc 0x94; bx lr"
        result["range_cache_wrapper_present"] = False
    (PORTING / f"analysis/stage{stage}-package-check.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
