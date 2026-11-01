"""One software-only reproduction of the hardware's later loader class.

The measured hardware checkpoint starts at75 versus software298; the later
loader exists on hardware534. A cap850 tests that concrete phase hypothesis.
No production source, existing build, frame oracle or CIA is changed.
"""
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from build_native_startup_legacy import sha
from build_native_game_target_init import RUNTIME, makerom

P = Path(__file__).resolve().parents[1]
BASE = P/'3ds/build-native-game-v0.1.2-crc'
D = P/'3ds/build-native-game-late-loader-v0.1.2-crc'
A = P/'analysis/native-game-stable-v0.1.2-hardware/late-loader-probe'


def main():
    assert not D.exists() and not A.exists(), 'Preserve previous evidence'
    D.mkdir()
    A.mkdir()
    manifest = json.loads((BASE/'build-manifest.json').read_text())
    for name, digest in manifest['outputs_sha256'].items():
        assert sha(BASE/name) == digest, name
    original = (BASE/'native-game-memory.c').read_text()
    assert original.count('#define MAX_CALLBACKS 600u') == 1
    source = original.replace('#define MAX_CALLBACKS 600u', '#define MAX_CALLBACKS 850u')
    source = source.replace('ds-native-game-v0.1.2/', 'ds-native-game-late-loader-v0.1.2/')
    source = source.replace('native-game-stable-v012', 'native-game-late-loader-v012')
    (D/'native-game-memory.c').write_text(source)
    (A/'entry.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True), source.splitlines(True), fromfile='frozen negative software source', tofile='software-only later-phase probe')))
    for name in RUNTIME+['native-game.rsf', 'native-game.smdh', 'native-game.bnr']:
        shutil.copyfile(BASE/name, D/name)
    command = [word.replace(str(BASE), str(D)) for word in manifest['commands'][0]]
    assert '-DFORCE_CRC_FAIL=1' in command
    subprocess.run(command, cwd=D, check=True)
    subprocess.run(makerom('cxi', D), cwd=D, check=True)
    host = (P/'tests/smoke_native_game_stable.py').read_text()
    assert host.count("P = Path(__file__).resolve().parents[1]") == 1
    host = host.replace('native-game-v0.1.2', 'native-game-late-loader-v0.1.2')
    host = host.replace("validation['callbacks_completed'] == 600", "validation['callbacks_completed'] == 850")
    host = host.replace('P = Path(__file__).resolve().parents[1]', 'P = Path('+repr(str(P))+')')
    host = host.replace('import smoke_azahar as f', "sys.path.insert(0, str(P/'tests'))\nimport smoke_azahar as f")
    runner = D/'host-runner.py'
    runner.write_text(host)
    proof = {'software_only': True, 'hardware_launch': False, 'CIA_created': False,
             'callback_cap': 850, 'forced_CRC_rejection': True,
             'production_entry_unchanged_sha256': sha(P/'tests/native_game_stable.c'),
             'baseline_CIA_sha256': sha(P/'3ds/build-native-game-v0.1.2-normal/native-game.cia'),
             'entry_sha256': sha(D/'native-game-memory.c'), 'CXI_sha256': sha(D/'native-game.cxi'),
             'host_runner_sha256': sha(runner), 'compiler_command': command}
    (A/'build-manifest.json').write_text(json.dumps(proof, indent=2)+'\n')
    with (A/'console.log').open('wb') as console:
        job = subprocess.run([sys.executable, str(runner), '--variant', 'crc', '--cycles', '1'], stdout=console, stderr=subprocess.STDOUT)
    proof['host_exit_code'] = job.returncode
    proof['production_and_CIA_unchanged_after'] = (proof['production_entry_unchanged_sha256'] == sha(P/'tests/native_game_stable.c') and proof['baseline_CIA_sha256'] == sha(P/'3ds/build-native-game-v0.1.2-normal/native-game.cia'))
    root = P/'analysis/azahar-native-game-late-loader-v0.1.2-crc-cxi'
    result = root/'result.json'
    if result.exists():
        r = json.loads(result.read_text())
        proof['guest_result'] = r['final_guest_result']
        proof['software_cleanup_passed'] = r['safe_exit']
        probe = root/'cycle-0001/threads-before_pause.json'
        if probe.exists():
            data = json.loads(probe.read_text())
            base = data['image_base']
            proof['generic_loader_virtual_Run_offsets'] = [w['userdata_vtable'][0]-base for w in data['workers'] if len(w['argument_words']) > 4 and w['argument_words'][3] == base+0x320624 and w['userdata_vtable']]
            proof['hardware_later_Run_b6e6c_reproduced'] = 0xb6e6c in proof['generic_loader_virtual_Run_offsets']
    (A/'result.json').write_text(json.dumps(proof, indent=2)+'\n')
    print(json.dumps({k: v for k, v in proof.items() if k != 'compiler_command'}, indent=2))


if __name__ == '__main__':
    main()
