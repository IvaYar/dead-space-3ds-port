#ifndef TARGET_INITIAL_RGBA
#define TARGET_INITIAL_RGBA 0x000000ffu
#endif
#ifndef SEQUENCE_CALLBACKS
#define SEQUENCE_CALLBACKS 8u
#endif
#ifndef FORCE_CRC_FAIL
#define FORCE_CRC_FAIL 0
#endif
#define DS_GAME_NORMAL_BYTES (20u*1024*1024)
#define DS_GAME_LINEAR_BYTES (100u*1024*1024)
#define DS_GAME_ARENA_BYTES (92u*1024*1024)
#define DS_GAME_REQUIRED_APP_BYTES (124u*1024*1024)
/* Separate native-capable checkpoint. Original donor executes; no recorded draws.
 * No dependency on engine_azahar.c, fixture headers, or its emulator guard. */
#include <3ds.h>
#include <citro3d.h>
#include <errno.h>
#include <malloc.h>
#include "native_game_memory_observer.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "ds_exec.h"
#include "ds8.h"
#include "ds9_memory.h"
#include "ds_runtime.h"
#include "ds_init.h"
#include "ds_bootstrap.h"
#include "ds10_jni.h"
#include "ds13_gles.h"
#include "ds17_jump.h"
#include "ds20_dirs.h"
#include "ds24_files.h"
#include "ds25_assets.h"
#include "ds27_pages.h"
#include "ds28_font.h"
#include "ds29_allocator.h"
#include "ds30_fog.h"
#include "ds31_combine.h"
#include "ds32_lighting.h"
#include "ds33_surface.h"
#include "ds34_gpu.h"
#include "donor_config.h"
#include "font_subset_config.h"
#include "native_thread_probe.h"

#define ROOT "sdmc:/3ds/ds-native-game-v0.1.2/"
#define MAX_CALLBACKS 600u
#define TARGET_RGB565_CRC 0xea733050u /* Preserved original GPU frame180, also stable181..189. */
#define BYTES 288000u
u32 __ctru_heap_size=DS_GAME_NORMAL_BYTES;
u32 __ctru_linear_heap_size=DS_GAME_LINEAR_BYTES;
u32 __stacksize__=256*1024;
static DSExec exec;
static DSInfo info;
static DSInitPlan plan;
static DS10Context bridge;
static DS13Context graphics;
static DS12Sensor sensor;
static DS12Hid sensor_hid;
static int sensor_attached;
static DSIO io;
static DSBinding bindings[768];
static u8 *donor,*image;
static void *arena;
static u32 *trampoline,trap_count,canary=0x9b1d73a5,current_frame;
static const char *trap_names[768],*phase="ready";
static char jni_names[DS_JNI_ENV_SLOTS][24],folder[128];
static FILE *journal;
static RecursiveLock log_lock;
static u64 started;
static int gpu_started,threads_started,frame_saved,setup_ok,exit_ok;
static int lifecycle_ready,cleanup_complete,frame_failed;
static const char *failure_reason="none",*cleanup_state="not_started";
static u32 last_crc565,matched_callback,sequence_completed,callbacks_completed;
static gxCmdQueue_s *queue;
static volatile u32 submits,failed_submits,events[3];
static u32 rx_pages,rx_ranges;
static DS7Stats thread_snapshot;
static u32 main_thread_id;
/* Bounded, CPU-only recording. No file I/O or allocation in SDK wrappers.
 * Buffers stay alive until process teardown; never alter GPU command words. */
static u8 command_capture[128*1024];
static u32 command_bytes,command_overflow,draw_input_digest,draw_input_count;
static const u8 *vertex_source;
static u32 vertex_stride;
extern u32 __ctru_linear_heap,__ctru_linear_heap_size;
static struct {u32 address,size;} protected[8];
extern void ds_audit_trap(void),ds_invalidate_entire_instruction_cache(void);
extern void ds34_native_finish(void);

static void report(const char *fmt,...){
    RecursiveLock_Lock(&log_lock);
    va_list ap;va_start(ap,fmt);if(journal){vfprintf(journal,fmt,ap);fflush(journal);}va_end(ap);
    RecursiveLock_Unlock(&log_lock);
}

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
        (unsigned long)linearSpaceFree(),arena?(unsigned long)DS_GAME_ARENA_BYTES:0ul,
        (unsigned long)a.break_bytes,(unsigned long)a.break_peak,(unsigned long)a.mapped_pages,
        (unsigned long)a.map_peak,(unsigned long)a.refusals,(unsigned long)r.live_bytes,
        (unsigned long)r.peak_bytes,(unsigned long)r.failures);

    report("PEAKJSON {\"normal_live\":%lu,\"normal_footprint\":%lu,\"normal_request\":%lu,\"linear_used\":%lu,\"linear_other\":%lu,\"linear_request\":%lu,\"vram_used\":%lu,\"vram_request\":%lu,\"arena_actual_size\":%lu}\n",
        (unsigned long)observed_normal_live,(unsigned long)observed_normal_footprint,
        (unsigned long)observed_normal_request,(unsigned long)observed_linear_used,
        (unsigned long)observed_linear_other,(unsigned long)observed_linear_request,
        (unsigned long)observed_vram_used,(unsigned long)observed_vram_request,
        (unsigned long)observed_arena_size);
}

