"""Isolated successor to frozen stable runner; uses verified shared assets."""
import difflib
import json
from pathlib import Path
import subprocess
import sys

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P/'tools'))
from azahar_resource_store import ensure_dataset, sha


def main():
    # Keep the accepted old runner immutable. Save every adaptation for audit.
    old = P/'tests/smoke_native_game_stable.py'
    assert sha(old) == 'f14b3842eab6eafd66a0210e0fd3d68877ea3229f7d2326f84df0a9ecf83a0f4'
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--variant', default='lateprobe')
    ap.add_argument('--cycles', type=int, default=1)
    ap.add_argument('--attempt', default='')
    ap.add_argument('--container', choices=['cxi', 'cia'], default='cxi')
    args = ap.parse_args()
    assert 1 <= args.cycles <= 5 and (not args.attempt or args.attempt.isalnum())
    assert args.container == 'cxi' or args.variant == 'normal'
    variants = ['normal', 'crc', 'lateprobe', 'latepending', 'latefixed', 'latefixed2', 'latefixed3', 'lateprogress', 'latefinal', 'late', 'latehome', 'latestopped', 'latecrc', 'apt', 'apthome', 'apt2', 'home', 'stopped', 'stopped2', 'retain']
    assert args.variant in variants
    dataset = ensure_dataset(P/'private/native-game-v0.1.0-sd/3ds/deadspace')
    d = P/('3ds/build-native-game-v0.1.3-'+args.variant)
    runner = d/('host-runner'+('-'+args.attempt if args.attempt else '')+'.py')
    assert not runner.exists()
    text = old.read_text()
    text = text.replace('native-game-v0.1.2', 'native-game-v0.1.3')
    text = text.replace("['normal', 'poison', 'crc', 'retain']", repr(variants))
    text = text.replace("args.variant in ['normal', 'retain']", "args.variant in ['normal', 'retain', 'stopped', 'stopped2']")
    text = text.replace("if args.variant == 'normal':", "if args.variant in ['normal', 'apt', 'apthome', 'apt2', 'home', 'stopped', 'stopped2']:")
    text = text.replace("if final['status'] == 'blocked':", "if final['status'] == 'blocked' and args.variant not in ['stopped', 'stopped2', 'latestopped']:")
    # The pending delegate case stops at an observed real loader state, rather
    # than pretending it completed all 600 callbacks. CRC600 stays a separate gate.
    check = """    if args.variant in ['latefixed', 'latefixed2', 'latefixed3', 'lateprogress', 'latefinal', 'late', 'latehome', 'latestopped', 'latepending']:
        pending = read_json(evidence/'threads-test_pending_delegate.json')
        late = [w for w in pending['workers'] if w['userdata_vtable'] and w['userdata_vtable'][0]-pending['image_base'] == 0xb6e6c] if pending else []
        exact_pending = len(late) == 1 and late[0]['loader_sync_words'][4] == 1 and late[0]['loader_sync_words'][5]&255 == 0 and late[0]['late_flag68'] == 0 and late[0]['kernel_wait'] != 0 and late[0]['userdata_words'][5]-pending['image_base'] == 0xb6d04 and late[0]['wait_stack'][15]-pending['image_base'] == 0xb7084
        expected = bool(safe and exact_pending and final['status'] == 'failed' and validation['frame_status'] == 'FAIL' and validation['callbacks_completed'] >= 320 and 'test stop at pending late loader delegate' in validation['failure_reason'] and re.search(r'LOADER drained .*Run=b6e6c completion=0 pumps=[1-9]', log))
    if args.variant in ['latefixed', 'latefixed2', 'latefixed3', 'lateprogress', 'latefinal', 'late', 'latehome', 'latestopped', 'latecrc']:
        before = read_json(evidence/'threads-before_pause.json')
        expected &= bool(before and any(w['userdata_vtable'] and w['userdata_vtable'][0]-before['image_base'] == 0xb6e6c for w in before['workers']))
    if args.variant in ['apt', 'apthome', 'apt2', 'home', 'latehome', 'latestopped', 'stopped', 'stopped2']:
        expected &= 'TEST APT HOME-menu cancel IPC result=00000000' in log and 'APT close pending;' in log and 'PROCESS return close_pending=1 source=APT' in log
        expected &= 'APT HOME handover AFTER quiescence' in log and 'APT HOME returned should_close=1' in log and 'TEST HLE HOME screenshot readiness shim' in log
        expected &= log.index('SHUTDOWN live workers=0') < log.index('APT HOME handover AFTER quiescence') < log.index('APT HOME returned should_close=1') < log.index('PROCESS return')
    if args.variant in ['stopped', 'stopped2', 'latestopped']:
        expected &= 'STOPPED retry close_pending=0 home_pending=1' in log and 'stopped_boundary=1 cleanup=complete attempts=2' in log
        retained = read_json(evidence/'threads-stopped_retained.json')
        expected &= bool(retained and sum(w['done'] == 0 and w['kernel_wait'] != 0 for w in retained['workers'] if w['token']&255) == 6)
"""
    text = text.replace("    report = {'passed': bool(expected and capture_checks and not bad),", check+"    report = {'passed': bool(expected and capture_checks and not bad),")
    text = text.replace('000400000FDE7500', '000400000FDE7600')
    text = text.replace('P = Path(__file__).resolve().parents[1]', 'P = Path('+repr(str(P))+')')
    text = text.replace('import smoke_azahar as f', "sys.path.insert(0, str(P/'tests'))\nsys.path.insert(0, str(P/'tools'))\nimport smoke_azahar as f")
    begin = text.index('    card.mkdir(parents=True)')
    end = text.index('    core = C.CDLL', begin)
    text = text[:begin]+"    from azahar_resource_store import prepare_card\n    prepare_card(card, Path("+repr(str(dataset))+"))\n"+text[end:]
    runner.write_text(text)
    (runner.with_suffix('.diff')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True), text.splitlines(True))))
    command = [sys.executable, str(runner), '--variant', args.variant, '--cycles', str(args.cycles), '--container', args.container]
    if args.attempt:
        command += ['--attempt', args.attempt]
    console = runner.with_suffix('.console.log')
    with console.open('wb') as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    print(console.read_text(errors='replace')[-3500:])
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
