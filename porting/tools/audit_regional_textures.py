"""Read-only UV models and independent lossless Morton backing verification."""
from collections import Counter
import json
import math
from pathlib import Path
import re
import statistics
import struct
import zlib

import numpy as np
from azahar_resource_store import sha, STORE, verify_dataset
from audit_native_scene import tagged
from audit_scene_textures import function_body

P=Path(__file__).resolve().parents[1]
A=P/'analysis/regional-texture-residency'


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def run_root(rev,attempt):
    root=P/('analysis/azahar-native-menu-v0.1.7-'+rev+'-'+attempt)
    return root,root/'Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001'


def inspect(rev,attempt,require_safe=True):
    root,d=run_root(rev,attempt);log=(d/'native-game.log').read_text()
    result=read(root/'result.json');m=read(P/('3ds/build-native-game-v0.1.7-'+rev+'/build-manifest.json'))
    if require_safe:assert result['safety_passed'] and result['guest_result']['safe_exit']
    assert result['guest_result']['GL_error']==0 and result['guest_result']['failed_submits']==0 and not result['invalid_memory_accesses']
    invalid=re.findall(r'SCENE_STATE .*invalid_frees=(\d+)',log);assert invalid and set(invalid)=={'0'}
    assert result['validation']['frame_status']=='FAIL' and result['validation']['expected_crc565']=='ea733050'
    assert m['clean_backing'] and m['emulator_only'] and not m['CIA_created']
    build=P/('3ds/build-native-game-v0.1.7-'+rev)
    assert not list(build.glob('*.cia')) and sha(build/'native-game.cxi')==result['CXI_sha256']
    for group in ['outputs_sha256','headers_sha256','runtime_sha256','generated_sources_sha256']:
        for n,h in m[group].items():assert sha(build/n)==h,n
    for n in ['ds10_jni.c','ds15_textures.c','ds22_draw.c','ds26_framebuffer.c','ds27_pages_3ds.c','native_menu_page_crc.h','native_hid_collector.h','native_hid_queue.h','native_menu_hid_controls.h','ds34_shader.h']:
        assert sha(build/n)==sha(P/'3ds/build-native-game-v0.1.7-visible05'/n),n
    captures=tagged(log,'CAPTUREJSON');inputs=tagged(log,'INPUTJSON')
    for c in captures:
        raw=(d/c['file']).read_bytes();assert len(raw)==288000
        assert '%08x'%(zlib.crc32(raw)&0xffffffff)==c['raw_crc_a']==c['raw_crc_b']
        bgr=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3).astype(np.uint16)
        quant=((bgr[:,2]>>3)<<11)|((bgr[:,1]>>2)<<5)|(bgr[:,0]>>3)
        assert '%08x'%(zlib.crc32(quant.astype('<u2').tobytes())&0xffffffff)==c['crc565_a']==c['crc565_b']
    assert not any(i['capture_truncated'] for i in inputs)
    if result['safety_passed']:
        assert result['kernel_joins']>=5 and not result['worker_handles_remaining']
        assert result['files_balanced'] and result['collector_joined'] and result['close_state']['cleanup_complete']
        assert log.index('AUDIO 504 completion=0')<log.index('JOB 302 completion=0')
    menu=[];menu_unmatched=[];baseline=P/'analysis/azahar-native-menu-v0.1.7-loadclean-measure/Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001'
    for c in captures:
        f=baseline/c['file']
        if 3120<=c['frame']<=4320 and f.exists():
            (menu if f.read_bytes()==(d/c['file']).read_bytes() else menu_unmatched).append(c['frame'])
    assert len(menu)>=8
    callbacks=tagged(log,'CALLBACKJSON');warm=max((c for c in callbacks if c['frame']<4320),key=lambda c:c['ms'])
    assert warm['page_saves']==38 and warm['page_loads']==166
    alloc=Counter(int(f) for f in re.findall(r'^TEXALLOC frame=(\d+) ',log,re.M))
    ev=[json.loads(l) for l in (d/'scene-textures.jsonl').read_text().splitlines()]
    uploaded=Counter();evicted=Counter()
    for e in ev:
        if e['kind']==4:uploaded[e['frame']]+=e['bytes']
        if e['kind']==3:evicted[e['frame']]+=1
    morton={e['frame']:e for e in tagged(log,'MORTONJSON')}
    times={e['frame']:e for e in tagged(log,'MORTONTIMEJSON')}
    rows=[]
    for c in callbacks:
        if c['frame']<4324:continue
        s=morton.get(c['frame'],{})
        rows.append({'frame':c['frame'],'ms':c['ms'],'canonical_loads':c['page_loads'],
                     'canonical_saves':c['page_saves'],'gpu_allocations':alloc[c['frame']],
                     'gpu_evictions':evicted[c['frame']],'gpu_population_bytes':uploaded[c['frame']],
                     'morton_loads':s.get('loads',0),'morton_saves':s.get('saves',0),
                     'morton_read_bytes':s.get('read_bytes',0),'morton_write_bytes':s.get('write_bytes',0),
                     'morton_failures':s.get('failures',0),'morton_times':times.get(c['frame'])})
    assert not any(r['morton_failures'] for r in rows)
    peak=tagged(log,'PEAKJSON')[-1];mem=tagged(log,'MEMJSON')
    assert peak['linear_used']<=104857600 and max(e['commit'] for e in mem)<=130023424
    ack=int(re.search(r'HIDACK .*frame=(\d+).*phase=3 closing=1',log)[1])
    request=float(re.search(r'HIDSESSION original_engine_request ms=([0-9.]+)',log)[1]);ready=float(re.search(r'HID_BARRIER ms=([0-9.]+) ready=1',log)[1])
    return {'safety_passed':result['safety_passed'],'reason':result['guest_result']['reason'],
            'GL_error':result['guest_result']['GL_error'],'callbacks_completed':result['guest_result']['frame'],
            'last_returned_callback_in_log':max(c['frame'] for c in callbacks),'original_A_ACK':ack,
            'host_seconds':result['elapsed_host_seconds'],'guest_budget_seconds':m['scene_seconds'],
            'host_deadline_seconds':result.get('host_deadline_seconds',180),'peak':peak,
            'max_commit':max(e['commit'] for e in mem),'min_scene_linear_free':min(e['linear_free'] for e in mem if e['frame']>4323),
            'donor_arena_peak':max(e['donor_brk_peak']+4096*e['donor_map_peak_pages'] for e in mem),
            'donor_refusals':max(e['donor_refusals'] for e in mem),'runtime_refusals':max(e['runtime_failures'] for e in mem),
            'captures_verified':len(captures),'menu_pairs_byte_identical':len(menu),
            'menu_frames_not_byte_identical':menu_unmatched,
            'kernel_joins':result['kernel_joins'],'worker_handles_remaining':result['worker_handles_remaining'],
            'invalid_memory_accesses':result['invalid_memory_accesses'],'engine_ready_ms':round(ready-request,3),
            'gpu_allocation_refusals':len(re.findall(r'^TEXALLOC .*ok=0$',log,re.M)),
            'warm_callback_ms':warm['ms'],'callbacks':rows,
            'new_resources':sorted(set(re.findall(r'^SCENE_RESOURCE .*path=(.*)$',log,re.M))),
            'CXI_sha256':result['CXI_sha256']}