static void stage(const char *name){if(!strcmp(phase,name))return;phase=name;report("STAGE %s\n",name);memory_sample(name);}
static void path(char out[192],const char *name){snprintf(out,192,"%s%s",folder,name);}
static void screen(const char *text){
    printf("\x1b[2J\x1b[HDS Game Stable 0.1.2\n%s\nRun: %s\n",text,folder+strlen(ROOT));
    u16 w,h;void *p=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,&w,&h);GSPGPU_FlushDataCache(p,(u32)w*h*3);
}
static int elapsed(u64 tick,u32 ms){return svcGetSystemTick()-tick>(u64)SYSCLOCK_ARM11*ms/1000;}
static int drain(u32 ms){
    u64 tick=svcGetSystemTick();
    while(queue && !gxCmdQueueWait(queue,0)){if(elapsed(tick,ms))return -1;svcSleepThread(1000000);}
    return __atomic_load_n(&failed_submits,__ATOMIC_ACQUIRE)?-1:0;
}
extern void __real_gxCmdQueueRun(gxCmdQueue_s *);
void __wrap_gxCmdQueueRun(gxCmdQueue_s *q){
    queue=q;
    if(current_frame && q && q->entries && q->numEntries<=q->maxEntries && q->numEntries<=32){
        for(u32 i=0;i<q->numEntries;++i){
            const gxCmdEntry_s *e=&q->entries[i];u32 n=0;
            if(e->type==1){
                u32 address=e->args[0],bytes=e->args[1];
                if(address>=__ctru_linear_heap && !(address&7) && !(bytes&3) && bytes &&
                   address-__ctru_linear_heap<=__ctru_linear_heap_size &&
                   bytes<=__ctru_linear_heap_size-(address-__ctru_linear_heap))n=bytes;
                else command_overflow=1;
            }
            if(sizeof(command_capture)-command_bytes<36 || n>sizeof(command_capture)-command_bytes-36){command_overflow=1;continue;}
            memcpy(command_capture+command_bytes,e->data,32);command_bytes+=32;
            memcpy(command_capture+command_bytes,&n,4);command_bytes+=4;
            if(n){memcpy(command_capture+command_bytes,(void *)e->args[0],n);command_bytes+=n;}
        }
    }
    __real_gxCmdQueueRun(q);
}
extern int __real_BufInfo_Add(C3D_BufInfo *,const void *,ptrdiff_t,int,u64);
int __wrap_BufInfo_Add(C3D_BufInfo *b,const void *p,ptrdiff_t stride,int count,u64 permutation){
    int result=__real_BufInfo_Add(b,p,stride,count,permutation);
    if(result>=0 && count==4 && stride==(ptrdiff_t)sizeof(DS34Vertex)){vertex_source=p;vertex_stride=(u32)stride;}
    return result;
}
extern void __real_C3D_DrawArrays(GPU_Primitive_t,int,int);
void __wrap_C3D_DrawArrays(GPU_Primitive_t primitive,int first,int count){
    if(vertex_source && vertex_stride==sizeof(DS34Vertex) && first>=0 && count>=0 && first<=8190 && count<=8190-first){
        u32 meta[3]={(u32)primitive,(u32)first,(u32)count};
        for(u32 i=0;i<sizeof(meta);++i)draw_input_digest=(draw_input_digest^((u8 *)meta)[i])*16777619u;
        const u8 *p=vertex_source+(u32)first*vertex_stride;
        for(u32 i=0;i<(u32)count*vertex_stride;++i)draw_input_digest=(draw_input_digest^p[i])*16777619u;
        ++draw_input_count;
    }else command_overflow=1;
    __real_C3D_DrawArrays(primitive,first,count);
}
extern Result __real_gspSubmitGxCommand(const u32 *);
Result __wrap_gspSubmitGxCommand(const u32 *w){
    Result r=__real_gspSubmitGxCommand(w);__atomic_fetch_add(&submits,1,__ATOMIC_RELAXED);
    if(R_FAILED(r))__atomic_fetch_add(&failed_submits,1,__ATOMIC_RELEASE);
    return r;
}
static void event0(void *p){(void)p;__atomic_fetch_add(&events[0],1,__ATOMIC_RELEASE);}
static void event1(void *p){(void)p;__atomic_fetch_add(&events[1],1,__ATOMIC_RELEASE);}
static void event2(void *p){(void)p;__atomic_fetch_add(&events[2],1,__ATOMIC_RELEASE);}
void ds34_diagnostic_mark(const char *p){(void)p;}
int ds34_diagnostic_begin(uint32_t flags){
    (void)flags;
    if(drain(2000))return 0;
    u32 a=C3D_FrameCounter(0),b=C3D_FrameCounter(1);u64 tick=svcGetSystemTick();
    while(a==C3D_FrameCounter(0) || b==C3D_FrameCounter(1)){
        if(elapsed(tick,1000))return 0;
        svcSleepThread(1000000);
    }
    return C3D_FrameBegin(C3D_FRAME_NONBLOCK);
}
void ds34_diagnostic_end(void){C3D_FrameEnd(0);}
int ds34_diagnostic_sync(void){return drain(2000);}
static void outcome(const char *status,const char *reason){
    char out[192];path(out,"result.json");FILE *f=fopen(out,"w");if(!f)return;
    /* Failure can be reported from an imported call while its caller owns a
     * runtime gate. Use the last main-thread snapshot rather than re-locking. */
    DS7Stats t=thread_snapshot;
    u32 g[4]={0},cpu[4]={0};if(graphics.draw){ds34_stats(g);ds22_stats(&graphics,cpu);}
    fprintf(f,"{\"status\":\"%s\",\"reason\":\"%s\",\"environment\":\"%s\",\"frame\":%lu,\"game_called\":%s,\"frame_saved\":%s,\"GL_error\":%lu,\"gpu_draws\":%lu,\"gpu_triangles\":%lu,\"gpu_uploads\":%lu,\"cpu_fragments\":%lu,\"cpu_samples\":%lu,\"submits\":%lu,\"failed_submits\":%lu,\"events\":[%lu,%lu,%lu],\"active_threads\":%lu,\"finished_threads\":%lu,\"rx_pages\":%lu,\"rx_ranges\":%lu,\"native_RX_verified\":%s,\"safe_exit\":%s}\n",
        status,reason,exec.emulator?"emulator":"native",(unsigned long)current_frame,current_frame?"true":"false",frame_saved?"true":"false",(unsigned long)graphics.error,
        (unsigned long)g[0],(unsigned long)g[1],(unsigned long)g[2],(unsigned long)cpu[2],(unsigned long)cpu[3],(unsigned long)submits,(unsigned long)failed_submits,
        (unsigned long)events[0],(unsigned long)events[1],(unsigned long)events[2],(unsigned long)t.active_threads,(unsigned long)t.finished_threads,
        (unsigned long)rx_pages,(unsigned long)rx_ranges,!exec.emulator && rx_ranges?"true":"false",exit_ok?"true":"false");fclose(f);
    path(out,"validation.json");f=fopen(out,"w");if(!f)return;
    fprintf(f,"{\"frame_status\":\"%s\",\"failure_reason\":\"%s\",\"cleanup_status\":\"%s\",\"cleanup_complete\":%s,\"matched_callback\":%lu,\"callbacks_completed\":%lu,\"sequence_completed\":%lu,\"last_crc565\":\"%08lx\",\"expected_crc565\":\"ea733050\",\"safe_exit\":%s}\n",
        frame_failed?"FAIL":frame_saved?"PASS":"UNVERIFIED",failure_reason,cleanup_state,cleanup_complete?"true":"false",
        (unsigned long)matched_callback,(unsigned long)callbacks_completed,(unsigned long)sequence_completed,(unsigned long)last_crc565,exit_ok?"true":"false");fclose(f);
}
static void fatal(const char *text) __attribute__((noreturn));
static void fatal(const char *text){
    if(!frame_saved)frame_failed=1;
    if(!strcmp(failure_reason,"none"))failure_reason=text;
    cleanup_state="retained";
    u32 caller=0;svcGetThreadId(&caller,CUR_THREAD_HANDLE);
    /* An imported failure can still own the DS7 gate, even on main. Never
     * re-enter it here. Refresh only after a callback/shutdown has returned. */
    report("FAIL phase=%s frame=%lu: %s\n",phase,(unsigned long)current_frame,text);outcome("blocked",text);
    /* Retain donor/GPU allocations and workers; no cross-thread longjmp/free. */
    if(caller==main_thread_id){
        screen("STOPPED / FAIL: cleanup incomplete\nResources retained; see log.");
        for(;;){
            /* Service APT/HID on main even when destruction is unsafe. A close
             * request does not authorize freeing resources still in use. */
            aptMainLoop();hidScanInput();
            if(hidKeysDown()&KEY_START)report("START: cleanup incomplete; live resources retained\n");
            svcSleepThread(16666667);
        }
    }
    for(;;)svcSleepThread(1000000000LL); /* Imported-call fault: caller stack stays alive. */
}
void ds_audit_stop(u32 index,u32 caller,u32 argument){
    (void)argument;report("UNSUPPORTED: %s caller=%08lx phase=%s\n",index<trap_count?trap_names[index]:"bad trap",(unsigned long)(caller-(u32)image),phase);
    fatal(index<trap_count?trap_names[index]:"unsupported call");
}
static void log_android(const char *s){report("ANDROID %s\n",s);}
static void java_request(const char *op,const char *cls,const char *name,const char *signature,int missing){
    if(missing || !strcmp(op,"FindClass"))report("JNI %s %s.%s %s missing=%d\n",op,cls,name,signature,missing);
    if(missing==1)fatal("unsupported JNI request");
}
static void unsupported(const char *op,u32 value){report("GLES %s %08lx\n",op,(unsigned long)value);fatal("unsupported GLES state");}
static void ds_failure(const char *op,u32 size,int error){report("ARENA %s size=%lu errno=%d\n",op,(unsigned long)size,error);}
static void *DS_IO_SOFT compat_sbrk(int32_t size){return ds29_sbrk(size,(u32)__builtin_return_address(0));}
static int32_t DS_IO_SOFT monotonic_clock(void){return (int32_t)((svcGetSystemTick()-started)*1000000/SYSCLOCK_ARM11);}
static u32 word(const u8 *p){return p[0]|(u32)p[1]<<8|(u32)p[2]<<16|(u32)p[3]<<24;}
static u32 trap_for(const char *name){
    if(trap_count>=768)fatal("trap capacity");
    u32 i=trap_count++;trap_names[i]=name;u32 *c=trampoline+i*4;
    c[0]=0xe59fc000;c[1]=0xe59ff000;c[2]=i;c[3]=(u32)ds_audit_trap;return (u32)c;
}
static int rx_range(u32 address,u32 bytes){
    if(rx_ranges>=8 || (address&4095) || (bytes&4095) || !bytes)return -1;
    Result r=svcFlushProcessDataCache(exec.process,address,bytes);
    report("RX flush address=%08lx bytes=%lu result=%08lx\n",(unsigned long)address,(unsigned long)bytes,(unsigned long)r);
    if(R_FAILED(r))return -1;
    if(!exec.emulator){
        r=svcControlProcessMemory(exec.process,address,0,bytes,MEMOP_PROT,MEMPERM_READEXECUTE);if(R_FAILED(r)){report("RX protect %08lx bytes=%lu result=%08lx\n",(unsigned long)address,(unsigned long)bytes,(unsigned long)r);return -1;}
        MemInfo mi;PageInfo pi;
        r=svcQueryProcessMemory(&mi,&pi,exec.process,address);
        report("RX query result=%08lx base=%08lx size=%lu perm=%lu\n",(unsigned long)r,R_SUCCEEDED(r)?(unsigned long)mi.base_addr:0,R_SUCCEEDED(r)?(unsigned long)mi.size:0,R_SUCCEEDED(r)?(unsigned long)mi.perm:0);
        if(R_FAILED(r) || mi.perm!=MEMPERM_READEXECUTE || mi.base_addr>address || address-mi.base_addr>mi.size || bytes>mi.size-(address-mi.base_addr))return -1;
    }
    protected[rx_ranges].address=address;protected[rx_ranges].size=bytes;++rx_ranges;rx_pages+=bytes/4096;
    report("RX range %08lx bytes=%lu native_verified=%d\n",(unsigned long)address,(unsigned long)bytes,!exec.emulator);return 0;
}
static u32 exported(const char *name){u32 address,size;if(ds_elf_find_export(donor,&info,name,&address,&size))fatal("missing donor export");return (u32)image+address-info.load_min;}
typedef void (*Lifecycle)(void *,void *,int,int) DS_IO_SOFT;
typedef int (*PushFrame)(DSJniHandle *,int) DS_JNI_SOFT;
typedef void *(*PopFrame)(DSJniHandle *,void *) DS_JNI_SOFT;
static void lifecycle(const char *suffix,int x,int y){
    char name[128];snprintf(name,sizeof(name),"Java_com_ea_blast_%s",suffix);
    report("CALL %s\n",suffix);
    if(((PushFrame)bridge.base.env_functions[19])(&bridge.base.env,16))fatal("JNI PushLocalFrame");
    ((Lifecycle)exported(name))(&bridge.base.env,NULL,x,y);
    ((PopFrame)bridge.base.env_functions[20])(&bridge.base.env,NULL);
    report("RETURN %s\n",suffix);
}
static int receipt(const char *file,const char *expected){
    char value[160];FILE *f=fopen(file,"rb");if(!f)return -1;size_t n=fread(value,1,sizeof(value),f);fclose(f);
    return n==strlen(expected) && !memcmp(value,expected,n)?0:-1;
}

