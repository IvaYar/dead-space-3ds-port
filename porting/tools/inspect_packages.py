"""Inspect donor APKs without executing their code. Uses Python standard library only."""

import argparse
import collections
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import zipfile


VITA_SHA1 = "0ed42b611415015807f759ec9b5457857143ce39"


def cstring(data, offset):
    end = data.find(b"\0", offset)
    return data[offset:end if end >= 0 else len(data)].decode("utf-8", "replace")


def inspect_elf(data):
    result = {
        "bytes": len(data),
        "sha1": hashlib.sha1(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    if data[:4] != b"\x7fELF":
        return {**result, "error": "Not an ELF file"}
    bits = {1: 32, 2: 64}[data[4]]
    result["bits"] = bits
    if data[5] != 1:
        return {**result, "error": "Only little-endian ELF is supported"}
    is32 = bits == 32
    header = struct.unpack_from("<16sHHIIIIIHHHHHH" if is32 else "<16sHHIQQQIHHHHHH", data)
    result["machine"] = {40: "ARM", 183: "AArch64"}.get(header[2], header[2])
    result["flags"] = hex(header[7])
    sections = [
        struct.unpack_from("<IIIIIIIIII" if is32 else "<IIQQQQIIQQ", data, header[6] + i * header[11])
        for i in range(header[12])
    ]
    name_section = sections[header[13]]
    section_names = data[name_section[4]:name_section[4] + name_section[5]]
    named = {cstring(section_names, s[0]): s for s in sections}
    result["needed"] = []
    if ".dynamic" in named:
        dynamic = named[".dynamic"]
        strings = sections[dynamic[6]]
        strings = data[strings[4]:strings[4] + strings[5]]
        for offset in range(dynamic[4], dynamic[4] + dynamic[5], dynamic[9]):
            tag, value = struct.unpack_from("<iI" if is32 else "<qQ", data, offset)
            if tag == 1:
                result["needed"].append(cstring(strings, value))
    imports, exports = [], []
    if ".dynsym" in named:
        symbols = named[".dynsym"]
        strings = sections[symbols[6]]
        strings = data[strings[4]:strings[4] + strings[5]]
        for offset in range(symbols[4], symbols[4] + symbols[5], symbols[9]):
            fields = struct.unpack_from("<IIIBBH" if is32 else "<IBBHQQ", data, offset)
            name, index = fields[0], fields[5] if is32 else fields[3]
            if name:
                (imports if index == 0 else exports).append(cstring(strings, name))
    result["imports"] = sorted(set(imports))
    result["import_count"] = len(result["imports"])
    result["graphics_imports"] = [n for n in result["imports"] if n.startswith(("gl", "egl"))]
    result["jni_exports"] = sorted(n for n in exports if n.startswith(("Java_", "JNI_")))
    if ".ARM.attributes" in named:
        attrs = named[".ARM.attributes"]
        result["arm_attributes_hex"] = data[attrs[4]:attrs[4] + attrs[5]].hex()
    result["matches_vita_donor_sha1"] = result["sha1"] == VITA_SHA1
    return result


def asset_summary(archive):
    entries = [e for e in archive.infolist() if not e.is_dir()]
    return {
        "files": len(entries),
        "uncompressed_bytes": sum(e.file_size for e in entries),
        "extensions": dict(collections.Counter(Path(e.filename).suffix.lower() for e in entries)),
        "largest_files": [{"path": e.filename, "bytes": e.file_size}
                          for e in sorted(entries, key=lambda e: e.file_size, reverse=True)[:10]],
    }


def inspect_apk(archive, label):
    result = {"package": label, **asset_summary(archive), "libraries": {}, "bundled_assets": {}}
    for entry in archive.infolist():
        if entry.filename.endswith(".so"):
            result["libraries"][entry.filename] = inspect_elf(archive.read(entry))
        elif entry.filename == "assets/bundled-game.zip":
            with zipfile.ZipFile(io.BytesIO(archive.read(entry))) as assets:
                result["bundled_assets"][entry.filename] = asset_summary(assets)
    return result


def extract_candidate(root, output):
    """Extract only the SD donor's original library and data, never an executable build."""
    target = output / "candidate-sd"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(root / "DeadSpace-1.1.33-Universal.zip") as outer:
        with zipfile.ZipFile(io.BytesIO(outer.read("DeadSpace-1.1.33-Universal-SD.apk"))) as apk:
            library = apk.read("lib/armeabi/libEAMGameDeadSpace_orig.so")
            library_path = target / "libEAMGameDeadSpace_orig.so"
            if library_path.exists() and library_path.read_bytes() != library:
                raise FileExistsError(f"Refusing to overwrite a different library: {library_path}")
            library_path.write_bytes(library)
            with zipfile.ZipFile(io.BytesIO(apk.read("assets/bundled-game.zip"))) as assets:
                base = (target / "assets").resolve()
                for entry in assets.infolist():
                    destination = (base / entry.filename).resolve()
                    if not destination.is_relative_to(base):
                        raise ValueError(f"Unsafe archive path: {entry.filename}")
                    if entry.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        # Do not overwrite previously extracted or modified donor files.
                        with assets.open(entry) as source, destination.open("xb") as dest:
                            shutil.copyfileobj(source, dest)
    return str(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--extract-candidate", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or root / "porting" / "analysis").resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "target": "New Nintendo 3DS family",
        "status": "Package inspection only; this report does not test or build the game runtime",
        "reference_vita_sha1": VITA_SHA1,
        "tools_on_path": {name: shutil.which(name) for name in
                          ("arm-none-eabi-gcc", "make", "cmake", "makerom", "bannertool", "ctrtool")},
        "devkit_environment": {name: os.environ.get(name) for name in ("DEVKITPRO", "DEVKITARM")},
        "input_archives": [],
        "packages": [],
    }
    for filename in ("Dead-Space-v1-2-0-rus.apk", "DeadSpace-1.1.33-Universal.zip"):
        path = root / filename
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        report["input_archives"].append({"name": filename, "bytes": path.stat().st_size, "sha256": digest})
        with zipfile.ZipFile(path) as archive:
            if path.suffix == ".apk":
                report["packages"].append(inspect_apk(archive, filename))
            else:
                for entry in archive.infolist():
                    if entry.filename.endswith(".apk"):
                        with zipfile.ZipFile(io.BytesIO(archive.read(entry))) as apk:
                            report["packages"].append(inspect_apk(apk, f"{filename}!/{entry.filename}"))
    if args.extract_candidate:
        report["extracted_candidate"] = extract_candidate(root, output)
    report_path = output / "packages.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Inspected {len(report['packages'])} APKs. Report: {report_path}")
    for package in report["packages"]:
        print(package["package"].split("!/")[-1])
        for name, library in package["libraries"].items():
            print(f"  {name}: {library['machine']} {library['bits']}-bit; "
                  f"{library.get('import_count', 0)} imports; SHA-1 {library['sha1']}; "
                  f"Vita donor match: {library.get('matches_vita_donor_sha1', False)}")


if __name__ == "__main__":
    main()