def uv_model():
    _,d=run_root('regionuv01','baseline');raw=[json.loads(l) for l in (d/'scene-uv.jsonl').read_text().splitlines()]
    rows=[r for r in raw if r['frame']==4430];assert rows
    def axis(lo,hi,w,wrap,quantum):
        if wrap==0x812f:lo=max(0,min(1,lo));hi=max(0,min(1,hi))
        low=math.floor(lo*w)-1;high=math.floor(hi*w)+1
        if wrap==0x812f:low=max(0,low);high=min(w-1,high)
        origin=math.floor(low/quantum)*quantum;n=max(8,1<<(high-origin).bit_length())
        return (0,max(8,w)) if n>=w else (origin,n)
    models=[]
    for quantum in [1,16,32,64]:
        seq=[]
        for r in rows:
            x,w=axis(r['uv'][0],r['uv'][2],r['w'],r['wrap'][0],quantum)
            y,h=axis(r['uv'][1],r['uv'][3],r['h'],r['wrap'][1],quantum)
            seq.append((r['name'],x,y,w,h,*r['wrap']))
        cache={};stamp=0
        for repeat in range(4):
            misses=uploaded=0
            for key in seq:
                stamp+=1
                if key not in cache:
                    misses+=1;uploaded+=key[3]*key[4]*4
                    while len(cache)>=32 or sum(k[3]*k[4]*4 for k in cache)+key[3]*key[4]*4>8388608:
                        del cache[min(cache,key=cache.get)]
                cache[key]=stamp
        models.append({'origin_quantum_texels':quantum,'keys':len(set(seq)),
                       'working_set_bytes':sum(k[3]*k[4]*4 for k in set(seq)),
                       'steady_LRU_misses':misses,'steady_population_bytes':uploaded})
    return {'source_frame':4430,'draw_units':len(rows),'textures':len(set(r['name'] for r in rows)),
            'triangle_unit_samples':sum(r['triangles'] for r in rows),'sampled_frames':len(set(r['frame'] for r in raw)),
            'uv_outside_unit_square_draws':sum(any(v<0 or v>1 for v in r['uv']) for r in rows),
            'models':models,'cropping_deployed':False,
            'reason':'Even rectangles of surviving triangles plus filtering halo exceed 8 MiB and CACHE32; geometry subdivision would add seam and projective interpolation risk.'}


