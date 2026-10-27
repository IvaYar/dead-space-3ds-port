"""Build, validate and package milestone 2 without replacing milestone 1 artifacts."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PORTING = Path(__file__).resolve().parents[1]
DIST = PORTING / "dist/stage2"


def run(script, *args):
    subprocess.run([sys.executable, str(PORTING / script), *args], check=True, cwd=PORTING.parent)


def main():
    run("tools/build_stage2.py")
    # Run the established core regression suite against the newly compiled core;
    # keep all original stage-1 binaries and their installed title unchanged.
    run("tests/test_stage2_regression.py")
    run("tests/test_stage2_loader.py")
    run("tests/test_exec_backend.py")
    run("tools/verify_stage1.py", "--stage", "2")
    for format_ in ("3dsx", "cxi"):
        for case in ("ready", "missing", "wrong", "present"):
            run("tests/smoke_azahar.py", "--stage", "2", "--format", format_, "--case", case)
    shutil.copyfile(PORTING / "3ds/README-stage2.ru.md", DIST / "README.ru.md")
    validation = DIST / "validation"; validation.mkdir(exist_ok=True)
    for filename in ("stage2-regression.json", "stage2-tests.json", "stage2-backend-tests.json", "stage2-package-check.json"):
        shutil.copyfile(PORTING / "analysis" / filename, validation / filename)
    for path in (PORTING / "analysis/azahar-smoke").iterdir():
        if path.name.startswith(("result-stage2-", "stage2-3dsx-", "stage2-cxi-")):
            shutil.copyfile(path, validation / path.name)
    manifest_path = DIST / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    backend_report = json.loads((PORTING / "analysis/stage2-backend-tests.json").read_text(encoding="utf-8"))
    manifest["validation"] = {"arm_regression_tests": 14, "arm_stage2_tests": 4,
                              "arm_native_backend_tests": backend_report["tests_run"], "azahar_cases": 8,
                              "cia_hashes_verified": True, "native_rx_and_cache_tested": False,
                              "native_backend_test_method": "ARM code and libctru wrappers with simulated kernel SVCs",
                              "game_entry_point_called": False}
    manifest["files"] = {}
    for path in sorted(DIST.rglob("*")):
        if path.is_file() and path != manifest_path:
            manifest["files"][path.relative_to(DIST).as_posix()] = {
                "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    archive_path = PORTING / f"dist/deadspace-3ds-stage2-v{manifest['version']}-local.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(DIST.rglob("*")):
            if path.is_file(): archive.write(path, path.relative_to(DIST).as_posix())
    with zipfile.ZipFile(archive_path) as archive: assert archive.testzip() is None
    shutil.copyfile(archive_path, PORTING / "dist/deadspace-3ds-stage2-local.zip")
    print("Stage 2 package:", archive_path, "bytes:", archive_path.stat().st_size)
    print("SHA256:", hashlib.sha256(archive_path.read_bytes()).hexdigest())


if __name__ == "__main__": main()
