"""Azahar-only copy of h2: sample allocator counters, preserve engine/GPU/heaps."""
import difflib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from build_native_startup_legacy import sha

P = Path(__file__).resolve().parents[1]
BASE = P / '3ds/build-native-game-v0.1.0-h2'
D = P / '3ds/build-native-game-v0.1.0-mem1'
A = P / 'analysis/native-game-memory-v0.1.0'

SAMPLE = r'''
/* Read-only phase/frame samples. Does not change allocation limits or owners. */
static void memory_sample(const char *tag){
    struct mallinfo m=mallinfo();DS9MemoryStats a={0};DSRuntimeStats r={0};
    if(threads_started){ds9_memory_stats(&a);ds_runtime_stats(&r);}
    Handle h=0;ResourceLimitType kind=RESLIMIT_COMMIT;s64 limit=0,current=0;
    Result rc=svcGetResourceLimit(&h,CUR_PROCESS_HANDLE);
    if(R_SUCCEEDED(rc)){
        rc=svcGetResourceLimitLimitValues(&limit,h,&kind,1);
        if(R_SUCCEEDED(rc))rc=svcGetResourceLimitCurrentValues(&current,h,&kind,1);
        svcCloseHandle(h);
    }
    report("MEMJSON {\"tag\":\"%s\",\"frame\":%lu,\"query_result\":%lu,\"limit\":%lld,\"commit\":%lld,\"normal_allocated\":%lu,\"normal_allocator_arena\":%lu,\"normal_allocator_free\":%lu,\"linear_free\":%lu,\"donor_arena_reserved\":%lu,\"donor_brk\":%lu,\"donor_brk_peak\":%lu,\"donor_map_pages\":%lu,\"donor_map_peak_pages\":%lu,\"donor_refusals\":%lu,\"runtime_live\":%lu,\"runtime_peak\":%lu,\"runtime_failures\":%lu}\n",
        tag,(unsigned long)current_frame,(unsigned long)rc,(long long)limit,(long long)current,
        (unsigned long)m.uordblks,(unsigned long)m.arena,(unsigned long)m.fordblks,
        (unsigned long)linearSpaceFree(),arena?134217728ul:0ul,
        (unsigned long)a.break_bytes,(unsigned long)a.break_peak,(unsigned long)a.mapped_pages,
        (unsigned long)a.map_peak,(unsigned long)a.refusals,(unsigned long)r.live_bytes,
        (unsigned long)r.peak_bytes,(unsigned long)r.failures);
}
'''


def main():
    resume = sys.argv[1:] == ['--resume-unfinished']
    assert not sys.argv[1:] or resume
    if resume:
        assert D.exists() and A.exists() and not (D / 'build-manifest.json').exists()
        assert not (D / 'native-game.elf').exists() and not (D / 'native-game.cxi').exists()
    else:
        assert not D.exists() and not A.exists(), 'Preserve evidence'
    old = json.loads((BASE / 'build-manifest.json').read_text())
    for name, digest in old['inputs_sha256'].items():
        assert sha(P / name) == digest, name
    for name, digest in old['outputs_sha256'].items():
        assert sha(BASE / name) == digest, name
    D.mkdir(exist_ok=resume); A.mkdir(exist_ok=resume)
    source = (P / 'tests/native_game.c').read_text()
    text = source
    edits = [('#include "ds9_memory.h"', '#include "ds9_memory.h"\n#include "ds_runtime.h"'),
             ('static void stage(const char *name)', SAMPLE + '\nstatic void stage(const char *name)'),
             ('phase=name;report("STAGE %s\\n",name);}', 'phase=name;report("STAGE %s\\n",name);memory_sample(name);}'),
             ('if(initialize())return -1;', 'if(initialize())return -1;\n    memory_sample("initialized");'),
             ('if(graphics.error || ds34_present(&graphics))return -1;', 'if(graphics.error || ds34_present(&graphics))return -1;\n        memory_sample("after_draw");'),
             ('exit_ok=1;outcome(', 'exit_ok=1;memory_sample("after_shutdown");outcome(')]
    for before, after in edits:
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    probe = D / 'native-game-memory.c'; probe.write_text(text)
    (A / 'entry-instrumentation.diff').write_text(''.join(difflib.unified_diff(
        source.splitlines(True), text.splitlines(True), fromfile='native_game.c h2', tofile='generated memory probe')))
    for name in ['ds7_threads_probe.c','ds7_platform_probe.c','ds6_time_probe.c','ds8_cpp_probe.c',
                 'ds34_gpu_native.c','ds34_shader.h','ds34.shbin','native-game.rsf','native-game.smdh','native-game.bnr']:
        shutil.copyfile(BASE / name, D / name)
    commands = []
    compile_cmd = next(q for q in old['commands'] if q[0].endswith('arm-none-eabi-gcc.exe'))
    compile_cmd = [q.replace(str(BASE), str(D)).replace(str(P / 'tests/native_game.c'), str(probe)) for q in compile_cmd]
    commands.append(compile_cmd); subprocess.run(compile_cmd, cwd=D, check=True)
    cmd = [str(P / 'toolchain/extras/makerom/makerom.exe'), '-f', 'cxi', '-o', str(D / 'native-game.cxi'),
           '-rsf', str(D / 'native-game.rsf'), '-target', 't', '-exefslogo', '-elf', str(D / 'native-game.elf'),
           '-icon', str(D / 'native-game.smdh'), '-banner', str(D / 'native-game.bnr')]
    commands.append(cmd); subprocess.run(cmd, cwd=D, check=True)
    result = {'emulator_only_memory_probe': True, 'CIA_created': False, 'hardware_run_authorized': False,
              'normal_linear_heaps_MiB': [40,132], 'donor_arena_MiB':128, 'source_unchanged':sha(P/'tests/native_game.c'),
              'baseline_CIA_sha256':sha(BASE/'native-game.cia'),'commands':commands,
              'outputs_sha256':{n:sha(D/n) for n in ['native-game-memory.c','native-game.elf','native-game.cxi']}}
    (D / 'build-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Built Azahar-only memory telemetry CXI. No CIA, no heap/arena/GPU/shutdown changes.')


if __name__ == '__main__':
    main()
