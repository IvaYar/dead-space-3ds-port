"""Read-only audit of original scene evidence; writes numerical summaries only."""
import json
from pathlib import Path
import re
import zlib
import numpy as np
from azahar_resource_store import sha, STORE, verify_dataset
from audit_native_game_hid import tagged
from inspect_android_sensor import Dex
P=Path(__file__).resolve().parents[1]
A=P/'analysis/native-first-scene'

def read(p):return json.loads(p.read_text(encoding='utf-8'))

def audit(revision,attempt):
    root=P/('analysis/azahar-native-menu-v0.1.7-'+revision+'-'+attempt)
    d=root/'Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001';build=P/('3ds/build-native-game-v0.1.7-'+revision)
    result=read(root/'result.json');m=read(build/'build-manifest.json');log=(d/'native-game.log').read_text()
    assert result['safety_passed'] and result['collector_joined'] and result['files_balanced']
    assert result['guest_result']['GL_error']==0 and result['guest_result']['failed_submits']==0
    assert result['worker_handles_remaining']==0 and result['kernel_joins']>=5 and not result['invalid_memory_accesses']
    assert result['validation']['frame_status']=='FAIL' and result['validation']['expected_crc565']=='ea733050'
    assert m['scene_probe'] and m['emulator_only'] and m['clean_backing'] and not m['CIA_created'] and not list(build.glob('*.cia'))
    assert sha(build/'native-game.cxi')==result['CXI_sha256']
    for group in ['outputs_sha256','headers_sha256','runtime_sha256','loading_sources_sha256','generated_sources_sha256']:
        for name,digest in m[group].items():assert sha(build/name)==digest,name
    for name in ['ds27_pages_3ds.c','native_menu_page_crc.h','native_hid_collector.h','native_hid_queue.h','native_menu_hid_controls.h','native_menu_engine_state.h']:
        assert sha(build/name)==sha(P/'3ds/build-native-game-v0.1.7-release'/name),name
    assert log.index('AUDIO 504 completion=0')<log.index('JOB 302 completion=0')
    assert log.index('SHUTDOWN live workers=0')>log.index('AUDIO_SINK')
    captures=tagged(log,'CAPTUREJSON');inputs=tagged(log,'INPUTJSON')
    for c in captures:
        raw=(d/c['file']).read_bytes();assert len(raw)==288000
        assert '%08x'%(zlib.crc32(raw)&0xffffffff)==c['raw_crc_a']==c['raw_crc_b']
        rgb=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3).astype(np.uint16)
        quant=((rgb[:,2]>>3)<<11)|((rgb[:,1]>>2)<<5)|(rgb[:,0]>>3)
        assert '%08x'%(zlib.crc32(quant.astype('<u2').tobytes())&0xffffffff)==c['crc565_a']==c['crc565_b']
    assert not any(c['capture_truncated'] for c in inputs)
    baseline=P/'analysis/azahar-native-menu-v0.1.7-loadclean-measure/Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001'
    paired=[]
    for c in captures:
        p=baseline/c['file']
        if 3120<=c['frame']<=4320 and p.exists():
            if p.read_bytes()==(d/c['file']).read_bytes():paired.append(c['frame'])
    assert len(paired)>=8,paired
    callbacks=tagged(log,'CALLBACKJSON');warm=max((c for c in callbacks if c['frame']<4320),key=lambda c:c['ms'])
    assert warm['page_saves']==38 and warm['page_loads']==166
    pages=[read_line for read_line in map(json.loads,(d/'loading-pages.jsonl').read_text().splitlines())]
    ev=[e for e in pages if e['frame']==warm['frame']]
    assert all(e['result']==0 for e in pages)
    assert sum(e['kind']==1 for e in ev)==38 and sum(e['kind']==2 for e in ev)==166
    mem=tagged(log,'MEMJSON');peak=tagged(log,'PEAKJSON')[-1]
    assert peak['linear_used']<=104857600 and max(x['commit'] for x in mem)<=130023424
    assert all(x['donor_refusals']==0 for x in mem)
    invalid=re.findall(r'SCENE_STATE .*invalid_frees=(\d+)',log);assert invalid and set(invalid)=={'0'}
    request=float(re.search(r'HIDSESSION original_engine_request ms=([0-9.]+)',log)[1])
    ready=float(re.search(r'HID_BARRIER ms=([0-9.]+) ready=1',log)[1])
    confirm=int(re.search(r'HIDACK .*frame=(\d+).*phase=3 closing=1',log)[1])
    frame=result['guest_result']['frame']
    scene=[c for c in callbacks if c['frame']>confirm]
    resources=sorted(set(re.findall(r'^SCENE_RESOURCE .*path=(.*)$',log,re.M)))
    objects=sorted(set(re.findall(r'SCENE_OBJECT app_offset=(\w+) vtable_offset=(\w+)',log)))
    budget=re.findall(r'SCENE_BUDGET frame=(\d+) limit_ms=(\d+) elapsed_ms=(\d+)',log)
    if m.get('test_HOME_callback'):
        assert 'APT HOME handover AFTER quiescence' in log
    return {'safety_passed':True,'CXI_sha256':result['CXI_sha256'],'callbacks_completed':frame,
            'confirmation_ack_callback':confirm,'callbacks_after_ack':frame-confirm,
            'exit_reason':result['guest_result']['reason'],'scene_time_budget_seconds':m['scene_seconds'],
            'budget_record':budget,'elapsed_host_seconds':result['elapsed_host_seconds'],
            'engine_request_to_ready_ms':round(ready-request,3),'menu_warm_callback':warm,
            'menu_raw_pairs_byte_identical':paired,'captures_crc_verified':len(captures),
            'scene_capture_frames':[c['frame'] for c in captures if c['frame']>confirm],
            'peak':peak,'max_commit':max(x['commit'] for x in mem),
            'linear_headroom':104857600-peak['linear_used'],
            'donor_brk_peak':max(x['donor_brk_peak'] for x in mem),
            'donor_map_peak_pages':max(x['donor_map_peak_pages'] for x in mem),
            'runtime_allocation_refusals_including_retries':max(x['runtime_failures'] for x in mem),
            'stable_menu_window':next(p for p in tagged(log,'PERFJSON') if p['frame']==3240),
            'scene_callbacks_profiled':[{'frame':c['frame'],'ms':c['ms'],'draws':c['ops'][0]['calls'],
                'texture_allocations':len(re.findall(r'^TEXALLOC frame='+str(c['frame'])+r' ',log,re.M)),
                'gpu_begin_draw_ms':c['ops'][7]['ms'],'resident_ms':c['ops'][9]['ms'],
                'page_loads':c['page_loads'],'page_saves':c['page_saves']} for c in scene],
            'observed_resources':resources,'observed_app_objects':objects,'new_HOME_fixture':bool(m.get('test_HOME_callback'))}

