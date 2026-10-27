"""Download a workspace-local Windows devkitARM toolchain from official repositories.

Requires zstandard (pip install --target porting/toolchain/python zstandard).
No installer, registry changes, or system PATH changes are performed.
Package SHA-256 values are checked against the official HTTPS repository database.
"""

import concurrent.futures
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.request
import zipfile

BASE = Path(__file__).resolve().parents[1] / "toolchain"
sys.path.insert(0, str(BASE / "python"))
import zstandard

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://devkitpro.org/",
}
REPOS = {
    "libs": "https://pkg.devkitpro.org/packages/",
    "windows": "https://pkg.devkitpro.org/packages/windows/x86_64/",
}
PACKAGES = {
    "libs": ["devkitarm-newlib", "devkitarm-crtls", "devkitarm-rules", "libctru", "citro3d"],
    "windows": ["devkitarm-binutils", "devkitarm-gcc", "3dstools", "general-tools", "picasso"],
}
EXTRAS = [
    ("makerom", "https://github.com/3DSGuy/Project_CTR/releases/download/makerom-v0.19.0/makerom-v0.19.0-win_x86_64.zip",
     "88df4455e60556374e202d507f54ee03fac7493ec9554ab853157524b6d69db0"),
    ("ctrtool", "https://github.com/3DSGuy/Project_CTR/releases/download/ctrtool-v1.3.0/ctrtool-v1.3.0-win_x64.zip",
     "8031dff3be72d0adb250fae1f969f27627e12a89ebc6dd074a15a75f87ddc949"),
    ("bannertool", "https://github.com/carstene1ns/3ds-bannertool/releases/download/1.2.3/bannertool-1.2.3-windows.zip",
     "d0f277bd875e2ad411844378155d27afe124780fcccbd81d9a594e886e2dd3c4"),
]


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as response:
        return response.read()


def database(repo):
    name = "dkp-libs.db" if repo == "libs" else "dkp-windows.db"
    raw = fetch(REPOS[repo] + name)
    (BASE / "cache" / name).write_bytes(raw)
    packages = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for entry in archive:
            if not entry.name.endswith("/desc"):
                continue
            blocks = archive.extractfile(entry).read().decode().strip().split("\n\n")
            desc = {block.splitlines()[0].strip("%"): block.splitlines()[1:] for block in blocks}
            packages[desc["NAME"][0]] = desc
    return packages


def install(item):
    repo, desc = item
    filename, expected = desc["FILENAME"][0], desc["SHA256SUM"][0]
    cached = BASE / "cache" / filename
    if not cached.exists() or hashlib.sha256(cached.read_bytes()).hexdigest() != expected:
        raw = fetch(REPOS[repo] + filename)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"SHA-256 mismatch: {filename}")
        cached.write_bytes(raw)
    print(f"Verified {filename}", flush=True)
    prefix = BASE / "devkitpro"
    links = []
    with cached.open("rb") as source, zstandard.ZstdDecompressor().stream_reader(source) as unpacked:
        with tarfile.open(fileobj=unpacked, mode="r|") as archive:
            for member in archive:
                path = Path(member.name)
                parts = path.parts
                if len(parts) < 3 or parts[:2] != ("opt", "devkitpro"):
                    continue
                target = prefix.joinpath(*parts[2:]).resolve()
                if not target.is_relative_to(prefix.resolve()):
                    raise ValueError(f"Unsafe archive path: {member.name}")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                elif member.issym() or member.islnk():
                    link = Path(member.linkname)
                    if member.islnk() or member.linkname.startswith("/opt/devkitpro/"):
                        normalized = member.linkname.lstrip("/")
                        if not normalized.startswith("opt/devkitpro/"):
                            raise ValueError(f"Unsupported link target: {member.linkname}")
                        link = prefix / normalized[len("opt/devkitpro/"):]
                    else:
                        link = target.parent / link
                    link = link.resolve()
                    if not link.is_relative_to(prefix.resolve()):
                        raise ValueError(f"Unsafe link: {member.name}")
                    links.append((str(target), str(link)))
                else:
                    raise ValueError(f"Unsupported archive member: {member.name}")
    return {"name": desc["NAME"][0], "version": desc["VERSION"][0],
            "url": REPOS[repo] + filename, "sha256": expected, "links": links}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-emulator", action="store_true", help="Also install the headless Azahar libretro test core")
    args = parser.parse_args()
    (BASE / "cache").mkdir(parents=True, exist_ok=True)
    selected = []
    for repo, names in PACKAGES.items():
        packages = database(repo)
        selected.extend((repo, packages[name]) for name in names)
    # Downloads can run together; extraction is sequential because packages share directories.
    def download(item):
        repo, desc = item
        path = BASE / "cache" / desc["FILENAME"][0]
        if not path.exists():
            raw = fetch(REPOS[repo] + path.name)
            if hashlib.sha256(raw).hexdigest() != desc["SHA256SUM"][0]:
                raise ValueError(path.name)
            path.write_bytes(raw)
        return item
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        items = list(pool.map(download, selected))
    manifest = [install(item) for item in items]
    links = [link for item in manifest for link in item.pop("links")]
    while links:
        pending = []
        for dest, source in links:
            if Path(source).is_file():
                Path(dest).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
            else:
                pending.append((dest, source))
        if len(pending) == len(links):
            raise ValueError(f"Unresolved package links: {pending}")
        links = pending
    (BASE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    extras = list(EXTRAS)
    if args.with_emulator:
        extras.append(("azahar-libretro", "https://github.com/azahar-emu/azahar/releases/download/2126.2/azahar-libretro-windows-x86_64-2126.2.zip",
                       "d863711cff775ed697ba0cc5a963f2145b9672c4ad9a891367821d7f3cc1f888"))
    records = []
    for name, url, expected in extras:
        cached = BASE / "cache" / (name + ".zip")
        if not cached.exists(): cached.write_bytes(fetch(url))
        raw = cached.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected: raise ValueError(f"SHA-256 mismatch: {name}")
        destination = BASE / "azahar-libretro" if name == "azahar-libretro" else BASE / "extras" / name
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                if not member.is_dir(): (destination / Path(member.filename).name).write_bytes(archive.read(member))
        records.append({"name": name, "url": url, "sha256": expected})
    (BASE / "extras-manifest.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print("Toolchain ready:", BASE / "devkitpro")


if __name__ == "__main__":
    main()
