"""Audit original-menu evidence without converting exploration into CRC PASS."""
import argparse
import json
from pathlib import Path
import sys
import zlib
from azahar_resource_store import sha,verify_dataset,STORE
from build_native_game_target_init import RUNTIME

P=Path(__file__).resolve().parents[1]
BASE=P/'3ds/build-native-game-v0.1.4r2-normal'
A=P/'analysis/native-game-menu-v0.1.5'

def read(p):return json.loads(p.read_text())
def packed(raw):
    out=bytearray()
    for b,g,r in zip(raw[0::3],raw[1::3],raw[2::3]):
        v=(r>>3)<<11|(g>>2)<<5|(b>>3);out.extend((v&255,v>>8))
    return bytes(out)

def audit_run(name):
    root=P/('analysis/azahar-native-menu-v0.1.5-'+name)
    result=read(root/'result.json')
    assert result['safety_passed'] and not result['invalid_memory_accesses']
    assert result['validation']['frame_status']=='FAIL' and result['validation']['expected_crc565']=='ea733050'
    assert result['validation']['safe_exit'] and result['validation']['cleanup_complete']
    assert result['kernel_joins']==result['handles_at_shutdown']>=5 and result['worker_handles_remaining']==0
    assert result['files_balanced']
    assert result['guest_result']['GL_error']==0 and result['guest_result']['failed_submits']==0
    build=P/('3ds/build-native-game-v0.1.5-'+name.split('-')[0])
    manifest=read(build/'build-manifest.json')
    assert result['CXI_sha256']==sha(build/'native-game.cxi')
    for n,digest in manifest['outputs_sha256'].items():assert sha(build/n)==digest,n
    for n,digest in manifest['headers_sha256'].items():assert sha(build/n)==digest,n
    for n,digest in manifest['runtime_sha256'].items():assert sha(build/n)==digest,n
    for n in RUNTIME:
        if n=='ds34_gpu_native.c':
            assert (build/n).read_text()==(BASE/n).read_text().replace('#define BUDGET (4u*1024*1024)','#define BUDGET (8u*1024*1024)')
        else:assert sha(build/n)==sha(BASE/n),n
    run=root/'Azahar/sdmc/3ds/ds-native-game-v0.1.5/run-0001'
    log=(run/'native-game.log').read_text()
    captures=[json.loads(l[12:]) for l in log.splitlines() if l.startswith('CAPTUREJSON ')]
    inputs=[json.loads(l[10:]) for l in log.splitlines() if l.startswith('INPUTJSON ')]
    assert len(captures)==len(inputs)>0
    partial_warm_traces=[]
    import re
    controls=[int(m[1]) for m in re.finditer(r'CONTROL frame=(\d+)',log)]
    for c,i in zip(captures,inputs):
        raw=(run/c['file']).read_bytes()
        assert len(raw)==288000 and c['raw_crc_a']==c['raw_crc_b']==f'{zlib.crc32(raw):08x}'
        assert c['crc565_a']==c['crc565_b']==f'{zlib.crc32(packed(raw)):08x}'
        assert (run/i['file']).stat().st_size==i['command_bytes']>0
        if i['capture_truncated']:
            # The bounded observer retains a prefix during initial font-atlas
            # creation (>1000 real draws). Never claim a complete GX proof for
            # it. Every stable menu/input capture must remain complete.
            assert i['draw_input_count']>=1000 and c['frame']<(min(controls) if controls else 3000)
            assert c['crc565_a'] not in ['7296717d','223b5e75','0ded835d']
            partial_warm_traces.append(c['frame'])
    memory=[json.loads(l[8:]) for l in log.splitlines() if l.startswith('MEMJSON ')]
    peaks=[json.loads(l[9:]) for l in log.splitlines() if l.startswith('PEAKJSON ')]
    assert all(m['query_result']==0 and m['commit']<=m['limit']==124*1024*1024 for m in memory)
    assert not any(m['donor_refusals'] or m['runtime_failures'] for m in memory)
    windows=result['timing_windows']
    steady=[w for w in windows if w['frame']>=3000]
    ms=sum(w['elapsed_ms'] for w in steady)
    summary={'safety_passed':True,'CXI_sha256':result['CXI_sha256'],'callbacks':result['validation']['callbacks_completed'],
        'capture_count':len(captures),'kernel_joins_at_shutdown':result['kernel_joins'],
        'independent_readbacks_and_internal_GPU_audits_passed':True,
        'complete_GX_captures':len(captures)-len(partial_warm_traces),'partial_initial_font_GX_captures':partial_warm_traces,
        'frame_status':'FAIL','GL_error':result['guest_result']['GL_error'],'host_renderer':result['host_renderer'],
        'cpu_percent':result['cpu_percent'],'steady_FPS_guest_ticks':sum(w['callbacks'] for w in steady)*1000/ms if ms else None,
        'steady_callback_ms':sum(w['callback_ms'] for w in steady)/sum(w['callbacks'] for w in steady) if steady else None,
        'steady_present_ms':sum(w['present_ms'] for w in steady)/sum(w['callbacks'] for w in steady) if steady else None,
        'steady_diagnostic_ms':sum(w['diagnostic_ms'] for w in steady)/sum(w['callbacks'] for w in steady) if steady else None,
        'steady_vblank_wait_ms':sum(w['vblank_wait_ms'] for w in steady)/sum(w['callbacks'] for w in steady) if steady else None,
        'max_normal_allocated':max(m['normal_allocated'] for m in memory),'min_linear_free':min(m['linear_free'] for m in memory),
        'max_normal_footprint':max(m['normal_footprint'] for m in peaks),
        'max_linear_used':max(m['linear_used'] for m in peaks),
        'linear_free_at_peak':int(manifest.get('memory_MiB',{}).get('linear',96)*1024*1024)-max(m['linear_used'] for m in peaks),
        'last_C3D_drawing_ms_samples':[w['last_c3d_drawing_ms'] for w in steady],
        'max_donor_brk':max(m['donor_brk_peak'] for m in memory),'max_donor_mmap_pages':max(m['donor_map_peak_pages'] for m in memory),
        'max_callback_window_ms':max(w['callback_ms'] for w in windows),'control_events':[l for l in log.splitlines() if l.startswith('CONTROL ')],
        'close_state':result['close_state'],'private_result_sha256':sha(root/'result.json')}
    if manifest.get('test_HOME_callback'):
        assert result['close_state']['home_pending'] and result['close_state']['close_pending'] and result['close_state']['source']=='APT'
        assert 'APT HOME handover AFTER quiescence' in log and 'APT HOME returned should_close=1' in log
    if 'MENU_ONLY original confirm callback=' in log:
        import re
        match=re.search(r'MENU_ONLY original confirm callback=(\d+) tail_complete=(\d+)',log)
        assert match and int(match[2])-int(match[1])==2
        summary['original_confirm_callback']=int(match[1]);summary['bounded_tail_complete']=int(match[2])
        if int(match[1])==4321:
            frames={c['frame']:c for c in captures}
            for frame,crc in [(3360,'7296717d'),(3480,'0ded835d'),(3720,'223b5e75'),(3960,'0ded835d'),(4200,'0ded835d')]:
                assert frames[frame]['crc565_a']==crc,(frame,frames[frame]['crc565_a'])
            for action in ['button=DOWN','button=UP','B=1 module=600 key=4','B=0 module=600 key=4','button=A']:
                assert action in log,action
            summary['menu_button_sequence_confirmed']=True
            summary['B_visual_back_action_confirmed']=False
            summary['menu_images']={str(f):{'raw_sha256':sha(run/frames[f]['file']),'crc565':frames[f]['crc565_a']} for f in [3360,3480,3720,3960,4200]}
    return summary

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--runs',required=True)
    args=ap.parse_args();names=args.runs.split(',');assert all(n.replace('-','').isalnum() for n in names)
    A.mkdir(exist_ok=True)
    rows={n:audit_run(n) for n in names}
    # Frozen startup verifier and every recorded protected input stay unchanged.
    protected=read(P/'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for n,digest in protected.items():assert sha(P/n)==digest,n
    old=read(BASE/'build-manifest.json')
    assert sha(P/'tests/native_game_progress.c')==old['source_sha256']
    for n,digest in old['headers_sha256'].items():assert sha(P/'tests'/n)==digest
    for n,digest in old['outputs_sha256'].items():assert sha(BASE/n)==digest
    dataset=STORE/'datasets/a46655efb24fab59c7649322986eea2ae0a5827454bca4c5e71be3d13818ceef'
    verified=verify_dataset(dataset)
    master=P/'private/native-game-v0.1.0-sd/3ds/deadspace'
    assert all(sha(master/e['path'])==e['sha256'] for e in verified['files'])
    result={'audited':True,'runs':rows,'frozen_protected_files':len(protected),
        'strict_verifier_unchanged':True,'baseline_crc':'ea733050','resource_files_verified':len(verified['files']),
        'hardware_tested':False,'image_validation_passed':False}
    (A/'software-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