C3D_RenderTarget *__real_C3D_RenderTargetCreate(int,int,GPU_COLORBUF,C3D_DEPTHTYPE);
C3D_RenderTarget *__wrap_C3D_RenderTargetCreate(int width,int height,GPU_COLORBUF color,C3D_DEPTHTYPE depth){
    C3D_RenderTarget *target=__real_C3D_RenderTargetCreate(width,height,color,depth);
    if(!target)return NULL;
    if(color!=GPU_RB_RGBA8 || width!=240 || height!=400)fatal("unexpected target format for initialization");
    u32 bytes=C3D_CalcColorBufSize(width,height,color);
    report("TARGET INIT color=%08lx bytes=%lu before original draw\n",(unsigned long)TARGET_INITIAL_RGBA,(unsigned long)bytes);
    /* GPU MemoryFill, not a CPU write to read-only VRAM; complete before use.
     * Initialize COLOR ONLY once. No game pixels or shader state supplied. */
    C3D_SyncMemoryFill(target->frameBuf.colorBuf,TARGET_INITIAL_RGBA,
        (u32 *)((u8 *)target->frameBuf.colorBuf+bytes),0x0201,NULL,0,NULL,0);
    return target;
}

static int graphics_setup(void){
    u16 w,h;void *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);
    if(gfxGetScreenFormat(GFX_TOP)!=GSP_BGR8_OES || w!=240 || h!=400)return -1;
    if(ds13_init(&graphics,pixels,400,240,BYTES,DS13_BGR8_CTR) || ds13_current(&graphics))return -1;
    if(ds22_client_range(&graphics,image,info.image_size) || ds22_client_range(&graphics,arena,DS_GAME_ARENA_BYTES))return -1;
    void *sp;__asm__ volatile("mov %0, sp":"=r"(sp));MemInfo mi;PageInfo pi;
    if(R_FAILED(svcQueryMemory(&mi,&pi,(u32)sp)) || !(mi.perm&1) || !mi.size || mi.size>124*1024*1024 || ds22_client_range(&graphics,(void *)mi.base_addr,mi.size))return -1;
    if(ds30_attach(&graphics) || ds31_attach(&graphics) || ds32_attach(&graphics) || ds33_attach(&graphics,16,8))return -1;
    if(ds15_limits(&graphics.texture,128,96*1024*1024) || ds15_backing(&graphics.texture,ds27_sd_backing(),6*1024*1024))return -1;
    ds13_observer(&graphics,unsupported,NULL);
    if(ds34_attach(&graphics))return -1;
    gpu_started=1;
    gspSetEventCallback(GSPGPU_EVENT_PSC0,event0,NULL,false);gspSetEventCallback(GSPGPU_EVENT_P3D,event1,NULL,false);gspSetEventCallback(GSPGPU_EVENT_PPF,event2,NULL,false);
    return 0;
}
static void add(DSBinding b,u32 *count){
    for(u32 i=0;i<*count;++i)if(!strcmp(bindings[i].name,b.name)){bindings[i]=b;return;}
    if(*count==768)fatal("binding capacity");
    bindings[(*count)++]=b;
}

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

