"""Read-only selective full-texture/rectangle LRU model from saved callback4430.

Reads immutable UV evidence and previously verified Morton snapshots. Writes
only a numerical model summary; never builds, runs or modifies the renderer.
"""
from collections import defaultdict
from itertools import groupby
import json
from pathlib import Path
import struct

from azahar_resource_store import sha

P=Path(__file__).resolve().parents[1]
A=P/'analysis/regional-texture-residency'


def axis(lo,hi,width,wrap,quantum):
    from math import floor
    if wrap==0x812f:lo=max(0,min(1,lo));hi=max(0,min(1,hi))
    low=floor(lo*width)-1;high=floor(hi*width)+1
    if wrap==0x812f:low=max(0,low);high=min(width-1,high)
    origin=floor(low/quantum)*quantum;size=max(8,1<<(high-origin).bit_length())
    return (0,max(8,width)) if size>=width else (origin,size)


def main():
    uv=P/'analysis/azahar-native-menu-v0.1.7-regionuv01-baseline/Azahar/sdmc/3ds/ds-native-game-v0.1.7/run-0001/scene-uv.jsonl'
    rows=[json.loads(l) for l in uv.read_text().splitlines()];rows=[r for r in rows if r['frame']==4430]
    root=P/'analysis/azahar-native-menu-v0.1.7-morton05-repeat/Azahar/sdmc/3ds'
    events=[json.loads(l) for l in (root/'ds-native-game-v0.1.7/run-0001/scene-textures.jsonl').read_text().splitlines()]
    sources={e['name']:e for e in events if e['kind']==7 and e['frame']<=4440}
    blocks={};dimensions={};fingerprints={}
    for r in rows:
        n=r['name']
        if n in blocks:continue
        e=sources[n];assert (e['w'],e['h'])==(r['w'],r['h'])
        path=root/('deadspace/test-output/morton-pages/image-%08x.bin'%e['bytes'])
        with path.open('rb') as f:
            magic,version,raw,crc,limit=struct.unpack('<5I',f.read(20))
            assert (magic,version,crc)==(0x504d5344,2,e['reason'])
            remaining=raw;parts=[]
            while remaining:
                dec,enc,_=struct.unpack('<3I',f.read(12));assert dec==min(limit,remaining)
                parts.append((dec,enc+12));f.seek(enc,1);remaining-=dec
            assert not f.read()
        fingerprints[str(n)]=sha(path);blocks[n]=parts
        dimensions[n]=(max(8,1<<(r['w']-1).bit_length()),max(8,1<<(r['h']-1).bit_length()),r['w'],r['h'],limit)
    results=[]
    for quantum in [1,8,16,32,64]:
        full={};plans=defaultdict(set);sequence=[];cost={}
        for r in rows:
            n=r['name'];pw,ph,w,h,limit=dimensions[n];full[n]=(n,0,0,pw,ph,*r['wrap'])
            x,rw=axis(r['uv'][0],r['uv'][2],w,r['wrap'][0],quantum)
            y,rh=axis(r['uv'][1],r['uv'][3],h,r['wrap'][1],quantum)
            key=(n,x,y,rw,rh,*r['wrap']);plans[n].add(key);sequence.append((r['draw'],n,key))
        for k in set(full.values())|{k for keys in plans.values() for k in keys}:
            n,x,y,rw,rh,ws,wt=k;pw,ph,w,h,limit=dimensions[n]
            # Format2 blocks span full-width bands, so x does not select a
            # smaller compressed block. Preserve wrapped/clamped source rows.
            ys={(y+i)%h if wt==0x2901 else max(0,min(h-1,y+i)) for i in range(rh)}
            selected=set(range(len(blocks[n]))) if k==full[n] else {((ph-1-j)*pw*4)//limit for j in ys}
            cost[k]=(rw*rh*4,len(selected),sum(blocks[n][b][0] for b in selected),20+sum(blocks[n][b][1] for b in selected))
        candidates=sorted(n for n in plans if plans[n]!={full[n]})
        def simulate(mask):
            groups=[[k if n in mask else full[n] for _,n,k in items] for _,items in groupby(sequence,key=lambda x:x[0])]
            cache={};used=clock=0;previous=None
            for repeat in range(4):
                totals=[0,0,0,0,0]
                for requests in groups:
                    pinned=set(requests)
                    for key in requests:
                        clock+=1
                        if key not in cache:
                            size,b,d,read=cost[key]
                            while len(cache)>=32 or used+size>8388608:
                                victims=[k for k in cache if k not in pinned];assert victims
                                victim=min(victims,key=cache.get);used-=cost[victim][0];del cache[victim]
                            used+=size;totals=[totals[0]+1,totals[1]+size,totals[2]+b,totals[3]+d,totals[4]+read]
                        cache[key]=clock
                if repeat==3:assert totals==previous
                previous=totals
            return totals
        baseline=simulate(set());assert baseline==[29,51003648,200,51003648,18405917]
        evaluated=[]
        for bits in range(1<<len(candidates)):
            mask={n for j,n in enumerate(candidates) if bits>>j&1};evaluated.append((simulate(mask),sorted(mask)))
        def record(item):
            values,selected=item
            return dict(zip(['GPU_misses','GPU_population_bytes','backing_block_reads','decoded_bytes','compressed_read_bytes'],values),regional_texture_ids=selected)
        results.append({'origin_quantum':quantum,'candidate_textures':len(candidates),'masks_tested':len(evaluated),
            'baseline':record((baseline,[])),
            'minimum_GPU_misses':record(min(evaluated,key=lambda e:(e[0][0],e[0][4],e[0][1]))),
            'minimum_GPU_bytes':record(min(evaluated,key=lambda e:(e[0][1],e[0][0]))),
            'minimum_IO_without_more_GPU_misses':record(min((e for e in evaluated if e[0][0]<=baseline[0]),key=lambda e:(e[0][4],e[0][0]))),
            'minimum_IO':record(min(evaluated,key=lambda e:(e[0][4],e[0][0])))})
    result={'frame':4430,'GPU_budget':8388608,'GPU_entries':32,'draw_units':len(rows),'textures':len(dimensions),
            'source_UV_sha256':sha(uv),'snapshot_sha256_by_texture_id':fingerprints,'models':results,
            'regional_path_implemented':False,'cache_budgets_changed':False,
            'limitations':['Identical callback repeated four cycles; moving UV regions can reduce reuse.',
                'Per-draw clipped bounds are optimistic; no triangle subdivision is modelled.',
                'Open/seek, new block CRC, region extraction, GPU drains and allocator fragmentation costs are omitted.',
                'Region-level sampler pinning is assumed; existing object-level pinning would require review.']}
    (A/'hybrid-4430.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'model_passed':True,'minimum_GPU_misses':min(r['minimum_GPU_misses']['GPU_misses'] for r in results),
        'best_no_more_misses':min((r['minimum_IO_without_more_GPU_misses'] for r in results),key=lambda e:e['compressed_read_bytes']),
        'best_IO':min((r['minimum_IO'] for r in results),key=lambda e:e['compressed_read_bytes'])},indent=2))


if __name__=='__main__':main()
