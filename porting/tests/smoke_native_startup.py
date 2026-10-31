"""Actual startup CIA payload: reach main/READY, measure small heaps, START exit."""
import ctypes as C
import hashlib
import json
import os
import re
import shutil
import struct
import time
from pathlib import Path

P=Path(__file__).resolve().parents[1]
ROOT=P/'analysis/azahar-native-startup-v0.1.0'
assert not ROOT.exists(),'Preserve existing evidence'
os.environ['DEADSPACE_EMULATOR_ROOT']=str(ROOT)
import smoke_azahar as f

def main():
    b=P/'3ds/build-native-startup-v0.1.0';raw=(b/'startup.cia').read_bytes()
    h,_,_,cert,ticket,tmd,_,size=struct.unpack_from('<IHHIIIIQ',raw);offset=sum((n+63)&~63 for n in [h,cert,ticket,tmd])
    assert raw[offset:offset+size]==(b/'cia-payload.cxi').read_bytes()
    assert struct.unpack_from('<Q',raw,offset+0x108)[0]==0x000400000FDE7200
    core=C.CDLL(str((P/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    start=False
    @C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
    def input_state(port,device,index,key):return int(start and (port,device,index,key)==(0,1,0,3))
    for name,cb in [('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',input_state)]:
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(cb)];setter(cb)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();cycles=[];started=time.monotonic()
    for number in range(1,4):
        start=False;host_start=(ROOT/'azahar-host.log').stat().st_size
        info=f.GameInfo(str((b/'cia-payload.cxi').resolve()).encode(),None,0,None)
        assert core.retro_load_game(C.byref(info))
        run=ROOT/('Azahar/sdmc/3ds/ds-native-startup-v0.1.0/run-%04d'%number)
        ready=None
        for _ in range(600):
            core.retro_run()
            try:ready=json.loads((run/'result.json').read_text())
            except (FileNotFoundError,json.JSONDecodeError):continue
            if ready['state']=='ready':break
            assert time.monotonic()-started<45
        assert ready and ready['state']=='ready' and ready['main_entered'] and ready['probe_valid']
        assert ready['heap_wrapper_calls']==1 and ready['heap_commit_delta_bytes']==4194304
        assert ready['normal_heap_bytes']==ready['linear_heap_bytes']==2097152
        assert not ready['game_called'] and not ready['DS34_called'] and ready['PICA_submits']==0
        for _ in range(3):core.retro_run()
        evidence=ROOT/('cycle-%04d'%number);evidence.mkdir();f.save_frame(evidence/'READY.png')
        start=True;clean=False;exit_begin=(ROOT/'azahar-host.log').stat().st_size
        for _ in range(180):
            core.retro_run()
            segment=(ROOT/'azahar-host.log').read_bytes()[exit_begin:].decode(errors='replace')
            if (run/'exit.txt').exists() and 'ReleaseRight:999: called' in segment and all('operation=0x00000001, addr0='+addr in segment for addr in ['0x08000000','0x30000000']):
                clean=True;break
        final=json.loads((run/'result.json').read_text())
        assert clean and final['START_exit_requested'] and final['state']=='START_exit_requested'
        host=(ROOT/'azahar-host.log').read_bytes()[host_start:].decode(errors='replace')
        bad=re.findall(r'.*(?:unmapped (?:Read|Write)|Unknown virtual address|Unknown GetPhysMemRegionInfo|Assertion failed|Exception Type:|LogException:).*',host)
        assert not bad,bad[:3]
        for q in run.iterdir():
            if q.is_file():shutil.copyfile(q,evidence/('guest-result.json' if q.name=='result.json' else q.name))
        (evidence/'START-cleanup.log').write_text(segment)
        cycles.append({'cycle':number,'passed':True,'READY':ready,'START_cleanup_before_host_unload':clean,'guest_exit':final,'invalid_memory_accesses':bad})
        core.retro_unload_game()
        print('Startup cycle',number,'PASS; pre-heap limit/current:',ready['pre_heap_limit_bytes'],ready['pre_heap_current_bytes'],flush=True)
    core.retro_deinit()
    result={'passed':True,'startup_test_only':True,'hardware_tested':False,'hardware_compatible_proven':False,'donor_or_PICA_executed':False,'actual_CIA_payload_tested':True,'cycles':cycles,'same_core_and_SD':True,'CIA_sha256':hashlib.sha256(raw).hexdigest(),'payload_sha256':hashlib.sha256((b/'cia-payload.cxi').read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'elapsed_host_seconds':round(time.monotonic()-started,3)}
    (ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Three startup-only CIA payload cycles PASS. No hardware compatibility claim.')

if __name__=='__main__':main()