static int initialize(void){
    stage("preflight");
    if(ds_exec_open(&exec)<0 || osGetMemRegionSize(MEMREGION_APPLICATION)<DS_GAME_REQUIRED_APP_BYTES)return -1;
    report("Environment=%s appbytes=%lu Luma=%08lx\n",exec.emulator?"emulator":"native",(unsigned long)osGetMemRegionSize(MEMREGION_APPLICATION),(unsigned long)exec.luma_version);
    if(receipt("sdmc:/3ds/deadspace/assets-verified.txt","DS_ASSETS_V1 dd42272365d0abd8ad9c89450bb7f869ee4ac0ad548525758e6a1e7df4d3c1eb 1728 414822611\n") || receipt("sdmc:/3ds/deadspace/apk-assets-verified.txt","DS_APK_ASSETS_V1 0d3c870ae38687e1ac7e8dbf0ca8568862437491529e8ef45b818f4c38958845 20\n"))return -1;
    FILE *f=fopen("sdmc:/3ds/deadspace/libEAMGameDeadSpace_orig.so","rb");if(!f)return -1;
    donor=malloc(DS_DONOR_SIZE);int ok=donor && fread(donor,1,DS_DONOR_SIZE,f)==DS_DONOR_SIZE && fgetc(f)==EOF;fclose(f);
    if(!ok || ds_crc32(donor,DS_DONOR_SIZE)!=DS_DONOR_CRC32 || ds_elf_inspect(donor,DS_DONOR_SIZE,&info))return -1;
    image=memalign(4096,(info.image_size+4095)&~4095u);arena=linearMemAlign(DS_GAME_ARENA_BYTES,4096);trampoline=memalign(4096,12288);
    if(!image || !arena || !trampoline)return -1;
    if(owned_region("donor_file",donor,DS_DONOR_SIZE,1,0) || owned_region("image",image,info.image_size,4096,0) || owned_region("arena",arena,DS_GAME_ARENA_BYTES,4096,1) || owned_region("trampoline",trampoline,12288,4096,0))return -1;
    report("Memory image=%08lx size=%lu arena=%08lx/%lu trampoline=%08lx\n",(unsigned long)image,(unsigned long)info.image_size,(unsigned long)arena,(unsigned long)DS_GAME_ARENA_BYTES,(unsigned long)trampoline);
    if(ds_elf_prepare(donor,DS_DONOR_SIZE,image,info.image_size,(u32)image,&info))return -1;
    ds_io_init(&io,ds_io_sd_ops());ds_runtime_init(64*1024*1024);ds6_init(log_android);
    if(ds7_init() || ds8_init())return -1;
    threads_started=1;
    if(ds9_memory_init_shared(arena,DS_GAME_ARENA_BYTES) || ds29_allocator_init(image,info.image_size))return -1;
    ds9_memory_observer(ds_failure);
    u32 count=ds6_bindings(bindings,768);count+=ds7_bindings(bindings+count,768-count);count+=ds8_bindings(bindings+count,768-count);
    count+=ds9_memory_bindings(bindings+count,768-count);count+=ds17_bindings(bindings+count,768-count);
    add((DSBinding){"sbrk",(u32)compat_sbrk},&count);add((DSBinding){"clock",(u32)monotonic_clock},&count);
    stage("graphics setup");if(graphics_setup())return -1;
    count+=ds13_bindings(bindings+count,768-count);count+=ds32_bindings(bindings+count,768-count);
    DSBinding overrides[DS26_BINDINGS];if(ds26_bindings(overrides,DS26_BINDINGS)!=DS26_BINDINGS)return -1;
    for(unsigned i=0;i<DS26_BINDINGS;++i)add(overrides[i],&count);
    stage("font verification");f=fopen(DS28_FONT_PATH,"rb");u8 *font=malloc(DS28_FONT_SIZE);
    ok=f && font && fread(font,1,DS28_FONT_SIZE,f)==DS28_FONT_SIZE && fgetc(f)==EOF && ds_crc32(font,DS28_FONT_SIZE)==DS28_FONT_CRC;
    if(f)fclose(f);
    free(font);if(!ok || ds_io_read_override(ds28_font_path))return -1;
    stage("private file namespace");
    mkdir("sdmc:/3ds/deadspace/test-output",0700);mkdir("sdmc:/3ds/deadspace/test-output/native-game-stable-v012",0700);
    if(ds6_appdata_namespace("native-game-stable-v012") || ds24_init(ds24_native_ops()) || ds20_init(ds20_native_ops()))return -1;
    DSBinding files[5];if(ds24_bindings(files,5)!=5)return -1;for(unsigned i=0;i<5;++i)add(files[i],&count);
    count+=ds20_bindings(bindings+count,768-count);add((DSBinding){"__stack_chk_guard",(u32)&canary},&count);
    stage("JNI/bootstrap");DSBootstrap boot;if(ds_bootstrap_verify(donor,DS_DONOR_SIZE,image,info.image_size,(u32)image,&info,&boot))return -1;
    if(ds10_init(&bridge,java_request,(DS10Startup)exported("Java_com_ea_EAIO_EAIO_Startup")))return -1;
    ds19_assets_backend_full(&bridge,ds19_native_list,ds25_native_open,ds19_apk_path,(void *)DS25_ROOT);
    int fd=ds25_native_open((void *)DS25_ROOT,"EAMCore.ini",2);u8 core[4096];int n=fd<0?-1:ds_io_read(fd,core,sizeof(core));if(fd>=0)ds_io_close(fd);
    if(n!=3119 || ds_crc32(core,3119)!=0x33c9beb3)return -1;
    add((DSBinding){"fcntl",(u32)ds_io_fcntl},&count);ds10_query_compat(&bridge,1);
    ds11_orientation_backend(&bridge,(DS11Orientation)exported("Java_com_ea_blast_DeviceOrientationHandlerAndroidDelegate_NativeOnDeviceOrientationChange"),1);
    /* The original bootstrap enables orientation/acceleration even for this UI
     * checkpoint. Reuse the existing native HID service; no control mapping. */
    DS12SensorOps sensor_ops;DS12Calibration calibration={{1,2,3},{0,0,0},{512,512,512}};
    if(ds12_hid_ops(&sensor_hid,&sensor_ops) || ds12_sensor_init(&sensor,&calibration,&sensor_ops) ||
       ds12_jni_sensor(&bridge,&sensor,(DS12Acceleration)exported("Java_com_ea_blast_AccelerometerAndroidDelegate_NativeOnAcceleration")))return -1;
    sensor_attached=1;
    for(u32 i=1;i<info.symcount;++i){
        if(!ds_elf_symbol_is_import(donor,&info,i))continue;
        const char *name=ds_elf_symbol_name(donor,&info,i);const u8 *symbol=donor+info.symoff+i*16;
        if((symbol[12]>>4)==2)continue;
        u32 j=0;for(;j<count;++j)if(!strcmp(bindings[j].name,name))break;if(j<count)continue;
        if((symbol[12]&15)==1){report("UNSUPPORTED DATA %s\n",name);return -1;}add((DSBinding){name,trap_for(name)},&count);
    }
    for(u32 i=4;i<DS_JNI_ENV_SLOTS;++i)if(!bridge.base.env_functions[i]){snprintf(jni_names[i],sizeof(jni_names[i]),"JNI slot %lu",(unsigned long)i);bridge.base.env_functions[i]=trap_for(jni_names[i]);}
    stage("relocations/imports");DSResolve resolved;if(ds_init_bind_plan(donor,DS_DONOR_SIZE,image,(u32)image,bindings,count,&plan,&resolved))return -1;
    report("Bindings=%lu unsupported fail-stop functions=%lu constructors=%lu\n",(unsigned long)count,(unsigned long)trap_count,(unsigned long)plan.count);
    for(u32 i=0;i<info.phnum;++i){
        const u8 *ph=donor+info.phoff+i*32;if(word(ph)!=1 || !(word(ph+24)&1))continue;if(word(ph+24)&2)return -1;
        u32 first=word(ph+8)&~4095u,last=(word(ph+8)+word(ph+20)+4095)&~4095u;
        if(last<first || rx_range((u32)image+first-info.load_min,last-first))return -1;
    }
    if(rx_range((u32)trampoline,12288))return -1;
    report("ICACHE entire invalidate before constructors; application affinity core0\n");
    ds_invalidate_entire_instruction_cache();
    stage("constructors");started=svcGetSystemTick();if(ds_init_run(&plan))return -1;
    report("Constructors completed=%lu\n",(unsigned long)plan.executed);
    typedef int (*OnLoad)(void *,void *) DS_IO_SOFT;
    stage("JNI_OnLoad");if(((OnLoad)((u32)image+boot.on_load-info.load_min))(&bridge.base.vm,NULL)!=0x10004)return -1;
    stage("lifecycle");lifecycle("MainActivity_NativeOnCreate",400,240);lifecycle("AndroidRenderer_NativeOnSurfaceCreated",400,240);lifecycle("AndroidRenderer_NativeOnSurfaceChanged",400,240);
    return 0;
}
static int save_raw(const char *name){
    char out[192];path(out,name);FILE *f=fopen(out,"wb");if(!f)return -1;
    int ok=fwrite(graphics.pixels,1,BYTES,f)==BYTES;if(fclose(f))ok=0;return ok?0:-1;
}
static u32 quantize(u16 *out){
    for(u32 i=0;i<96000;++i){const u8 *p=graphics.pixels+i*3;out[i]=(p[2]>>3)<<11|(p[1]>>2)<<5|(p[0]>>3);}
    return ds_crc32((const u8 *)out,192000);
}
/* Independent byte-at-a-time RGB565 CRC: explicitly little endian; no u16
 * aliasing, row transforms, tolerance or substitution of the reference. */
