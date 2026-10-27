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
#include "ds13_gles.h"
#include "ds17_jump.h"
#include "ds20_dirs.h"
#include "donor_config.h"
#include "jni10_fixture.h"
#include "platform_fixture.h"
#include "jump_fixture.h"
#include "strings_fixture.h"
#include "assets_fixture.h"
#define LOG "sdmc:/3ds/deadspace/engine-azahar-log.txt"
/* Preserve enough normal heap for two donor arenas and its loaded image. */
u32 __ctru_linear_heap_size=4*1024*1024;
u32 __stacksize__=256*1024;
static FILE *journal;
static RecursiveLock journal_lock;
static const char *phase="setup",*trap_names[768];
static char jni_slot_names[DS_JNI_ENV_SLOTS][32];
static uint32_t trap_count,*trampoline,canary=0x9b1d73a5,image_base,image_length;
static DS10Context bridge;
static DS12Sensor sensor;
static DS12Hid sensor_hid;
static int sensor_attached;
static DS13Context graphics;
static int graphics_attached;
#define jni bridge.base
static DSIO io;
static DSInitPlan plan;
static uint64_t started;
static volatile uint32_t audit_frame;
static volatile uint32_t fs_events;
static int partial_draw_saved;
static uint8_t exception_stack[16384] __attribute__((aligned(8)));
void ds_audit_trap(void);
static void report(const char *format,...) {
    RecursiveLock_Lock(&journal_lock);
    va_list args;if(!graphics_attached){va_start(args,format);vprintf(format,args);va_end(args);}
    if(journal) { va_start(args,format); vfprintf(journal,format,args); va_end(args); fflush(journal); }
    RecursiveLock_Unlock(&journal_lock);
}
static void sensor_shutdown(void){
    if(!sensor_attached)return;
    int result=ds12_sensor_close(&sensor);
    report("Sensor shutdown: result=%d active=%lu events=%lu delay=%ld\n",result,(unsigned long)sensor_hid.enabled,(unsigned long)bridge.acceleration_events,(long)bridge.acceleration_delay);
    if(!result)sensor_attached=0;
}
static void audit_exception(ERRF_ExceptionInfo *info,CpuRegisters *regs){
    report("STOP CPU exception: type=%lu pc=%08lx offset=%08lx lr=%08lx far=%08lx fsr=%08lx fpexc=%08lx\n",(unsigned long)info->type,(unsigned long)regs->pc,(unsigned long)(regs->pc-image_base),(unsigned long)regs->lr,(unsigned long)info->far,(unsigned long)info->fsr,(unsigned long)info->fpexc);
    for(unsigned i=0;i<13;++i)report("r%u=%08lx ",i,(unsigned long)regs->r[i]);
    report("sp=%08lx cpsr=%08lx\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n",(unsigned long)regs->sp,(unsigned long)regs->cpsr);
    if(journal){fclose(journal);journal=NULL;}svcExitProcess();
}
static void graphics_stats(void){
    if(graphics_attached){uint32_t s[6];ds19_jni_stats(&bridge,s);report("JNI assets: lists=%lu names=%lu gets=%lu sets=%lu strings=%lu arrays=%lu\n",(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3],(unsigned long)s[4],(unsigned long)s[5]);}
    if(graphics_attached)report("JNI strings: new16=%lu newUTF=%lu get16=%lu getUTF=%lu regions=%lu errors=%lu\n",(unsigned long)bridge.string_stats[0],(unsigned long)bridge.string_stats[1],(unsigned long)bridge.string_stats[2],(unsigned long)bridge.string_stats[3],(unsigned long)bridge.string_stats[4],(unsigned long)bridge.string_stats[5]);
    if(graphics_attached)report("GLES error at stop: %08lx\n",(unsigned long)graphics.error);
    if(graphics_attached){uint32_t s[4];ds13_stats(&graphics,s);report("GLES counters: queries=%lu clears=%lu pixels=%lu flushes=%lu\n",(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3]);}
    if(graphics_attached){uint32_t s[4];ds15_stats(&graphics.texture,s);report("GLES texture stores: names=%lu bytes=%lu uploads=%lu patches=%lu\n",(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3]);}
    if(graphics_attached){const DS15Level *l=ds15_level(&graphics.texture,1,0);if(l)report("GLES first texture: %lux%lu format=%04lx bytes=%lu CRC32=%08lx\n",(unsigned long)l->width,(unsigned long)l->height,(unsigned long)l->format,(unsigned long)(l->width*l->height*4),(unsigned long)ds_crc32(l->rgba,l->width*l->height*4));}
}
static void jump_stats(void){DS17Stats s;ds17_stats(&s);report("Jump contexts: saves=%lu restores=%lu refusals=%lu\n",(unsigned long)s.saves,(unsigned long)s.restores,(unsigned long)s.refusals);}
static void thread_event(uint32_t event,uint32_t thread,uint32_t detail){report("Thread event: %lu id=%08lx detail=%08lx\n",(unsigned long)event,(unsigned long)thread,(unsigned long)detail);}
static int save_surface(DS13Context *c,const char *stem,uint32_t caller){
    char path[128];snprintf(path,sizeof(path),"sdmc:/3ds/deadspace/%s.raw",stem);FILE *f=fopen(path,"wb");if(!f)return -1;
    uint32_t bytes=c->width*c->height*(c->layout==DS13_RGB565_CTR?2:3);int ok=fwrite(c->pixels,1,bytes,f)==bytes;if(fclose(f))ok=0;if(!ok)return -1;
    snprintf(path,sizeof(path),"sdmc:/3ds/deadspace/%s.json",stem);f=fopen(path,"w");if(!f)return -1;
    uint32_t s[4];ds22_stats(c,s);
    fprintf(f,"{\"width\":%lu,\"height\":%lu,\"layout\":%lu,\"bytes\":%lu,\"crc32\":\"%08lx\",\"frame\":%lu,\"caller_offset\":\"%08lx\",\"draws\":%lu,\"triangles\":%lu,\"fragments\":%lu,\"samples\":%lu}\n",(unsigned long)c->width,(unsigned long)c->height,(unsigned long)c->layout,(unsigned long)bytes,(unsigned long)ds_crc32(c->pixels,bytes),(unsigned long)audit_frame,(unsigned long)(caller-image_base),(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3]);
    return fclose(f)?-1:0;
}
static void game_draw(DS13Context *c,uint32_t caller){
    uint32_t s[4];ds22_stats(c,s);report("GAME DRAW: caller-offset=%08lx calls=%lu triangles=%lu fragments=%lu samples=%lu\n",(unsigned long)(caller-image_base),(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3]);
    if(!partial_draw_saved && s[2] && s[3]){if(!save_surface(c,"first-game-draw",caller)){partial_draw_saved=1;report("PARTIAL GAME DRAW CAPTURED\n");}}
}
void ds_fs_trace(const char *operation,const char *path,int result){if(fs_events++<100)report("FS %s: %s result=%d\n",operation,path,result);}
static void audit_watchdog(void *unused){
    (void)unused;
    for(unsigned sample=0;sample<15;++sample){
        svcSleepThread(10000000000LL);DS7DebugThread views[17];ds7_debug_threads(views);
        report("WATCH phase=%s frame=%lu image=%08lx fs-events=%lu\n",phase,(unsigned long)audit_frame,(unsigned long)image_base,(unsigned long)fs_events);
        for(unsigned i=0;i<17;++i)if(views[i].token)report("WATCH thread=%08lx entry-offset=%08lx wait=%lu object=%08lx\n",(unsigned long)views[i].token,(unsigned long)(views[i].entry-image_base),(unsigned long)views[i].wait_kind,(unsigned long)views[i].wait_object);
    }
    report("DIAGNOSTIC WATCHDOG STOPPED\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n");
    if(journal){fclose(journal);journal=NULL;}svcExitProcess();
}
static void arena_refused(const char *operation,uint32_t bytes,int error){
    DS9MemoryStats s;ds9_memory_stats(&s);
    report("STOP arena refusal: %s bytes=%lu errno=%d\n",operation,(unsigned long)bytes,error);
    report("Donor arenas: break=%lu peak=%lu mapped-pages=%lu refusals=%lu\n",(unsigned long)s.break_bytes,(unsigned long)s.break_peak,(unsigned long)s.mapped_pages,(unsigned long)s.refusals);
    report("Diagnostic policy: stop at first arena refusal; donor recovery not attempted\n");
    graphics_stats();jump_stats();sensor_shutdown();
    report("Phase: %s\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n",phase);
    if(journal){fclose(journal);journal=NULL;}svcExitProcess();
}
static void bad_jump(uint32_t reason){report("STOP invalid jump: %lu\n",(unsigned long)reason);jump_stats();if(journal){fclose(journal);journal=NULL;}svcExitProcess();}
static void graphics_unsupported(const char *op,uint32_t value){
    report("STOP GLES state: %s enum=%08lx\n",op,(unsigned long)value);graphics_stats();sensor_shutdown();
    report("Phase: %s\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n",phase);
    if(journal){fclose(journal);journal=NULL;}svcExitProcess();
}
static int graphics_sync(void *pixels,uint32_t bytes){return R_FAILED(GSPGPU_FlushDataCache(pixels,bytes))?-1:0;}
static int graphics_setup(void){
    GSPGPU_FramebufferFormat format=gfxGetScreenFormat(GFX_TOP);
    if(format!=GSP_BGR8_OES && format!=GSP_RGB565_OES)return -1;
    uint32_t bytes=format==GSP_RGB565_OES?2:3,layout=bytes==2?DS13_RGB565_CTR:DS13_BGR8_CTR;
    u16 width,height;uint8_t *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&width,&height);
    if(ds13_init(&graphics,pixels,height,width,(uint32_t)width*height*bytes,layout) || ds13_current(&graphics))return -1;
    DSBinding gl[128];if(ds13_bindings(gl,128)!=DS13_BINDINGS)return -1;
    typedef void (*ColorX)(int32_t,int32_t,int32_t,int32_t) DS13_SOFT;
    typedef void (*One)(uint32_t) DS13_SOFT;
    typedef void (*Box)(int32_t,int32_t,int32_t,int32_t) DS13_SOFT;
    typedef void (*Query)(uint32_t,int32_t *) DS13_SOFT;
    /* Registry indexes are verified here; fixture is a real framebuffer clear. */
    if(strcmp(gl[9].name,"glColorMask") || strcmp(gl[13].name,"glClear"))return -1;
    ((ColorX)gl[8].address)(0,0,0,65536);((One)gl[13].address)(0x4000);
    ((Box)gl[3].address)(20,20,40,30);((One)gl[4].address)(0xc11);
    ((ColorX)gl[8].address)(0,65536,0,65536);((One)gl[13].address)(0x4000);
    int32_t viewport[4];((Query)gl[1].address)(0xba2,viewport);
    uint32_t green=(20u*width+20u)*bytes;
    int color_ok=bytes==2?(pixels[green]==0xe0 && pixels[green+1]==7):(pixels[green]==0 && pixels[green+1]==255 && pixels[green+2]==0);
    if(!color_ok || pixels[0] || pixels[1] ||
       viewport[0] || viewport[1] || viewport[2]!=height || viewport[3]!=width)return -1;
    report("GLES surface probe: OK %ux%u; black clear + green scissor; pixels=%lu format=%lu\n",height,width,(unsigned long)graphics.pixels_written,(unsigned long)format);
    typedef void (*Names)(int32_t,uint32_t *) DS13_SOFT;
    typedef void (*Delete)(int32_t,const uint32_t *) DS13_SOFT;
    typedef void (*Bind)(uint32_t,uint32_t) DS13_SOFT;
    typedef void (*Upload)(uint32_t,int32_t,const void *,uint32_t) DS13_SOFT;
    typedef void (*Sub)(uint32_t,int32_t,int32_t,const void *) DS13_SOFT;
    typedef void (*Pointer)(int32_t,uint32_t,int32_t,const void *) DS13_SOFT;
    if(strcmp(gl[26].name,"glGenBuffers") || strcmp(gl[30].name,"glBufferData") || strcmp(gl[21].name,"glVertexPointer"))return -1;
    uint32_t buffer=0;float data[6]={1,2,3,4,5,6},patch[3]={7,8,9},readback[3]={0};
    ((Names)gl[26].address)(1,&buffer);((Bind)gl[27].address)(0x8892,buffer);
    ((Upload)gl[30].address)(0x8892,sizeof(data),data,0x88e4);
    ((Pointer)gl[21].address)(3,0x1406,12,NULL);
    ((Sub)gl[31].address)(0x8892,12,sizeof(patch),patch);
    if(!buffer || ds14_read_array(&graphics.vertex,0,1,readback,sizeof(readback))!=12 || memcmp(readback,patch,12))return -1;
    ((Delete)gl[29].address)(1,&buffer);
    if(graphics.vertex.bytes || graphics.vertex.array_buffer)return -1;
    for(unsigned i=0;i<DS14_BUFFERS;++i)if(graphics.vertex.buffers[i].used)return -1;
    report("GLES buffer probe: OK upload=24 sub=12 readback=12 active=0\n");
    ds14_init(&graphics.vertex);
    typedef void (*TextureImage)(uint32_t,int32_t,int32_t,int32_t,int32_t,int32_t,uint32_t,uint32_t,const void *) DS13_SOFT;
    typedef void (*TextureSub)(uint32_t,int32_t,int32_t,int32_t,int32_t,int32_t,uint32_t,uint32_t,const void *) DS13_SOFT;
    typedef uint32_t (*Error)(void) DS13_SOFT;
    if(strcmp(gl[33].name,"glGenTextures") || strcmp(gl[47].name,"glTexImage2D") || strcmp(gl[48].name,"glTexSubImage2D"))return -1;
    uint32_t texture=0;uint8_t image[16]={255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255},tex_patch[4]={17,34,51,68},texel[4];
    ((Names)gl[33].address)(1,&texture);((Bind)gl[34].address)(0xde1,texture);
    ((TextureImage)gl[47].address)(0xde1,0,0x1908,2,2,0,0x1908,0x1401,image);
    ((TextureSub)gl[48].address)(0xde1,0,1,1,1,1,0x1908,0x1401,tex_patch);
    if(!texture || ((Error)gl[0].address)() || ds15_read_texel(&graphics.texture,texture,0,1,1,texel) || memcmp(texel,tex_patch,4))return -1;
    ((Delete)gl[36].address)(1,&texture);
    uint32_t texture_stats[4];ds15_stats(&graphics.texture,texture_stats);if(texture_stats[0] || texture_stats[1])return -1;
    report("GLES texture probe: OK upload=16 sub=4 readback=4 active=0\n");
    ds15_close(&graphics.texture);ds15_init(&graphics.texture);
    typedef void (*AlphaX)(uint32_t,int32_t) DS13_SOFT;
    typedef void (*FloatQuery)(uint32_t,float *) DS13_SOFT;
    if(strcmp(gl[49].name,"glCullFace") || strcmp(gl[56].name,"glAlphaFuncx") || strcmp(gl[64].name,"glGetFloatv"))return -1;
    ((One)gl[4].address)(0xb44);((One)gl[49].address)(0x404);
    if(ds16_culled(&graphics.pipeline,2)!=1 || ds16_culled(&graphics.pipeline,-2)!=0)return -1;
    ((One)gl[4].address)(0xbc0);((AlphaX)gl[56].address)(0x204,32768);
    if(ds16_alpha_pass(&graphics.pipeline,.25f) || !ds16_alpha_pass(&graphics.pipeline,.75f))return -1;
    float alpha_ref=0;((FloatQuery)gl[64].address)(0xbc2,&alpha_ref);if(alpha_ref!=.5f)return -1;
    float src[4]={1,0,0,.25f},dst[4]={0,0,1,1},blended[4],expected[4]={.25f,0,.75f,.8125f};
    ((Bind)gl[57].address)(0x302,0x303);ds16_blend(&graphics.pipeline,1,src,dst,blended);
    if(memcmp(blended,expected,sizeof(expected)) || ((Error)gl[0].address)())return -1;
    report("GLES pipeline probe: OK cull=2 alpha=2 blend=4 typed=1\n");ds16_init(&graphics.pipeline);
    ((One)gl[5].address)(0xc11);((Box)gl[3].address)(0,0,height,width);((ColorX)gl[8].address)(0,0,0,0);
    graphics.queries=graphics.clears=graphics.pixels_written=graphics.flushes=0;
    /* Clear diagnostic console/probe pixels from both borrowed buffers before
     * donor execution. No game rendering counters include this initialization. */
    for(unsigned i=0;i<2;++i){u16 w,h;void *target=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);memset(target,0,(uint32_t)w*h*bytes);GSPGPU_FlushDataCache(target,(uint32_t)w*h*bytes);gfxSwapBuffers();}
    u16 w,h;void *target=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);if(ds13_target(&graphics,target,(uint32_t)w*h*bytes))return -1;
    ds13_observer(&graphics,graphics_unsupported,graphics_sync);graphics_attached=1;return 0;
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
    graphics_stats();jump_stats();sensor_shutdown();report("ENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n");
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
        graphics_stats();jump_stats();sensor_shutdown();report("STOP Java adapter\nPhase: %s\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n",phase);
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
    DS10Context probe={0};ds10_init(&probe,NULL,ds10_test_startup);ds19_assets_backend(&probe,ds19_native_list,NULL);uint32_t out[4]={0};
    typedef int (*Probe)(DSJniHandle *,uint32_t *) DS_JNI_SOFT;
    int result=((Probe)(image+address-info.load_min))(&probe.base.env,out);
    if(platform==3)report("Asset probe: %d checks=%lu names=%lu CRC32-xor=%08lx\n",result,(unsigned long)out[1],(unsigned long)out[2],(unsigned long)out[3]);
    else if(platform==2)report("String probe: %d checks=%lu units=%lu bytes=%lu\n",result,(unsigned long)out[1],(unsigned long)out[2],(unsigned long)out[3]);
    else if(platform)report("Platform probe: %d checks=%lu properties=%lu\n",result,(unsigned long)out[1],(unsigned long)out[2]);
    else report("JNI I/O probe: %d checks=%lu bytes=%lu CRC32=%08lx\n",result,(unsigned long)out[1],(unsigned long)out[2],(unsigned long)out[3]);
    ds10_cleanup(&probe);free(image);
    DSRuntimeStats stats;ds_runtime_stats(&stats);
    report("%s cleanup: files=%lu heap=%lu\n",platform==3?"Asset":platform==2?"String":platform?"Platform":"JNI I/O",(unsigned long)io.active,(unsigned long)stats.live_blocks);
    if(stats.live_blocks || io.active)return -1;
    return result;
}
static int jump_probe(DSExec *exec,const uint8_t *blob,uint32_t blob_size,const char *mode){
    DSInfo info;int error=ds_elf_inspect(blob,blob_size,&info);if(error){report("Jump probe %s inspect: %d\n",mode,error);return -1;}
    uint8_t *image=memalign(4096,info.image_size);if(!image)return -1;
    error=ds_elf_prepare(blob,blob_size,image,info.image_size,(uint32_t)image,&info);if(error){report("Jump probe %s prepare: %d\n",mode,error);free(image);return -1;}
    DSBinding bindings[4];DSResolve result;ds17_bindings(bindings,4);
    error=ds_elf_resolve(blob,&info,image,bindings,4,&result);if(error){report("Jump probe %s resolve: %d\n",mode,error);free(image);return -1;}
    for(uint32_t i=0;i<info.phnum;++i){const uint8_t *ph=blob+info.phoff+i*32;if(word(ph)!=1 || !(word(ph+24)&1))continue;
        for(uint32_t page=word(ph+8)&~4095u;page<word(ph+8)+word(ph+20);page+=4096)if(ds_exec_page(exec,image+page-info.load_min)<0){free(image);return -1;}}
    uint32_t out[32] __attribute__((aligned(8))),address,size;int values[]={0,41,-17};
    typedef int (*Value)(uint32_t *,int) DS_IO_SOFT;typedef int (*Simple)(uint32_t *) DS_IO_SOFT;
    const char *functions[]={"probe_jump","probe_jump_underscore"};
    for(unsigned fn=0;fn<2;++fn){error=ds_elf_find_export(blob,&info,functions[fn],&address,&size);if(error){report("Jump probe %s export %s: %d\n",mode,functions[fn],error);free(image);return -1;}
        for(unsigned i=0;i<3;++i){int code=((Value)(image+address-info.load_min))(out,values[i]);if(code || out[0]!=(uint32_t)(values[i]?values[i]:1) || out[1]!=(fn?23u:17u)){report("Jump probe %s failed: %s value=%d code=%d out=%08lx/%lu image=%08lx\n",mode,functions[fn],values[i],code,(unsigned long)out[0],(unsigned long)out[1],(unsigned long)image);free(image);return -1;}}}
    if(ds_elf_find_export(blob,&info,"probe_jump_nested",&address,&size) || ((Simple)(image+address-info.load_min))(out) || out[0]!=11 || out[1]!=2){report("Jump probe %s nested failed: %lu/%lu\n",mode,(unsigned long)out[0],(unsigned long)out[1]);free(image);return -1;}
    if(ds_elf_find_export(blob,&info,"probe_jump_registers",&address,&size) || ((Simple)(image+address-info.load_min))(out) || out[0]!=37 || out[10]!=0x00400000 || (out[11]&7)!=4 || out[9]!=out[30] || out[28]!=0xdeadbeef || out[29]!=0xdeadbeef){report("Jump probe %s registers failed: result=%lu fp=%08lx sp=%08lx ip=%08lx/%08lx guard=%08lx/%08lx\n",mode,(unsigned long)out[0],(unsigned long)out[10],(unsigned long)out[11],(unsigned long)out[9],(unsigned long)out[30],(unsigned long)out[28],(unsigned long)out[29]);free(image);return -1;}
    for(unsigned i=4;i<12;++i)if(out[i-3]!=0x11111111u*i){report("Jump probe %s core%u failed: %08lx\n",mode,i,(unsigned long)out[i-3]);free(image);return -1;}
    for(unsigned i=8;i<16;++i)if(out[12+(i-8)*2]!=0x11110000+i || out[13+(i-8)*2]!=0xaaaa0000+i){report("Jump probe %s VFP%u failed\n",mode,i);free(image);return -1;}
    free(image);report("Jump probe %s: OK cases=8 core/VFP=OK\n",mode);return 0;
}
static void run(void) {
    DSExec exec={0};
    if(ds_exec_open(&exec)<0 || !exec.emulator) { report("REFUSED: emulator-only audit\n"); return; }
    if(R_FAILED(svcSetThreadPriority(CUR_THREAD_HANDLE,0x30))){report("Application priority setup failed\n");return;}
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
    report("Application memory: bytes=%lu; donor arenas=20+80MiB\n",(unsigned long)osGetMemRegionSize(MEMREGION_APPLICATION));
    if(osGetMemRegionSize(MEMREGION_APPLICATION)<124*1024*1024){report("REFUSED: New3DS 124MiB memory profile required\n");return;}
    void *brk_arena=memalign(4096,20*1024*1024),*map_arena=memalign(4096,80*1024*1024);
    trampoline=memalign(4096,3*4096);
    if(!image || !brk_arena || !map_arena || !trampoline) { report("Arena allocation failed\n"); return; }
    image_base=(uint32_t)image;image_length=info.image_size;
    if(ds_elf_prepare(file,(uint32_t)length,image,info.image_size,image_base,&info)) return;
    ds_io_init(&io,ds_io_sd_ops()); ds_runtime_init(4*1024*1024); ds6_init(log_android);
    if(ds7_init() || ds8_init() || ds9_memory_init(brk_arena,20*1024*1024,map_arena,80*1024*1024)) return;
    uint8_t missing_stat[104];int missing_result=ds6_stat("appdata://var/settings.sb",missing_stat);
    report("Pre-thread missing stat: %d errno=%ld\n",missing_result,(long)*ds_io_errno());
    ds9_memory_observer(arena_refused);
    ds7_observer(thread_event);
    ds17_observer(bad_jump);ds17_reset_stats();
    if(jump_probe(&exec,jump_arm_fixture,sizeof(jump_arm_fixture),"ARM") || jump_probe(&exec,jump_thumb_fixture,sizeof(jump_thumb_fixture),"Thumb")){report("JUMP PROBE STOPPED\n");return;}
    DS17Stats jumps;ds17_stats(&jumps);if(jumps.saves!=18 || jumps.restores!=18 || jumps.refusals){report("JUMP COUNTERS FAILED\n");return;}
    report("Jump probe counters: saves=18 restores=18 refusals=0\n");ds17_reset_stats();
    if(service_probe(&exec,strings_fixture,sizeof(strings_fixture),"probe_strings",2)){report("STRING PROBE STOPPED\n");return;}
    if(service_probe(&exec,jni10_fixture,sizeof(jni10_fixture),"probe_jni10",0)){report("JNI I/O PROBE STOPPED\n");return;}
    if(service_probe(&exec,assets_fixture,sizeof(assets_fixture),"probe_assets",3)){report("ASSET PROBE STOPPED\n");return;}
    if(service_probe(&exec,platform_fixture,sizeof(platform_fixture),"probe_platform",1)){report("PLATFORM PROBE STOPPED\n");return;}
    DSBootstrap boot;
    if(ds_bootstrap_verify(file,(uint32_t)length,image,info.image_size,image_base,&info,&boot)) { report("Bootstrap code verification failed\n"); return; }
    DSBinding bindings[768]; uint32_t count=ds6_bindings(bindings,768);
    count+=ds7_bindings(bindings+count,768-count); count+=ds8_bindings(bindings+count,768-count);
    count+=ds9_memory_bindings(bindings+count,768-count);
    count+=ds17_bindings(bindings+count,768-count);
    DSResolve result; uint32_t before=ds_crc32(image,info.image_size);
    int code=ds_elf_resolve(file,&info,image,bindings,count,&result);
    report("Production preflight: bound=%lu missing=%lu weak=%lu\n",(unsigned long)result.resolved,(unsigned long)result.missing,(unsigned long)result.weak_zero);
    if(code!=DS_UNRESOLVED_IMPORTS || result.resolved!=154 || result.missing!=234 || before!=ds_crc32(image,info.image_size)) return;
    report("Production guard: REFUSED; image unchanged\nAudit clock: emulator monotonic, excluded from supported count\n");
    FILE *gl_mode=fopen("sdmc:/3ds/deadspace/graphics-bridge-test.txt","rb");
    if(gl_mode){
        char marker[3];size_t n=fread(marker,1,3,gl_mode);fclose(gl_mode);
        if(n!=2 || memcmp(marker,"1\n",2) || graphics_setup()){report("GLES context setup failed\n");return;}
        if(ds22_client_range(&graphics,image,info.image_size) || ds22_client_range(&graphics,brk_arena,20*1024*1024) || ds22_client_range(&graphics,map_arena,80*1024*1024)){report("Client range registration failed\n");return;}
        void *sp;__asm__ volatile("mov %0, sp":"=r"(sp));MemInfo mi={0};PageInfo pi;
        Result queried=svcQueryMemory(&mi,&pi,(uint32_t)sp);
        report("Stack query: sp=%08lx result=%08lx base=%08lx size=%08lx perm=%lu\n",(unsigned long)sp,(unsigned long)queried,(unsigned long)mi.base_addr,(unsigned long)mi.size,(unsigned long)mi.perm);
        /* libctru's main stack is allocated from the committed application
         * heap, and Horizon may coalesce it with the surrounding RW region.
         * Register that bounded readable mapping; pointer lifetime remains the
         * GL caller's responsibility, as for other registered client ranges. */
        if(R_FAILED(queried) || !(mi.perm&1) || !mi.size || mi.size>124*1024*1024 || ds22_client_range(&graphics,(void *)mi.base_addr,mi.size)){report("Stack range registration failed\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n");return;}
        ds22_observer(&graphics,game_draw);
        uint32_t added=ds13_bindings(bindings+count,768-count);count+=added;
        report("GLES context bindings: %lu; bounded CPU triangle renderer\n",(unsigned long)added);
    }
    bindings[count++]=(DSBinding){"clock",(uint32_t)audit_clock};
    if(ds20_init(ds20_native_ops()))return;
    count+=ds20_bindings(bindings+count,768-count);
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
    ds19_assets_backend(&bridge,ds19_native_list,NULL);
    ds10_query_compat(&bridge,1);
    uint32_t orientation_address,orientation_size,top;
    if(ds_elf_find_export(file,&info,"Java_com_ea_blast_DeviceOrientationHandlerAndroidDelegate_NativeOnDeviceOrientationChange",&orientation_address,&orientation_size) ||
       ds_elf_constant_export(file,&info,"Java_com_ea_blast_DeviceOrientationHandlerAndroidDelegate_NativeGetDeviceOrientationTopSideUp",0xe3a00001,&top))return;
    ds11_orientation_backend(&bridge,(DS11Orientation)(image+orientation_address-info.load_min),1);
    FILE *sensor_mode=fopen("sdmc:/3ds/deadspace/sensor-bridge-test.txt","rb");
    if(sensor_mode){
        char marker[32]={0};size_t n=fread(marker,1,sizeof(marker),sensor_mode);fclose(sensor_mode);
        if(n==20 && !memcmp(marker,"DS12_SENSOR_TEST_V1\n",20)){
            uint32_t acceleration,acceleration_size;DS12SensorOps ops;
            DS12Calibration calibration={{1,2,3},{0,0,0},{512,512,512}};
            if(ds_elf_find_export(file,&info,"Java_com_ea_blast_AccelerometerAndroidDelegate_NativeOnAcceleration",&acceleration,&acceleration_size) ||
               ds12_hid_ops(&sensor_hid,&ops) || ds12_sensor_init(&sensor,&calibration,&ops) ||
               ds12_jni_sensor(&bridge,&sensor,(DS12Acceleration)(image+acceleration-info.load_min))){report("Sensor attach failed\n");return;}
            sensor_attached=1;report("Sensor bridge attached: native HID; emulator identity axes, nominal 512 counts/g\n");
        }else{report("Invalid sensor test marker\n");return;}
    }
    for(uint32_t slot=4;slot<DS_JNI_ENV_SLOTS;++slot) if(!jni.env_functions[slot]){
        snprintf(jni_slot_names[slot],sizeof(jni_slot_names[slot]),"JNIEnv slot %lu",(unsigned long)slot);
        jni.env_functions[slot]=trap_for(slot==6?"JNI FindClass (slot 6)":jni_slot_names[slot]);
    }
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
    uint32_t capture_after=2;FILE *capture_config=fopen("sdmc:/3ds/deadspace/capture-frame.txt","rb");
    if(capture_config){unsigned value=0;if(fscanf(capture_config,"%u",&value)==1 && value>=2 && value<=16)capture_after=value;fclose(capture_config);}
    if(graphics_attached){
        s32 priority;if(R_FAILED(svcGetThreadPriority(&priority,CUR_THREAD_HANDLE)) || !threadCreate(audit_watchdog,NULL,16384,priority,0,true)){report("Watchdog creation failed\n");return;}
        svcSleepThread(0);
    }
    for(uint32_t frame=1;frame<=120;++frame){
        audit_frame=frame;
        report("Frame %lu begin\n",(unsigned long)frame);
        if(((PushFrame)jni.env_functions[19])(&jni.env,16))return;
        ((Lifecycle)(image+draw-info.load_min))(&jni.env,NULL,400,240);
        ((PopFrame)jni.env_functions[20])(&jni.env,NULL);
        report("Frame %lu returned\n",(unsigned long)frame);
        if(graphics_attached){
            uint32_t drawn[4];ds22_stats(&graphics,drawn);
            if(frame>=capture_after && drawn[2] && drawn[3] && !save_surface(&graphics,"first-game-frame",image_base)){
                gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
                report("FIRST GAME FRAME CAPTURED: frame=%lu draws=%lu fragments=%lu samples=%lu\n",(unsigned long)frame,(unsigned long)drawn[0],(unsigned long)drawn[2],(unsigned long)drawn[3]);
                graphics_stats();jump_stats();DS9MemoryStats arena;ds9_memory_stats(&arena);
                report("Donor arenas: break=%lu peak=%lu mapped-pages=%lu map-peak=%lu refusals=%lu\n",(unsigned long)arena.break_bytes,(unsigned long)arena.break_peak,(unsigned long)arena.mapped_pages,(unsigned long)arena.map_peak,(unsigned long)arena.refusals);
                uint32_t j[7];ds10_stats(&bridge,j);uint32_t loans=0;
                for(unsigned i=0;i<DS_JNI_STRING_COUNT;++i)loans+=bridge.base.strings[i].pins;
                report("JNI checkpoint: pending=%lu failures=%lu refs=%lu frame-depth=%lu string-loans=%lu\n",(unsigned long)j[0],(unsigned long)j[3],(unsigned long)j[4],(unsigned long)bridge.frame_depth,(unsigned long)loans);
                sensor_shutdown();report("ENGINE EXPERIMENT STOPPED\nCompleted game frame saved.\n");if(journal){fclose(journal);journal=NULL;}svcExitProcess();
            }
        }
        ds11_pump_events(&bridge);
        if(sensor_attached && ds12_jni_pump(&bridge,(svcGetSystemTick()-started)*1000000/SYSCLOCK_ARM11)<0){sensor_shutdown();report("Sensor pump failed\n");return;}
        gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
        if(graphics_attached){u16 w,h;void *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);if(ds13_target(&graphics,pixels,(uint32_t)w*h*(graphics.layout==DS13_RGB565_CTR?2:3)))return;}
    }
    uint32_t final_state[7];ds10_stats(&bridge,final_state);
    report("Frame budget refs=%lu failures=%lu\n",(unsigned long)final_state[4],(unsigned long)final_state[3]);
    sensor_shutdown();
    report("FRAME BUDGET STOPPED; no renderer implemented\n");
}
int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP,NULL); RecursiveLock_Init(&journal_lock);
    threadOnException(audit_exception,exception_stack+sizeof(exception_stack),WRITE_DATA_TO_HANDLER_STACK);
    journal=fopen(LOG,"w");report("DEAD SPACE ENGINE AUDIT - EMULATOR ONLY\nREADY - press A\n");
    while(aptMainLoop()) {
        hidScanInput();if(hidKeysDown()&KEY_START) break;
        if(hidKeysDown()&KEY_A) {run();break;}
        gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
    }
    if(journal) fclose(journal);
    gfxExit();return 0;
}
