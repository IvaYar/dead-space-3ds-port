"""Build, validate and package the first development milestone, including local donor data."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PORTING = Path(__file__).resolve().parents[1]
DIST = PORTING / "dist/stage1"


def run(script, *args):
    subprocess.run([sys.executable, str(PORTING / script), *args], check=True, cwd=PORTING.parent)


def main():
    run("tools/build_stage1.py")
    run("tests/test_arm_loader.py")
    run("tools/verify_stage1.py")
    for format_ in ("3dsx", "cxi"):
        for case in ("missing", "wrong", "present"):
            run("tests/smoke_azahar.py", "--format", format_, "--case", case)
    shutil.copyfile(PORTING / "3ds/README.ru.md", DIST / "README.ru.md")
    validation = DIST / "validation"
    validation.mkdir(exist_ok=True)
    for filename in ("stage1-tests.json", "stage1-package-check.json"):
        shutil.copyfile(PORTING / "analysis" / filename, validation / filename)
    smoke = PORTING / "analysis/azahar-smoke"
    for path in smoke.iterdir():
        if path.name.startswith(("result-3dsx-", "result-cxi-", "stage1-3dsx-", "stage1-cxi-")):
            shutil.copyfile(path, validation / path.name)
    manifest_path = DIST / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validation"] = {"arm_core_tests": 14, "azahar_cases": 6, "cia_hashes_verified": True,
                              "game_code_executed": False, "hardware_tested": False}
    manifest["files"] = {}
    for path in sorted(DIST.rglob("*")):
        if path.is_file() and path != manifest_path:
            manifest["files"][path.relative_to(DIST).as_posix()] = {
                "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    output = PORTING / "dist/deadspace-3ds-stage1-local.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(DIST.rglob("*")):
            if path.is_file(): archive.write(path, path.relative_to(DIST).as_posix())
    print("Ready:", output)
    print("ZIP SHA256:", hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__": main()
