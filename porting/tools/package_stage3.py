"""Build, validate and package the bounded JNI bootstrap as a separate title."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PORTING = Path(__file__).resolve().parents[1]
DIST = PORTING / "dist/stage3"


def run(script, *args):
    subprocess.run([sys.executable, str(PORTING / script), *args], check=True, cwd=PORTING.parent)


def main():
    run("tools/build_stage3.py")
    run("tests/test_stage3_regression.py")
    run("tests/test_stage3_jni.py")
    run("tools/verify_stage1.py", "--stage", "3")
    # Azahar cases share a local virtual SD card and must run sequentially.
    for format_ in ("3dsx", "cxi"):
        for case in ("ready", "missing", "wrong", "present"):
            run("tests/smoke_azahar.py", "--stage", "3", "--format", format_, "--case", case)
    shutil.copyfile(PORTING / "3ds/README-stage3.ru.md", DIST / "README.ru.md")
    validation = DIST / "validation"; validation.mkdir(exist_ok=True)
    for filename in ("stage3-regression.json", "stage3-jni-tests.json", "stage3-package-check.json"):
        shutil.copyfile(PORTING / "analysis" / filename, validation / filename)
    for name in ("stage2-v0.2.2-result.json", "stage2-v0.2.2-user.log"):
        shutil.copyfile(PORTING / "analysis/hardware" / name, validation / name)
    for path in (PORTING / "analysis/azahar-smoke").iterdir():
        if path.name.startswith(("result-stage3-", "stage3-3dsx-", "stage3-cxi-")):
            shutil.copyfile(path, validation / path.name)
    manifest_path = DIST / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    regression = json.loads((validation / "stage3-regression.json").read_text(encoding="utf-8"))
    jni = json.loads((validation / "stage3-jni-tests.json").read_text(encoding="utf-8"))
    manifest["validation"] = {"arm_regression_tests": regression["tests_run"], "arm_jni_tests": jni["tests_run"],
                              "azahar_cases": 8, "cia_hashes_verified": True,
                              "stage3_hardware_tested": False, "game_engine_started": False,
                              "constructors_called": False}
    manifest["files"] = {}
    for path in sorted(DIST.rglob("*")):
        if path.is_file() and path != manifest_path:
            manifest["files"][path.relative_to(DIST).as_posix()] = {
                "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    version = manifest["version"]
    archive_path = PORTING / f"dist/deadspace-3ds-stage3-v{version}-local.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(DIST.rglob("*")):
            if path.is_file(): archive.write(path, path.relative_to(DIST).as_posix())
    with zipfile.ZipFile(archive_path) as archive: assert archive.testzip() is None
    cia_path = PORTING / f"dist/deadspace-loader-stage3-v{version}.cia"
    shutil.copyfile(DIST / "deadspace-loader-stage3.cia", cia_path)
    print("Stage 3 package:", archive_path, "bytes:", archive_path.stat().st_size)
    print("SHA256:", hashlib.sha256(archive_path.read_bytes()).hexdigest())
    print("CIA:", cia_path)


if __name__ == "__main__": main()
