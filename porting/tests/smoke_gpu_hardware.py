"""Verify the CIA payload in isolated Azahar, without claiming hardware PASS."""
import argparse,ctypes as C,hashlib,json,os,re,shutil,struct,time,zlib
from pathlib import Path
P=Path(__file__).resolve().parents[1]
VERSION='0.1.3'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--scenario',choices=['success','vblank0','vblank1','queue-after-submit'],default='success')
args=parser.parse_args()
fault_test=args.scenario!='success'
os.environ['DEADSPACE_EMULATOR_ROOT']=str(P/('analysis/azahar-gpu-hardware-v'+VERSION+('-'+args.scenario if fault_test else '')))
import smoke_azahar as f
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def png(raw):
    out=bytearray()
    for row in range(240):
        out.append(0);y=239-row
        for x in range(400):
            off=(x*240+y)*2;v=raw[off]|raw[off+1]<<8
            out.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',400,240,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(out))+chunk(b'IEND',b'')
def main():
    build=P/('3ds/build-gpu-hardware-v'+VERSION+('-faults' if fault_test else ''));data=(build/'ds34-gpu-test.cia').read_bytes()
    header,kind,version,cert,ticket,tmd,footer,content=struct.unpack_from('<IHHIIIIQ',data)
    align=lambda n:(n+63)&~63
    offset=align(header)+align(cert)+align(ticket)+align(tmd);payload=data[offset:offset+content]
    assert header==0x2020 and kind==version==0 and payload[0x100:0x104]==b'NCCH'
    assert len(payload)==content and struct.unpack_from('<Q',payload,0x108)[0]==0x000400000FDE6800
    app=build/'cia-payload.cxi';app.write_bytes(payload)
    card=f.ROOT/('Azahar/sdmc/3ds/ds34-gpu-test-v'+VERSION);card.mkdir(parents=True,exist_ok=True)
    for name in ['result.json','ready.txt','gpu-test.log','diag-fault.txt','gx-first-frame.json',*[f'gx-first-{i}.pica' for i in range(32)],*[f'case-{i}.{ext}' for i in range(8) for ext in ['raw','json']]]:
        path=card/name
        if path.exists():path.unlink()
    (card/'result.json').write_text('{"passed":true,"stale":true}\n')
    if fault_test:(card/'diag-fault.txt').write_text(args.scenario+'\n')
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    original_input=f.input_state;press_start=False
    @C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
    def input_state(port,device,index,identifier):
        if port==0 and device==1 and index==0 and identifier==3:return int(press_start)
        return original_input(port,device,index,identifier)
    f.input_state=input_state
    for name,callback in (('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',f.input_state)):
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(callback)];setter(callback)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();info=f.GameInfo(str(app.resolve()).encode(),None,0,None);assert core.retro_load_game(C.byref(info))
    start=time.monotonic();ready_frame=None;sent=None;result=card/'result.json'
    for frame in range(5400):
        if (card/'ready.txt').exists() and ready_frame is None:
            assert not result.exists(),'Previous PASS was not cleared on startup'
            ready_frame=frame
        if ready_frame is not None and sent is None and frame>=ready_frame+30:
            assert not result.exists() and not (card/'case-0.raw').exists(),'GPU test ran without A'
            sent=frame
        f.button_a=sent is not None and sent<=frame<sent+10
        core.retro_run()
        if sent is not None and result.exists() and result.stat().st_size:break
        if time.monotonic()-start>90:break
    for _ in range(3):core.retro_run() # allow the final console status to flush
    if f.frame:f.save_frame(f.ROOT/'screen.png')
    # Exercise normal shutdown while DS34 has reopened an empty C3D frame.
    f.button_a=False;press_start=True;exit_drained=False;exit_deferred=False
    if result.exists():
        for _ in range(180):
            core.retro_run()
            log=(card/'gpu-test.log').read_text(errors='replace')
            if args.scenario=='queue-after-submit' and 'EXIT DEFERRED: GX QUEUE STILL BUSY' in log and not exit_deferred:
                assert 'EXIT BEGIN' not in log and 'EXIT GPU DRAINED' not in log,'Cleanup entered while queue reported busy'
                exit_deferred=True;press_start=False
                for _ in range(3):core.retro_run()
                press_start=True
            if 'EXIT GPU DRAINED' in log:exit_drained=True;break
    core.retro_unload_game();core.retro_deinit()
    assert result.exists(),'No result; inspect isolated screen/log'
    native=json.loads(result.read_text());assert native['passed'] is (not fault_test),native
    log=(card/'gpu-test.log').read_text()
    assert 'ATTACH OK: white texture transfer verified' in log
    assert exit_drained,'START did not finish the GPU queue cleanup'
    assert native['version']==VERSION and native['environment']=='emulator' and native['game_called'] is False
    host=(f.ROOT/'azahar-host.log').read_text(errors='replace');errors=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo).*',host);assert not errors,errors[:8]
    assert (f.ROOT/'azahar-host.log').stat().st_size<524288
    shutil.copyfile(card/'gpu-test.log',f.ROOT/'gpu-test.log')
    snapshots=re.findall(r'GX SNAPSHOT (.*?) runs=(\d+) queue=([0-9a-f]+) total=(\d+) submitted=(\d+) completed=(\d+) capacity=(\d+)',log)
    assert snapshots and all(int(n)<=int(cap) and int(sub)<=int(n) and int(done)<=int(n) for _,_,_,n,sub,done,cap in snapshots)
    submits=re.findall(r'GX SUBMIT (\d+) (\w+) result=([0-9a-f]{8})((?: [0-9a-f]{8}){8})',log)
    assert submits and all(not (int(result,16)&0x80000000) for _,_,result,_ in submits),submits
    observer={'queue_wrapper_verified':True,'submit_return_results_success':True,'submit_records':len(submits),
        'irq_observation_available':False,'sdk_callbacks_preserved':True}
    capture=card/'gx-first-frame.json'
    if not fault_test or args.scenario=='queue-after-submit':
        first=json.loads(capture.read_text());assert first['captures_complete'] and first['version']==VERSION
        kinds=[e['name'] for e in first['entries']];assert {'PICA','FILL','DISPLAY'}<=set(kinds),first
        assert first['num_entries']==len(first['entries']) and 'GX FIRST FRAME CAPTURE OK' in log
        for entry in first['entries']:
            if entry['name']=='PICA':
                raw=(card/entry['pica_file']).read_bytes();assert len(raw)==entry['bytes']==entry['words'][2]
                assert len(raw)>0 and len(raw)%4==0
                shutil.copyfile(card/entry['pica_file'],f.ROOT/entry['pica_file'])
        shutil.copyfile(capture,f.ROOT/capture.name)
        observer['first_frame_queue_types']=kinds
        observer['pica_capture_verified']=True
    else:assert not capture.exists(),'A frame was submitted after initial VBlank timeout'
    if fault_test:
        phase='GX QUEUE WAIT' if args.scenario=='queue-after-submit' else 'VBLANK WAIT'
        assert native['wait_timeout'] and native['timeout_phase']==phase+' TIMEOUT',native
        assert native['cases_completed']==native['presents']==0 and not (card/'case-0.raw').exists()
        assert 'GPU TEST FAILED' in log and 'RESULT WRITE RETURNED' in log and 'EXIT QUEUE IDLE' in log
        stamps=re.findall(r'PHASE \d+ ms=(\d+) vb=\d+,\d+ '+phase+r' (BEGIN|TIMEOUT)',log)
        deadline_ms=int(stamps[-1][0])-int(stamps[-2][0]);assert 1900<=deadline_ms<=4000,stamps
        if args.scenario=='queue-after-submit':
            assert exit_deferred and 'FRAME END OK' in log and native['gpu_draws']==1
            snap=re.search(r'GX SNAPSHOT TIMEOUT runs=\d+ queue=[0-9a-f]+ total=(\d+) submitted=(\d+) completed=(\d+)',log)
            assert snap and len(set(snap.groups()))==1,'Fake busy must not modify the real completed queue'
            observer['simulated_busy_real_queue_idle']=True
        for phase in ['POST TIMEOUT APT BEGIN','POST TIMEOUT APT OK','POST TIMEOUT HID BEGIN','POST TIMEOUT HID OK',
                      'POST TIMEOUT CONSOLE FLUSH BEGIN','POST TIMEOUT CONSOLE FLUSH OK','EXIT PRECHECK BEGIN']:
            assert phase in log,phase
        report={'passed':True,'version':VERSION,'scenario':args.scenario,'intentional_fault':True,'hardware_tested':False,
            'native_failure_result':native,'timeout_observed_ms':deadline_ms,'START_exit_gpu_drained':exit_drained,
            'busy_exit_deferred':exit_deferred,'invalid_accesses':len(errors),'cia_sha256':sha(build/'ds34-gpu-test.cia'),
            'payload_sha256':sha(app),'queue_observer':observer,'elapsed_seconds':round(time.monotonic()-start,3)}
        (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return
    assert native['game_called'] is False and native['cases']==8 and native['presents']==23
    assert native['cpu_fragments']==native['cpu_samples']==native['gl_error']==0
    assert native['peak_vertices']==8190 and native['drains']>=2 and native['uploads']==native['upload_checks']==2
    assert native['upload_mismatches']==native['vertex_mismatches']==native['texture_mismatches']==0
    assert not native['wait_timeout'] and native['timeout_phase']=='none' and native['cases_completed']==8
    assert any(int(done)==int(n) and int(n)>0 for _,_,_,n,_,done,_ in snapshots)
    phases=['VERTEX SETUP BEGIN','VERTEX SETUP OK','GLES CLEAR BEGIN','VBLANK WAIT BEGIN','VBLANK WAIT OK',
        'GX QUEUE WAIT BEGIN','GX QUEUE WAIT OK','CLEAR SPLIT BEGIN','CLEAR SPLIT OK','CLEAR QUEUE BEGIN','CLEAR QUEUE OK',
        'GLES CLEAR RETURNED','GLES DRAW BEGIN','VERTEX CACHE FLUSH BEGIN','VERTEX CACHE FLUSH OK','DRAW ARRAYS BEGIN',
        'DRAW ARRAYS OK','GLES DRAW RETURNED','PRESENT BEGIN','FRAME END BEGIN','FRAME END OK','VBLANK WAIT BEGIN',
        'VBLANK WAIT OK','VBLANK WAIT BEGIN','VBLANK WAIT OK','GX QUEUE WAIT BEGIN','GX QUEUE WAIT OK',
        'STAGING RELEASE BEGIN','STAGING RELEASE OK','READBACK INVALIDATE BEGIN','READBACK INVALIDATE OK',
        'INTEGRITY AUDIT BEGIN','INTEGRITY AUDIT OK','PRESENT OK','PIXEL CHECKS OK; CAPTURE BEGIN','CAPTURE OK','CASE 0 PASS']
    cursor=0
    for phase in phases:
        where=log.find(phase,cursor);assert where>=0,(phase,cursor);cursor=where+len(phase)
    images=[]
    for i in range(8):
        raw=(card/f'case-{i}.raw').read_bytes();m=json.loads((card/f'case-{i}.json').read_text())
        assert len(raw)==m['bytes']==192000 and f'{zlib.crc32(raw):08x}'==m['crc32']
        image=png(raw);(f.ROOT/f'case-{i}.png').write_bytes(image);images.append(hashlib.sha256(image).hexdigest())
    previous=json.loads((P/'analysis/azahar-gpu-hardware-v0.1.1/result.json').read_text())
    assert images==previous['png_sha256'],'Synthetic pixel output changed'
    report={'passed':True,'version':VERSION,'first_case_phase_order_verified':True,'v0.1.1_pixels_unchanged':True,'bounded_waits':True,'inactive_transfer_verified':True,'tested_payload':'NCCH extracted from actual CIA','cia_sha256':sha(build/'ds34-gpu-test.cia'),'payload_sha256':sha(app),'title_id':'000400000FDE6800','stale_result_cleared':True,'start_A_gate_verified':sent is not None,'START_exit_gpu_drained':exit_drained,'invalid_accesses':len(errors),
        'native_result':native,'png_sha256':images,'queue_observer':observer,'hardware_tested':False,'game_resources_used':False,'elapsed_seconds':round(time.monotonic()-start,3)}
    (f.ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
