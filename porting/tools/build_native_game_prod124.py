"""Isolated, gated memory-profile ladder. Never runs hardware or pushes Git."""
import argparse
import difflib
import json
import math
import shutil
import struct
import subprocess
from pathlib import Path
from build_native_startup_legacy import payload, sha
from build_native_game_memory_probe import SAMPLE

P = Path(__file__).resolve().parents[1]
BASE = P / '3ds/build-native-game-v0.1.0-h2'
MEM = P / '3ds/build-native-game-v0.1.0-mem1'
A = P / 'analysis/native-game-prod124-v0.1.0'
STEPS = ['observe', 'arena', 'linear', 'normal', 'guard', 'prod']
REVS = dict(zip(STEPS, ['p124o','p124a','p124l','p124n','p124g','p124p']))
TITLE = '000400000FDE7300'
GENERATED = ['ds7_threads_probe.c','ds7_platform_probe.c','ds6_time_probe.c',
             'ds8_cpp_probe.c','ds34_gpu_native.c','ds34_shader.h','ds34.shbin']
WRAPS = ['malloc','calloc','realloc','memalign','free','linearAlloc','linearMemAlign',
         'linearFree','vramAlloc','vramMemAlign','vramFree']
PROD_PROOF_ATTEMPT = ''

PEAK = r'''
    report("PEAKJSON {\"normal_live\":%lu,\"normal_footprint\":%lu,\"normal_request\":%lu,\"linear_used\":%lu,\"linear_other\":%lu,\"linear_request\":%lu,\"vram_used\":%lu,\"vram_request\":%lu,\"arena_actual_size\":%lu}\n",
        (unsigned long)observed_normal_live,(unsigned long)observed_normal_footprint,
        (unsigned long)observed_normal_request,(unsigned long)observed_linear_used,
        (unsigned long)observed_linear_other,(unsigned long)observed_linear_request,
        (unsigned long)observed_vram_used,(unsigned long)observed_vram_request,
        (unsigned long)observed_arena_size);
'''
REGIONS = r'''
static int owned_region(const char *name,void *pointer,u32 bytes,u32 alignment,int linear){
    u32 start=(u32)pointer;MemInfo mi;PageInfo pi;
    if(!start || !bytes || (start&(alignment-1)) || bytes>UINT32_MAX-start ||
       R_FAILED(svcQueryMemory(&mi,&pi,start)) || (mi.perm&3)!=3 ||
       mi.base_addr>start || start-mi.base_addr>mi.size || bytes>mi.size-(start-mi.base_addr))return -1;
    u32 physical=linear?osConvertVirtToPhys(pointer):0;
    u32 last=linear?osConvertVirtToPhys((u8 *)pointer+bytes-1):0;
    if(linear && (!physical || last-physical!=bytes-1 || linearGetSize(pointer)<bytes))return -1;
    report("REGIONJSON {\"name\":\"%s\",\"base\":%lu,\"bytes\":%lu,\"alignment\":%lu,\"rw_span\":true,\"linear\":%s,\"physical\":%lu,\"physical_last\":%lu}\n",
        name,(unsigned long)start,(unsigned long)bytes,(unsigned long)alignment,linear?"true":"false",(unsigned long)physical,(unsigned long)last);
    return 0;
}
'''


def build_dir(step):
    return P / ('3ds/build-native-game-v0.1.0-' + REVS[step])


def proof(step, cycles=1, container='cxi'):
    suffix = ('-' + PROD_PROOF_ATTEMPT) if step == 'prod' and container == 'cxi' and PROD_PROOF_ATTEMPT else ''
    root = P / ('analysis/azahar-native-game-v0.1.0-' + REVS[step] + '-' + container + suffix)
    r = json.loads((root / 'result.json').read_text())
    assert r['passed'] and r['safe_exit'] and r['sequential_cycles'] >= cycles
    for c in r['cycles']:
        assert c['baseline_RGB565_exact'] and c['different_pixels'] == 0 and c['both_heaps_released']
        assert c['shutdown_proof']['kernel_joins'] == 6 and not c['shutdown_proof']['worker_handles_remaining']
    assert r['CXI_sha256'] == sha(build_dir(step) / 'native-game.cxi')
    assert r['runner_sha256'] == sha(P / 'tests/smoke_native_game_prod124.py')
    manifest = json.loads((build_dir(step) / 'build-manifest.json').read_text())
    assert manifest['observer_sha256'] == sha(P / 'tests/native_game_memory_observer.h')
    for name, digest in manifest['outputs_sha256'].items():
        assert sha(build_dir(step) / name) == digest, name
    return root, r


