"""Audit saved texture working-set runs without starting the emulator."""
import json
from pathlib import Path
import re
import statistics
from collections import Counter

from audit_native_scene import audit, tagged
from azahar_resource_store import sha, STORE, verify_dataset

P=Path(__file__).resolve().parents[1]
A=P/'analysis/native-scene-textures'


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def inspect(revision,attempt):
    summary=audit(revision,attempt)
    root=P/('analysis/azahar-native-menu-v0.1.7-'+revision+'-'+attempt)
    run=root/'Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001'
    log=(run/'native-game.log').read_text()
    events=[json.loads(l) for l in (run/'scene-textures.jsonl').read_text().splitlines()]
    callbacks=tagged(log,'CALLBACKJSON')
    sizes={e['object']:e['bytes'] for e in events if e['kind']==4}
    has_visible_trace=any(e['kind']==5 for e in events)
    byframe={}
    for e in events:
        byframe.setdefault(e['frame'],[]).append(e)
    rows=[]
    for c in callbacks:
        if c['frame']<=summary['confirmation_ack_callback']:
            continue
        ev=byframe.get(c['frame'],[])
        allocations=len(re.findall(r'^TEXALLOC frame='+str(c['frame'])+r' ',log,re.M))
        visible={e['object'] for e in ev if e['kind']==5}
        rows.append({'frame':c['frame'],'ms':c['ms'],'page_loads':c['page_loads'],
                     'page_saves':c['page_saves'],'page_read_bytes':c['ops'][11]['bytes'],
                     'gpu_allocations':allocations,'gpu_upload_bytes':sum(e['bytes'] for e in ev if e['kind']==4) if ev else (0 if not allocations else None),
                     'gpu_evictions':sum(e['kind']==3 for e in ev) if ev else None,
                     'gpu_dirty_evictions':sum(e['kind']==3 and e['reason']==1 for e in ev) if ev else None,
                     'gpu_cached_bytes':max((e['cached'] for e in ev),default=None),
                     'visible_texture_count':len(visible) if has_visible_trace and ev else None,
                     'visible_texture_bytes':sum(sizes[o] for o in visible) if has_visible_trace and ev else None})
    stable=[r for r in rows if 4328<=r['frame']<=4338]
    assert stable
    summary.update(callbacks=rows,
        stable_4328_4338={k:{'median':statistics.median(r[k] for r in stable),
                            'min':min(r[k] for r in stable),'max':max(r[k] for r in stable)}
                          for k in ['ms','page_loads','gpu_allocations','gpu_upload_bytes','gpu_evictions']},
        new_resource_opens_after_prologue_start=sorted(set(re.findall(r'^SCENE_RESOURCE .*path=(.*)$',log,re.M))),
        new_isaac_resource_open=bool(re.search(r'^SCENE_RESOURCE .*?(?:isaac\.m3g|01_gov_01\.scene\.sb)',log,re.M)),
        boundary_min_linear_free=min(m['linear_free'] for m in tagged(log,'MEMJSON') if m['frame']>4323),
        trace_sha256=sha(run/'scene-textures.jsonl'))
    # Addresses and full resource manifests remain in the private run trees.
    return summary


def capacity_model():
    """Read-only capacity model, not a GPU allocation experiment."""
    p=P/'analysis/azahar-native-menu-v0.1.7-visible05-detailed/Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001/scene-textures.jsonl'
    events=[json.loads(l) for l in p.read_text().splitlines()]
    sizes={e['object']:e['bytes'] for e in events if e['kind']==4}
    sequence=[e['object'] for e in events if e['frame']==4430 and e['kind']==6]
    assert sequence
    results=[]
    for mib in [8,10,12]:
        cache={};stamp=0
        for repeat in range(4):
            misses=upload_bytes=0
            for obj in sequence:
                stamp+=1
                if obj not in cache:
                    misses+=1;upload_bytes+=sizes[obj]
                    while sum(sizes[k] for k in cache)+sizes[obj]>mib*1048576:
                        del cache[min(cache,key=cache.get)]
                cache[obj]=stamp
        results.append({'capacity_mib':mib,'misses':misses,'upload_bytes':upload_bytes})
    return {'source_frame':4430,'requests':len(sequence),'unique_textures':len(Counter(sequence)),
            'working_set_bytes':sum(sizes[o] for o in set(sequence)),
            'repeated_sequence_LRU':results,'cache_budgets_actually_changed':False,
            'limitation':'Capacity model omits VRAM placement, simultaneous sampler pins and allocator fragmentation.'}


def function_body(source,name):
    match=re.search(r'\b'+name+r'\([^;{}]*\)\s*\{',source)
    assert match,name
    start=match.end()-1;depth=1;end=start+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]


