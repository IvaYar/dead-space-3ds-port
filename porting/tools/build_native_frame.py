"""Separate original-code checkpoint. Build CXI first; CIA requires software PASS."""
import argparse
import ast
import difflib
import hashlib
import json
import subprocess
from pathlib import Path
import build_stage1 as b
import build_ds34_rgba8 as rgba

P=b.PORTING
D=P/'3ds/build-native-frame-v0.1.0'
A=P/'analysis/native-original-frame-v0.1.0'
LIB=P/'toolchain/citro3d'
TITLE='000400000FDE7000'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    global D
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cia',action='store_true');parser.add_argument('--revision',default='');args=parser.parse_args()
    if args.revision:
        assert args.revision.isalnum()
        D=D.with_name(D.name+'-'+args.revision)
    if args.cia:
        proof=json.loads((P/('analysis/azahar-native-frame-v0.1.0'+('-'+args.revision if args.revision else ''))/'result.json').read_text())
        assert proof['passed'] and proof['safe_exit'] and proof['baseline_RGB565_exact']
        assert proof.get('sequential_passed') and proof.get('sequential_cycles',0)>=3 and proof.get('same_core_and_SD')
        assert all(q['passed'] and q['safe_exit'] and q['both_heaps_released'] and not q['invalid_memory_accesses'] and q['final_guest_result']['active_threads']==0 for q in proof['cycles'])
        assert all(q['shutdown_proof']['kernel_joins']==6 and q['shutdown_proof']['worker_handles_remaining']==0 and q['shutdown_proof']['files_balanced'] for q in proof['cycles'])
        assert proof['CXI_sha256']==sha(D/'native-frame.cxi')
        manifest=json.loads((D/'build-manifest.json').read_text())
        assert all(sha(P/name)==digest for name,digest in manifest['inputs_sha256'].items()), 'Source changed after validation'
        assert proof['runner_sha256']==sha(P/'tests/smoke_native_frame.py')
        subprocess.run([str(P/'toolchain/extras/makerom/makerom.exe'),'-f','cia','-o',str(D/'native-frame.cia'),'-rsf',str(D/'native-frame.rsf'),'-target','t','-exefslogo','-elf',str(D/'native-frame.elf'),'-icon',str(D/'native-frame.smdh'),'-banner',str(P/'3ds/build-stage8/stage8.bnr'),'-ver','1'],check=True)
        return
    if (D/'build-manifest.json').exists():raise SystemExit('Existing native candidate is preserved; select a new version for revisions')
    D.mkdir(exist_ok=True);A.mkdir(exist_ok=True)
    tree=ast.parse((P/'tools/build_emulator_runtime.py').read_text())
    names=next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='names' for t in n.targets))
    extra=('ds_exec.c','ds_cache.s','ds6_platform_3ds.c','ds7_platform_3ds.c','ds11_platform_3ds.c','ds12_sensor_3ds.c','ds19_assets_3ds.c','ds20_dirs_3ds.c','ds24_files_3ds.c','ds25_assets_3ds.c','ds27_pages_3ds.c')
    sources=[P/'3ds/source'/n for n in (*names,*extra)]
    # Diagnostic copies keep the baseline DS7 implementation byte-for-byte.
    worker_source=(P/'3ds/source/ds7_threads.c').read_text()
    worker_source=worker_source.replace('volatile uint32_t wait_kind,wait_object;', 'volatile uint32_t wait_kind,wait_object; uint32_t probe_caller,probe_stack[32];')
    worker_source=worker_source.replace('uint32_t probe_caller,probe_stack[32];','uint32_t probe_caller,probe_stack[32]; int32_t sleep_cv; int sleep_interrupted; uint32_t sleep_seconds,sleep_nanoseconds,sleep_interrupt_returns;')
    worker_source=worker_source.replace('static void waiting(', '''#define PROBE_WAIT() do { Worker *pw=current(); if(pw){ pw->probe_caller=(uint32_t)__builtin_return_address(0); uint32_t *ps; __asm__ volatile("mov %0,sp":"=r"(ps)); memcpy(pw->probe_stack,ps,sizeof(pw->probe_stack)); }} while(0)
static void waiting(''')
    worker_source=worker_source.replace('waiting(3,s);','PROBE_WAIT();waiting(3,s);').replace('waiting(2,c);','PROBE_WAIT();waiting(2,c);')
    worker_source=worker_source.replace('return t?condition_wait(c,m,t):22;', 'PROBE_WAIT();waiting(4,c);int r=t?condition_wait(c,m,t):22;waiting(0,NULL);return r;')
    worker_source=worker_source.replace('return t?semaphore_wait(s,0,t):sem_result(22);', 'PROBE_WAIT();waiting(5,s);int r=t?semaphore_wait(s,0,t):sem_result(22);waiting(0,NULL);return r;')
    worker_source+='''
#include "native_thread_probe.h"
void ds7_probe_workers(NativeWorkerProbe out[17]){
    ds7_gate_lock();
    for(unsigned i=0;i<17;++i){
        Worker *w=&workers[i];
        out[i]=(NativeWorkerProbe){.token=w->used?w->token:0,.entry=(uint32_t)w->entry,.argument=(uint32_t)w->argument,.wait_kind=w->wait_kind,.wait_object=w->wait_object,.done=w->done,.detached=w->detached,.joining=w->joining,.stack_bytes=w->attr.size,.kernel_wait=-1,.wait_caller=w->probe_caller};
        memcpy(out[i].wait_stack,w->probe_stack,sizeof(w->probe_stack));
        out[i].sleep_seconds=w->sleep_seconds;out[i].sleep_nanoseconds=w->sleep_nanoseconds;out[i].sleep_interrupt_returns=w->sleep_interrupt_returns;
        if(w->used && w->native && !w->joining)out[i].kernel_wait=ds7_probe_kernel(w->native);
    }
    ds7_gate_unlock();
}
void ds7_probe_sleep_begin(uint32_t caller,const uint32_t *stack){
    Worker *w=current();if(w){w->probe_caller=caller;memcpy(w->probe_stack,stack,sizeof(w->probe_stack));waiting(6,NULL);}
}
void ds7_probe_sleep_end(void){waiting(0,NULL);}
/* Native checkpoint only: a timed condition wait preserves a normal sleep,
 * while shutdown can cooperatively interrupt a worker with EINTR. No teardown,
 * stack unwinding or fabricated worker completion happens here. */
int ds7_checkpoint_interrupt(uint32_t token){
    ds7_gate_lock();Worker *w=find_worker(token);
    if(!w || w==&workers[0])return unlock_result(3);
    if(w->done)return unlock_result(0);
    w->sleep_interrupted=1;ds7_cv_wake(&w->sleep_cv,1);return unlock_result(0);
}
int ds7_checkpoint_sleep(const DS6Time *request,DS6Time *remaining){
    DS6Time now;if(ds6_native_clock(1,&now))return -1;
    int64_t duration=(int64_t)request->sec*1000000000+request->nsec;
    if(!duration){ds7_platform_yield();return 0;}
    int64_t deadline=(int64_t)now.sec*1000000000+now.nsec+duration;
    ds7_gate_lock();Worker *w=current();
    if(!w){ds7_gate_unlock();return ds6_native_sleep(request);}
    w->sleep_seconds=request->sec;w->sleep_nanoseconds=request->nsec;
    for(;;){
        if(ds6_native_clock(1,&now)){ds7_gate_unlock();return -1;}
        int64_t left=deadline-((int64_t)now.sec*1000000000+now.nsec);
        if(left<=0){ds7_gate_unlock();return 0;}
        if(w->sleep_interrupted){
            ++w->sleep_interrupt_returns;
            if(remaining){remaining->sec=(int32_t)(left/1000000000);remaining->nsec=(int32_t)(left%1000000000);}
            ds7_gate_unlock();*ds_io_errno()=4;return -1;
        }
        int result=ds7_cv_wait(&w->sleep_cv,left);
        if(result && result!=110){ds7_gate_unlock();*ds_io_errno()=5;return -1;}
    }
}
'''
    platform_source=(P/'3ds/source/ds7_platform_3ds.c').read_text()
    platform_source+='''
#include "native_thread_probe.h"
int32_t ds7_probe_kernel(void *pointer){
    NativeThread *native=pointer;
    return svcWaitSynchronization(native->handle,0);
}
'''
    (D/'ds7_threads_probe.c').write_text(worker_source)
    (D/'ds7_platform_probe.c').write_text(platform_source)
    time_source=(P/'3ds/source/ds6_time.c').read_text()
    time_source=time_source.replace('int DS_IO_SOFT ds6_usleep(uint32_t microseconds) {', '''extern void ds7_probe_sleep_begin(uint32_t,const uint32_t *);
extern void ds7_probe_sleep_end(void);
int DS_IO_SOFT ds6_usleep(uint32_t microseconds) {
    uint32_t *stack;__asm__ volatile("mov %0,sp":"=r"(stack));ds7_probe_sleep_begin((uint32_t)__builtin_return_address(0),stack);''')
    time_source=time_source.replace('return ds6_nanosleep(&request,NULL);\n}', 'int result=ds6_nanosleep(&request,NULL);ds7_probe_sleep_end();return result;\n}',1)
    time_source=time_source.replace('#include "ds6.h"', '#include "ds6.h"\nextern void ds7_probe_sleep_begin(uint32_t,const uint32_t *);\nextern void ds7_probe_sleep_end(void);')
    time_source=time_source.replace('extern void ds7_probe_sleep_end(void);','extern void ds7_probe_sleep_end(void);\nextern int ds7_checkpoint_sleep(const DS6Time *,DS6Time *);',1)
    time_source=time_source.replace('int result=ds6_native_sleep(request);', '''uint32_t *sleep_stack;__asm__ volatile("mov %0,sp":"=r"(sleep_stack));ds7_probe_sleep_begin((uint32_t)__builtin_return_address(0),sleep_stack);
    int result=ds7_checkpoint_sleep(request,remaining);ds7_probe_sleep_end();''')
    (D/'ds6_time_probe.c').write_text(time_source)
    cpp_source=(P/'3ds/source/ds8_cpp.c').read_text()+'''
#include "native_thread_probe.h"
uint32_t ds8_probe_destructors(NativeDestructorProbe out[256]){
    uint32_t n=0;ds7_gate_lock();
    for(unsigned i=0;i<DESTRUCTORS;++i)if(destructors[i].state==1){Destructor *d=&destructors[i];out[n++]=(NativeDestructorProbe){(uint32_t)d->destroy,(uint32_t)d->object,(uint32_t)d->dso,d->sequence};}
    ds7_gate_unlock();return n;
}
'''
    (D/'ds8_cpp_probe.c').write_text(cpp_source)
    replacements={'ds7_threads.c':'ds7_threads_probe.c','ds7_platform_3ds.c':'ds7_platform_probe.c','ds6_time.c':'ds6_time_probe.c','ds8_cpp.c':'ds8_cpp_probe.c'}
    sources=[D/replacements[q.name] if q.name in replacements else q for q in sources]
    original=(P/'3ds/source/ds34_gpu_3ds.c').read_text();overlay=original
    for old,new in rgba.EDITS:
        assert overlay.count(old)==1;overlay=overlay.replace(old,new)
    overlay+='\n/* Native checkpoint: close the empty post-present frame without another LCD transfer. */\nvoid ds34_native_finish(void){if(g.frame){C3D_RenderTargetDetachOutput(g.target);FRAME_END();g.frame=0;}}\n'
    (D/'ds34_gpu_native.c').write_text(overlay)
    (A/'backend.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),overlay.splitlines(True),fromfile='preserved/backend.c',tofile='native-copy/backend.c')))
    sources += [D/'ds34_gpu_native.c',P/'tests/engine_native_frame.c',P/'tests/engine_trap.s']
    commands=[]
    def run(*cmd):
        commands.append(list(map(str,cmd)));subprocess.run(commands[-1],cwd=D,check=True)
    run(b.DKP/'tools/bin/picasso.exe','-o',D/'ds34.shbin',P/'3ds/source/ds34_gpu.v.pica')
    blob=(D/'ds34.shbin').read_bytes();assert blob==(P/'3ds/build-ds34-uv-mask-v0.2.1/ds34.shbin').read_bytes()
    (D/'ds34_shader.h').write_text('static const unsigned char ds34_shader[] __attribute__((aligned(4)))={'+','.join(map(str,blob))+'};\n')
    includes=['-I'+str(q) for q in [D,P/'tests',P/'3ds/include',P/'3ds/build-emulator',b.DKP/'libctru/include',LIB/'include']]
    flags=['-DDS_NEW3DS_178','-DDS7_SEMAPHORE_COUNT=64','-DDS34_CAPTURE_RGBA','-DDS34_SEQUENCE_AUDIT','-DDS34_FRAME_DIAGNOSTICS']
    run(b.GCC,*b.FLAGS,*flags,*includes,'-fno-builtin','-D__3DS__','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',*sources,
        '-Wl,--wrap=gxCmdQueueRun,--wrap=gspSubmitGxCommand','-L'+str(LIB/'lib'),'-L'+str(b.DKP/'libctru/lib'),'-lcitro3d','-lctru','-lm','-Wl,--gc-sections','-o',D/'native-frame.elf')
    rsf=(P/'3ds/build-emulator/audit-178.rsf').read_text().replace('DS-LOADER-AUDT','DS-NATIVE-FRAME').replace('CTR-H-DSEA','CTR-H-DSNF').replace('0xFDE5E','0xFDE70')
    (D/'native-frame.rsf').write_text(rsf)
    run(b.DKP/'tools/bin/smdhtool.exe','--create','DS Native Frame 0.1.0','Original GPU image checkpoint; experimental','Homebrew port research',b.DKP/'libctru/default_icon.png',D/'native-frame.smdh')
    run(P/'toolchain/extras/makerom/makerom.exe','-f','cxi','-o',D/'native-frame.cxi','-rsf',D/'native-frame.rsf','-target','t','-exefslogo','-elf',D/'native-frame.elf','-icon',D/'native-frame.smdh','-banner',P/'3ds/build-stage8/stage8.bnr')
    inputs=sources+list((P/'3ds/include').glob('*.h'))+[Path(__file__).resolve(),P/'tests/native_thread_probe.h',P/'3ds/source/ds6_time.c',P/'3ds/source/ds8_cpp.c',P/'3ds/source/ds7_threads.c',P/'3ds/source/ds7_platform_3ds.c',P/'3ds/source/ds34_gpu.v.pica',LIB/'lib/libcitro3d.a',b.DKP/'libctru/lib/libctru.a']
    report={'native_capable':True,'hardware_tested':False,'reference_game_frame':180,'target_RGB565_crc32':'ea733050','max_original_callbacks':600,'title_id':TITLE,'CIA_created':False,'emulator_harness_modified':False,'RGBA8_RGB8':True,'hardware_successful_shader_identical':True,'commands':commands,'inputs_sha256':{q.relative_to(P).as_posix():sha(q) for q in inputs},'outputs_sha256':{n:sha(D/n) for n in ['native-frame.elf','native-frame.cxi','ds34.shbin']}}
    (D/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Built separate native-capable CXI; no CIA until frame and safe-exit verification')
if __name__=='__main__':main()