def budget_from_observation():
    root, _ = proof('observe')
    lines = (root / 'cycle-0001/native-game.log').read_text().splitlines()
    peaks = [json.loads(l[9:]) for l in lines if l.startswith('PEAKJSON ')]
    memory = [json.loads(l[8:]) for l in lines if l.startswith('MEMJSON ')]
    assert peaks and memory
    peak = {k: max(s[k] for s in peaks) for k in peaks[0]}
    # Normal capacity keeps a largest-request-sized reserve plus1MiB above the
    # measured allocator footprint; round to4MiB. Linear slack includes1MiB
    # above observed transient peak, rounded to4MiB. Keep total heaps<=120MiB.
    unit = 4 << 20
    normal = math.ceil((peak['normal_footprint'] + peak['normal_request'] + (1 << 20)) / unit) * 4
    slack = math.ceil((peak['linear_other'] + (1 << 20)) / unit) * 4
    linear = 120 - normal
    arena = linear - slack
    donor_peak = max(s['donor_brk_peak'] + s['donor_map_peak_pages'] * 4096 for s in memory)
    assert normal < 40 and 0 < linear < 132 and donor_peak + (16 << 20) < arena << 20
    result = {'normal_MiB':normal, 'linear_MiB':linear, 'arena_MiB':arena,
              'other_linear_budget_MiB':slack, 'total_heaps_MiB':120,
              'observation_peaks':peak, 'observed_donor_high_water_bytes':donor_peak,
              'not_a_gameplay_minimum':True}
    (A / 'budget.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    global PROD_PROOF_ATTEMPT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', required=True, choices=STEPS + ['cia'])
    parser.add_argument('--proof-attempt', default='')
    args = parser.parse_args(); step = args.step
    assert not args.proof_attempt or (args.proof_attempt.isalnum() and step == 'cia')
    PROD_PROOF_ATTEMPT = args.proof_attempt
    if step == 'cia':
        validated_root, _ = proof('prod', 3)
        d = build_dir('prod'); assert not (d / 'native-game.cia').exists()
        cmd = makerom('cia', d)
        subprocess.run(cmd, cwd=d, check=True)
        data = payload((d / 'native-game.cia').read_bytes())
        assert data == (d / 'native-game.cxi').read_bytes()
        (d / 'cia-payload.cxi').write_bytes(data)
        (d / 'cia-manifest.json').write_text(json.dumps({'title_id':TITLE,
            'CIA_sha256':sha(d/'native-game.cia'),'CIA_bytes':(d/'native-game.cia').stat().st_size,
            'payload_sha256':sha(d/'cia-payload.cxi'),'hardware_tested':False,
            'hardware_run_authorized':False,'game_resources_included':False,
            'CXI_software_proof':validated_root.relative_to(P).as_posix(),'command':cmd},indent=2)+'\n')
        print('CIA created after3-cycle CXI gate. Its own payload must pass before readiness.')
        return
    if not A.exists():
        assert step == 'observe'; A.mkdir()
        old = json.loads((P/'analysis/native-startup-prod124-v0.1.0/preservation.json').read_text())['before']
        for folder in [BASE, MEM, P/'3ds/build-native-startup-v0.1.0-prod124']:
            for q in folder.rglob('*'):
                if q.is_file():old[q.relative_to(P).as_posix()]=sha(q)
        (A/'preservation.json').write_text(json.dumps({'before':old},indent=2)+'\n')
    protected=json.loads((A/'preservation.json').read_text())['before']
    assert all(sha(P/n)==h for n,h in protected.items())
    index=STEPS.index(step)
    if index:proof(STEPS[index-1])
    budget=budget_from_observation() if index else None
    normal=budget['normal_MiB'] if index>=3 else 40
    linear=budget['linear_MiB'] if index>=2 else 132
    arena=budget['arena_MiB'] if index>=1 else 128
    guard=124 if index>=4 else 178
    mode=124 if index>=5 else 178
    d=build_dir(step);assert not d.exists(),'Preserve completed build'
    d.mkdir();commands=[]
    for n in GENERATED:shutil.copyfile(BASE/n,d/n)
    for n in ['native-game.bnr']:shutil.copyfile(BASE/n,d/n)
    rsf=(BASE/'native-game.rsf').read_text().replace('DS-NATIVE-GAME','DS-GAME-P124').replace('CTR-H-DSNG','CTR-H-DG24').replace('0xFDE71','0xFDE73')
    if mode==124:rsf=rsf.replace('SystemModeExt: 178MB','SystemModeExt: 124MB')
    (d/'native-game.rsf').write_text(rsf)
    if step=='prod':
        previous=build_dir('guard')
        for n in ['native-game.elf','native-game-memory.c','native-game.smdh']:
            shutil.copyfile(previous/n,d/n)
    else:
        old_source=(MEM/'native-game-memory.c').read_text()
        source=old_source
        assert source.count(SAMPLE)==1
        sample=SAMPLE.replace('arena?134217728ul:0ul','arena?(unsigned long)DS_GAME_ARENA_BYTES:0ul')
        sample=sample[:-2]+PEAK+'}\n'
        source=source.replace(SAMPLE,sample)
        source=source.replace('#include <malloc.h>','#include <malloc.h>\n#include "native_game_memory_observer.h"')
        source=source.replace('u32 __ctru_heap_size=40*1024*1024;','u32 __ctru_heap_size=DS_GAME_NORMAL_BYTES;')
        source=source.replace('u32 __ctru_linear_heap_size=132*1024*1024;','u32 __ctru_linear_heap_size=DS_GAME_LINEAR_BYTES;')
        source=source.replace('128*1024*1024','DS_GAME_ARENA_BYTES')
        source=source.replace('<178*1024*1024','<DS_GAME_REQUIRED_APP_BYTES')
        source=source.replace('arena=%08lx/134217728 trampoline=', 'arena=%08lx/%lu trampoline=')
        source=source.replace('(unsigned long)arena,(unsigned long)trampoline','(unsigned long)arena,(unsigned long)DS_GAME_ARENA_BYTES,(unsigned long)trampoline')
        source=source.replace('static int initialize(void){',REGIONS+'\nstatic int initialize(void){')
        anchor='if(!image || !arena || !trampoline)return -1;'
        assert source.count(anchor)==1
        source=source.replace(anchor,anchor+'\n    if(owned_region("donor_file",donor,DS_DONOR_SIZE,1,0) || owned_region("image",image,info.image_size,4096,0) || owned_region("arena",arena,DS_GAME_ARENA_BYTES,4096,1) || owned_region("trampoline",trampoline,12288,4096,0))return -1;')
        source=source.replace('ds-native-game-v0.1.0/','ds-native-game-prod124-v0.1.0/')
        source=source.replace('native-game-v010','native-game-prod124-v010')
        source=source.replace('DS Native Game 0.1.0','DS Game Prod124 0.1.0')
        defines=f'#define DS_GAME_NORMAL_BYTES ({normal}u*1024*1024)\n#define DS_GAME_LINEAR_BYTES ({linear}u*1024*1024)\n#define DS_GAME_ARENA_BYTES ({arena}u*1024*1024)\n#define DS_GAME_REQUIRED_APP_BYTES ({guard}u*1024*1024)\n'
        source=defines+source
        (d/'native-game-memory.c').write_text(source)
        (d/'entry.diff').write_text(''.join(difflib.unified_diff(old_source.splitlines(True),source.splitlines(True),fromfile='mem1',tofile=step)))
        old=json.loads((BASE/'build-manifest.json').read_text())
        command=next(q for q in old['commands'] if q[0].endswith('arm-none-eabi-gcc.exe'))
        command=[q.replace(str(BASE),str(d)).replace(str(P/'tests/native_game.c'),str(d/'native-game-memory.c')) for q in command]
        command.insert(-2,'-Wl,'+','.join('--wrap='+name for name in WRAPS))
        commands.append(command);subprocess.run(command,cwd=d,check=True)
        cmd=[str(P/'toolchain/devkitpro/tools/bin/smdhtool.exe'),'--create','DS Game Prod124','One original frame; experimental','Dead Space port research',str(P/'toolchain/devkitpro/libctru/default_icon.png'),str(d/'native-game.smdh')]
        commands.append(cmd);subprocess.run(cmd,cwd=d,check=True)
    cmd=makerom('cxi',d);commands.append(cmd);subprocess.run(cmd,cwd=d,check=True)
    m={'step':step,'revision':REVS[step],'normal_MiB':normal,'linear_MiB':linear,'arena_MiB':arena,
       'required_app_MiB':guard,'memory_mode_MiB':mode,'title_id':TITLE,
       'hardware_run_authorized':False,'CIA_created':False,'commands':commands,
       'observer_sha256':sha(P/'tests/native_game_memory_observer.h'),
       'outputs_sha256':{n:sha(d/n) for n in ['native-game.elf','native-game.cxi','native-game-memory.c','native-game.rsf','native-game.smdh','native-game.bnr']}}
    (d/'build-manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    print(json.dumps({k:v for k,v in m.items() if k not in ['commands','outputs_sha256']}))


def makerom(kind,d):
    return [str(P/'toolchain/extras/makerom/makerom.exe'),'-f',kind,'-o',str(d/('native-game.'+kind)),
            '-rsf',str(d/'native-game.rsf'),'-target','t','-exefslogo','-elf',str(d/'native-game.elf'),
            '-icon',str(d/'native-game.smdh'),'-banner',str(d/'native-game.bnr'),'-ver','1']


if __name__=='__main__':main()