def main():
    A.mkdir(exist_ok=True)
    rows={key:audit(*key.split(':')) for key in ['scene14:first','scene15home:home','scene16:repeat']}
    protected=read(P/'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for name,digest in protected.items():assert sha(P/name)==digest,name
    stores=[]
    for folder in (STORE/'datasets').iterdir():
        if (folder/'manifest.json').exists():stores.append(verify_dataset(folder))
    assert stores
    for manifest in stores:
        for entry in manifest['files']:
            assert sha(P/'private/native-game-v0.1.0-sd/3ds/deadspace'/entry['path'])==entry['sha256']
    fixture=read(P/'analysis/scene-gpu-test-f5/result.json');assert fixture['passed']
    contracts=read(P.parent/'.local/native-scene-contracts-s14pressure/result.json');assert contracts['passed']
    dex_data=(P/'analysis/android-abi/candidate-sd-classes.dex').read_bytes();dex=Dex(dex_data)
    cls=dex.inspect('Lcom/ea/EAAudioCore/AndroidEAAudioCore;')
    init=next(m for m in cls['methods'] if m['name']=='Init');assert init['signature']=='(Landroid/media/AudioTrack;III)V'
    failed_root=P/'analysis/azahar-native-menu-v0.1.7-scene04-combine'
    host=(failed_root/'azahar-host.log').read_text(errors='replace')
    assert 'unmapped Read8 @ 0x0000003C' in host and 'unmapped Read32 @ 0x00000030' in host
    experiments=[]
    for p in sorted((P/'analysis').glob('azahar-native-menu-v0.1.7-scene*')):
        r=read(p/'result.json') if (p/'result.json').exists() else {}
        timeout=read(p/'timeout.json') if (p/'timeout.json').exists() else None
        experiments.append({'name':p.name,'safety_passed':r.get('safety_passed',False),'timeout':timeout,
                            'reason':r.get('guest_result',{}).get('reason'),'original_data_retained':True})
    result={'software_scene_checks_passed':True,'Isaac_seen':False,'playable_gameplay_confirmed':False,
            'original_prologue_seen':True,'audio_NULL_reproduced':True,'original_audio_init_removes_reproduced_NULL_reads':True,
            'audible_audio_backend':False,'fog_COMBINE_fixture':fixture,'ARM_contracts':contracts,
            'protected_files_verified':len(protected),'store_files_verified':sum(len(m['files']) for m in stores),
            'runs':rows,'experiments':experiments,'CIA_created':False,'hardware_tested':False,
            'hardware_authorized':False,'ready_for_experimental_CIA':False,
            'blockers':['Opening prologue only; no Isaac or player control yet.','Scene canonical/GPU atlas working set thrashes; frequent allocator refusals recovered by safe paging.','Linear headroom remains 222336 bytes.','PCM sink is emulator research only.'],
            'audio_contract':{'DEX_source_sha256':sha(P/'analysis/android-abi/candidate-sd-classes.dex'),
                'native_Init_signature':init['signature'],'integer_argument_order':['bufferFrames','channels','sampleRate'],
                'emulator_values':[1024,2,22050],'PCM_method':'AudioTrack.write([SII)I; signed PCM16 sample count',
                'VM_DetachCurrentThread_required':True,'shutdown_order':['drain loaders','Pause/Stop','stop audio while jobs remain live','stop jobs','stop periodic','Release audio globals','JNI cleanup','GPU drain/Fini'],
                'old_NULL_donor_offsets':['265f80','265f98']}}
    (A/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'runs':{k:{n:v[n] for n in ['callbacks_completed','callbacks_after_ack','engine_request_to_ready_ms','max_commit','linear_headroom','runtime_allocation_refusals_including_retries']} for k,v in rows.items()},'protected':len(protected),'contracts':contracts['tests_run']},indent=2))

if __name__=='__main__':main()