def main():
    A.mkdir(exist_ok=True)
    keys=['thrash03:baseline','visible04:onward','visible05:detailed','visible05:repeat','visible05home:home']
    runs={key:inspect(*key.split(':')) for key in keys}
    base=runs['thrash03:baseline']['stable_4328_4338']
    after=runs['visible05:detailed']['stable_4328_4338']
    ratio=base['ms']['median']/after['ms']['median']
    assert ratio>25 and after['page_loads']['max']==0 and after['gpu_allocations']['max']==0
    assert after['gpu_upload_bytes']['max']==0
    late=[r for r in runs['visible05:detailed']['callbacks'] if r['frame']>=4420]
    assert late and min(r['visible_texture_bytes'] for r in late)>8*1024*1024
    protected=read(P/'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for name,digest in protected.items():
        assert sha(P/name)==digest,name
    store_count=0
    for folder in (STORE/'datasets').iterdir():
        if not (folder/'manifest.json').exists():
            continue
        manifest=verify_dataset(folder)
        for entry in manifest['files']:
            assert sha(P/'private/native-game-v0.1.0-sd/3ds/deadspace'/entry['path'])==entry['sha256']
        store_count+=len(manifest['files'])
    fixture=read(P/'analysis/scene-gpu-test-projective06/result.json')
    contracts=read(P.parent/'.local/native-scene-contracts-visible03/result.json')
    assert fixture['passed'] and contracts['passed']
    fixture_build=P/'3ds/build-scene-gpu-test-projective06'
    fixture_manifest=read(fixture_build/'build-manifest.json')
    assert sha(fixture_build/'native-game.cxi')==fixture_manifest['cxi_sha256']
    for name,digest in fixture_manifest['inputs'].items():
        source=P/name
        if sha(source)!=digest:
            source=P.parent/'.local/source-snapshots'/digest/Path(name).name
        assert sha(source)==digest,name
    assert sha(P.parent/'.local/native-scene-contracts-visible03/core-test.elf')==contracts['ELF_sha256']
    old=P/'3ds/build-native-game-v0.1.7-scene16'
    new=P/'3ds/build-native-game-v0.1.7-visible05'
    for name,digest in contracts['optimized_source_sha256'].items():
        assert sha(new/name)==digest,name
    for name in ['ds10_jni.c','ds15_textures.c','ds22_draw.c','ds26_framebuffer.c','ds27_pages_3ds.c','native_menu_page_crc.h','native_hid_collector.h','native_hid_queue.h','native_menu_hid_controls.h']:
        assert sha(old/name)==sha(new/name),name
    untouched_gpu_functions=['release_staging','sync_gpu','frame','ds34_present','ds34_native_finish']
    for name in untouched_gpu_functions:
        assert function_body((old/'ds34_gpu_native.c').read_text(),name)==function_body((new/'ds34_gpu_native.c').read_text(),name),name
    old_manifest=read(old/'build-manifest.json')
    for group in ['outputs_sha256','headers_sha256','runtime_sha256','generated_sources_sha256']:
        for name,digest in old_manifest[group].items():
            assert sha(old/name)==digest,name
    for rev in ['visible05','visible05home']:
        assert not list((P/('3ds/build-native-game-v0.1.7-'+rev)).glob('*.cia'))
    result={'software_checks_passed':True,'initial_redundant_thrashing_eliminated':True,
            'all_prologue_thrashing_eliminated':False,'Isaac_seen':False,'playable_gameplay_confirmed':False,
            'runs':runs,'stable_callback_speedup':round(ratio,3),
            'stable_callback_time_reduction_percent':round((1-1/ratio)*100,3),
            'late_visible_working_set_bytes':sorted(set(r['visible_texture_bytes'] for r in late)),
            'late_upload_bytes_per_callback':sorted(set(r['gpu_upload_bytes'] for r in late)),
            'late_page_loads_per_callback':sorted(set(r['page_loads'] for r in late)),
            'gpu_budget_bytes':8388608,'cpu_budget_bytes':6291456,
            'protected_files_verified':len(protected),'master_and_store_resources_verified':store_count,
            'gpu_fixture':fixture,'ARM_contracts':contracts,'hardware_tested':False,'CIA_created':False,
            'capacity_model':capacity_model(),'unchanged_GPU_lifetime_functions':untouched_gpu_functions,
            'frozen_scene16_build_verified':True,
            'original_scene_replaced':False,'strict_frame_CRC_weakened':False,
            'comparison_limit':'Main-menu raw frames are byte identical; moving prologue frames have different clocks. Pixel proof uses independent CPU/PICA fixtures, not an asserted golden prologue CRC.',
            'remaining_barrier':'Later visible station geometry needs >32 MiB RGBA8 texture storage; the unchanged 8 MiB GPU cache cannot retain it. A bounded regional or lossless representation is needed before long continuation.'}
    (A/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['software_checks_passed','stable_callback_speedup','stable_callback_time_reduction_percent','late_visible_working_set_bytes','late_page_loads_per_callback','protected_files_verified','master_and_store_resources_verified']},indent=2))


if __name__=='__main__':
    main()
