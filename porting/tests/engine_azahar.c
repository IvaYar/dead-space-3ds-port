/* EMULATOR ONLY. Resolving an unknown import to a terminating trap is execution
 * instrumentation, not an implementation. This file is never built into a CIA. */
#include <3ds.h>
#include <malloc.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ds_exec.h"
#include "ds8.h"
#include "ds9_memory.h"
#include "ds_init.h"
#include "ds_bootstrap.h"
#include "ds_jni.h"
#include "ds10_jni.h"
#include "donor_config.h"
#include "jni10_fixture.h"
#include "platform_fixture.h"
#define LOG "sdmc:/3ds/deadspace/engine-azahar-log.txt"
/* Preserve enough normal heap for two donor arenas and its loaded image. */
u32 __ctru_linear_heap_size=4*1024*1024;
static FILE *journal;
static RecursiveLock journal_lock;
static const char *phase="setup",*trap_names[768];
static uint32_t trap_count,*trampoline,canary=0x9b1d73a5,image_base,image_length;
static DS10Context bridge;
#define jni bridge.base
static DSIO io;
static DSInitPlan plan;
static uint64_t started;
void ds_audit_trap(void);
static void report(const char *format,...) {
    RecursiveLock_Lock(&journal_lock);
    va_list args; va_start(args,format); vprintf(format,args); va_end(args);
    if(journal) { va_start(args,format); vfprintf(journal,format,args); va_end(args); fflush(journal); }
    RecursiveLock_Unlock(&journal_lock);
}
void ds_audit_stop(uint32_t index,uint32_t caller,uint32_t argument) __attribute__((noreturn));
void ds_audit_stop(uint32_t index,uint32_t caller,uint32_t argument) {
    report("STOP unsupported: %s\nPhase: %s\nCaller offset: %08lx\n",index<trap_count?trap_names[index]:"bad trap index",phase,(unsigned long)(caller-image_base));
    if(index<trap_count && !strcmp(trap_names[index],"JNI FindClass (slot 6)") && argument>=image_base && argument-image_base<image_length) {
        uint32_t limit=image_length-(argument-image_base); if(limit>192) limit=192;
        report("Requested class: %.*s\n",(int)limit,(const char *)argument);
    }
    DS9MemoryStats stats; ds9_memory_stats(&stats);
    report("Donor arenas: break=%lu peak=%lu mapped-pages=%lu refusals=%lu\n",(unsigned long)stats.break_bytes,(unsigned long)stats.break_peak,(unsigned long)stats.mapped_pages,(unsigned long)stats.refusals);
    report("ENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n");
    if(journal) { fclose(journal); journal=NULL; }
    /* No cross-thread longjmp or unloading code under a still-running worker. */
    svcExitProcess();
}
static void log_android(const char *text) { report("ANDROID: %s\n",text); }
static void java_request(const char *op,const char *cls,const char *name,const char *signature,int missing) {
    report("JNI %s: %s.%s %s%s\n",op,cls,name,signature,missing==1?" MISSING":missing==2?" EXCEPTION":"");
    if(missing==1) {
        uint32_t state[7];ds10_stats(&bridge,state);
        report("JNI runtime: startup=%lu refs=%lu failures=%lu\n",(unsigned long)state[6],(unsigned long)state[4],(unsigned long)state[3]);
        DS9MemoryStats arena;ds9_memory_stats(&arena);
        report("Donor arenas: break=%lu peak=%lu mapped-pages=%lu refusals=%lu\n",(unsigned long)arena.break_bytes,(unsigned long)arena.break_peak,(unsigned long)arena.mapped_pages,(unsigned long)arena.refusals);
        report("STOP Java adapter\nPhase: %s\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n",phase);
        if(journal){fclose(journal);journal=NULL;}
        svcExitProcess();
    }
}
static int32_t DS_IO_SOFT audit_clock(void) {
    /* Monotonic emulator elapsed time, not a native process CPU clock. */
    return (int32_t)((svcGetSystemTick()-started)*1000000/SYSCLOCK_ARM11);
}
static uint32_t trap_for(const char *name) {
    if(trap_count>=768) ds_audit_stop(768,0,0);
    uint32_t index=trap_count++; trap_names[index]=name;
    uint32_t *code=trampoline+index*4;
    code[0]=0xe59fc000; code[1]=0xe59ff000; code[2]=index; code[3]=(uint32_t)ds_audit_trap;
    return (uint32_t)code;
}
static uint32_t word(const uint8_t *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
extern void DS_JNI_SOFT ds10_test_startup(DSJniHandle *,void *,void *);
static int service_probe(DSExec *exec,const uint8_t *blob,uint32_t blob_size,const char *function,int platform) {
    DSInfo info;
    if(ds_elf_inspect(blob,blob_size,&info))return -1;
    uint8_t *image=memalign(4096,info.image_size);if(!image)return -1;
    if(ds_elf_prepare(blob,blob_size,image,info.image_size,(uint32_t)image,&info))return -1;
    DSResolve resolved;
    if(ds_elf_resolve(blob,&info,image,NULL,0,&resolved) || resolved.imports)return -1;
    uint32_t address,size;
    if(ds_elf_find_export(blob,&info,function,&address,&size))return -1;
    for(uint32_t i=0;i<info.phnum;++i){
        const uint8_t *ph=blob+info.phoff+i*32;
        if(word(ph)!=1 || !(word(ph+24)&1))continue;
        for(uint32_t page=word(ph+8)&~4095u;page<word(ph+8)+word(ph+20);page+=4096)
            if(ds_exec_page(exec,image+page-info.load_min)<0)return -1;
    }
    DS10Context probe={0};ds10_init(&probe,NULL,ds10_test_startup);uint32_t out[4]={0};
    typedef int (*Probe)(DSJniHandle *,uint32_t *) DS_JNI_SOFT;
    int result=((Probe)(image+address-info.load_min))(&probe.base.env,out);
    if(platform)report("Platform probe: %d checks=%lu properties=%lu\n",result,(unsigned long)out[1],(unsigned long)out[2]);
    else report("JNI I/O probe: %d checks=%lu bytes=%lu CRC32=%08lx\n",result,(unsigned long)out[1],(unsigned long)out[2],(unsigned long)out[3]);
    ds10_cleanup(&probe);free(image);
    DSRuntimeStats stats;ds_runtime_stats(&stats);
    report("%s cleanup: files=%lu heap=%lu\n",platform?"Platform":"JNI I/O",(unsigned long)io.active,(unsigned long)stats.live_blocks);
    if(stats.live_blocks || io.active)return -1;
    return result;
}
static void run(void) {
    DSExec exec={0};
    if(ds_exec_open(&exec)<0 || !exec.emulator) { report("REFUSED: emulator-only audit\n"); return; }
    report("Backend: Azahar; native RX not tested\n");
    FILE *input=fopen("sdmc:/3ds/deadspace/libEAMGameDeadSpace_orig.so","rb");
    if(!input) { report("Missing library\n"); return; }
    fseek(input,0,SEEK_END); long length=ftell(input); rewind(input);
    if(length!=DS_DONOR_SIZE) { fclose(input); report("Wrong donor size\n"); return; }
    uint8_t *file=malloc((size_t)length);
    if(!file || fread(file,1,(size_t)length,input)!=(size_t)length) { fclose(input); report("Read/allocation failed\n"); return; }
    fclose(input);
    if(ds_crc32(file,(uint32_t)length)!=DS_DONOR_CRC32) { report("Wrong donor CRC\n"); return; }
    DSInfo info;
    if(ds_elf_inspect(file,(uint32_t)length,&info)) { report("Inspect failed\n"); return; }
    uint8_t *image=memalign(4096,info.image_size);
    void *brk_arena=memalign(4096,20*1024*1024),*map_arena=memalign(4096,20*1024*1024);
    trampoline=memalign(4096,3*4096);
    if(!image || !brk_arena || !map_arena || !trampoline) { report("Arena allocation failed\n"); return; }
    image_base=(uint32_t)image;image_length=info.image_size;
    if(ds_elf_prepare(file,(uint32_t)length,image,info.image_size,image_base,&info)) return;
    ds_io_init(&io,ds_io_sd_ops()); ds_runtime_init(4*1024*1024); ds6_init(log_android);
    if(ds7_init() || ds8_init() || ds9_memory_init(brk_arena,20*1024*1024,map_arena,20*1024*1024)) return;
    if(service_probe(&exec,jni10_fixture,sizeof(jni10_fixture),"probe_jni10",0)){report("JNI I/O PROBE STOPPED\n");return;}
    if(service_probe(&exec,platform_fixture,sizeof(platform_fixture),"probe_platform",1)){report("PLATFORM PROBE STOPPED\n");return;}
    DSBootstrap boot;
    if(ds_bootstrap_verify(file,(uint32_t)length,image,info.image_size,image_base,&info,&boot)) { report("Bootstrap code verification failed\n"); return; }
    DSBinding bindings[768]; uint32_t count=ds6_bindings(bindings,768);
    count+=ds7_bindings(bindings+count,768-count); count+=ds8_bindings(bindings+count,768-count);
    count+=ds9_memory_bindings(bindings+count,768-count);
    DSResolve result; uint32_t before=ds_crc32(image,info.image_size);
    int code=ds_elf_resolve(file,&info,image,bindings,count,&result);
    report("Production preflight: bound=%lu missing=%lu weak=%lu\n",(unsigned long)result.resolved,(unsigned long)result.missing,(unsigned long)result.weak_zero);
    if(code!=DS_UNRESOLVED_IMPORTS || result.resolved!=152 || result.missing!=236 || before!=ds_crc32(image,info.image_size)) return;
    report("Production guard: REFUSED; image unchanged\nAudit clock: emulator monotonic, excluded from supported count\n");
    bindings[count++]=(DSBinding){"clock",(uint32_t)audit_clock};
    bindings[count++]=(DSBinding){"__stack_chk_guard",(uint32_t)&canary};
    for(uint32_t i=1;i<info.symcount;++i) {
        if(!ds_elf_symbol_is_import(file,&info,i)) continue;
        const char *name=ds_elf_symbol_name(file,&info,i);
        const uint8_t *symbol=file+info.symoff+i*16;
        if((symbol[12]>>4)==2) continue;
        int found=0; for(uint32_t j=0;j<count;++j) if(!strcmp(bindings[j].name,name)) found=1;
        if(found) continue;
        if((symbol[12]&15)==1) { report("Unknown data import: %s\n",name); return; }
        bindings[count++]=(DSBinding){name,trap_for(name)};
    }
    uint32_t startup_address,startup_size;
    if(ds_elf_find_export(file,&info,"Java_com_ea_EAIO_EAIO_Startup",&startup_address,&startup_size))return;
    if(ds10_init(&bridge,java_request,(DS10Startup)(image+startup_address-info.load_min)))return;
    ds10_query_compat(&bridge,1);
    uint32_t orientation_address,orientation_size,top;
    if(ds_elf_find_export(file,&info,"Java_com_ea_blast_DeviceOrientationHandlerAndroidDelegate_NativeOnDeviceOrientationChange",&orientation_address,&orientation_size) ||
       ds_elf_constant_export(file,&info,"Java_com_ea_blast_DeviceOrientationHandlerAndroidDelegate_NativeGetDeviceOrientationTopSideUp",0xe3a00001,&top))return;
    ds11_orientation_backend(&bridge,(DS11Orientation)(image+orientation_address-info.load_min),1);
    for(uint32_t slot=4;slot<DS_JNI_ENV_SLOTS;++slot) if(!jni.env_functions[slot])
        jni.env_functions[slot]=trap_for(slot==6?"JNI FindClass (slot 6)":"unimplemented JNI slot");
    if(ds_init_bind_plan(file,(uint32_t)length,image,image_base,bindings,count,&plan,&result)) return;
    /* The immutable RX backend takes its existing explicit emulator branch.
     * Real hardware was refused above, before mapping or executing donor code. */
    for(uint32_t i=0;i<info.phnum;++i) {
        const uint8_t *ph=file+info.phoff+i*32;
        if(word(ph)!=1 || !(word(ph+24)&1)) continue;
        for(uint32_t page=word(ph+8)&~4095u;page<word(ph+8)+word(ph+20);page+=4096)
            if(ds_exec_page(&exec,image+page-info.load_min)<0) { report("Emulator cache boundary failed\n"); return; }
    }
    for(uint32_t page=0;page<3*4096;page+=4096) if(ds_exec_page(&exec,(uint8_t *)trampoline+page)<0) return;
    started=svcGetSystemTick();phase="constructors";
    report("Running %lu donor constructors...\n",(unsigned long)plan.count);
    if(ds_init_run(&plan)) return;
    report("Donor constructors completed: %lu\n",(unsigned long)plan.executed);
    typedef int (*OnLoad)(void *,void *) DS_IO_SOFT;
    phase="JNI_OnLoad";int version=((OnLoad)(image+boot.on_load-info.load_min))(&jni.vm,NULL);
    report("JNI_OnLoad: %08x; stored VM: %s\n",version,*(uint32_t *)(image+boot.vm_storage-info.load_min)==(uint32_t)&jni.vm?"MATCH":"FAILED");
    if(version!=0x10004) return;
    const char *names[]={"Java_com_ea_blast_MainActivity_NativeOnCreate","Java_com_ea_blast_AndroidRenderer_NativeOnSurfaceCreated", 
        "Java_com_ea_blast_AndroidRenderer_NativeOnSurfaceChanged","Java_com_ea_blast_AndroidRenderer_NativeOnDrawFrame"};
    const char *labels[]={"NativeOnCreate","NativeOnSurfaceCreated","NativeOnSurfaceChanged","NativeOnDrawFrame"};
    typedef void (*Lifecycle)(void *,void *,int,int) DS_IO_SOFT;
    typedef int (*PushFrame)(DSJniHandle *,int) DS_JNI_SOFT;
    typedef void *(*PopFrame)(DSJniHandle *,void *) DS_JNI_SOFT;
    for(uint32_t i=0;i<3;++i) {
        uint32_t address,size;
        if(ds_elf_find_export(file,&info,names[i],&address,&size)) return;
        phase=labels[i];report("Calling %s...\n",phase);
        if(((PushFrame)jni.env_functions[19])(&jni.env,16))return;
        ((Lifecycle)(image+address-info.load_min))(&jni.env,NULL,400,240);
        ((PopFrame)jni.env_functions[20])(&jni.env,NULL);
        report("%s returned\n",phase);
    }
    uint32_t draw,size;
    if(ds_elf_find_export(file,&info,names[3],&draw,&size))return;
    phase="NativeOnDrawFrame";
    for(uint32_t frame=1;frame<=120;++frame){
        report("Frame %lu begin\n",(unsigned long)frame);
        if(((PushFrame)jni.env_functions[19])(&jni.env,16))return;
        ((Lifecycle)(image+draw-info.load_min))(&jni.env,NULL,400,240);
        ((PopFrame)jni.env_functions[20])(&jni.env,NULL);
        report("Frame %lu returned\n",(unsigned long)frame);
        ds11_pump_events(&bridge);
        gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
    }
    uint32_t final_state[7];ds10_stats(&bridge,final_state);
    report("Frame budget refs=%lu failures=%lu\n",(unsigned long)final_state[4],(unsigned long)final_state[3]);
    report("FRAME BUDGET STOPPED; no renderer implemented\n");
}
int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP,NULL); RecursiveLock_Init(&journal_lock);
    journal=fopen(LOG,"w");report("DEAD SPACE ENGINE AUDIT - EMULATOR ONLY\nREADY - press A\n");
    while(aptMainLoop()) {
        hidScanInput();if(hidKeysDown()&KEY_START) break;
        if(hidKeysDown()&KEY_A) {run();break;}
        gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
    }
    if(journal) fclose(journal);
    gfxExit();return 0;
}
