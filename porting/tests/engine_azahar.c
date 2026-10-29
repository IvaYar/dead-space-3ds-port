/* EMULATOR ONLY. Resolving an unknown import to a terminating trap is execution
 * instrumentation, not an implementation. This file is never built into a CIA. */
#include <3ds.h>
#ifdef DS_PICA_BACKEND
#include "ds34_gpu.h"
#endif
#include <malloc.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <sys/stat.h>
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
#include "ds23_touch.h"
#include "ds24_files.h"
#include "ds25_assets.h"
#include "ds27_pages.h"
#include "ds28_font.h"
#include "ds29_allocator.h"
#include "font_subset_config.h"
#include "donor_config.h"
#include "jni10_fixture.h"
#include "platform_fixture.h"
#include "jump_fixture.h"
#include "strings_fixture.h"
#include "assets_fixture.h"
#define LOG "sdmc:/3ds/deadspace/engine-azahar-log.txt"
/* Preserve enough normal heap for two donor arenas and its loaded image. */
#ifdef DS_NEW3DS_178
/* Normal heap VAs stop at 0x10000000; the large donor arena belongs in the
 * New3DS linear mapping. This ELF requires kernel descriptor >=2.44. */
u32 __ctru_heap_size=40*1024*1024;
u32 __ctru_linear_heap_size=132*1024*1024;
#else
u32 __ctru_linear_heap_size=4*1024*1024;
#endif
u32 __stacksize__=256*1024;
static FILE *journal;
static char journal_buffer[32768];
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
static DS23Touch touch;
static int touch_attached;
typedef struct {uint32_t frame,x,y;} AuditTap;
static AuditTap taps[16];static uint32_t tap_count;
#define jni bridge.base
static DSIO io;
static DSInitPlan plan;
static uint64_t started;
static volatile uint32_t audit_frame;
static volatile uint32_t fs_events;
static uint32_t watchdog_samples=15;
static void *main_thread_record;
typedef struct {uint32_t caller,kind,count;int id;uint64_t first,last;} ClockSeen;
static ClockSeen clocks[32];
static int partial_draw_saved;
static uint8_t exception_stack[16384] __attribute__((aligned(8)));
void ds_audit_trap(void);
static void report(const char *format,...) {
    RecursiveLock_Lock(&journal_lock);
    va_list args;if(!graphics_attached){va_start(args,format);vprintf(format,args);va_end(args);}
    if(journal) { va_start(args,format); vfprintf(journal,format,args); va_end(args);
        /* Preserve complete draw traces without a synchronous SD transaction
         * per draw. Frame boundaries, JNI messages and errors still flush. */
        if(strncmp(format,"GAME DRAW:",10))fflush(journal);
    }
    RecursiveLock_Unlock(&journal_lock);
}
void ds15_upload_trace(uint32_t w,uint32_t h,uint32_t format,uint32_t required,uint32_t limit,int result){
    report("GLES upload: %lux%lu format=%04lx required=%lu limit=%lu result=%d\n",(unsigned long)w,(unsigned long)h,(unsigned long)format,(unsigned long)required,(unsigned long)limit,result);
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
void ds26_trace(const char *op,uint32_t a,uint32_t b,uint32_t c,uint32_t d){
    static unsigned calls,last_target;
    if(!strcmp(op,"bind")){unsigned previous=last_target;last_target=a;if(!a && !previous)return;}
    if(++calls<=128 || calls%256==0)report("FBO %s: %lu %lu %08lx %08lx frame=%lu\n",op,(unsigned long)a,(unsigned long)b,(unsigned long)c,(unsigned long)d,(unsigned long)audit_frame);
}
static void graphics_stats(void){
    if(graphics.default_storage)report("Default surface: depth=%u stencil=%u bytes=%lu\n",graphics.default_storage->depth?16:0,graphics.default_storage->stencil?8:0,(unsigned long)graphics.default_storage->bytes);
    if(graphics.lighting_state){DS32Lighting *s=graphics.lighting_state;unsigned mask=0;for(unsigned i=0;i<8;++i)mask|=(graphics.pipeline.lights[i]!=0)<<i;
        report("Lighting state: enabled=%lu lights=%02x two-side=%lu setters=%lu vertices=%lu normal=%g,%g,%g\n",(unsigned long)graphics.pipeline.lighting,mask,(unsigned long)s->two_side,(unsigned long)s->setters,(unsigned long)s->vertices,(double)s->normal[0],(double)s->normal[1],(double)s->normal[2]);}
    if(graphics.fog_state){DS30Fog *f=graphics.fog_state;report("Fog state: enabled=%lu mode=%04lx density=%g start=%g end=%g color=%g,%g,%g,%g\n",(unsigned long)graphics.fog,(unsigned long)f->mode,(double)f->density,(double)f->start,(double)f->end,(double)f->color[0],(double)f->color[1],(double)f->color[2],(double)f->color[3]);}
    if(graphics.draw && graphics.draw->combine)for(unsigned u=0;u<2;++u){DS31Unit *s=&graphics.draw->combine->unit[u];report("Combine state: unit=%u enabled=%lu mode=%04lx rgb=%04lx alpha=%04lx scale=%g,%g\n",u,(unsigned long)graphics.texture.enabled[u],(unsigned long)graphics.draw->env_mode[u],(unsigned long)s->rgb,(unsigned long)s->alpha,(double)s->rgb_scale,(double)s->alpha_scale);}
    uint32_t fbo[4];ds26_stats(&graphics,fbo);report("FBO state: objects=%lu renderbuffers=%lu bytes=%lu changes=%lu bound=%lu\n",(unsigned long)fbo[0],(unsigned long)fbo[1],(unsigned long)fbo[2],(unsigned long)fbo[3],(unsigned long)graphics.framebuffer_binding);
    if(graphics_attached){uint32_t s[6];ds19_jni_stats(&bridge,s);report("JNI assets: lists=%lu names=%lu gets=%lu sets=%lu strings=%lu arrays=%lu\n",(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3],(unsigned long)s[4],(unsigned long)s[5]);}
    if(graphics_attached)report("JNI strings: new16=%lu newUTF=%lu get16=%lu getUTF=%lu regions=%lu errors=%lu\n",(unsigned long)bridge.string_stats[0],(unsigned long)bridge.string_stats[1],(unsigned long)bridge.string_stats[2],(unsigned long)bridge.string_stats[3],(unsigned long)bridge.string_stats[4],(unsigned long)bridge.string_stats[5]);
    if(graphics_attached)report("GLES error at stop: %08lx\n",(unsigned long)graphics.error);
    if(graphics_attached){uint32_t s[4];ds13_stats(&graphics,s);report("GLES counters: queries=%lu clears=%lu pixels=%lu flushes=%lu\n",(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3]);}
    if(graphics_attached){uint32_t s[4];ds15_stats(&graphics.texture,s);report("GLES texture stores: names=%lu bytes=%lu uploads=%lu patches=%lu\n",(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3]);}
    if(graphics_attached && !graphics.texture.backing_ops){const DS15Level *l=ds15_level(&graphics.texture,1,0);if(l)report("GLES first texture: %lux%lu format=%04lx bytes=%lu CRC32=%08lx\n",(unsigned long)l->width,(unsigned long)l->height,(unsigned long)l->format,(unsigned long)(l->width*l->height*4),(unsigned long)ds_crc32(l->rgba,l->width*l->height*4));}
    if(graphics.texture.backing_ops)report("Texture pages: resident=%lu limit=%lu saves=%lu loads=%lu failures=%lu\n",(unsigned long)graphics.texture.resident,(unsigned long)graphics.texture.resident_limit,(unsigned long)graphics.texture.page_saves,(unsigned long)graphics.texture.page_loads,(unsigned long)graphics.texture.page_failures);
}
static void jump_stats(void){DS17Stats s;ds17_stats(&s);report("Jump contexts: saves=%lu restores=%lu refusals=%lu\n",(unsigned long)s.saves,(unsigned long)s.restores,(unsigned long)s.refusals);}
static void thread_event(uint32_t event,uint32_t thread,uint32_t detail){
    static unsigned pool_refusals;
    if(event==5 && pool_refusals++>=8)return;
    report("Thread event: %lu id=%08lx detail=%08lx\n",(unsigned long)event,(unsigned long)thread,(unsigned long)detail);
}
static int save_surface(DS13Context *c,const char *stem,uint32_t caller){
    char path[128];snprintf(path,sizeof(path),"sdmc:/3ds/deadspace/%s.raw",stem);FILE *f=fopen(path,"wb");if(!f)return -1;
    uint32_t bytes=c->width*c->height*(c->layout==DS13_RGB565_CTR?2:3);int ok=fwrite(c->pixels,1,bytes,f)==bytes;if(fclose(f))ok=0;if(!ok)return -1;
    snprintf(path,sizeof(path),"sdmc:/3ds/deadspace/%s.json",stem);f=fopen(path,"w");if(!f)return -1;
    uint32_t s[4];ds22_stats(c,s);
    fprintf(f,"{\"width\":%lu,\"height\":%lu,\"layout\":%lu,\"bytes\":%lu,\"crc32\":\"%08lx\",\"frame\":%lu,\"caller_offset\":\"%08lx\",\"draws\":%lu,\"triangles\":%lu,\"fragments\":%lu,\"samples\":%lu}\n",(unsigned long)c->width,(unsigned long)c->height,(unsigned long)c->layout,(unsigned long)bytes,(unsigned long)ds_crc32(c->pixels,bytes),(unsigned long)audit_frame,(unsigned long)(caller-image_base),(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3]);
    return fclose(f)?-1:0;
}
static void game_draw(DS13Context *c,uint32_t caller){
    static uint32_t previous_fragments;static unsigned dominant,intermediate_saved;
    uint32_t now[4];ds22_stats(c,now);uint32_t changed=now[2]-previous_fragments;previous_fragments=now[2];
    if(audit_frame==2604 && !c->framebuffer_binding){
        uint32_t bytes=c->width*c->height*(c->layout==DS13_RGB565_CTR?2:3),nonzero=0;
        for(uint32_t i=0;i<bytes;++i)nonzero+=c->pixels[i]!=0;
        report("SCENE surface: frame=%lu draw=%lu caller=%08lx nonzero=%lu changed=%lu texture=%lu,%lu enabled=%lu,%lu env=%04lx,%04lx\n",(unsigned long)audit_frame,(unsigned long)now[0],(unsigned long)(caller-image_base),(unsigned long)nonzero,(unsigned long)changed,(unsigned long)c->texture.binding[0],(unsigned long)c->texture.binding[1],(unsigned long)c->texture.enabled[0],(unsigned long)c->texture.enabled[1],(unsigned long)c->draw->env_mode[0],(unsigned long)c->draw->env_mode[1]);
    }
    if(audit_frame>=2604 && changed>=48000 && dominant++<12)
        report("SCENE large draw: frame=%lu draw=%lu pixels=%lu lit=%lu fog=%lu depth=%lu stencil=%lu blend=%lu factors=%04lx,%04lx color=%g,%g,%g,%g mask=%u%u%u%u\n",(unsigned long)audit_frame,(unsigned long)now[0],(unsigned long)changed,(unsigned long)c->pipeline.lighting,(unsigned long)c->fog,(unsigned long)c->pipeline.depth,(unsigned long)c->pipeline.stencil,(unsigned long)c->blend,(unsigned long)c->pipeline.blend_src,(unsigned long)c->pipeline.blend_dst,(double)c->draw->color[0],(double)c->draw->color[1],(double)c->draw->color[2],(double)c->draw->color[3],c->color_mask[0],c->color_mask[1],c->color_mask[2],c->color_mask[3]);
    if(audit_frame>=2604 && c->pipeline.lighting && !intermediate_saved){uint32_t bytes=c->width*c->height*(c->layout==DS13_RGB565_CTR?2:3);unsigned nonzero=0;
        for(uint32_t i=0;i<bytes;++i)if(c->pixels[i]){nonzero=1;break;}
        if(nonzero && !save_surface(c,"scene-intermediate",caller)){intermediate_saved=1;report("SCENE INTERMEDIATE SAVED: frame=%lu\n",(unsigned long)audit_frame);}
    }
    static unsigned lit_draws;
    if(c->pipeline.lighting && c->lighting_state && ++lit_draws==1)report("LIT GAME DRAW: frame=%lu vertices=%lu\n",(unsigned long)audit_frame,(unsigned long)c->lighting_state->vertices);
    if(c->pipeline.lighting && c->lighting_state && lit_draws==1){DS32Lighting *s=c->lighting_state;
        report("Lit material: diffuse=%g,%g,%g,%g ambient=%g,%g,%g scene=%g,%g,%g emission=%g,%g,%g color-material=%lu\n",(double)s->diffuse[0],(double)s->diffuse[1],(double)s->diffuse[2],(double)s->diffuse[3],(double)s->ambient[0],(double)s->ambient[1],(double)s->ambient[2],(double)s->scene[0],(double)s->scene[1],(double)s->scene[2],(double)s->emission[0],(double)s->emission[1],(double)s->emission[2],(unsigned long)c->pipeline.color_material);
        for(unsigned i=0;i<8;++i)if(c->pipeline.lights[i]){DS32Light *l=&s->light[i];report("Lit light%u: position=%g,%g,%g,%g diffuse=%g,%g,%g\n",i,(double)l->position[0],(double)l->position[1],(double)l->position[2],(double)l->position[3],(double)l->diffuse[0],(double)l->diffuse[1],(double)l->diffuse[2]);}
    }
    static unsigned fog_draws;
    if(c->fog && c->fog_state && ++fog_draws==1)report("FOG GAME DRAW: frame=%lu mode=%04lx start=%g end=%g\n",(unsigned long)audit_frame,(unsigned long)c->fog_state->mode,(double)c->fog_state->start,(double)c->fog_state->end);
    uint32_t s[4];ds22_stats(c,s);report("GAME DRAW: caller-offset=%08lx calls=%lu triangles=%lu fragments=%lu samples=%lu\n",(unsigned long)(caller-image_base),(unsigned long)s[0],(unsigned long)s[1],(unsigned long)s[2],(unsigned long)s[3]);
    if(!partial_draw_saved && s[2] && s[3]){if(!save_surface(c,"first-game-draw",caller)){partial_draw_saved=1;report("PARTIAL GAME DRAW CAPTURED\n");}}
}
void ds22_vertex_trace(DS13Context *c,uint32_t index,const float *eye,const float *clip,const float *color,float fog){
    static unsigned events;if(audit_frame!=2604 || events++>=512)return;
    report("SCENE vertex: frame=%lu draw=%lu index=%lu eye=%g,%g,%g,%g clip=%g,%g,%g,%g rgba=%g,%g,%g,%g fog=%g lit=%lu target=%lu\n",(unsigned long)audit_frame,(unsigned long)(c->draw->calls+1),(unsigned long)index,(double)eye[0],(double)eye[1],(double)eye[2],(double)eye[3],(double)clip[0],(double)clip[1],(double)clip[2],(double)clip[3],(double)color[0],(double)color[1],(double)color[2],(double)color[3],(double)fog,(unsigned long)c->pipeline.lighting,(unsigned long)c->framebuffer_binding);
}
void ds22_pixel_trace(DS13Context *c,unsigned x,unsigned y,const float *src,const float *dst,const float *out){
    static unsigned events;if(audit_frame!=2604 || events++>=512)return;
    report("SCENE pixel: frame=%lu draw=%lu target=%lu xy=%u,%u src=%g,%g,%g,%g dst=%g,%g,%g,%g out=%g,%g,%g,%g alpha=%lu/%04lx/%g blend=%lu/%04lx/%04lx\n",(unsigned long)audit_frame,(unsigned long)(c->draw->calls+1),(unsigned long)c->framebuffer_binding,x,y,(double)src[0],(double)src[1],(double)src[2],(double)src[3],(double)dst[0],(double)dst[1],(double)dst[2],(double)dst[3],(double)out[0],(double)out[1],(double)out[2],(double)out[3],(unsigned long)c->pipeline.alpha,(unsigned long)c->pipeline.alpha_func,(double)c->pipeline.alpha_ref,(unsigned long)c->blend,(unsigned long)c->pipeline.blend_src,(unsigned long)c->pipeline.blend_dst);
}
void ds_fs_trace(const char *operation,const char *path,int result){
    static unsigned failures,late_opens;
    if(fs_events++<100 || (result<0 && failures++<48) || (audit_frame>=120 && strstr(operation,"open") && late_opens++<32))
        report("FS %s: %s result=%d\n",operation,path,result);
}
static void clock_seen(uint32_t kind,uint32_t caller,int id,const DS6Time *value,int result){
    if(ds7_tls()->record!=main_thread_record)return;
    if(result){report("CLOCK failure: kind=%lu caller=%08lx id=%d result=%d\n",(unsigned long)kind,(unsigned long)(caller-image_base),id,result);return;}
    if(!value)return;
    for(unsigned i=0;i<32;++i)if(!clocks[i].count || (clocks[i].caller==caller && clocks[i].kind==kind && clocks[i].id==id)){
        ClockSeen *s=&clocks[i];uint64_t us=(uint64_t)(uint32_t)value->sec*1000000u+(uint32_t)value->nsec/(kind==1?1:1000);
        if(!s->count)*s=(ClockSeen){caller,kind,0,id,us,us};
        ++s->count;s->last=us;return;
    }
}
static void clock_report(void){
    struct mallinfo heap=mallinfo();DSRuntimeStats runtime;ds_runtime_stats(&runtime);
    report("Native heap: used=%lu free=%lu; runtime live=%lu peak=%lu blocks=%lu failures=%lu\n",(unsigned long)heap.uordblks,(unsigned long)heap.fordblks,(unsigned long)runtime.live_bytes,(unsigned long)runtime.peak_bytes,(unsigned long)runtime.live_blocks,(unsigned long)runtime.failures);
    for(unsigned i=0;i<32;++i)if(clocks[i].count){ClockSeen *s=&clocks[i];
        report("CLOCK main: kind=%lu caller=%08lx id=%d calls=%lu first-us=%llu last-us=%llu\n",(unsigned long)s->kind,(unsigned long)(s->caller-image_base),s->id,(unsigned long)s->count,(unsigned long long)s->first,(unsigned long long)s->last);
    }
    DS7Stats threads;ds7_stats(&threads);
    report("Thread pools: active=%lu mutex=%lu cond=%lu sem=%lu keys=%lu\n",(unsigned long)threads.active_threads,(unsigned long)threads.mutexes,(unsigned long)threads.conditions,(unsigned long)threads.semaphores,(unsigned long)threads.keys);
}
static int DS_IO_SOFT audit_gettimeofday(DS6Time *out,void *zone){int result=ds6_gettimeofday(out,zone);clock_seen(1,(uint32_t)__builtin_return_address(0),0,out,result);return result;}
static int DS_IO_SOFT audit_clock_gettime(int id,DS6Time *out){int result=ds6_clock_gettime(id,out);clock_seen(2,(uint32_t)__builtin_return_address(0),id,out,result);return result;}
static const uint32_t *audit_words(uint32_t pointer,uint32_t count);
static void allocation_stack(void){
    uint32_t sp;__asm__ volatile("mov %0, sp":"=r"(sp));const uint32_t *words=audit_words(sp,128);if(!words)return;
    unsigned emitted=0;
    for(unsigned i=0;i<128 && emitted<12;++i){uint32_t address=words[i]&~1u;
        if(address<image_base+4 || address-image_base>=image_length || (address&3))continue;
        uint32_t instruction=*(const uint32_t *)(address-4);
        if((instruction&0x0f000000)==0x0b000000 || (instruction&0x0ffffff0)==0x012fff30 || (instruction&0x0c10f000)==0x0410f000){
            report("ARENA stack: word=%u return=%08lx\n",i,(unsigned long)(address-image_base));++emitted;
        }
    }
}
static void *DS_IO_SOFT audit_sbrk(int32_t bytes){
    if(bytes>=1048576)report("ARENA request: sbrk bytes=%ld caller=%08lx thread=%s frame=%lu\n",(long)bytes,(unsigned long)((uint32_t)__builtin_return_address(0)-image_base),ds7_tls()->record==main_thread_record?"main":"worker",(unsigned long)audit_frame);
    if(bytes>=16777216 && audit_frame>100)allocation_stack();
    void *result=ds29_sbrk(bytes,(uint32_t)__builtin_return_address(0));
    if(bytes>=1048576)report("ARENA result: sbrk pointer=%08lx\n",(unsigned long)result);
    return result;
}
static void *DS_IO_SOFT audit_mmap(void *hint,uint32_t bytes,int protection,int flags,int fd,int32_t offset){
    if(bytes>=1048576)report("ARENA request: mmap bytes=%lu caller=%08lx thread=%s frame=%lu\n",(unsigned long)bytes,(unsigned long)((uint32_t)__builtin_return_address(0)-image_base),ds7_tls()->record==main_thread_record?"main":"worker",(unsigned long)audit_frame);
    if(bytes>=16777216 && audit_frame>100)allocation_stack();
    return ds9_mmap(hint,bytes,protection,flags,fd,offset);
}
static int DS_IO_SOFT audit_munmap(void *pointer,uint32_t bytes){
    if(bytes>=1048576)report("ARENA release: munmap bytes=%lu caller=%08lx thread=%s frame=%lu\n",(unsigned long)bytes,(unsigned long)((uint32_t)__builtin_return_address(0)-image_base),ds7_tls()->record==main_thread_record?"main":"worker",(unsigned long)audit_frame);
    return ds9_munmap(pointer,bytes);
}
static const uint32_t *audit_words(uint32_t pointer,uint32_t count){
    if(pointer&3)return NULL;
    for(unsigned i=0;i<DS14_RANGES;++i){DS14Range *r=&graphics.vertex.ranges[i];if(r->base && pointer>=r->base && (uint64_t)pointer+count*4<=(uint64_t)r->base+r->size)return (const uint32_t *)pointer;}
    return NULL;
}
static void audit_watchdog(void *unused){
    (void)unused;
    for(unsigned sample=0;sample<watchdog_samples;++sample){
        svcSleepThread(10000000000LL);DS7DebugThread views[17];ds7_debug_threads(views);
        report("WATCH phase=%s frame=%lu image=%08lx fs-events=%lu\n",phase,(unsigned long)audit_frame,(unsigned long)image_base,(unsigned long)fs_events);
        for(unsigned i=0;i<17;++i)if(views[i].token){
            uint32_t offset=views[i].entry-image_base;
            report("WATCH thread=%08lx entry-offset=%08lx wait=%lu object=%08lx\n",(unsigned long)views[i].token,(unsigned long)offset,(unsigned long)views[i].wait_kind,(unsigned long)views[i].wait_object);
            if(offset==0x24c7f8 || offset==0x24c914){const uint32_t *args=audit_words(views[i].argument,6);
                if(args){uint32_t target=args[5],object=args[offset==0x24c7f8?3:4];
                    if(!target && offset==0x24c914)target=args[3];
                    if(!target && offset==0x24c7f8){const uint32_t *o=audit_words(object,1),*v=o?audit_words(*o,3):NULL;if(v)target=v[2];}
                    report("WATCH EA callback=%08lx argument=%08lx state=%lu\n",(unsigned long)(target-image_base),(unsigned long)object,(unsigned long)args[1]);
                }
            }
        }
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
static int private_file_probe(void){
    const char *path="appdata:/fd-probe.bin";const char payload[]="DS24 persistent file";char readback[sizeof(payload)]={0};
    int fd=ds24_open(path,DS24_RDWR|DS24_CREAT|DS24_TRUNC,0600);
    if(fd<0 || ds24_write(fd,payload,sizeof(payload))!=sizeof(payload) || ds_io_seek(fd,0,0) ||
       ds24_read(fd,readback,sizeof(readback))!=sizeof(readback) || memcmp(readback,payload,sizeof(payload)) || ds_io_close(fd))return -1;
    fd=ds24_open(path,0);if(fd<0)return -1;
    uint8_t packed[104];if(ds6_fstat(fd,packed) || ds24_read(fd,readback,sizeof(readback))!=sizeof(readback) ||
       memcmp(readback,payload,sizeof(payload)) || ds24_write(fd,payload,1)!=-1 || *ds_io_errno()!=9 || ds_io_close(fd))return -1;
    if(ds24_open(path,DS24_WRONLY|DS24_CREAT|DS24_EXCL,0600)!=-1 || *ds_io_errno()!=17)return -1;
    fd=ds24_open(path,DS24_WRONLY|DS24_APPEND);if(fd<0 || ds_io_seek(fd,0,0) || ds24_write(fd,"!",1)!=1 || ds_io_close(fd))return -1;
    fd=ds24_open(path,0);if(fd<0 || ds_io_seek(fd,0,2)!=(int32_t)sizeof(payload)+1 || ds_io_close(fd))return -1;
    if(ds24_open("published/data/achievements.sb",DS24_WRONLY)!=-1 || *ds_io_errno()!=30 || ds6_remove(path))return -1;
    report("Private fd probe: OK read/write/reopen/append/exclusive/fstat; asset writes refused\n");return 0;
}
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
    /* Emulator-only budget; default adapter limits and OOM tests stay bounded. */
    if(ds15_limits(&graphics.texture,osGetMemRegionSize(MEMREGION_APPLICATION)>=178*1024*1024?128:32,
        (osGetMemRegionSize(MEMREGION_APPLICATION)>=178*1024*1024?48:6)*1024*1024))return -1;
    ds13_observer(&graphics,graphics_unsupported,graphics_sync);graphics_attached=1;
#ifdef DS_PICA_BACKEND
    if(ds34_attach(&graphics)){report("PICA backend attach failed\n");return -1;}
    report("PICA backend attached: experimental GPU fragments; CPU vertex processing\n");
#endif
    report("Graphics budget: texture names=%lu bytes=%lu\n",(unsigned long)graphics.texture.name_limit,(unsigned long)graphics.texture.limit);return 0;
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
    uint64_t us=(svcGetSystemTick()-started)*1000000/SYSCLOCK_ARM11;DS6Time value={(int32_t)(us/1000000),(int32_t)((us%1000000)*1000)};
    clock_seen(3,(uint32_t)__builtin_return_address(0),1,&value,0);return (int32_t)us;
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
    unsigned brk_mib=20;FILE *arena_mode=fopen("sdmc:/3ds/deadspace/arena-split-test.txt","rb");
    if(arena_mode){unsigned value=0;if(fscanf(arena_mode,"%u",&value)==1 && (value==33 || value==100))brk_mib=value;fclose(arena_mode);}
    unsigned arena_mib=brk_mib==100 && osGetMemRegionSize(MEMREGION_APPLICATION)>=178*1024*1024?128:100;
    if(brk_mib==100)brk_mib=arena_mib;
    uint32_t brk_bytes=brk_mib*1024*1024,map_bytes=(arena_mib-brk_mib)*1024*1024;
    report("Application memory: bytes=%lu; donor arenas=%u+%uMiB\n",(unsigned long)osGetMemRegionSize(MEMREGION_APPLICATION),brk_mib,arena_mib-brk_mib);
    if(osGetMemRegionSize(MEMREGION_APPLICATION)<124*1024*1024){report("REFUSED: New3DS 124MiB memory profile required\n");return;}
    void *brk_arena=brk_mib==128?linearMemAlign(brk_bytes,4096):memalign(4096,brk_bytes);
    void *map_arena=map_bytes?memalign(4096,map_bytes):brk_arena;
    trampoline=memalign(4096,3*4096);
    if(!image || !brk_arena || !map_arena || !trampoline) { report("Arena allocation failed\n"); return; }
    image_base=(uint32_t)image;image_length=info.image_size;
    if(ds_elf_prepare(file,(uint32_t)length,image,info.image_size,image_base,&info)) return;
    ds_io_init(&io,ds_io_sd_ops()); ds_runtime_init((osGetMemRegionSize(MEMREGION_APPLICATION)>=178*1024*1024?64:8)*1024*1024); ds6_init(log_android);
    if(ds7_init() || ds8_init())return;
    if(!map_bytes){if(ds9_memory_init_shared(brk_arena,brk_bytes))return;report("Donor shared arena: %uMiB; bottom brk + top-down mmap\n",arena_mib);}
    else if(ds9_memory_init(brk_arena,brk_bytes,map_arena,map_bytes))return;
    main_thread_record=ds7_tls()->record;
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
    ds29_allocator_reset();
    FILE *allocator_mode=fopen("sdmc:/3ds/deadspace/allocator-compat-test.txt","rb");
    if(allocator_mode){char marker[3];size_t n=fread(marker,1,3,allocator_mode);fclose(allocator_mode);
        if(n!=2 || memcmp(marker,"1\n",2) || ds29_allocator_init(image,info.image_size)){report("Allocator compatibility verification failed\n");return;}
        report("EA allocator compatibility: verified growth-call new-break result; other sbrk callers unchanged\n");
    }
    DSResolve result; uint32_t before=ds_crc32(image,info.image_size);
    int code=ds_elf_resolve(file,&info,image,bindings,count,&result);
    report("Production preflight: bound=%lu missing=%lu weak=%lu\n",(unsigned long)result.resolved,(unsigned long)result.missing,(unsigned long)result.weak_zero);
    if(code!=DS_UNRESOLVED_IMPORTS || result.resolved!=154 || result.missing!=234 || before!=ds_crc32(image,info.image_size)) return;
    report("Production guard: REFUSED; image unchanged\nAudit clock: emulator monotonic, excluded from supported count\n");
    for(uint32_t i=0;i<count;++i){
        if(!strcmp(bindings[i].name,"gettimeofday"))bindings[i].address=(uint32_t)audit_gettimeofday;
        if(!strcmp(bindings[i].name,"clock_gettime"))bindings[i].address=(uint32_t)audit_clock_gettime;
        if(!strcmp(bindings[i].name,"sbrk"))bindings[i].address=(uint32_t)audit_sbrk;
        if(!strcmp(bindings[i].name,"mmap"))bindings[i].address=(uint32_t)audit_mmap;
        if(!strcmp(bindings[i].name,"munmap"))bindings[i].address=(uint32_t)audit_munmap;
    }
    FILE *gl_mode=fopen("sdmc:/3ds/deadspace/graphics-bridge-test.txt","rb");
    if(gl_mode){
        char marker[3];size_t n=fread(marker,1,3,gl_mode);fclose(gl_mode);
        if(n!=2 || memcmp(marker,"1\n",2) || graphics_setup()){report("GLES context setup failed\n");return;}
        if(ds22_client_range(&graphics,image,info.image_size) || ds22_client_range(&graphics,brk_arena,brk_bytes) || (map_bytes && ds22_client_range(&graphics,map_arena,map_bytes))){report("Client range registration failed\n");return;}
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
        FILE *fog_mode=fopen("sdmc:/3ds/deadspace/fog-test.txt","rb");
        if(fog_mode){int enabled=fgetc(fog_mode)=='1';fclose(fog_mode);
            if(!enabled || ds30_attach(&graphics))return;
            uint32_t fog_bindings=ds30_bindings(bindings+count,768-count);if(fog_bindings!=DS30_BINDINGS)return;count+=fog_bindings;
            report("Fog bridge attached: 4 operations; LINEAR/EXP/EXP2; eye-z vertex factors + RGB after texturing\n");
        }
        FILE *combine_mode=fopen("sdmc:/3ds/deadspace/combine-test.txt","rb");
        if(combine_mode){int enabled=fgetc(combine_mode)=='1';fclose(combine_mode);
            if(!enabled || ds31_attach(&graphics))return;
            report("Combine bridge attached: 2 units; RGB/alpha functions, sources, operands, scales + DOT3\n");
        }
        FILE *lighting_mode=fopen("sdmc:/3ds/deadspace/lighting-test.txt","rb");
        if(lighting_mode){int enabled=fgetc(lighting_mode)=='1';fclose(lighting_mode);
            if(!enabled || ds32_attach(&graphics))return;
            uint32_t n=ds32_bindings(bindings+count,768-count);if(n!=DS32_BINDINGS)return;count+=n;
            report("Lighting bridge attached: 18 operations; 8 lights + material + transformed normals + two-sided colors\n");
        }
        FILE *depth_mode=fopen("sdmc:/3ds/deadspace/default-depth-test.txt","rb");
        if(depth_mode){int enabled=fgetc(depth_mode)=='1';fclose(depth_mode);if(!enabled || ds33_attach(&graphics,16,8))return;
            report("Default depth attached: depth16/stencil8; 288000 owned bytes; borrowed LCD color\n");
        }
        FILE *fbo_mode=fopen("sdmc:/3ds/deadspace/framebuffer-test.txt","rb");
        if(fbo_mode){int enabled=fgetc(fbo_mode)=='1';fclose(fbo_mode);DSBinding overrides[DS26_BINDINGS];
            if(!enabled || ds26_bindings(overrides,DS26_BINDINGS)!=DS26_BINDINGS)return;
            if(ds15_limits(&graphics.texture,128,96*1024*1024) || ds15_backing(&graphics.texture,ds27_sd_backing(),6*1024*1024))return;
            for(unsigned i=0;i<DS26_BINDINGS;++i){uint32_t j=0;for(;j<count;++j)if(!strcmp(bindings[j].name,overrides[i].name)){bindings[j]=overrides[i];break;}
                if(j==count)bindings[count++]=overrides[i];}
            report("FBO bridge attached: 15 operations; texture/RBO targets + depth16/stencil8 + readback\n");
            report("Texture paging attached: 128 names; 96MiB logical; 6MiB resident; exact RGBA8 + CRC\n");
        }
    }
    bindings[count++]=(DSBinding){"clock",(uint32_t)audit_clock};
    FILE *font_mode=fopen("sdmc:/3ds/deadspace/font-subset-test.txt","rb");
    if(font_mode){int enabled=fgetc(font_mode)=='1';fclose(font_mode);FILE *f=fopen(DS28_FONT_PATH,"rb");
        uint8_t *data=malloc(DS28_FONT_SIZE);int valid=enabled && f && data && fread(data,1,DS28_FONT_SIZE,f)==DS28_FONT_SIZE &&
            fgetc(f)==EOF && ds_crc32(data,DS28_FONT_SIZE)==DS28_FONT_CRC;
        if(f)fclose(f);
        free(data);
        if(!valid || ds_io_read_override(ds28_font_path)){report("Font subset verification failed\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n");return;}
        report("Font subset attached: bytes=%lu CRC32=%08lx; original font untouched\n",(unsigned long)DS28_FONT_SIZE,(unsigned long)DS28_FONT_CRC);
    }
    FILE *private_mode=fopen("sdmc:/3ds/deadspace/private-files-test.txt","rb");
    if(private_mode){int enabled=fgetc(private_mode)=='1';fclose(private_mode);
        if(!enabled || (mkdir("sdmc:/3ds/deadspace/test-output",0700) && errno!=EEXIST) ||
           (mkdir("sdmc:/3ds/deadspace/test-output/save-bridge",0700) && errno!=EEXIST) ||
           ds6_appdata_namespace("save-bridge") || ds24_init(ds24_native_ops()) || private_file_probe()){
            report("Private file setup failed: errno=%ld\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n",(long)*ds_io_errno());return;
        }
        DSBinding overrides[5];ds24_bindings(overrides,5);
        for(unsigned i=0;i<5;++i){uint32_t j=0;for(;j<count;++j)if(!strcmp(bindings[j].name,overrides[i].name)){bindings[j]=overrides[i];break;}
            if(j==count)bindings[count++]=overrides[i];}
        report("Private file bridge: appdata mounted at test-output/save-bridge; 5 bindings\n");
    }
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
    FILE *touch_mode=fopen("sdmc:/3ds/deadspace/touch-bridge-test.txt","rb");
    if(touch_mode){
        char line[80],extra;unsigned lines=0,invalid=0;
        while(fgets(line,sizeof(line),touch_mode)){
            unsigned value=0,x=160,y=120;int fields=sscanf(line,"%u %u %u %c",&value,&x,&y,&extra);++lines;
            if((fields!=1 && fields!=3) || value>3598 || (value && value<2) || x>=320 || y>=240 ||
               tap_count>=16 || (!value && lines!=1) || (value && tap_count && value<=taps[tap_count-1].frame+1)){invalid=1;break;}
            if(value)taps[tap_count++]=(AuditTap){value,x,y};
        }
        fclose(touch_mode);
        uint32_t pointer,pointer_size;
        if(!lines || invalid ||
           ds_elf_find_export(file,&info,"Java_com_ea_blast_TouchSurfaceAndroid_NativeOnPointerEvent",&pointer,&pointer_size) ||
           ds23_touch_init(&touch,&bridge,320,240,(DS23Pointer)(image+pointer-info.load_min))){report("Touch attach failed\n");return;}
        touch_attached=1;
        report("Touch bridge attached: source=320x240 surface=400x240 module=1000 scripted-tap=%lu\n",(unsigned long)(tap_count?taps[0].frame:0));
        if(tap_count>1)report("Scripted tap sequence: %lu events\n",(unsigned long)tap_count);
    }
    ds19_assets_backend(&bridge,ds19_native_list,NULL);
    FILE *apk_mode=fopen("sdmc:/3ds/deadspace/apk-assets-test.txt","rb");
    if(apk_mode){int enabled=fgetc(apk_mode)=='1';fclose(apk_mode);
        FILE *verified=fopen("sdmc:/3ds/deadspace/apk-assets-verified.txt","rb");char receipt[128]={0};
        size_t n=verified?fread(receipt,1,sizeof(receipt),verified):0;if(verified)fclose(verified);
        const char expected[]="DS_APK_ASSETS_V1 0d3c870ae38687e1ac7e8dbf0ca8568862437491529e8ef45b818f4c38958845 20\n";
        if(!enabled || n!=sizeof(expected)-1 || memcmp(receipt,expected,n)){
            report("APK assets unverified\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n");return;
        }
        int fd=ds25_native_open((void *)DS25_ROOT,"EAMCore.ini",2);uint8_t core[4096];
        int bytes=fd<0?-1:ds_io_read(fd,core,sizeof(core));if(fd>=0)ds_io_close(fd);
        if(bytes!=3119 || ds_crc32(core,3119)!=0x33c9beb3){report("APK core asset probe failed\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n");return;}
        ds19_assets_backend_full(&bridge,ds19_native_list,ds25_native_open,ds19_apk_path,(void *)DS25_ROOT);
        for(uint32_t i=0;i<count;++i)if(!strcmp(bindings[i].name,"fcntl"))bindings[i].address=(uint32_t)ds_io_fcntl;
        report("APK AssetManager attached: 20 genuine files; EAMCore.ini bytes=3119 CRC32=33c9beb3\n");
    }
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
    if(capture_config){unsigned value=0;if(fscanf(capture_config,"%u",&value)==1 && value>=2 && value<=12000)capture_after=value;fclose(capture_config);}
#ifdef DS34_SEQUENCE_AUDIT
    unsigned sequence_start=0,sequence_count=0;
    FILE *sequence_config=fopen("sdmc:/3ds/deadspace/gpu-sequence-test.txt","rb");
    int sequence_valid=sequence_config && fscanf(sequence_config,"%u %u",&sequence_start,&sequence_count)==2;
    if(sequence_config)fclose(sequence_config);
    if(!sequence_valid || !graphics_attached || sequence_start<2 || sequence_count<2 || sequence_count>10 || sequence_start+sequence_count-1!=capture_after){report("Invalid GPU sequence configuration\n");return;}
    FILE *sequence_log=fopen("sdmc:/3ds/deadspace/gpu-sequence.jsonl","w");
    if(!sequence_log){report("GPU sequence journal unavailable\n");return;}fclose(sequence_log);
#endif
    unsigned auto_menu=0,auto_state=0,auto_frame=0,auto_confirm=0;
    FILE *auto_config=fopen("sdmc:/3ds/deadspace/auto-menu-test.txt","rb");
    if(auto_config){unsigned value=0;if(fscanf(auto_config,"%u",&value)==1 && value>=2 && value<=3600)auto_menu=value;fclose(auto_config);
        if(!auto_menu || !touch_attached || tap_count || !graphics_attached){report("Invalid automatic menu configuration\n");return;}
        report("AUTO MENU enabled: exact Normal/Easy frame CRCs; capture %u callbacks after confirmation\n",auto_menu);
    }
    if(capture_after>120)watchdog_samples=90+capture_after*2;
    int resume_focus=0;FILE *lifecycle_mode=fopen("sdmc:/3ds/deadspace/lifecycle-bridge-test.txt","rb");
    if(lifecycle_mode){resume_focus=fgetc(lifecycle_mode)=='1';fclose(lifecycle_mode);}
    if(graphics_attached){
        s32 priority;if(R_FAILED(svcGetThreadPriority(&priority,CUR_THREAD_HANDLE)) || !threadCreate(audit_watchdog,NULL,16384,priority,0,true)){report("Watchdog creation failed\n");return;}
        svcSleepThread(0);
    }
    for(uint32_t frame=1;frame<=(graphics_attached?capture_after:120);++frame){
        audit_frame=frame;
        report("Frame %lu begin\n",(unsigned long)frame);
        if(((PushFrame)jni.env_functions[19])(&jni.env,16))return;
        ((Lifecycle)(image+draw-info.load_min))(&jni.env,NULL,400,240);
        ((PopFrame)jni.env_functions[20])(&jni.env,NULL);
#ifdef DS_PICA_BACKEND
        if(graphics_attached && ds34_present(&graphics))return;
#endif
        report("Frame %lu returned\n",(unsigned long)frame);
        if(resume_focus && frame==2){
            const char *events[]={"Java_com_ea_blast_MainActivity_NativeOnResume","Java_com_ea_blast_MainActivity_NativeOnWindowFocusChanged"};
            const char *event_labels[]={"NativeOnResume","NativeOnWindowFocusChanged"};
            for(unsigned i=0;i<2;++i){
                uint32_t address,event_size;if(ds_elf_find_export(file,&info,events[i],&address,&event_size))return;
                phase=event_labels[i];report("Calling %s after engine initialization...\n",phase);
                if(((PushFrame)jni.env_functions[19])(&jni.env,16))return;
                ((Lifecycle)(image+address-info.load_min))(&jni.env,NULL,1,0);
                ((PopFrame)jni.env_functions[20])(&jni.env,NULL);report("%s returned\n",phase);
            }
            phase="NativeOnDrawFrame";
        }
        if(touch_attached){
            hidScanInput();touchPosition p;hidTouchRead(&p);uint32_t pressed=(hidKeysHeld()&KEY_TOUCH)!=0;
            if(tap_count){pressed=0;for(unsigned i=0;i<tap_count;++i)if(frame>=taps[i].frame){pressed=frame==taps[i].frame;p.px=(u16)taps[i].x;p.py=(u16)taps[i].y;}}
            if(auto_menu && auto_state<4){
                pressed=0;
                if(auto_state==1){auto_state=2;report("AUTO MENU select released: frame=%lu\n",(unsigned long)frame);}
                else if(auto_state==3){auto_state=4;report("AUTO MENU confirm released: frame=%lu\n",(unsigned long)frame);}
                else if((auto_state==0 && frame%60==0) || (auto_state==2 && frame%4==0)){
                    uint32_t crc=ds_crc32(graphics.pixels,graphics.width*graphics.height*2);
                    if((auto_state==0 && crc==0x95a4497f) || (auto_state==2 && crc==0x416337f3)){
                        char stem[48];snprintf(stem,sizeof(stem),"progress-frame-%lu",(unsigned long)frame);
                        if(save_surface(&graphics,stem,image_base)){report("AUTO MENU capture failed\n");return;}
                        report("PROGRESS FRAME SAVED: frame=%lu\n",(unsigned long)frame);
                        pressed=1;p.px=auto_state==0?160:284;p.py=auto_state==0?134:225;
                        report("AUTO MENU %s: frame=%lu crc=%08lx\n",auto_state==0?"select Easy":"confirm",(unsigned long)frame,(unsigned long)crc);
                        if(auto_state==0){auto_state=1;auto_frame=frame;}else{auto_state=3;auto_confirm=frame;capture_after=frame+auto_menu;}
                    }else if(auto_state==2 && frame>auto_frame+120){report("AUTO MENU Easy state not observed\nENGINE EXPERIMENT STOPPED\nNo game frame rendered.\n");return;}
                }
            }
            int delivered=ds23_touch_sample(&touch,pressed,p.px,p.py);
            if(delivered<0){report("Touch sample failed\n");return;}
            if(delivered)report("Touch event returned: frame=%lu pressed=%lu x=%u y=%u events=%lu\n",(unsigned long)frame,(unsigned long)pressed,p.px,p.py,(unsigned long)touch.events);
        }
        if(graphics_attached){
            if(auto_menu && auto_state==4 && frame%60==0){
                FILE *live=fopen("sdmc:/3ds/deadspace/auto-menu-test.txt","rb");unsigned value=0;
                if(live){int valid=fscanf(live,"%u",&value)==1 && value>=2 && value<=3600;fclose(live);
                    if(valid && value!=auto_menu){auto_menu=value;capture_after=auto_confirm+value;report("AUTO MENU duration updated: callbacks=%u target=%lu\n",value,(unsigned long)capture_after);}}
            }
            uint32_t drawn[4];ds22_stats(&graphics,drawn);
#ifdef DS34_SEQUENCE_AUDIT
            if(frame>=sequence_start && frame<sequence_start+sequence_count){
                DS34Audit a;int bad=ds34_sequence_audit(&a);uint32_t counters[4];ds34_stats(counters);
                char stem[48];snprintf(stem,sizeof(stem),"gpu-frame-%lu",(unsigned long)frame);
                if(save_surface(&graphics,stem,image_base)){report("GPU sequence capture failed\n");return;}
                FILE *f=fopen("sdmc:/3ds/deadspace/gpu-sequence.jsonl","a");if(!f){report("GPU sequence journal failed\n");return;}
                fprintf(f,"{\"frame\":%lu,\"gl_error\":%lu,\"draws\":%lu,\"triangles\":%lu,\"uploads\":%lu,\"vram\":%lu,\"presents\":%lu,\"drains\":%lu,\"peak_vertices\":%lu,\"upload_checks\":%lu,\"upload_mismatches\":%lu,\"vertex_checks\":%lu,\"vertex_mismatches\":%lu,\"texture_checks\":%lu,\"texture_mismatches\":%lu,\"pending_staging\":%lu,\"stream_used\":%lu,\"cached_textures\":%lu,\"texture_digest\":%lu}\n",
                    (unsigned long)frame,(unsigned long)graphics.error,(unsigned long)counters[0],(unsigned long)counters[1],(unsigned long)counters[2],(unsigned long)counters[3],(unsigned long)a.presents,(unsigned long)a.drains,(unsigned long)a.peak_vertices,(unsigned long)a.upload_checks,(unsigned long)a.upload_mismatches,(unsigned long)a.vertex_checks,(unsigned long)a.vertex_mismatches,(unsigned long)a.texture_checks,(unsigned long)a.texture_mismatches,(unsigned long)a.pending_staging,(unsigned long)a.stream_used,(unsigned long)a.cached_textures,(unsigned long)a.texture_digest);
                if(fclose(f)){report("GPU sequence journal close failed\n");return;}
                report("GPU SEQUENCE FRAME SAVED: frame=%lu audit=%s\n",(unsigned long)frame,bad?"FAILED":"OK");
                if(bad || graphics.error){report("GPU sequence audit failed\n");return;}
            }
#endif
            if(capture_after>120 && frame%120==0 && frame<capture_after){
                char stem[48];snprintf(stem,sizeof(stem),"progress-frame-%lu",(unsigned long)frame);
                if(!save_surface(&graphics,stem,image_base))report("PROGRESS FRAME SAVED: frame=%lu\n",(unsigned long)frame);
                clock_report();
            }
            int pixels_drawn=drawn[2] && drawn[3];
#ifdef DS_PICA_BACKEND
            uint32_t gpu[4];ds34_stats(gpu);pixels_drawn=gpu[1]!=0;
#endif
            if(frame>=capture_after && pixels_drawn && !save_surface(&graphics,"first-game-frame",image_base)){
#ifndef DS_PICA_BACKEND
                gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
#else
                report("PICA checkpoint: draws=%lu triangles=%lu uploads=%lu VRAM=%lu\n",(unsigned long)gpu[0],(unsigned long)gpu[1],(unsigned long)gpu[2],(unsigned long)gpu[3]);
#endif
                report("FIRST GAME FRAME CAPTURED: frame=%lu draws=%lu fragments=%lu samples=%lu\n",(unsigned long)frame,(unsigned long)drawn[0],(unsigned long)drawn[2],(unsigned long)drawn[3]);
                graphics_stats();jump_stats();clock_report();DS9MemoryStats arena;ds9_memory_stats(&arena);
                report("Donor arenas: break=%lu peak=%lu mapped-pages=%lu map-peak=%lu refusals=%lu\n",(unsigned long)arena.break_bytes,(unsigned long)arena.break_peak,(unsigned long)arena.mapped_pages,(unsigned long)arena.map_peak,(unsigned long)arena.refusals);
                uint32_t j[7];ds10_stats(&bridge,j);uint32_t loans=0;
                for(unsigned i=0;i<DS_JNI_STRING_COUNT;++i)loans+=bridge.base.strings[i].pins;
                report("JNI checkpoint: pending=%lu failures=%lu refs=%lu frame-depth=%lu string-loans=%lu\n",(unsigned long)j[0],(unsigned long)j[3],(unsigned long)j[4],(unsigned long)bridge.frame_depth,(unsigned long)loans);
                for(unsigned i=0;i<DS_JNI_STRING_COUNT;++i)if(bridge.base.strings[i].pins){
                    unsigned refs=0;for(unsigned k=0;k<128;++k)if(bridge.refs[k].token && bridge.refs[k].kind==4 && bridge.refs[k].identity==i)++refs;
                    report("JNI retained string: slot=%u text=%s loans=%lu refs=%u\n",i,bridge.base.strings[i].bytes,(unsigned long)bridge.base.strings[i].pins,refs);
                }
                if(touch_attached){uint32_t events=touch.events;int result=ds23_touch_close(&touch);touch_attached=0;report("Touch shutdown: result=%d events=%lu\n",result,(unsigned long)events);}
                sensor_shutdown();report("ENGINE EXPERIMENT STOPPED\nCompleted game frame saved.\n");if(journal){fclose(journal);journal=NULL;}
                /* Keep borrowed donor code/arenas alive while the frontend
                 * observes the LCD and shuts the emulator down. Exiting the
                 * process under its workers can throw inside Azahar. */
                for(;;)svcSleepThread(1000000000LL);
            }
        }
        ds11_pump_events(&bridge);
        if(sensor_attached && ds12_jni_pump(&bridge,(svcGetSystemTick()-started)*1000000/SYSCLOCK_ARM11)<0){sensor_shutdown();report("Sensor pump failed\n");return;}
#ifdef DS_PICA_BACKEND
        if(!graphics_attached){gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();}
#else
        gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
        if(graphics_attached){u16 w,h;void *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);if(ds13_target(&graphics,pixels,(uint32_t)w*h*(graphics.layout==DS13_RGB565_CTR?2:3)))return;}
#endif
    }
    uint32_t final_state[7];ds10_stats(&bridge,final_state);
    report("Frame budget refs=%lu failures=%lu\n",(unsigned long)final_state[4],(unsigned long)final_state[3]);
    sensor_shutdown();
    report("FRAME BUDGET STOPPED; no renderer implemented\n");
}
int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP,NULL); RecursiveLock_Init(&journal_lock);
    threadOnException(audit_exception,exception_stack+sizeof(exception_stack),WRITE_DATA_TO_HANDLER_STACK);
    journal=fopen(LOG,"w");if(journal)setvbuf(journal,journal_buffer,_IOFBF,sizeof(journal_buffer));
    report("DEAD SPACE ENGINE AUDIT - EMULATOR ONLY\nREADY - press A\n");
    while(aptMainLoop()) {
        hidScanInput();if(hidKeysDown()&KEY_START) break;
        if(hidKeysDown()&KEY_A) {run();break;}
        gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
    }
    if(journal) fclose(journal);
    gfxExit();return 0;
}
