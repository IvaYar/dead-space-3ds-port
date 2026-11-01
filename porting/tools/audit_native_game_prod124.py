"""Audit saved Prod124 artifacts, memory, one-factor changes and release gates."""
import json
import struct
from pathlib import Path
from build_native_game_prod124 import A, BASE, GENERATED, P, REVS, STEPS, build_dir
from build_native_startup_legacy import payload, sha
from audit_native_startup_memory import globals_from_elf, pre_heap_model


def samples(log):
    lines = log.read_text().splitlines()
    return tuple([json.loads(l[len(prefix):]) for l in lines if l.startswith(prefix)]
                 for prefix in ['MEMJSON ', 'PEAKJSON ', 'REGIONJSON '])


def main():
    stage_results=[]
    for step in STEPS:
        d=build_dir(step)
        m=json.loads((d/'build-manifest.json').read_text())
        assert m['observer_sha256']==sha(P/'tests/native_game_memory_observer.h')
        for n,h in m['outputs_sha256'].items():assert sha(d/n)==h,n
        for n in GENERATED:assert sha(d/n)==sha(BASE/n),n
        if step=='prod':
            root=P/'analysis/azahar-native-game-v0.1.0-p124p-cxi-r2'
        else:root=P/('analysis/azahar-native-game-v0.1.0-'+REVS[step]+'-cxi')
        r=json.loads((root/'result.json').read_text());assert r['passed'] and r['safe_exit']
        assert r['runner_sha256']==sha(P/'tests/smoke_native_game_prod124.py')
        assert r['CXI_sha256']==sha(d/'native-game.cxi')
        for c in r['cycles']:
            assert c['baseline_RGB565_exact'] and c['different_pixels']==0 and c['both_heaps_released']
            assert c['shutdown_proof']['kernel_joins']==6 and not c['shutdown_proof']['worker_handles_remaining']
        stage_results.append({k:m[k] for k in ['step','normal_MiB','linear_MiB','arena_MiB','required_app_MiB','memory_mode_MiB']}
                             | {'cycles_passed':r['sequential_cycles'],'proof':root.relative_to(P).as_posix()})
    for a,b in zip(STEPS,STEPS[1:]):
        old=(build_dir(a)/'native-game-memory.c').read_text().splitlines(True)
        new=(build_dir(b)/'native-game-memory.c').read_text().splitlines(True)
        changed=[i for i,(x,y) in enumerate(zip(old,new)) if x!=y]
        assert len(old)==len(new)
        assert not changed if b=='prod' else len(changed)==1 and changed[0]<4
    d=build_dir('prod');cxi=(d/'native-game.cxi').read_bytes()
    cia=payload((d/'native-game.cia').read_bytes());assert cia==cxi
    old=(build_dir('guard')/'native-game.cxi').read_bytes()[0x200:0xa00]
    ex=cxi[0x200:0xa00]
    diffs=[{'offset':hex(i),'before':x,'after':y} for i,(x,y) in enumerate(zip(old,ex)) if x!=y and not 0x400<=i<0x500]
    assert diffs==[{'offset':'0x20d','before':2,'after':1},{'offset':'0x60d','before':2,'after':1}]
    assert ex[0x500:0x600]==old[0x500:0x600]
    assert sha(d/'native-game.elf')==sha(build_dir('guard')/'native-game.elf')
    assert struct.unpack_from('<II',cxi,0x1b0)==(0,0), 'RomFS must be empty'
    assert globals_from_elf(d/'native-game.elf')==dict(__ctru_heap_size=20<<20,__ctru_linear_heap_size=100<<20,__stacksize__=256<<10)
    cia_root=P/'analysis/azahar-native-game-v0.1.0-p124p-cia'
    result=json.loads((cia_root/'result.json').read_text())
    assert result['passed'] and result['CIA_payload_verified'] and result['sequential_cycles']==3
    assert result['CIA_sha256']==sha(d/'native-game.cia')
    memory=[];peaks=[];regions=[];stacks=[]
    for c in result['cycles']:
        assert c['passed'] and c['safe_exit'] and c['different_pixels']==0 and not c['invalid_memory_accesses']
        assert c['shutdown_proof']['kernel_joins']==6 and c['shutdown_proof']['worker_handles_remaining']==0
        folder=cia_root/('cycle-%04d'%c['cycle'])
        ms,ps,rs=samples(folder/'native-game.log');memory+=ms;peaks+=ps;regions+=rs
        workers=json.loads((folder/'threads-after_quiesce.json').read_text())['workers']
        stacks.append(sum(w['stack_bytes'] for w in workers if w['token']&255))
    assert all(s['query_result']==0 and s['limit']==124<<20 and not s['donor_refusals'] and not s['runtime_failures'] for s in memory)
    maxof=lambda name:max(s[name] for s in peaks)
    peak={k:maxof(k) for k in peaks[0]}
    assert peak['normal_footprint']<20<<20 and peak['linear_used']<100<<20
    assert peak['arena_actual_size']==92<<20 and peak['linear_other']<8<<20
    for region in regions:
        assert region['rw_span'] and not region['base']&(region['alignment']-1)
        if region['linear']:assert region['physical_last']-region['physical']==region['bytes']-1
    model=pre_heap_model(A/'final-exheader.bin')
    commit=max(s['commit'] for s in memory)
    assert commit==(120<<20)+model['image_and_stack_bytes']
    donor_peak=max(s['donor_brk_peak']+s['donor_map_peak_pages']*4096 for s in memory)
    assert donor_peak<92<<20
    e=lambda off:struct.unpack_from('<I',ex,off)[0]
    measured={'hardware_tested':False,'profile':'Prod124','kernel_process_commit_peak_bytes':commit,
        'app_limit_bytes':124<<20,'uncommitted_headroom_bytes':(124<<20)-commit,
        'heap_reservations':{'normal':20<<20,'linear':100<<20,'donor_arena_SUBSET_linear':92<<20,'other_linear_budget':8<<20},
        'native_executable':{'text_bytes':e(0x18),'text_page_commit':e(0x14)*4096,
            'ro_bytes':e(0x28),'ro_page_commit':e(0x24)*4096,'data_bytes':e(0x38),'BSS_bytes':e(0x3c),**model},
        'main_stack_reserved_bytes':e(0x1c),'donor_worker_stack_sums_SUBSET_normal':stacks,
        'allocation_observations':peak,'donor_sbrk_plus_map_high_water_bytes':donor_peak,
        'runtime_peak_SUBSET_normal':max(s['runtime_peak'] for s in memory),
        'nonoverlapping_footprint_maxima_bound_bytes':peak['normal_footprint']+donor_peak+peak['linear_other']+model['image_and_stack_bytes'],
        'VRAM_not_part_of124MiB':peak['vram_used'],'regions_first_cycle':regions[:4],
        'limitations':['wrapper peaks cover external linked allocator entry points, not every libc-internal transient',
                      'stack allocation sizes are measured; deepest stack usage is not measured',
                      'sum of separate maxima is not a simultaneous object-live measurement',
                      'only original startup/UI checkpoint measured; gameplay peak remains unknown'],
        'one_factor_stages':stage_results,'mode_only_exheader_configuration_differences':diffs}
    donor=(P/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
    ph=struct.unpack_from('<I',donor,28)[0];size,count=struct.unpack_from('<HH',donor,42)
    loads=[]
    for i in range(count):
        kind,off,va,pa,fs,ms,flags,align=struct.unpack_from('<8I',donor,ph+i*size)
        if kind==1:loads.append({'virtual_address':va,'file_bytes':fs,'memory_bytes':ms,'BSS_bytes':ms-fs,'flags':flags,'alignment':align})
    measured['donor_ELF']={'file_bytes':len(donor),'image_allocation_bytes':4792320,'LOAD_segments':loads,
                           'trampolines_page_aligned_bytes':12288,'temporary_RGB565_comparison_bytes':192000,
                           'temporary_font_bytes':47036}
    (A/'memory-report.json').write_text(json.dumps(measured,indent=2)+'\n')
    before=json.loads((A/'preservation.json').read_text())['before']
    changes=[n for n,h in before.items() if not (P/n).is_file() or sha(P/n)!=h];assert not changes,changes
    audit=(A/'CIA-container-audit.txt').read_text()
    errors=[l for l in audit.splitlines() if ' ERROR]' in l]
    allowed=['Signature for Ticket was invalid','Signature for TitleMetaData was invalid','Signature for AccessDescriptor was invalid']
    assert len(errors)==3 and all(any(x in e for x in allowed) for e in errors)
    assert not any('Hash:' in l and '(FAIL)' in l for l in audit.splitlines())
    gate={'software_original_frame_Prod124_PASS':True,'ready_for_separate_hardware_approval':True,
        'hardware_tested':False,'hardware_run_authorized':False,'title_id':'000400000FDE7300',
        'CIA_sha256':sha(d/'native-game.cia'),'CIA_bytes':(d/'native-game.cia').stat().st_size,
        'final_CXI_clean_cycles':3,'final_CIA_payload_clean_cycles':3,
        'initial_third_reload_host_crash_preserved':True,'host_crash_signature_previously_seen_in_h1':True,
        'host_crash_fixed':False,'no_guest_memory_errors_in_successful_cycles':True,
        'six_kernel_joins_each_cycle':True,'baseline_files_protected':len(before),'baseline_changes':changes,
        'GPU_shader_thread_overlays_identical_to_h2':True,'original_assets_in_CIA':False,
        'RX_cache_semantics_on_real_hardware_proven':False,'full_gameplay_supported':False}
    (A/'release-gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    print(json.dumps({'commit_MiB':commit/1048576,'free_MiB':((124<<20)-commit)/1048576,
                     'normal_peak_MiB':peak['normal_live']/1048576,'other_linear_peak_MiB':peak['linear_other']/1048576,
                     'VRAM_peak_MiB':peak['vram_used']/1048576,'baseline_files':len(before),
                     'CIA_sha256':gate['CIA_sha256'],'CIA_bytes':gate['CIA_bytes']}))


if __name__=='__main__':main()
