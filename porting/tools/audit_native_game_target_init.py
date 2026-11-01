"""Audit the isolated initial-color experiment without running hardware."""
import json
import struct
import subprocess
from pathlib import Path
from build_native_game_target_init import A, BASE, P, RUNTIME
from build_native_startup_legacy import payload, sha
from audit_native_startup_memory import globals_from_elf, pre_heap_model


def main():
    black=P/'3ds/build-native-game-v0.1.1-black'
    poison=P/'3ds/build-native-game-v0.1.1-poison'
    assert (black/'native-game-memory.c').read_text().splitlines()[1:]==(poison/'native-game-memory.c').read_text().splitlines()[1:]
    for d in [black,poison]:
        manifest=json.loads((d/'build-manifest.json').read_text())
        for n,h in manifest['outputs_sha256'].items():assert sha(d/n)==h,n
        for n in RUNTIME:assert sha(d/n)==sha(BASE/n),n
        assert globals_from_elf(d/'native-game.elf')==dict(__ctru_heap_size=20<<20,__ctru_linear_heap_size=100<<20,__stacksize__=256<<10)
    cxi=(black/'native-game.cxi').read_bytes()
    assert payload((black/'native-game.cia').read_bytes())==cxi
    assert struct.unpack_from('<Q',cxi,0x108)[0]==0x000400000FDE7400
    assert struct.unpack_from('<II',cxi,0x1b0)==(0,0),'No RomFS/game assets'
    ex=cxi[0x200:0xa00];old=(BASE/'native-game.cxi').read_bytes()[0x200:0xa00]
    assert ex[0x20d]==ex[0x60d]==1
    # ACI program IDs legitimately differ. All other ACI permissions are exact.
    assert ex[0x208:0x400]==old[0x208:0x400]
    assert ex[0x608:0x800]==old[0x608:0x800]
    assert (black/'native-game.rsf').read_text()==(BASE/'native-game.rsf').read_text().replace('DS-GAME-P124','DS-GAME-INIT').replace('CTR-H-DG24','CTR-H-DGIN').replace('0xFDE73','0xFDE74')
    (A/'final-exheader.bin').write_bytes(ex)
    model=pre_heap_model(A/'final-exheader.bin')
    measurements=[];cycles=[]
    for kind,suffix in [('cxi',''),('cia','-r2')]:
        root=P/('analysis/azahar-native-game-v0.1.1-black-'+kind+suffix)
        r=json.loads((root/'result.json').read_text())
        assert r['passed'] and r['safe_exit'] and r['sequential_cycles']==3
        assert r['runner_sha256']==sha(P/'tests/smoke_native_game_target_init.py')
        assert r['CXI_sha256']==sha(black/'native-game.cxi')
        if kind=='cia':assert r['CIA_payload_verified'] and r['CIA_sha256']==sha(black/'native-game.cia')
        for c in r['cycles']:
            assert c['passed'] and c['different_pixels']==0 and c['both_heaps_released']
            assert not c['invalid_memory_accesses']
            assert c['shutdown_proof']['kernel_joins']==6 and not c['shutdown_proof']['worker_handles_remaining']
            log=(root/('cycle-%04d'%c['cycle'])/'native-game.log').read_text()
            assert log.count('TARGET INIT color=000000ff bytes=384000 before original draw')==1
            measurements += [json.loads(l[8:]) for l in log.splitlines() if l.startswith('MEMJSON ')]
            cycles.append({'container':kind,'cycle':c['cycle'],'callback':c['actual_callback'],'exact_baseline':True,'safe_exit':True})
    assert all(m['limit']==124<<20 and not m['donor_refusals'] and not m['runtime_failures'] for m in measurements)
    commit=max(m['commit'] for m in measurements)
    assert commit==(120<<20)+model['image_and_stack_bytes'] and commit<124<<20
    negative=json.loads((A/'poison-result.json').read_text())
    assert negative['unwritten_target_color_persists'] and not negative['full_frame_gate_passed']
    before=json.loads((P/'analysis/native-game-prod124-v0.1.0/preservation.json').read_text())['before']
    for n,h in before.items():assert sha(P/n)==h,n
    manifest=json.loads((BASE/'build-manifest.json').read_text())
    for n,h in manifest['outputs_sha256'].items():assert sha(BASE/n)==h,n
    prior_cia=json.loads((BASE/'cia-manifest.json').read_text())
    assert sha(BASE/'native-game.cia')==prior_cia['CIA_sha256']
    cmd=[str(P/'toolchain/extras/ctrtool/ctrtool.exe'),'--verify',str(black/'native-game.cia')]
    audit=subprocess.run(cmd,capture_output=True,text=True)
    text=audit.stdout+audit.stderr;(A/'CIA-container-audit.txt').write_text(text)
    # Locally generated homebrew signatures are expected, hash failures are not.
    assert not any('Hash:' in l and '(FAIL)' in l for l in text.splitlines())
    errors=[l for l in text.splitlines() if ' ERROR]' in l]
    allowed=['Signature for Ticket was invalid','Signature for TitleMetaData was invalid','Signature for AccessDescriptor was invalid']
    assert len(errors)==3 and all(any(a in e for a in allowed) for e in errors),errors
    gate={'software_original_frame_and_safe_exit_PASS':True,'hardware_tested':False,'hardware_run_authorized':False,
          'ready_for_separate_hardware_approval':True,'title_id':'000400000FDE7400','CIA_sha256':sha(black/'native-game.cia'),
          'CIA_bytes':(black/'native-game.cia').stat().st_size,'SystemModeExt':1,'AccessDesc_SystemModeExt':1,
          'same_kernel_SVC_and_permissions_as_Prod124':True,'initial_target_color_is_only_behavior_change_in_pair':True,
          'initial_color':'000000ff','target_fill_bytes':384000,'depth_clear_added':False,
          'original_draw_callbacks_unmodified':True,'GPU_shader_thread_sources_identical':True,
          'process_commit_peak_bytes':commit,'uncommitted_headroom_bytes':(124<<20)-commit,
          'main_image_and_stack':model,'protected_baseline_files':len(before),'old_Prod124_CIA_unchanged':True,
          'poison_negative_test_reproduced':True,'cycles':cycles,
          'initial_CIA_third_reload_host_crash_preserved':True,'host_crash_fixed':False,
          'hardware_hang_cause_fully_proven':False,'full_gameplay_supported':False}
    (A/'release-gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    print(json.dumps(gate,indent=2))


if __name__=='__main__':main()