def lz4_decode(data,expected):
    out=bytearray();i=0
    while i<len(data):
        token=data[i];i+=1;length=token>>4
        if length==15:
            while True:
                assert i<len(data);v=data[i];i+=1;length+=v
                if v!=255:break
        assert i+length<=len(data);out.extend(data[i:i+length]);i+=length
        if i==len(data):break
        assert i+2<=len(data);offset=int.from_bytes(data[i:i+2],'little');i+=2
        assert 0<offset<=len(out);length=(token&15)+4
        if (token&15)==15:
            while True:
                assert i<len(data);v=data[i];i+=1;length+=v
                if v!=255:break
        tail=out[-offset:];q,r=divmod(length,offset);out.extend(tail*q+tail[:r])
        assert len(out)<=expected
    assert len(out)==expected
    return bytes(out)


def decode_snapshot(path):
    data=path.read_bytes();magic,version,size,crc=struct.unpack_from('<4I',data)
    assert magic==0x504d5344 and version in [1,2] and size<=4194304
    pos=16;block_limit=65536
    if version==2:block_limit=struct.unpack_from('<I',data,16)[0];pos=20
    out=bytearray()
    while len(out)<size:
        n,packed,encoded_crc=struct.unpack_from('<3I',data,pos);pos+=12
        assert n==min(block_limit,size-len(out)) and 0<packed<=n+n//255+16
        encoded=data[pos:pos+packed];assert len(encoded)==packed and zlib.crc32(encoded)==encoded_crc
        out.extend(lz4_decode(encoded,n));pos+=packed
    assert pos==len(data) and zlib.crc32(out)==crc
    return bytes(out),crc


