"""Release gate for progress-budget native runs; never substitutes frame PASS."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from azahar_resource_store import STORE, sha, verify_dataset
from build_native_game_target_init import RUNTIME, makerom
from build_native_startup_legacy import payload

P=Path(__file__).resolve().parents[1]
A=P/'analysis/native-game-progress-v0.1.4'
BASE=P/'3ds/build-native-game-v0.1.3-normal'
CASES={'normal':(2,'final'),'crc':(1,''),'latecrc':(1,''),'slow':(2,''),
       'start':(1,''),'home':(1,''),'system':(1,''),'stall':(1,'final'),'stuck':(1,''),'hard':(1,'')}


def read(p):return json.loads(p.read_text())


def check_cycle(c,variant):
    assert c['passed'] and not c['invalid_memory_accesses'] and c['readback_and_independent_CRC_checks']
    g,v,w=c['final_guest_result'],c['validation'],c['loader_wait']
    assert not g['GL_error'] and not g['failed_submits']
    if variant in ['stuck','hard']:
        assert not c['safe_exit'] and not c['both_heaps_released'] and not v['cleanup_complete']
        assert g['status']=='blocked' and g['active_threads']==6
        assert w['state']=='retained' and w['stop_reason']==(1 if variant=='stuck' else 2)
        if variant=='hard':assert w['elapsed_ms']>=w['hard_limit_ms'] and w['idle_ms']<w['idle_limit_ms'] and w['bytes']>0
        else:assert w['idle_ms']>=w['idle_limit_ms'] and w['active_IO_ops']>0 and w['home_pending']
        return
    assert c['safe_exit'] and c['both_heaps_released'] and v['cleanup_complete'] and g['safe_exit']
    assert g['active_threads']==g['finished_threads']==0
    assert c['shutdown_proof']['kernel_joins']==6 and c['shutdown_proof']['worker_handles_remaining']==0
    assert c['shutdown_proof']['files_balanced']
    if variant=='normal':
        assert g['status']=='passed' and v['frame_status']=='PASS' and c['different_pixels']==0
        assert c['sequence_frames']==8 and c['sequence_exact']
    else:
        assert g['status']=='failed' and v['frame_status']=='FAIL'
        if variant in ['crc','latecrc']:assert v['callbacks_completed']==600
    if variant in ['slow','start','home','system']:
        assert w['elapsed_ms']>60000 and w['stop_reason']==0 and w['IO_errors']==0
        assert c['close_state']['shutdown_attempts']==1 and not c['close_state']['stopped_boundary']
    if variant=='start':assert w['START_seen'] and c['close_state']['source']=='START'
    if variant=='home':assert c['close_state']['source']=='APT' and c['close_state']['home_pending'] and c['close_state']['close_pending']
    if variant=='system':assert c['close_state']['source']=='APT' and not c['close_state']['home_pending'] and c['close_state']['close_pending']
    if variant=='stall':assert c['close_state']['shutdown_attempts']==2 and c['close_state']['source']=='none' and w['stop_reason']==1


def audit():
    negatives=read(A/'gate-negative-tests.json')
    assert negatives['passed'] and len(negatives['cases'])==7 and all(c['rejected'] for c in negatives['cases'])
    for absolute,digest in read(A/'preservation.json').items():
        current=sha(absolute)
        if Path(absolute).resolve()==(P.parent/'README.md').resolve() and current!=digest:
            # User requested screenshot provenance and supplied later hardware
            # results. Keep the original inventory and an explicit doc history.
            # Preserve the original inventory and README bytes; no code, game
            # resources, PNG or binary exceptions are allowed here.
            docs=read(A/'documentation-updates.json')
            assert docs['README_before_sha256']==digest
            assert sha(A/'README-before-renderer-provenance.md')==digest
            assert current==docs['README_after_sha256']
        else:
            assert current==digest,absolute
    for relative,digest in read(P/'analysis/native-game-stable-v0.1.2/preservation.json')['before'].items():assert sha(P/relative)==digest
    dataset=STORE/'datasets/a46655efb24fab59c7649322986eea2ae0a5827454bca4c5e71be3d13818ceef'
    verified=verify_dataset(dataset)
    master=P/'private/native-game-v0.1.0-sd/3ds/deadspace'
    assert all(sha(master/e['path'])==e['sha256'] for e in verified['files'])
    source=P/'tests/native_game_progress.c'
    assert '#define LOADER_IDLE_MS 30000u' in source.read_text() and '#define LOADER_HARD_MS 180000u' in source.read_text()
    assert '#define TARGET_RGB565_CRC 0xea733050u' in source.read_text() and '#define MAX_CALLBACKS 600u' in source.read_text()
    rows={};exits=0
    for variant,(count,attempt) in CASES.items():
        build=P/('3ds/build-native-game-v0.1.4r2-'+variant)
        m=read(build/'build-manifest.json')
        assert m['source_sha256']==sha(source)
        for name,digest in m['headers_sha256'].items():assert sha(P/'tests'/name)==digest
        for name,digest in m['outputs_sha256'].items():assert sha(build/name)==digest
        assert all(m['runtime_sha256'][n]==sha(BASE/n)==sha(build/n) for n in RUNTIME)
        assert (m['test_only_SDK'] is not None)==(variant in ['home','system','stuck'])
        root=P/('analysis/azahar-native-game-v0.1.4r2-'+variant+'-cxi'+('-'+attempt if attempt else ''))
        r=read(root/'result.json')
        assert r['passed'] and len(r['cycles'])==r['sequential_cycles']==count
        assert r['CXI_sha256']==sha(build/'native-game.cxi')
        assert r['runner_sha256']==sha(build/('host-runner'+('-'+attempt if attempt else '')+'.py'))
        small=[]
        for c in r['cycles']:
            check_cycle(c,variant)
            evidence=root/('cycle-%04d'%c['cycle']);log=(evidence/'native-game.log').read_text()
            if variant not in ['stuck','hard']:
                attempt_no=c['close_state']['shutdown_attempts']
                q=read(evidence/('threads-a%d-after_quiesce.json'%attempt_no));j=read(evidence/('threads-a%d-after_join.json'%attempt_no))
                workers=[w for w in q['workers'] if w['token']&255]
                assert len(workers)==6 and all(w['done']==1 and w['kernel_wait']==0 for w in workers)
                assert not any(w['token']&255 for w in j['workers'])
                exits+=1
                if variant=='stall':
                    retained=read(evidence/'threads-a1-stopped_retained.json')
                    assert sum(w['done']==0 and w['kernel_wait']!=0 for w in retained['workers'] if w['token']&255)==6
                    assert 'STOPPED automatic continuation:' in log and 'CANCEL START acknowledged' not in log
                if variant=='home':assert log.index('SHUTDOWN live workers=0')<log.index('APT HOME handover AFTER quiescence')<log.index('APT HOME returned should_close=1')
            else:
                assert not (evidence/'exit.txt').exists() and 'RESOURCES JNI=' not in log and 'SHUTDOWN live workers=0' not in log
                if variant=='stuck':assert 'CANCEL START acknowledged' in log
            small.append({'cycle':c['cycle'],'safe_exit':c['safe_exit'],'guest_status':c['final_guest_result']['status'],
                          'shutdown_proof':c['shutdown_proof'],'wait':c['loader_wait'],'close':c['close_state']})
        rows[variant]={'CXI_sha256':r['CXI_sha256'],'cycles':small}
    assert exits==10
    return {'software_passed':True,'completed_process_exits':exits,'retained_negative_cases':2,
            'source_sha256':sha(source),'headers_sha256':{n:sha(P/'tests'/n) for n in ['native_loader_budget.h','native_loader_io_monitor.h']},
            'default_idle_ms':30000,'default_hard_ms':180000,'frame_crc_unchanged':'ea733050',
            'original_runtime_GPU_shader_unchanged':True,'old_resources_preserved':True,
            'cancellation_mode':'stop scene continuation, finish original in-flight Run, then join; no mid-read abort or thread kill',
            'completed_donor_job_counter_available':False,
            'APT_test_scope':'deferred HOME injected; original SDK wakeup-cancel path, screenshot readiness shim only in tests; system exit flag injected in separate test',
            'hardware_tested':False,'hardware_run_authorized':False,'ready_for_one_separate_hardware_test':False,'cases':rows}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--cia',action='store_true');args=ap.parse_args()
    gate=audit();build=P/'3ds/build-native-game-v0.1.4r2-normal'
    data=(build/'native-game.cxi').read_bytes()
    assert struct.unpack_from('<Q',data,0x108)[0]==0x000400000FDE7700
    smdh=(build/'native-game.smdh').read_bytes()
    assert smdh[0x208:0x288].decode('utf-16le').split('\0')[0]=='DS Game Progress 0.1.4'
    if args.cia:
        assert not (build/'native-game.cia').exists(),'Preserve the single candidate'
        subprocess.run(makerom('cia',build),cwd=build,check=True)
        assert payload((build/'native-game.cia').read_bytes())==data
        (build/'cia-payload.cxi').write_bytes(data)
        m={'title_id':'000400000FDE7700','CIA_sha256':sha(build/'native-game.cia'),'CIA_bytes':(build/'native-game.cia').stat().st_size,
           'CXI_sha256':sha(build/'native-game.cxi'),'version':'0.1.4','hardware_tested':False,'hardware_run_authorized':False}
        (build/'cia-manifest.json').write_text(json.dumps(m,indent=2)+'\n');gate['CIA']=m
    elif (build/'native-game.cia').exists():
        m=read(build/'cia-manifest.json');assert m['CIA_sha256']==sha(build/'native-game.cia') and payload((build/'native-game.cia').read_bytes())==data
        tested=read(P/'analysis/azahar-native-game-v0.1.4r2-normal-cia-payload/result.json')
        assert tested['passed'] and tested['CIA_payload_verified'] and tested['CIA_sha256']==m['CIA_sha256'] and tested['CXI_sha256']==m['CXI_sha256']
        assert tested['sequential_cycles']==1;check_cycle(tested['cycles'][0],'normal')
        gate.update({'CIA':m,'CIA_payload_passed':True,'completed_process_exits':11,'ready_for_one_separate_hardware_test':True})
    hardware_path=P/'analysis/native-game-progress-v0.1.4-hardware/hardware-result.json'
    if hardware_path.exists():
        # Recompute from byte-preserved runs, not only a mutable summary flag.
        from analyze_native_game_progress_hardware import verify
        hardware,_=verify()
        assert hardware==read(hardware_path)
        assert hardware['expected_CIA_sha256']==gate['CIA']['CIA_sha256']
        gate.update({'hardware_tested':True,'hardware_result':hardware['overall_result'],
                     'hardware_automatic_cleanup_first_attempt_passed':hardware['automatic_cleanup_first_attempt_passed'],
                     'hardware_automatic_exit_without_registered_START':hardware['automatic_exit_without_registered_START'],
                     'hardware_HOME_X_tested':hardware['HOME_X_tested'],'hardware_HOME_X_passed':hardware['HOME_X_passed'],
                     'hardware_physical_START_acknowledgement_exercised':hardware['physical_START_acknowledgement_exercised'],
                     'ready_for_one_separate_hardware_test':False,'repeat_current_CIA_needed':False,
                     'hardware_followup':'This experiment is complete. No repeat needed; next: original difficulty screen/controls and targeted performance measurements. Frame FAIL remains.'})
    (A/'release-gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    print(json.dumps({k:v for k,v in gate.items() if k!='cases'},indent=2))


if __name__=='__main__':main()
