"""Compare real DS22 and PICA fog/COMBINE pixels, in a separate synthetic fixture."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import re
import threading
import time
import numpy as np
P=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--revision',required=True);args=ap.parse_args()
root=P/('analysis/scene-gpu-test-'+args.revision);assert not root.exists()
os.environ['DEADSPACE_EMULATOR_ROOT']=str(root)
import smoke_azahar as f
from azahar_opengl import Frontend

def finish(code):
    import sys
    sys.stdout.flush();k=C.WinDLL('kernel32');k.GetCurrentProcess.restype=C.c_void_p
    k.TerminateProcess.argtypes=[C.c_void_p,C.c_uint];k.TerminateProcess(k.GetCurrentProcess(),code)

def main():
    manifest=json.loads((P/('3ds/build-scene-gpu-test-'+args.revision+'/build-manifest.json')).read_text())
    case_count=manifest.get('fixture_cases',8)
    gl=Frontend(f);card=root/'Azahar/sdmc/3ds/deadspace';card.mkdir(parents=True,exist_ok=True)
    core=C.CDLL(str(P/'toolchain/azahar-libretro/azahar_libretro.dll'))
    for name,cb in [('environment',f.environment),('video_refresh',f.video),('audio_sample',f.audio),('audio_sample_batch',f.audio_batch),('input_poll',f.poll),('input_state',f.input_state)]:
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(cb)];setter(cb)
    core.retro_load_game.argtypes=[C.POINTER(f.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();game=f.GameInfo(str(P/('3ds/build-scene-gpu-test-'+args.revision+'/native-game.cxi')).encode(),None,0,None)
    assert core.retro_load_game(C.byref(game));gl.reset()
    timer=threading.Timer(60,lambda:finish(124));timer.daemon=True;timer.start();start=time.monotonic()
    for i in range(10000):
        core.retro_run()
        if (card/'scene-fixture-done.txt').exists():break
        if time.monotonic()-start>45:break
    timer.cancel();cases=[]
    for test in range(case_count):
        paths=[card/('scene-'+kind+'-'+str(test)+'.raw') for kind in ['cpu','gpu']]
        if not all(p.exists() and p.stat().st_size==288000 for p in paths):
            cases.append({'case':test,'completed':False});continue
        a,b=[np.frombuffer(p.read_bytes(),dtype=np.uint8).astype(np.int16).reshape(400,240,3) for p in paths]
        # Exclude only primitive perimeter, where rasterization edge rules can
        # differ. Every interior pixel remains in the numerical comparison.
        diff=np.abs(a[2:-2,2:-2]-b[2:-2,2:-2]);maxerr=int(diff.max())
        cases.append({'case':test,'completed':True,'max_channel_error':maxerr,'pixels_over_4':int((diff.max(axis=2)>4).sum()),'passed':maxerr<=4})
    host=(root/'azahar-host.log').read_text(errors='replace');bad=re.findall(r'.*(?:unmapped (?:Read|Write)|Assertion failed).*',host)
    stats_path=card/'scene-visible-stats.json'
    stats=json.loads(stats_path.read_text()) if stats_path.exists() else None
    refusal_path=card/'scene-projective-refusal.json'
    refusal=json.loads(refusal_path.read_text()) if refusal_path.exists() else None
    extra_ok=(case_count<11 or stats is not None and all(v==0 for v in stats.values())) and (case_count<15 or refusal=={'varying_unit1_error':1280})
    store=None
    if manifest.get('morton_store_contracts'):
        store_path=card/'scene-store-contracts.json'
        store=json.loads(store_path.read_text()) if store_path.exists() else {'passed':False}
        pair=[card/('store-reload-%u.raw'%i) for i in range(2)]
        reload_same=all(p.exists() for p in pair) and pair[0].read_bytes()==pair[1].read_bytes()
        store['reload_frames_byte_identical']=reload_same
        extra_ok=extra_ok and store['passed'] and reload_same
    result={'passed':all(c.get('passed',False) for c in cases) and not bad and extra_ok,'cases':cases,'hidden_draw_stats':stats,'projective_refusal':refusal,'store_contracts':store,'invalid_accesses':bad,'game_called':False,'hardware_tested':False}
    (root/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    # Fixture intentionally retains GPU/CPU allocations until process teardown.
    finish(0 if result['passed'] else 1)

if __name__=='__main__':main()
