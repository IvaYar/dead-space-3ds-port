"""Build isolated original-menu exploration; never replace the CRC verifier."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import wave
from PIL import Image, ImageDraw, ImageFont
from azahar_resource_store import sha
from build_native_game_target_init import RUNTIME, makerom

P = Path(__file__).resolve().parents[1]
BASE = P/'3ds/build-native-game-v0.1.4r2-normal'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision',required=True)
    ap.add_argument('--callbacks',type=int,default=4800)
    ap.add_argument('--dense',action='store_true',help='Additional menu-transition captures; investigation only')
    ap.add_argument('--home-at',type=int,default=0,help='Test-only deferred HOME at a callback boundary')
    ap.add_argument('--scene-probe',action='store_true',help='Emulator-only continuation into known audio/GPU faults; never a CIA candidate')
    args=ap.parse_args()
    assert args.revision.isalnum() and 600<=args.callbacks<=12000
    assert args.home_at==0 or 600<args.home_at<args.callbacks
    d=P/('3ds/build-native-game-v0.1.5-'+args.revision)
    assert not d.exists(), 'Preserve prior builds'
    m=json.loads((BASE/'build-manifest.json').read_text())
    for name,digest in m['outputs_sha256'].items():assert sha(BASE/name)==digest,name
    d.mkdir()
    source=P/'tests/native_game_menu.c'
    shutil.copyfile(source,d/'native-game-memory.c')
    headers=['native_menu_input.h','native_menu_texture_memory.h','native_loader_budget.h','native_loader_io_monitor.h','native_game_memory_observer.h']
    for name in headers:shutil.copyfile(P/'tests'/name,d/name)
    for name in RUNTIME:shutil.copyfile(BASE/name,d/name)
    # Menu atlas4MiB plus UI textures must coexist. Only the cache
    # capacity changes; all backend functions/shader bytes remain original.
    gpu=(BASE/'ds34_gpu_native.c').read_text()
    assert gpu.count('#define BUDGET (4u*1024*1024)')==1
    (d/'ds34_gpu_native.c').write_text(gpu.replace('#define BUDGET (4u*1024*1024)','#define BUDGET (8u*1024*1024)'))
    (d/'native-game.rsf').write_text((BASE/'native-game.rsf').read_text().replace('0xFDE77','0xFDE78').replace('DS-GAME-PROG','DS-GAME-MENU').replace('CTR-H-DGPR','CTR-H-DGMN'))
    command=[s.replace(str(BASE),str(d)) for s in m['commands'][0]]
    command[1:1]=['-DMENU_CALLBACKS='+str(args.callbacks),'-DMENU_ALLOW_SCENE='+str(int(args.scene_probe)),'-Wl,--wrap=C3D_TexInitWithParams,--wrap=C3D_SyncTextureCopy,--wrap=C3D_TexDelete']
    if args.dense:command.insert(1,'-DMENU_DENSE_CAPTURE=1')
    test_sdk=None
    if args.home_at:
        test_sdk=d/'apt-test.o'
        shutil.copyfile(P/'3ds/build-native-game-v0.1.4r2-home/apt-test.o',test_sdk)
        command[1:1]=[str(test_sdk),'-DTEST_APT_CLOSE=1','-DTEST_MENU_HOME_FRAME='+str(args.home_at)]
    commands=[command];subprocess.run(command,cwd=d,check=True)
    banner=Image.new('RGB',(256,128),(7,20,30));draw=ImageDraw.Draw(banner)
    for label,y,size in [('DS ORIGINAL MENU',22,20),('EXPLORATION / FRAME FAIL',61,14),('EXPERIMENTAL 0.1.5',94,14)]:
        draw.text((128,y),label,fill=(180,240,235),font=ImageFont.load_default(size=size),anchor='mt')
    banner.save(d/'banner.png')
    with wave.open(str(d/'silence.wav'),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(22050);audio.writeframes(b'\0'*8820)
    for cmd in [
        [str(P/'toolchain/extras/bannertool/bannertool.exe'),'makebanner','-i',str(d/'banner.png'),'-a',str(d/'silence.wav'),'-o',str(d/'native-game.bnr')],
        [str(P/'toolchain/devkitpro/tools/bin/smdhtool.exe'),'--create','DS Original Menu 0.1.5','Exploration; image validation FAIL','Dead Space port research',str(P/'toolchain/devkitpro/libctru/default_icon.png'),str(d/'native-game.smdh')],makerom('cxi',d)]:
        commands.append(cmd);subprocess.run(cmd,cwd=d,check=True)
    assert all(sha(d/n)==sha(BASE/n) for n in RUNTIME if n!='ds34_gpu_native.c')
    manifest={'commands':commands,'revision':args.revision,'callbacks':args.callbacks,'dense_capture':args.dense,'exploratory':True,
        'scene_probe':args.scene_probe,'confirm_tail_callbacks':None if args.scene_probe else 2,
        'test_HOME_callback':args.home_at,'test_only_SDK_sha256':sha(test_sdk) if test_sdk else None,
        'source_sha256':sha(source),'headers_sha256':{n:sha(d/n) for n in headers},
        'runtime_sha256':{n:sha(d/n) for n in RUNTIME},'GPU_only_source_change':'cache capacity4->8MiB',
        'memory_MiB':{'application':124,'normal':20,'linear':100,'donor_arena':85.5},'hardware_tested':False,
        'outputs_sha256':{n:sha(d/n) for n in ['native-game-memory.c','native-game.elf','native-game.cxi','native-game.rsf','native-game.smdh','native-game.bnr']}}
    (d/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Built exploratory CXI',d.name)

if __name__=='__main__':main()
