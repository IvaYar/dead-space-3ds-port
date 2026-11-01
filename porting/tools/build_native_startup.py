"""Build a small-heap, startup-only CIA. Never launches hardware or donor code."""
import hashlib
import json
import re
import struct
import subprocess
import wave
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import build_stage1 as b

P=b.PORTING
D=P/'3ds/build-native-startup-v0.1.0'
A=P/'analysis/native-startup-memory-v0.1.0'
TITLE='000400000FDE7200'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert not D.exists(),'Preserve existing startup candidate'
    D.mkdir();commands=[]
    def run(cmd):
        commands.append(list(map(str,cmd)));subprocess.run(commands[-1],cwd=D,check=True)
    sdk=b.DKP/'libctru'
    source=P/'tests/native_startup.c'
    run([b.GCC,*b.FLAGS,'-D__3DS__','-I'+str(sdk/'include'),'-specs=3dsx.specs','-Wl,-z,noexecstack',source,'-Wl,--gc-sections,--wrap=__system_allocateHeaps','-L'+str(sdk/'lib'),'-lctru','-lm','-o',D/'startup.elf'])
    original=(P/'3ds/build-native-game-v0.1.0-h2/native-game.rsf').read_text()
    rsf=original.replace('DS-NATIVE-GAME','DS-STARTUP').replace('CTR-H-DSNG','CTR-H-DSST').replace('0xFDE71','0xFDE72')
    assert 'SystemModeExt: 178MB' in rsf and 'ReleaseKernelMinor: "44"' in rsf
    (D/'startup.rsf').write_text(rsf)
    canvas=Image.new('RGB',(256,128),(7,20,30));draw=ImageDraw.Draw(canvas)
    for label,y,size in [('STARTUP TEST',20,22),('NO GAME / NO 3D',60,16),('2 MiB + 2 MiB',91,16)]:
        draw.text((128,y),label,font=ImageFont.load_default(size=size),anchor='mt',fill=(150,230,220))
    canvas.save(D/'banner.png')
    with wave.open(str(D/'silence.wav'),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(22050);out.writeframes(b'\0'*8820)
    run([P/'toolchain/extras/bannertool/bannertool.exe','makebanner','-i',D/'banner.png','-a',D/'silence.wav','-o',D/'startup.bnr'])
    run([b.DKP/'tools/bin/smdhtool.exe','--create','DS Startup Test 0.1.0','Startup only; no game or 3D','Dead Space port research',sdk/'default_icon.png',D/'startup.smdh'])
    maker=P/'toolchain/extras/makerom/makerom.exe'
    for kind in ['cxi','cia']:
        run([maker,'-f',kind,'-o',D/('startup.'+kind),'-rsf',D/'startup.rsf','-target','t','-exefslogo','-elf',D/'startup.elf','-icon',D/'startup.smdh','-banner',D/'startup.bnr','-ver','1'])
    data=(D/'startup.cia').read_bytes();h,_,_,c,t,m,_,size=struct.unpack_from('<IHHIIIIQ',data);offset=sum((n+63)&~63 for n in [h,c,t,m]);payload=data[offset:offset+size]
    assert payload[0x100:0x104]==b'NCCH' and struct.unpack_from('<Q',payload,0x108)[0]==int(TITLE,16)
    (D/'cia-payload.cxi').write_bytes(payload)
    objdump=b.DKP/'devkitARM/bin/arm-none-eabi-objdump.exe'
    disassembly={}
    for name in ['__libctru_init','__wrap___system_allocateHeaps']:
        r=subprocess.run([str(objdump),'-d','--disassemble='+name,str(D/'startup.elf')],capture_output=True,text=True,check=True);disassembly[name]=r.stdout
    assert '<__wrap___system_allocateHeaps>' in disassembly['__libctru_init'],'Linker wrap did not intercept the pre-main call'
    assert '<__system_allocateHeaps>' in disassembly['__wrap___system_allocateHeaps'],'Wrapper must call original SDK allocator'
    (A/'startup-heap-wrap.asm.txt').write_text('\n'.join(disassembly.values()))
    nm=subprocess.check_output([str(b.DKP/'devkitARM/bin/arm-none-eabi-nm.exe'),str(D/'startup.elf')],text=True)
    assert not any(name in nm for name in [' ds34_',' C3D_',' ds_init_run',' ds7_shutdown'])
    ctr=subprocess.run([str(P/'toolchain/extras/ctrtool/ctrtool.exe'),'--verify','--exheader='+str(A/'startup-exheader.bin'),str(D/'startup.cia')],capture_output=True,text=True)
    text=ctr.stdout+ctr.stderr;(A/'startup-CIA-audit.txt').write_text(text)
    errors=[l for l in text.splitlines() if ' ERROR]' in l]
    allowed=['Signature for Ticket was invalid','Signature for TitleMetaData was invalid','Signature for AccessDescriptor was invalid']
    assert len(errors)==3 and all(any(x in e for x in allowed) for e in errors)
    assert all('(GOOD)' in l for l in text.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)',l))
    inputs=[source,Path(__file__).resolve(),sdk/'lib/libctru.a',P/'3ds/build-native-game-v0.1.0-h2/native-game.rsf']
    manifest={'startup_test_only':True,'title_id':TITLE,'hardware_tested':False,'hardware_run_authorized':False,'normal_heap_bytes':2*1048576,'linear_heap_bytes':2*1048576,'New3DS_memory_mode_MiB':178,'same_memory_mode_as_h2':True,'original_libctru_allocator_used':True,'pre_main_wrapper_verified_in_ELF':True,'donor_or_original_assets_required':False,'Citro3D_or_DS34_linked':False,'commands':commands,'inputs_sha256':{q.relative_to(P).as_posix():sha(q) for q in inputs},'outputs_sha256':{n:sha(D/n) for n in ['startup.elf','startup.cia','startup.cxi','cia-payload.cxi','startup.rsf']}}
    (D/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Startup-only CIA built: same 178MiB mode, 2+2MiB heaps, original SDK allocator. Hardware not tested.')

if __name__=='__main__':main()
