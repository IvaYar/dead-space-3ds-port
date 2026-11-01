"""Isolated CIA candidate from the immutable s16 safe-exit implementation."""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import build_stage1 as b

P=b.PORTING
BASE=P/'3ds/build-native-frame-v0.1.0-s16'
A=P/'analysis/native-game-cia-v0.1.0'
D=P/'3ds/build-native-game-v0.1.0'
TITLE='000400000FDE7100'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def baseline():
    manifest=json.loads((BASE/'build-manifest.json').read_text())
    proof=json.loads((P/'analysis/azahar-native-frame-v0.1.0-s16/result.json').read_text())
    assert proof['passed'] and proof['safe_exit'] and proof['sequential_cycles']>=3
    assert proof['CXI_sha256']==sha(BASE/'native-frame.cxi')
    for name,digest in manifest['inputs_sha256'].items():assert sha(P/name)==digest,name
    for name,digest in manifest['outputs_sha256'].items():assert sha(BASE/name)==digest,name
    assert all(c['passed'] and c['baseline_RGB565_exact'] and c['shutdown_proof']['kernel_joins']==6 and c['shutdown_proof']['worker_handles_remaining']==0 for c in proof['cycles'])
    return manifest

def main():
    global D
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cia',action='store_true');parser.add_argument('--revision',default='');parser.add_argument('--proof-attempt',default='');args=parser.parse_args()
    assert not args.revision or args.revision.isalnum()
    assert not args.proof_attempt or args.proof_attempt.isalnum()
    if args.revision:D=D.with_name(D.name+'-'+args.revision)
    old=baseline()
    if args.cia:
        evidence=P/('analysis/azahar-native-game-v0.1.0'+('-'+args.revision if args.revision else '')+'-cxi'+('-'+args.proof_attempt if args.proof_attempt else ''))
        proof=json.loads((evidence/'result.json').read_text())
        assert proof['passed'] and proof['safe_exit'] and proof['sequential_passed'] and proof['sequential_cycles']>=3
        assert proof['CXI_sha256']==sha(D/'native-game.cxi')
        assert proof['runner_sha256']==sha(P/'tests/smoke_native_game.py')
        manifest=json.loads((D/'build-manifest.json').read_text())
        for name,digest in manifest['inputs_sha256'].items():assert sha(P/name)==digest,name
        for name,digest in manifest['outputs_sha256'].items():assert sha(D/name)==digest,name
        assert not (D/'native-game.cia').exists(),'Preserve existing CIA'
        subprocess.run([str(P/'toolchain/extras/makerom/makerom.exe'),'-f','cia','-o',str(D/'native-game.cia'),'-rsf',str(D/'native-game.rsf'),'-target','t','-exefslogo','-elf',str(D/'native-game.elf'),'-icon',str(D/'native-game.smdh'),'-banner',str(D/'native-game.bnr'),'-ver','1'],check=True)
        data=(D/'native-game.cia').read_bytes();header,_,_,cert,ticket,tmd,_,size=struct.unpack_from('<IHHIIIIQ',data)
        offset=sum((n+63)&~63 for n in [header,cert,ticket,tmd]);payload=data[offset:offset+size]
        assert payload[0x100:0x104]==b'NCCH' and struct.unpack_from('<Q',payload,0x108)[0]==int(TITLE,16)
        (D/'cia-payload.cxi').write_bytes(payload)
        (D/'cia-manifest.json').write_text(json.dumps({'title_id':TITLE,'CIA_sha256':sha(D/'native-game.cia'),'payload_sha256':sha(D/'cia-payload.cxi'),'CIA_bytes':len(data),'payload_offset':offset,'payload_bytes':size,'game_resources_included':False,'hardware_tested':False,'CXI_validation':evidence.relative_to(P).as_posix()},indent=2)+'\n')
        print('CIA created; not packaged until its own extracted payload passes Azahar.')
        return
    assert not D.exists(),'Preserve existing build'
    D.mkdir()
    generated=['ds7_threads_probe.c','ds7_platform_probe.c','ds6_time_probe.c','ds8_cpp_probe.c','ds34_gpu_native.c','ds34_shader.h','ds34.shbin']
    for name in generated:shutil.copyfile(BASE/name,D/name)
    commands=[]
    def run(cmd):
        commands.append(list(map(str,cmd)));subprocess.run(commands[-1],cwd=D,check=True)
    compile_cmd=next(q for q in old['commands'] if str(b.GCC)==q[0])
    compile_cmd=[q.replace(str(BASE),str(D)).replace(str(P/'tests/engine_native_frame.c'),str(P/'tests/native_game.c')).replace('native-frame.elf','native-game.elf') for q in compile_cmd]
    run(compile_cmd)
    rsf=(BASE/'native-frame.rsf').read_text().replace('DS-NATIVE-FRAME','DS-NATIVE-GAME').replace('CTR-H-DSNF','CTR-H-DSNG').replace('0xFDE70','0xFDE71')
    (D/'native-game.rsf').write_text(rsf)
    canvas=Image.new('RGB',(256,128),(7,20,30));draw=ImageDraw.Draw(canvas)
    draw.rectangle((8,8,247,119),outline=(90,230,222),width=2)
    for text,y,size in [('DS NATIVE GAME',24,20),('ONE ORIGINAL FRAME',62,16),('EXPERIMENTAL 0.1.0',92,12)]:
        draw.text((128,y),text,fill=(180,240,235),font=ImageFont.load_default(size=size),anchor='mt')
    canvas.save(D/'banner.png')
    with wave.open(str(D/'silence.wav'),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(22050);out.writeframes(b'\0'*8820)
    run([P/'toolchain/extras/bannertool/bannertool.exe','makebanner','-i',D/'banner.png','-a',D/'silence.wav','-o',D/'native-game.bnr'])
    run([b.DKP/'tools/bin/smdhtool.exe','--create','DS Native Game 0.1.0','Original code frame; experimental','Dead Space Mobile port research',b.DKP/'libctru/default_icon.png',D/'native-game.smdh'])
    run([P/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',D/'native-game.cxi','-rsf',D/'native-game.rsf','-target','t','-exefslogo','-elf',D/'native-game.elf','-icon',D/'native-game.smdh','-banner',D/'native-game.bnr'])
    assert (D/'ds34.shbin').read_bytes()==(BASE/'ds34.shbin').read_bytes()
    inputs={**old['inputs_sha256'],**{q.relative_to(P).as_posix():sha(q) for q in [Path(__file__).resolve(),P/'tests/native_game.c',*[D/n for n in generated]]}}
    outputs={n:sha(D/n) for n in ['native-game.elf','native-game.cxi','native-game.rsf','native-game.smdh','native-game.bnr','ds34.shbin']}
    report={'version':'0.1.0','title_id':TITLE,'baseline':'s16','baseline_CXI_sha256':old['outputs_sha256']['native-frame.cxi'],'hardware_tested':False,'CIA_created':False,'commands':commands,'inputs_sha256':inputs,'outputs_sha256':outputs,'graphics_and_thread_overlays_identical_to_s16':True,'resources_embedded':False}
    (D/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Isolated native-game CXI built; CIA gate requires its own three-cycle test.')

if __name__=='__main__':main()