static u32 crc565_bytes(void){
    u32 crc=~0u;
    for(u32 i=0;i<96000;++i){const u8 *p=graphics.pixels+i*3;
        u32 v=(p[2]>>3)<<11|(p[1]>>2)<<5|(p[0]>>3);
        for(u32 b=0;b<2;++b){crc^=(v>>(b*8))&255;
            for(u32 k=0;k<8;++k)crc=crc&1?(crc>>1)^0xedb88320u:crc>>1;}
    }
    return ~crc;
}
static int readback(void){
    u16 w,h;void *front=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);
    if(drain(2000) || w!=240 || h!=400 || gfxGetScreenFormat(GFX_TOP)!=GSP_BGR8_OES ||
       graphics.layout!=DS13_BGR8_CTR || graphics.width!=400 || graphics.height!=240 ||
       graphics.capacity!=BYTES || !graphics.pixels)return -1;
    /* The transferred allocation can differ from the next LCD back buffer.
     * Record both; do not silently redirect the CPU reader to a different frame. */
    Result r=GSPGPU_InvalidateDataCache(graphics.pixels,BYTES);
    if(R_FAILED(r))return -1;
    (void)front;return 0;
}
static int diagnostic_capture(u16 *quantized,const char *name){
    if(readback())return -1;
    u32 a=ds_crc32(graphics.pixels,BYTES),qa=quantize(quantized);
    /* No GPU submission between these reads. A changed hash is a readback
     * failure, not an image match. No CPU flush/write of TOP is allowed. */
    if(R_FAILED(GSPGPU_InvalidateDataCache(graphics.pixels,BYTES)))return -1;
    u32 b=ds_crc32(graphics.pixels,BYTES),qb=crc565_bytes();
    u32 stats[4];ds34_stats(stats);DS34Audit audit;
    if(ds34_sequence_audit(&audit))return -1;
    u16 w,h;void *next=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);
    report("CAPTUREJSON {\"frame\":%lu,\"file\":\"%s\",\"pixels\":%lu,\"next_buffer\":%lu,\"physical\":%lu,\"bytes\":288000,\"column_stride\":720,\"format\":\"BGR8_CTR\",\"raw_crc_a\":\"%08lx\",\"raw_crc_b\":\"%08lx\",\"crc565_a\":\"%08lx\",\"crc565_b\":\"%08lx\",\"draws\":%lu,\"triangles\":%lu,\"uploads\":%lu,\"texture_digest\":%lu,\"clears\":%lu,\"clear_rgba\":[%.6f,%.6f,%.6f,%.6f],\"viewport\":[%ld,%ld,%ld,%ld],\"submits\":%lu,\"events\":[%lu,%lu,%lu]}\n",
        (unsigned long)current_frame,name,(unsigned long)graphics.pixels,(unsigned long)next,(unsigned long)osConvertVirtToPhys(graphics.pixels),
        (unsigned long)a,(unsigned long)b,(unsigned long)qa,(unsigned long)qb,(unsigned long)stats[0],(unsigned long)stats[1],(unsigned long)stats[2],(unsigned long)audit.texture_digest,
        (unsigned long)graphics.clears,graphics.clear_color[0],graphics.clear_color[1],graphics.clear_color[2],graphics.clear_color[3],
        (long)graphics.viewport[0],(long)graphics.viewport[1],(long)graphics.viewport[2],(long)graphics.viewport[3],
        (unsigned long)submits,(unsigned long)events[0],(unsigned long)events[1],(unsigned long)events[2]);
    if(a!=b || qa!=qb)return -1;
    char command_name[96],out[192];snprintf(command_name,sizeof(command_name),"%s.gx",name);path(out,command_name);
    FILE *commands=fopen(out,"wb");if(!commands)return -1;
    int saved=fwrite(command_capture,1,command_bytes,commands)==command_bytes;if(fclose(commands))saved=0;
    if(!saved)return -1;
    report("INPUTJSON {\"frame\":%lu,\"file\":\"%s\",\"command_bytes\":%lu,\"capture_truncated\":%s,\"draw_input_digest\":%lu,\"draw_input_count\":%lu}\n",
        (unsigned long)current_frame,command_name,(unsigned long)command_bytes,command_overflow?"true":"false",(unsigned long)draw_input_digest,(unsigned long)draw_input_count);
    return save_raw(name);
}
static int run(void){
    if(ds_crc32((const u8 *)"123456789",9)!=0xcbf43926u){failure_reason="CRC selfcheck";return -1;}
    if(initialize()){failure_reason="initialization failed";return -1;}
    lifecycle_ready=1;memory_sample("initialized");
    u32 draw=exported("Java_com_ea_blast_AndroidRenderer_NativeOnDrawFrame");
    u16 *quantized=malloc(192000);if(!quantized){failure_reason="quantized allocation";return -1;}
    int result=-1;u32 first_checkpoint=0;
    screen("Original callbacks running\nStrict full-frame CRC + bounded sequence\nSTART: cooperative exit");
    for(current_frame=1;current_frame<=MAX_CALLBACKS;++current_frame){
        command_bytes=command_overflow=draw_input_count=0;draw_input_digest=2166136261u;
        if(!aptMainLoop()){failure_reason="APT exit requested";goto done;}
        hidScanInput();if(hidKeysDown()&KEY_START){failure_reason="START before validation";goto done;}
        stage("NativeOnDrawFrame");
        if(((PushFrame)bridge.base.env_functions[19])(&bridge.base.env,16)){failure_reason="JNI PushLocalFrame";goto done;}
        ((Lifecycle)draw)(&bridge.base.env,NULL,400,240);((PopFrame)bridge.base.env_functions[20])(&bridge.base.env,NULL);
        if(graphics.error || ds34_present(&graphics)){failure_reason="draw/present failed";goto done;}
        callbacks_completed=current_frame;memory_sample("after_draw");
        if(current_frame==2){lifecycle("MainActivity_NativeOnResume",1,0);lifecycle("MainActivity_NativeOnWindowFocusChanged",1,0);}
        u32 stats[4];ds34_stats(stats);
        if(stats[2]>=4){
            if(readback()){failure_reason="readback failed";goto done;}
            last_crc565=quantize(quantized);
            if(!first_checkpoint)first_checkpoint=current_frame;
            report("FRAMECRC frame=%lu crc565=%08lx draws=%lu triangles=%lu uploads=%lu clears=%lu\n",(unsigned long)current_frame,(unsigned long)last_crc565,(unsigned long)stats[0],(unsigned long)stats[1],(unsigned long)stats[2],(unsigned long)graphics.clears);
            if(current_frame==first_checkpoint || current_frame==first_checkpoint+1 || current_frame==first_checkpoint+8 || current_frame==351 || current_frame==352 || current_frame==400 || current_frame==534 || current_frame==MAX_CALLBACKS){
                char name[64];snprintf(name,sizeof(name),"checkpoint-%04lu.raw",(unsigned long)current_frame);
                if(diagnostic_capture(quantized,name)){failure_reason="checkpoint readback/audit failed";goto done;}
            }
            if(!matched_callback && last_crc565==TARGET_RGB565_CRC && !FORCE_CRC_FAIL){
                matched_callback=current_frame;
                if(diagnostic_capture(quantized,"frame.raw")){failure_reason="reference capture failed";goto done;}
                frame_saved=1;report("ORIGINAL FRAME SAVED callback=%lu reference565=ea733050\n",(unsigned long)current_frame);
            }else if(matched_callback){
                /* Only eight extra original callbacks, within the already
                 * measured startup budget. Every frame keeps the exact gate. */
                if(last_crc565!=TARGET_RGB565_CRC){failure_reason="sequence CRC_FAIL";goto done;}
                char name[64];snprintf(name,sizeof(name),"sequence-%02lu.raw",(unsigned long)(sequence_completed+1));
                if(diagnostic_capture(quantized,name)){failure_reason="sequence readback/audit failed";goto done;}
                ++sequence_completed;
            }
            if(matched_callback && sequence_completed==SEQUENCE_CALLBACKS){result=0;break;}
        }
        ds11_pump_events(&bridge);
        if(ds12_jni_pump(&bridge,(svcGetSystemTick()-started)*1000000/SYSCLOCK_ARM11)<0){failure_reason="sensor event pump";goto done;}
        if(current_frame%30==0)report("FRAME %lu complete\n",(unsigned long)current_frame);
    }
    if(result){
        current_frame=callbacks_completed;
        failure_reason="CRC_FAIL: full frame gate not reached";
        report("FULL FRAME CRC GATE NOT REACHED after %lu original callbacks\n",(unsigned long)callbacks_completed);
        if(diagnostic_capture(quantized,"comparison-miss.raw"))report("Comparison-miss capture failed\n");
    }
done:
    free(quantized);frame_failed=result!=0;ds7_stats(&thread_snapshot);
    outcome(result?"failed":"frame_saved",result?failure_reason:"exact original sequence; awaiting shutdown");
    return result;
}
static u32 diagnostic_words(u32 address,u32 out[24]){
    MemInfo mi;PageInfo pi;
    if(!address || (address&3) || R_FAILED(svcQueryMemory(&mi,&pi,address)) || !(mi.perm&1) || mi.base_addr>address || address-mi.base_addr>=mi.size)return 0;
    u32 count=(mi.size-(address-mi.base_addr))/4;if(count>24)count=24;
    memcpy(out,(void *)address,count*4);return count;
}
static void native_thread_snapshot(const char *stage){
    NativeWorkerProbe view[17];ds7_probe_workers(view);
    char name[64],out[192];snprintf(name,sizeof(name),"threads-%s.json",stage);path(out,name);
    FILE *f=fopen(out,"w");if(!f)return;
    fprintf(f,"{\"stage\":\"%s\",\"image_base\":%lu,\"image_size\":%lu,\"workers\":[",stage,(unsigned long)image,(unsigned long)info.image_size);
    unsigned emitted=0;
    for(unsigned i=0;i<17;++i)if(view[i].token){NativeWorkerProbe *v=&view[i];u32 values[24];
        fprintf(f,"%s{\"token\":%lu,\"entry\":%lu,\"entry_offset\":%lu,\"argument\":%lu,\"wait_kind\":%lu,\"wait_object\":%lu,\"done\":%lu,\"detached\":%lu,\"joining\":%lu,\"stack_bytes\":%lu,\"kernel_wait\":%ld,\"argument_words\":[",emitted++?",":"",(unsigned long)v->token,(unsigned long)v->entry,(unsigned long)(v->entry-(u32)image),(unsigned long)v->argument,(unsigned long)v->wait_kind,(unsigned long)v->wait_object,(unsigned long)v->done,(unsigned long)v->detached,(unsigned long)v->joining,(unsigned long)v->stack_bytes,(long)v->kernel_wait);
        u32 n=v->done?0:diagnostic_words(v->argument,values);for(u32 j=0;j<n;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)values[j]);
        u32 object=n>3?values[3]:0,userdata=n>4?values[4]:0;
        fputs("],\"object_words\":[",f);n=v->done?0:diagnostic_words(object,values);u32 table=n?values[0]:0;for(u32 j=0;j<n;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)values[j]);
        fputs("],\"vtable_words\":[",f);n=v->done?0:diagnostic_words(table,values);for(u32 j=0;j<n;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)values[j]);
        fputs("],\"userdata_words\":[",f);n=v->done?0:diagnostic_words(userdata,values);table=n?values[0]:0;for(u32 j=0;j<n;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)values[j]);
        fputs("],\"userdata_vtable\":[",f);n=v->done?0:diagnostic_words(table,values);for(u32 j=0;j<n;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)values[j]);
        fputs("],\"wait_words\":[",f);n=v->done?0:diagnostic_words(v->wait_object,values);for(u32 j=0;j<n;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)values[j]);
        fprintf(f,"],\"wait_caller\":%lu,\"sleep_seconds\":%lu,\"sleep_nanoseconds\":%lu,\"sleep_EINTR\":%lu,\"wait_stack\":[",(unsigned long)v->wait_caller,(unsigned long)v->sleep_seconds,(unsigned long)v->sleep_nanoseconds,(unsigned long)v->sleep_interrupt_returns);for(u32 j=0;j<32;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)v->wait_stack[j]);fputs("]}",f);
    }
    fputs("]}\n",f);fclose(f);
}
static void native_destructor_snapshot(void){
    NativeDestructorProbe list[256];u32 n=ds8_probe_destructors(list);char out[192];path(out,"destructors.json");FILE *f=fopen(out,"w");if(!f)return;
    fprintf(f,"{\"image_base\":%lu,\"destructors\":[",(unsigned long)image);
    for(u32 i=0;i<n;++i)fprintf(f,"%s{\"callback\":%lu,\"object\":%lu,\"dso\":%lu,\"sequence\":%lu}",i?",":"",(unsigned long)list[i].callback,(unsigned long)list[i].object,(unsigned long)list[i].dso,(unsigned long)list[i].sequence);
    fputs("]}\n",f);fclose(f);
}
static int native_stop_job_workers(void){
    static const u32 expected[]={0xe5d03004,0xe3530000,0x012fff1e,0xe2800018,0xea00029a};
    if(memcmp(image+0x35532c,expected,sizeof(expected)))return -1;
    typedef void (*RequestStop)(void *) DS_IO_SOFT;
    RequestStop request=(RequestStop)(image+0x35532c);
    NativeWorkerProbe view[17];ds7_probe_workers(view);u32 ids[2],count=0;
    for(unsigned i=1;i<17;++i)if(view[i].token && view[i].entry==(u32)image+0x24c7f8){
        u32 words[24],table[24];
        if(diagnostic_words(view[i].argument,words)<4 || diagnostic_words(words[3],table)<1 || table[0]!=(u32)image+0x43bc68 || count==2)return -1;
        ids[count++]=view[i].token;request((void *)words[3]);
    }
    if(count!=2)return -1;
    native_thread_snapshot("after_jobs_signal");
    for(unsigned i=0;i<count;++i){int result=ds7_probe_wait_thread(ids[i],1000);report("JOB %lx completion=%d\n",(unsigned long)ids[i],result);if(result)return -1;}
    return 0;
}
static int native_stop_audio_workers(void){
    /* Split the stop/wake operations from original destructor 0x275634.
     * Its buffer frees occur before its wake and cannot be used with live workers. */
    static const u32 expected[]={0xe92d4070,0xe59f3148,0xe59f5148,0xe3a06000,0xe08f3003,0xe0835005,0xe5952030,0xe1a04000,0xe5c56035};
    if(memcmp(image+0x275634,expected,sizeof(expected)))return -1;
    NativeWorkerProbe view[17];ds7_probe_workers(view);u32 ids[2],count=0,object=0;
    for(unsigned i=1;i<17;++i)if(view[i].token && view[i].entry==(u32)image+0x24c914){
        u32 words[24];if(diagnostic_words(view[i].argument,words)<5)return -1;
        if(words[3]!=(u32)image+0x29bf3c && words[3]!=(u32)image+0x271a10)continue;
        if(count==2 || (object && object!=words[4]))return -1;
        object=words[4];ids[count++]=view[i].token;
    }
    if(count!=2 || *(u32 *)object!=(u32)image+0x438988)return -1;
    u32 global=0x27564c+*(u32 *)(image+0x275788)+*(u32 *)(image+0x27578c);
    if(global!=0x44d488)return -1;
    __atomic_store_n(image+global+0x35,0,__ATOMIC_RELEASE);
    typedef int (*Wake)(void *,int) DS_IO_SOFT;
    ((Wake)(image+0x24ba40))(*(void **)(object+0xd8),2);
    for(unsigned i=0;i<count;++i)if(ds7_checkpoint_interrupt(ids[i]))return -1;
    native_thread_snapshot("after_audio_signal");
    for(unsigned i=0;i<count;++i){int result=ds7_probe_wait_thread(ids[i],1000);report("AUDIO %lx completion=%d\n",(unsigned long)ids[i],result);if(result){native_thread_snapshot("audio_timeout");return -1;}}
    return 0;
}
static int native_stop_periodic_worker(void){
    /* Original 0x360dfc first clears this run flag, polls its acknowledgement,
     * then destroys mutexes. Keep that last part deferred until kernel exit. */
    static const u32 expected[]={0xe92d4070,0xe59f4058,0xe59f6058,0xe08f4004,0xe0843006,0xe5d32048,0xe3520000,0x1a00000a,0xe59f5044,0xe5832094};
    if(memcmp(image+0x360dfc,expected,sizeof(expected)))return -1;
    u32 state=0x360e10+*(u32 *)(image+0x360e60)+*(u32 *)(image+0x360e64);
    if(state!=0x46cb90 || image[state+0x48])return -1;
    NativeWorkerProbe view[17];ds7_probe_workers(view);u32 id=0;
    for(unsigned i=1;i<17;++i)if(view[i].token && view[i].entry==(u32)image+0x360d9c){if(id)return -1;id=view[i].token;}
    if(!id)return -1;
    __atomic_store_n((u32 *)(image+state+0x94),0,__ATOMIC_RELEASE);
    if(ds7_checkpoint_interrupt(id))return -1;
    int result=ds7_probe_wait_thread(id,1000);report("PERIODIC %lx completion=%d\n",(unsigned long)id,result);
    return result?-1:0;
}
static int shutdown_game(void){
    cleanup_state="running";
    stage("shutdown lifecycle");
    native_thread_snapshot("before_pause");
#ifdef FORCE_CLEANUP_INCOMPLETE
    /* Host-only fault: prove live handles prevent destruction and PASS. */
    report("INJECTED cleanup incomplete; no resource destruction\n");return -1;
#endif
    lifecycle("MainActivity_NativeOnPause",0,0);native_thread_snapshot("after_pause");
    lifecycle("MainActivity_NativeOnStop",0,0);native_thread_snapshot("after_stop");
    native_destructor_snapshot();
    NativeWorkerProbe initial[17];ds7_probe_workers(initial);
    for(unsigned i=1;i<17;++i)if(initial[i].token && initial[i].entry==(u32)image+0x24c914 && initial[i].argument){
        u32 words[24];u32 count=diagnostic_words(initial[i].argument,words);
        if(count>3 && words[3]==(u32)image+0x320624){
            int waited=ds7_probe_wait_thread(initial[i].token,30000);
            report("LOADER natural completion=%d\n",waited);native_thread_snapshot("after_loader_wait");
            if(waited)return -1;
        }
    }
    if(native_stop_job_workers())return -1;
    if(native_stop_audio_workers())return -1;
    if(native_stop_periodic_worker())return -1;
    native_thread_snapshot("after_quiesce");
    ds7_stats(&thread_snapshot);
    if(thread_snapshot.active_threads || thread_snapshot.finished_threads)return -1;
    u32 jni_freed=ds10_cleanup(&bridge);if(jni_freed==UINT32_MAX)return -1;
    u32 stdio_closed=ds6_cleanup(),appdata_closed=ds24_shutdown();
    int io_closed=ds_io_shutdown(&io);u32 directories=ds20_active();
    report("RESOURCES JNI=%lu stdio=%lu appdata=%lu IOactive=%lu opens/closes=%lu/%lu dirs=%lu\n",(unsigned long)jni_freed,(unsigned long)stdio_closed,(unsigned long)appdata_closed,(unsigned long)io.active,(unsigned long)io.opens,(unsigned long)io.closes,(unsigned long)directories);
    if(io_closed || io.active || io.opens!=io.closes || directories)return -1;
    u32 live=ds7_shutdown(100000000);report("SHUTDOWN live workers=%lu\n",(unsigned long)live);
    native_thread_snapshot("after_join");
    if(live)return -1;
    ds7_stats(&thread_snapshot);
    if(sensor_attached && ds12_sensor_close(&sensor))return -1;
    sensor_attached=0;
    if(gpu_started){ds34_native_finish();if(drain(2000))return -1;C3D_Fini();queue=NULL;gpu_started=0;}
    /* Code/arena remain allocated until kernel process teardown, after workers
     * and GPU stop. Never reuse protected donor pages as heap allocations. */
    memory_sample("after_shutdown");
    char out[192];path(out,"exit.txt");FILE *f=fopen(out,"w");if(!f)return -1;
    int wrote=fputs("Workers stopped; GPU drained; returning to HOME\n",f)>=0;
    if(fclose(f) || !wrote)return -1;
    cleanup_complete=exit_ok=1;cleanup_state="complete";
    outcome(frame_failed?"failed":"passed",frame_failed?failure_reason:"original frame sequence and worker/GPU shutdown complete");
    return 0;
}
static int make_folder(void){
    if((mkdir("sdmc:/3ds",0777) && errno!=EEXIST) || (mkdir(ROOT,0777) && errno!=EEXIST))return -1;
    for(u32 i=1;i<=9999;++i){snprintf(folder,sizeof(folder),ROOT"run-%04lu/",(unsigned long)i);if(!mkdir(folder,0777))return 0;if(errno!=EEXIST)return -1;}return -1;
}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);RecursiveLock_Init(&log_lock);
    svcGetThreadId(&main_thread_id,CUR_THREAD_HANDLE);
    if(make_folder())return 1;
    char out[192];path(out,"native-game.log");journal=fopen(out,"w");if(!journal)return 1;
    screen("READY: A begins original code\nSTART exits before initialization.");path(out,"ready.txt");FILE *f=fopen(out,"w");if(f){fputs("A begins original callback 180\n",f);fclose(f);}
    while(aptMainLoop()){
        hidScanInput();u32 keys=hidKeysDown();if(keys&KEY_START)break;
        if(keys&KEY_A){
            setup_ok=run()==0;
            if(!lifecycle_ready)fatal("initialization blocked; unsafe to infer donor lifecycle");
            if(!setup_ok){
                frame_failed=1;ds7_stats(&thread_snapshot);outcome("failed",failure_reason);
                report("FRAME FAIL: %s; beginning cooperative shutdown\n",failure_reason);
                screen("FRAME FAIL: see log\nCooperative shutdown running");
            }else{
                screen("FRAME + SEQUENCE SAVED\nSTART: donor shutdown + GPU drain");
                while(aptMainLoop()){hidScanInput();if(hidKeysDown()&KEY_START)break;svcSleepThread(16666667);}
            }
            if(shutdown_game()){
                ds7_stats(&thread_snapshot); /* Returned main-thread boundary; no imported gate held. */
                fatal("worker/GPU shutdown incomplete");
            }
            break;}
        svcSleepThread(16666667);
    }
    if(journal)fclose(journal);
    gfxExit();return 0;
}
