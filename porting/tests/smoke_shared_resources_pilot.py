"""One unchanged native CXI/normal cycle through a new shared-resource SD.

The old runner stays byte-identical. A saved generated runner changes only SD
preparation and its own import root; all frame/CRC/join/GPU checks are retained.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P/'tools'))
from azahar_resource_store import STORE, ensure_dataset, prepare_card, sha, verify_dataset

A = P/'analysis/shared-resource-store-pilot'
RUN = P/'analysis/azahar-native-game-v0.1.2-normal-cxi-sharedstorepilot'
ORIGINAL = P/'tests/smoke_native_game_stable.py'
ORIGINAL_SHA = 'f14b3842eab6eafd66a0210e0fd3d68877ea3229f7d2326f84df0a9ecf83a0f4'


def main():
    if A.exists() or RUN.exists():
        raise FileExistsError('Pilot evidence is immutable; choose a new attempt')
    assert sha(ORIGINAL) == ORIGINAL_SHA
    A.mkdir()
    master = P/'private/native-game-v0.1.0-sd/3ds/deadspace'
    protected = [ORIGINAL, P/'tests/native_game_stable.c',
                 P/'3ds/source/ds34_gpu_3ds.c', P/'3ds/build-native-game-v0.1.2-normal/native-game.cxi',
                 P/'3ds/build-native-game-v0.1.2-normal/native-game.cia',
                 P/'3ds/build-native-game-v0.1.2-normal/ds34_gpu_native.c',
                 P/'3ds/build-native-game-v0.1.2-normal/ds7_threads_probe.c']
    before = {str(p.relative_to(P)): sha(p) for p in protected}
    dataset = ensure_dataset(master)
    initial = verify_dataset(dataset)
    # Dataset is also a before/after SHA inventory of the untouched master.
    assert all(sha(master/e['path']) == e['sha256'] for e in initial['files'])
    (A/'setup.json').write_text(json.dumps({'dataset_id': dataset.name, 'protected_before': before,
        'existing_source_master_unchanged': True, 'original_runner_sha256': ORIGINAL_SHA,
        'native_build_reused': True, 'new_CIA_created': False, 'hardware_launch': False}, indent=2)+'\n')
    text = ORIGINAL.read_text()
    old = '''    card.mkdir(parents=True)
    for name in ['assets', 'apk-assets']:
        shutil.copytree(source/name, card/name)
    shutil.copytree(source/'test-output/font-subset', card/'test-output/font-subset')
    for name in ['assets-verified.txt', 'apk-assets-verified.txt']:
        shutil.copyfile(source/name, card/name)
    shutil.copyfile(P/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so', card/'libEAMGameDeadSpace_orig.so')'''
    assert text.count(old) == 1
    new = """    from azahar_resource_store import prepare_card
    layout = prepare_card(card, Path(DATASET_PATH))
    (ROOT/'resource-layout.json').write_text(json.dumps(layout, indent=2)+'\\n')"""
    text = text.replace(old, new)
    text = text.replace('P = Path(__file__).resolve().parents[1]',
                        'P = Path('+repr(str(P))+')\nDATASET_PATH = '+repr(str(dataset)))
    text = text.replace('import smoke_azahar as f',
                        "sys.path.insert(0, str(P/'tests'))\nsys.path.insert(0, str(P/'tools'))\nimport smoke_azahar as f")
    runner_dir = P.parent/'.local/shared-resource-pilot'
    runner_dir.mkdir(parents=True, exist_ok=False)
    runner = runner_dir/'host-runner.py'
    runner.write_text(text)
    # Prove the preparation-only patch against the original, not relaxed tests.
    import difflib
    (A/'host-preparation.diff').write_text(''.join(difflib.unified_diff(
        ORIGINAL.read_text().splitlines(True), text.splitlines(True), fromfile='frozen runner', tofile='pilot preparation only')))
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    with (A/'console.log').open('wb') as console:
        job = subprocess.run([sys.executable, str(runner), '--variant', 'normal',
            '--container', 'cxi', '--cycles', '1', '--attempt', 'sharedstorepilot'],
            env=env, stdout=console, stderr=subprocess.STDOUT)
    r = json.loads((RUN/'result.json').read_text())
    layout = json.loads((RUN/'resource-layout.json').read_text())
    card = RUN/'Azahar/sdmc/3ds/deadspace'
    verify_dataset(dataset)
    assert all(sha(master/e['path']) == e['sha256'] for e in initial['files'])
    assert all(sha(p) == before[str(p.relative_to(P))] for p in protected)
    mutable = card/'test-output/shared-store-write-check'
    mutable.mkdir()
    marker = mutable/'private-save.bin'
    marker.write_bytes(b'isolated writable save\n')
    marker.write_bytes(marker.read_bytes()+b'append\n')
    writable_local = os.stat(marker).st_nlink == 1 and card.resolve() in marker.resolve().parents
    assert writable_local and not (dataset/'data/test-output/shared-store-write-check').exists()
    assert marker.read_bytes() == b'isolated writable save\nappend\n'
    overwritten_refused = False
    try:
        prepare_card(card, dataset)
    except FileExistsError:
        overwritten_refused = True
    private_original_sha = sha(card/'libEAMGameDeadSpace_orig.so')
    # A host fault fixture can change its own donor without changing the store.
    with (card/'libEAMGameDeadSpace_orig.so').open('r+b') as f:
        byte = f.read(1)
        f.seek(0)
        f.write(bytes([byte[0] ^ 1]))
        f.flush()
        assert sha(dataset/'data/libEAMGameDeadSpace_orig.so') == private_original_sha
        f.seek(0)
        f.write(byte)
    assert sha(card/'libEAMGameDeadSpace_orig.so') == private_original_sha
    verify_dataset(dataset)
    passed = bool(job.returncode == 0 and r['passed'] and r['safe_exit'] and
                  r['different_pixels'] == 0 and r['sequence_frames'] == 8 and
                  r['shutdown_proof']['kernel_joins'] == 6 and overwritten_refused and writable_local)
    proof = {'passed': passed, 'one_Azahar_cycle': True, 'dataset_id': dataset.name,
        'dataset_files': len(initial['files']), 'dataset_bytes': sum(e['bytes'] for e in initial['files']),
        'shared_bytes_per_run': layout['shared_bytes'], 'private_seed_bytes_per_run': layout['private_seed_bytes'],
        'all_1752_SD_path_SHA_checks': layout['files_verified'],
        'store_and_master_SHA_unchanged_after': True, 'protected_sources_and_binaries_unchanged': True,
        'shared_asset_write_denied': layout['writes_to_shared_asset_denied'],
        'writable_save_create_append_read': writable_local, 'private_donor_mutation_isolated_and_restored': True,
        'existing_card_overwrite_refused': overwritten_refused, 'hard_links_used': False,
        'original_runner_sha256': ORIGINAL_SHA, 'generated_runner_sha256': sha(runner),
        'storage_helper_sha256': sha(P/'tools/azahar_resource_store.py'),
        'pilot_driver_sha256': sha(Path(__file__)), 'guest': r,
        'new_CIA_created': False, 'hardware_tested': False,
        'old_39_datasets_deleted_or_moved': False,
        'scope': 'normal native runner only; mutating engine/negative asset cases stay on independent copies'}
    (A/'result.json').write_text(json.dumps(proof, indent=2)+'\n')
    print(json.dumps({k: v for k, v in proof.items() if k != 'guest'}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