def verify_texels(rev,attempt):
    root,d=run_root(rev,attempt);events=[json.loads(l) for l in (d/'scene-textures.jsonl').read_text().splitlines()]
    proofs={}
    for e in events:
        if e['kind']==7 and e['backing']:proofs.setdefault(e['bytes'],[]).append(e)
    card=root/'Azahar/sdmc/3ds/deadspace/test-output';count=compared=raw_bytes=0
    for f in (card/'morton-pages').glob('*.bin'):
        token=int(f.stem.split('-')[-1],16);pixels,crc=decode_snapshot(f);count+=1;raw_bytes+=len(pixels)
        for e in proofs.get(token,[]):
            canonical=card/('texture-pages/page-%08x.bin'%e['backing'])
            if not canonical.exists():continue
            p=canonical.read_bytes();size,expected=struct.unpack_from('<II',p);p=p[8:]
            assert len(p)==size==e['w']*e['h']*4 and zlib.crc32(p)==expected
            pw=max(8,1<<(e['w']-1).bit_length());ph=max(8,1<<(e['h']-1).bit_length())
            index=np.arange(pw*ph,dtype=np.uint32);tile=index//64;m=index&63
            x=(tile%(pw//8))*8+((m&1)|((m>>1)&2)|((m>>2)&4))
            y=ph-1-((tile//(pw//8))*8+(((m>>1)&1)|((m>>2)&2)|((m>>3)&4)))
            x=x%e['w'] if e['wrap'][0]==0x2901 else np.minimum(x,e['w']-1)
            y=y%e['h'] if e['wrap'][1]==0x2901 else np.minimum(y,e['h']-1)
            rgba=np.frombuffer(p,dtype=np.uint8).reshape(e['h'],e['w'],4)
            morton=rgba[y,x][:,[3,2,1,0]].tobytes()
            assert pixels==morton and crc==e['reason'],f
            compared+=1;break
    assert count and compared>=20
    return {'snapshots_independently_decoded':count,'bytes_decoded':raw_bytes,
            'bytewise_canonical_to_Morton_comparisons':compared,
            'host_decoder':'Independent Python LZ4 block decoder; host zlib CRC32; NumPy Morton reference'}


def window(run,low,high):
    rows=[c for c in run['callbacks'] if low<=c['frame']<=high];assert rows
    return {k:statistics.median(c[k] for c in rows) for k in ['ms','canonical_loads','gpu_allocations','gpu_evictions','gpu_population_bytes','morton_loads','morton_read_bytes']}


def main():
    keys=['regionuv01:baseline','morton02:first','mortonfast03:first','morton04:first','morton05:repeat','morton05home:home2','morton05:long2','morton06:chapter']
    runs={k:inspect(*k.split(':')) for k in keys}
    before=window(runs['regionuv01:baseline'],4420,4435);after=window(runs['morton05:repeat'],4420,4435)
    assert before['canonical_loads']==29 and after['canonical_loads']==0 and after['morton_loads']==29
    early=window(runs['morton05:repeat'],4328,4338);assert early['ms']<500 and early['gpu_allocations']==0
    fixture=P/'analysis/scene-gpu-test-morton05fbo2/result.json';gpu=read(fixture);assert gpu['passed']
    fixture_build=P/'3ds/build-scene-gpu-test-morton05fbo2';fm=read(fixture_build/'build-manifest.json')
    assert sha(fixture_build/'native-game.cxi')==fm['cxi_sha256']
    for n,h in fm['inputs'].items():assert sha(P/n)==h,n
    base=P/'3ds/build-native-game-v0.1.7-visible05';candidate=P/'3ds/build-native-game-v0.1.7-morton05'
    final=P/'3ds/build-native-game-v0.1.7-morton06'
    for n in ['ds34_gpu_native.c','scene_morton_store.c','native_scene_morton.h','scene_morton_store.h','ds34_shader.h','lz4.c','lz4.h']:
        assert sha(candidate/n)==sha(final/n),n
    functions=['release_staging','sync_gpu','frame','scene_materialize_draw','ds34_present','ds34_native_finish']
    for n in functions:assert function_body((base/'ds34_gpu_native.c').read_text(),n)==function_body((candidate/'ds34_gpu_native.c').read_text(),n),n
    protected=read(P/'analysis/native-game-stable-v0.1.2/preservation.json')['before']
    for n,h in protected.items():assert sha(P/n)==h,n
    count=0
    for directory in (STORE/'datasets').iterdir():
        if not (directory/'manifest.json').exists():continue
        manifest=verify_dataset(directory)
        for e in manifest['files']:assert sha(P/'private/native-game-v0.1.0-sd/3ds/deadspace'/e['path'])==e['sha256']
        count+=len(manifest['files'])
    vendor=P/'3ds/vendor/lz4-v1.10.0';vm=read(vendor/'source.json')
    for n,h in vm['files_sha256'].items():assert sha(vendor/n)==h,n
    result={'software_checks_passed':True,'regional_cropping_deployed':False,
            'lossless_Morton_backing_deployed':True,'late_full_texture_thrashing_eliminated':False,
            'late_canonical_paging_eliminated':True,'original_player_character_seen':True,
            'chapter_I_corridor_seen':True,'specific_character_model_name_verified':False,'playable_gameplay_confirmed':False,
            'late_before':before,'late_after':after,'late_callback_speedup':before['ms']/after['ms'],
            'early_window':early,'runs':runs,'uv_analysis':uv_model(),
            'late_station_texels':verify_texels('morton05','repeat'),
            'chapter_texels':verify_texels('morton05','long2'),'GPU_fixture':gpu,
            'unchanged_GPU_functions':functions,'protected_files_verified':len(protected),'master_store_files_verified':count,
            'codec_source':vm,'budgets':{'CPU':6291456,'GPU':8388608,'entries':32,'normal':20971520,'linear':104857600},
            'hardware_tested':False,'CIA_created':False,'strict_CRC_weakened':False,
            'failed_trials_retained':['morton05:long exhausted former host frame cap without safe_exit','morton05home:home started before build completed; no game run','morton05fbo fixture missed explicit FBO bindings; fixed in fbo2']}
    A.mkdir(exist_ok=True);(A/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['software_checks_passed','late_before','late_after','late_callback_speedup','early_window','late_station_texels','chapter_texels']},indent=2))


if __name__=='__main__':main()
