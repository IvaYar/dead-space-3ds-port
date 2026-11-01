"""New isolated long/stalled-loader tests, preserving frozen stable runner."""
import argparse
import difflib
from pathlib import Path
import subprocess
import sys
P = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'tools'))
from azahar_resource_store import ensure_dataset, sha
from build_native_game_progress import VARIANTS


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--variant', choices=VARIANTS, required=True)
    ap.add_argument('--cycles', type=int, default=1)
    ap.add_argument('--attempt', default='')
    ap.add_argument('--container', choices=['cxi','cia'], default='cxi')
    args=ap.parse_args()
    assert 1<=args.cycles<=5 and (not args.attempt or args.attempt.isalnum())
    assert args.variant not in ['stuck','hard'] or args.cycles==1
    assert args.container=='cxi' or args.variant=='normal'
    old=P/'tests/smoke_native_game_stable.py'
    assert sha(old)=='f14b3842eab6eafd66a0210e0fd3d68877ea3229f7d2326f84df0a9ecf83a0f4'
    dataset=ensure_dataset(P/'private/native-game-v0.1.0-sd/3ds/deadspace')
    d=P/('3ds/build-native-game-v0.1.4r2-'+args.variant)
    runner=d/('host-runner'+('-'+args.attempt if args.attempt else '')+'.py')
    assert not runner.exists()
    text=old.read_text().replace('native-game-v0.1.2','native-game-v0.1.4').replace('000400000FDE7500','000400000FDE7700')
    text=text.replace('analysis/azahar-native-game-v0.1.4-', 'analysis/azahar-native-game-v0.1.4r2-').replace('3ds/build-native-game-v0.1.4-', '3ds/build-native-game-v0.1.4r2-')
    text=text.replace("['normal', 'poison', 'crc', 'retain']",repr(list(VARIANTS)))
    text=text.replace("args.variant in ['normal', 'retain']","args.variant == 'normal'")
    text=text.replace("if final['status'] == 'blocked':","if final['status'] == 'blocked' and args.variant in ['stuck','hard']:")
    text=text.replace("args.variant != 'retain'","args.variant not in ['stuck','hard']")
    controls="""        wait = read_json(run_dir/'loader-wait.json')
        if args.variant == 'start' and wait and wait['elapsed_ms'] >= 1000:
            controls['start'] = True
        if args.variant == 'stuck' and final and final['status'] == 'blocked':
            controls['start'] = True
"""
    text=text.replace("        host = (ROOT/'azahar-host.log').read_text(errors='replace')[host_start:]", controls+"        host = (ROOT/'azahar-host.log').read_text(errors='replace')[host_start:]")
    text=text.replace("    quiesce = read_json(evidence/'threads-after_quiesce.json')", "    close = read_json(evidence/'close-state.json')\n    attempt = close['shutdown_attempts'] if close else 1\n    quiesce = read_json(evidence/('threads-a%d-after_quiesce.json' % attempt))")
    text=text.replace("    joined = read_json(evidence/'threads-after_join.json')", "    joined = read_json(evidence/('threads-a%d-after_join.json' % attempt))")
    extra="""    wait = read_json(evidence/'loader-wait.json')
    if args.variant == 'latecrc':
        before = read_json(evidence/'threads-a1-before_pause.json')
        expected &= bool(safe and before and any(w['userdata_vtable'] and w['userdata_vtable'][0]==before['image_base']+0xb6e6c for w in before['workers']))
    if args.variant not in ['normal','crc','latecrc']:
        pending = read_json(evidence/'threads-a0-test_pending_delegate.json')
        late = [w for w in pending['workers'] if w['userdata_vtable'] and w['userdata_vtable'][0] == pending['image_base']+0xb6e6c] if pending else []
        exact = len(late)==1 and late[0]['loader_sync_words'][4]==1 and late[0]['late_flag68']==0 and late[0]['kernel_wait']!=0 and late[0]['wait_stack'][15]==pending['image_base']+0xb7084
        # After STOPPED, wait.json preserves the expired window. Final kernel
        # snapshots/close-state prove completion, without resetting that budget.
        expected = bool(exact and safe and final['status']=='failed' and validation['frame_status']=='FAIL' and wait and wait['state'] in (['retained'] if args.variant=='stall' else ['complete']) and wait['IO_errors']==0 and wait['bytes']>0 and wait['completed_files']>0)
        if args.variant in ['slow','start','home','system']:
            expected &= bool(close and wait['elapsed_ms']>60000 and wait['stop_reason']==0 and close['shutdown_attempts']==1 and not close['stopped_boundary'])
        if args.variant == 'start':
            expected &= 'CANCEL START acknowledged during loader wait;' in log
        if args.variant == 'home':
            expected &= bool(close and close['home_pending'] and close['close_pending'] and close['source']=='APT' and 'APT HOME returned should_close=1' in log and log.index('SHUTDOWN live workers=0')<log.index('APT HOME handover AFTER quiescence'))
        if args.variant == 'system':
            expected &= bool(close and close['close_pending'] and not close['home_pending'] and close['source']=='APT' and 'APT close pending;' in log)
        if args.variant == 'stall':
            expected &= bool(close and close['shutdown_attempts']==2 and close['stopped_boundary'] and 'STOPPED automatic continuation:' in log)
            expected &= 'CANCEL START acknowledged' not in log and wait['stop_reason']==1
            retained=read_json(evidence/'threads-a1-stopped_retained.json')
            expected &= bool(retained and sum(w['done']==0 and w['kernel_wait']!=0 for w in retained['workers'] if w['token']&255)==6)
        if args.variant in ['stuck','hard']:
            expected=bool(exact and wait and wait['state']=='retained' and wait['stop_reason']==(1 if args.variant=='stuck' else 2) and not safe and not cleaned and final['status']=='blocked' and not validation['cleanup_complete'] and final['active_threads']==6 and 'RESOURCES JNI=' not in log and 'SHUTDOWN live workers=0' not in log and not (run_dir/'exit.txt').exists() and 'ReleaseRight:999: called' not in host and 'operation=0x00000001, addr0=0x30000000' not in host)
            if args.variant=='hard':
                expected &= wait['bytes']>0 and wait['idle_ms']<wait['idle_limit_ms'] and wait['elapsed_ms']>=wait['hard_limit_ms']
            else:
                expected &= wait['active_IO_ops']>0 and wait['elapsed_ms']>=wait['idle_limit_ms'] and wait['home_pending'] and 'CANCEL START acknowledged' in log
"""
    text=text.replace("    report = {'passed': bool(expected and capture_checks and not bad),",extra+"    report = {'loader_wait': wait, 'close_state': close, 'passed': bool(expected and capture_checks and not bad),")
    text=text.replace('P = Path(__file__).resolve().parents[1]','P = Path('+repr(str(P))+')')
    text=text.replace('import smoke_azahar as f',"sys.path.insert(0,str(P/'tests'))\nsys.path.insert(0,str(P/'tools'))\nimport smoke_azahar as f")
    a=text.index('    card.mkdir(parents=True)');b=text.index('    core = C.CDLL',a)
    text=text[:a]+"    from azahar_resource_store import prepare_card\n    prepare_card(card,Path("+repr(str(dataset))+"))\n"+text[b:]
    runner.write_text(text)
    runner.with_suffix('.diff').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),text.splitlines(True))))
    command=[sys.executable,str(runner),'--variant',args.variant,'--cycles',str(args.cycles),'--container',args.container]
    if args.attempt:command+=['--attempt',args.attempt]
    console=runner.with_suffix('.console.log')
    with console.open('wb') as output:
        r=subprocess.run(command,stdout=output,stderr=subprocess.STDOUT)
    import json
    runner.with_suffix('.execution.json').write_text(json.dumps({'child_exit_code':r.returncode,'command':command},indent=2)+'\n')
    print(console.read_text(errors='replace')[-2500:])
    return r.returncode


if __name__=='__main__':
    raise SystemExit(main())
