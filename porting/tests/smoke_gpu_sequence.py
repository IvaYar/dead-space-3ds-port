"""Capture 2..10 consecutive original game callbacks through the PICA backend.

Uses the verified Azahar Software guest RGB565 capture, not OpenGL readback.
Never changes baseline CPU/GPU builds or their SDs. No native CIA is produced.
"""
import argparse,hashlib,json,os,re,shutil,struct,subprocess,sys,zlib
from pathlib import Path
P=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def png(raw):
    scan=bytearray()
    for row in range(240):
        scan.append(0);y=239-row
        for x in range(400):
            off=(x*240+y)*2;v=raw[off]|raw[off+1]<<8
            scan.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',400,240,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--start',type=int,default=180);parser.add_argument('--count',type=int,default=10);args=parser.parse_args()
    if args.start<2 or not 2<=args.count<=10 or args.start+args.count-1>12000:parser.error('start>=2, count2..10, end<=12000 required')
    end=args.start+args.count-1;tag=f'{args.start}-{end}'
    root=P/f'analysis/azahar-gpu-sequence-{tag}';dest=P/f'analysis/gpu-sequence-{tag}';dest.mkdir(exist_ok=True)
    card=root/'Azahar/sdmc/3ds/deadspace';source=P/'analysis/azahar-gpu-engine/Azahar/sdmc/3ds/deadspace'
    if card.exists():raise RuntimeError('Use a new frame window; existing sequence SD/results are preserved')
    card.mkdir(parents=True)
    for name in ['assets','apk-assets','test-output']:shutil.copytree(source/name,card/name)
    for name in ['assets-verified.txt','apk-assets-verified.txt']:shutil.copyfile(source/name,card/name)
    # Original resources copied only to private ignored SD, never evidence.
    protected=[P/'3ds/build-emulator/engine-audit-178.cxi',P/'3ds/build-gpu-engine/engine-gpu.cxi',P/'analysis/gpu-safety/first-game-frame.raw']
    protected += list((P/'analysis/gpu-opengl-capture').glob('cycle*/*.json'))
    before={str(p.relative_to(P)):sha(p) for p in protected}
    (dest/'preserved.json').write_text(json.dumps(before,indent=2)+'\n')
    env={**os.environ,'DEADSPACE_EMULATOR_ROOT':str(root.resolve())}
    cmd=[sys.executable,str(P/'tests/smoke_engine_azahar.py'),'--case','graphics','--explore','--gpu','--gpu-sequence-start',str(args.start),'--gpu-sequence-count',str(args.count),
        '--capture-frame',str(end),'--timeout-seconds','120','--cpu-percent','400','--resume-focus','--private-files','--apk-assets','--shared-arena','--framebuffers','--memory-mib','178','--font-subset','--allocator-compat','--fog','--combine','--lighting','--default-depth']
    with (dest/'console.log').open('wb') as console:job=subprocess.run(cmd,env=env,stdout=console,stderr=subprocess.STDOUT)
    for path in protected:assert sha(path)==before[str(path.relative_to(P))],path
    log=(card/'engine-azahar-log.txt').read_text(encoding='utf-8')
    for name,path in [('run.log',card/'engine-azahar-log.txt'),('host.log',root/'azahar-host.log'),('build-manifest.json',P/'3ds/build-gpu-sequence/build-manifest.json')]:shutil.copyfile(path,dest/name)
    assert job.returncode==0,(job.returncode,'inspect console.log')
    assert 'Completed game frame saved.' in log and 'GLES error at stop: 00000000' in log
    host=(dest/'host.log').read_text(errors='replace');assert (dest/'host.log').stat().st_size<524288,'Host diagnostic log truncated'
    errors=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo).*',host)
    assert not errors,errors[:8]
    assert not re.search(r'STOP CPU exception|DIAGNOSTIC WATCHDOG STOPPED|GPU sequence audit failed|STOP unsupported',log)
    rows=[json.loads(line) for line in (card/'gpu-sequence.jsonl').read_text().splitlines()]
    assert [r['frame'] for r in rows]==list(range(args.start,end+1))
    frames=[];previous=None
    for row in rows:
        n=row['frame'];stem=f'gpu-frame-{n}';m=json.loads((card/f'{stem}.json').read_text());raw=(card/f'{stem}.raw').read_bytes()
        assert m['frame']==n and m['width']==400 and m['height']==240 and m['layout']==2 and len(raw)==m['bytes']==192000
        assert f'{zlib.crc32(raw):08x}'==m['crc32'] and any(raw)
        assert f'Frame {n} returned\n' in log and f'GPU SEQUENCE FRAME SAVED: frame={n} audit=OK\n' in log
        assert all(row[k]==0 for k in ['gl_error','upload_mismatches','vertex_mismatches','texture_mismatches','pending_staging','stream_used'])
        assert row['presents']==row['vertex_checks']==n and 0<row['peak_vertices']<=8190
        assert row['upload_checks']==row['uploads'] and row['cached_textures']>0
        assert m['fragments']==m['samples']==0
        if previous:
            assert row['draws']>previous['draws'] and row['triangles']>previous['triangles']
            assert row['texture_checks']-previous['texture_checks']==row['cached_textures']
        for suffix in ['.json','.raw']:shutil.copyfile(card/f'{stem}{suffix}',dest/f'{stem}{suffix}')
        data=png(raw);(dest/f'{stem}.png').write_bytes(data)
        frames.append({**row,'crc32':m['crc32'],'raw_sha256':hashlib.sha256(raw).hexdigest(),'png_sha256':hashlib.sha256(data).hexdigest(),'nonblack_pixels':sum(raw[i]!=0 or raw[i+1]!=0 for i in range(0,len(raw),2))})
        previous=row
    shutil.copyfile(card/'gpu-sequence.jsonl',dest/'telemetry.jsonl')
    baseline=P/'analysis/gpu-safety/first-game-frame.raw'
    report={'passed':True,'scope':'Consecutive original engine UI/loading callbacks through PICA; not 3D gameplay','graphics_api':'Azahar Software','capture':'Native RGB565 after blocking present; same decoder as verified export_native_frame','start':args.start,'count':args.count,'end':end,'frames':frames,'unique_frames':len({f['raw_sha256'] for f in frames}),
        'frame180_matches_preserved':(dest/'gpu-frame-180.raw').read_bytes()==baseline.read_bytes() if args.start<=180<=end else None,'invalid_accesses':len(errors),'full_552_tests_run':False,'hardware_tested':False,'cia_produced':False,'experimental_game_cia_ready':False,
        'native_blockers':['engine_azahar.c explicitly refuses non-emulator execution and is not a CIA entry point','Native GPU/cache/readback behavior untested on New3DS','Only a short UI/loading sequence covered; no 3D game scene verified'],
        'limitations':['Software PICA emulation is not hardware validation; known OpenGL/text issues deferred','Audit performs diagnostic VRAM reads and SD captures; elapsed time is not a FPS measurement','No claim of rollover/eviction coverage unless telemetry actually exercises it'],
        'cxi_sha256':sha(P/'3ds/build-gpu-sequence/engine-gpu.cxi'),'host_log_sha256':sha(dest/'host.log'),'run_log_sha256':sha(dest/'run.log'),'protected_artifacts_unchanged':True}
    (dest/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','start','count','unique_frames','invalid_accesses','frame180_matches_preserved','experimental_game_cia_ready']},indent=2))
if __name__=='__main__':main()
