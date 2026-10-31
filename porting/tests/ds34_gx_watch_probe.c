/* One unchanged DS34 RGBA8->RGB8 draw, followed by bounded observation. */
#include "gx_watch.h"
#include "ds13_gles.h"
#include "ds34_gpu.h"
#include "ds_runtime.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#define ROOT "sdmc:/3ds/ds34-gx-watch-v0.2.0/"
#define BYTES 288000u
u32 __stacksize__=256*1024;
static DS13Context ctx;
static DSBinding bindings[128];static unsigned binding_count;
static FILE *journal;static char folder[128];static int fault,setup_failed;
static u32 error_before_end;

/* Defensive enforcement as well as static separation of recorder and file I/O.
 * Reject filesystem stdio while armed; no actual SD operation is delegated. */
extern FILE *__real_fopen(const char*,const char*);
extern size_t __real_fwrite(const void*,size_t,size_t,FILE*);
extern int __real_fflush(FILE*),__real_fclose(FILE*),__real_fputs(const char*,FILE*);
FILE *__wrap_fopen(const char *p,const char *m){if(gw_critical()){gw_blocked_io();return NULL;}return __real_fopen(p,m);}
size_t __wrap_fwrite(const void *p,size_t s,size_t n,FILE *f){if(gw_critical()){gw_blocked_io();return 0;}return __real_fwrite(p,s,n,f);}
int __wrap_fflush(FILE *f){if(gw_critical()){gw_blocked_io();return EOF;}return __real_fflush(f);}
int __wrap_fclose(FILE *f){if(gw_critical()){gw_blocked_io();return EOF;}return __real_fclose(f);}
int __wrap_fputs(const char *p,FILE *f){if(gw_critical()){gw_blocked_io();return EOF;}return __real_fputs(p,f);}
int __wrap_fprintf(FILE *f,const char *fmt,...){
    if(gw_critical()){gw_blocked_io();return -1;}va_list args;va_start(args,fmt);int n=vfprintf(f,fmt,args);va_end(args);return n;
}
static void path(char out[192],const char *name){snprintf(out,192,"%s%s",folder,name);}
static void flush_bottom(void){u16 w,h;void *p=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,&w,&h);
    GSPGPU_FlushDataCache(p,(u32)w*h*(gfxGetScreenFormat(GFX_BOTTOM)==GSP_RGB565_OES?2:3));}
static void screen(const char *stage){
    if(gw_critical())return;
    printf("\x1b[2J\x1b[HDS34 GX Watch v0.2.0\n%s\nRun: %s\nNo game. START: checked exit.\n",stage,folder+strlen(ROOT));flush_bottom();
}
static void log_phase(const char *text){
    if(gw_critical())return;
    if(journal){fprintf(journal,"PHASE tick=%llu %s\n",(unsigned long long)svcGetSystemTick(),text);fflush(journal);}
}
void ds34_diagnostic_mark(const char *text){if(!gw_critical())log_phase(text);}
static int initial_begin(void){
    /* No extra unbounded VBlank wait even on the initial empty frame. */
    u64 start=svcGetSystemTick();u32 a=C3D_FrameCounter(0),b=C3D_FrameCounter(1);
    while(C3D_FrameCounter(0)==a || C3D_FrameCounter(1)==b){
        if(svcGetSystemTick()-start>SYSCLOCK_ARM11){setup_failed=1;return 0;}svcSleepThread(1000000);
    }
    int ok=C3D_FrameBegin(C3D_FRAME_NONBLOCK);if(!ok)setup_failed=1;return ok;
}
int ds34_diagnostic_begin(uint32_t flags){
    (void)flags;
    if(!gw_critical())return initial_begin();
    gw_sample(GW_BEGIN_ENTER);
    if(gw_data()->fault){gw_begin_result(0,0);return 0;}
    /* NONBLOCK is a diagnostic check, not a GPU algorithm correction. */
    int ok=C3D_FrameBegin(C3D_FRAME_NONBLOCK);gw_begin_result(1,ok);return ok;
}
void ds34_diagnostic_end(void){
    error_before_end=ctx.error;
    screen("03 FRAME END / OBSERVE IN RAM\nNo SD writes until window closes.\nWindow budget: 2 seconds.\nIf stuck here: photograph screen.");
    log_phase("03 ARMING; next FrameEnd and observation are RAM-only");
    gw_arm(fault);gw_sample(GW_END_ENTER);C3D_FrameEnd(0);gw_sample(GW_END_RETURN);
}
int ds34_diagnostic_sync(void){gw_observe(2000);return 0;}
static void observed(const char *text,u32 arg){
    if(gw_critical())return; /* Busy/NONBLOCK may raise a diagnostic GL error. */
    if(journal){fprintf(journal,"GLES %s %08lx\n",text,(unsigned long)arg);fflush(journal);}
}
typedef void (*One)(u32) DS13_SOFT;
typedef void (*Color)(float,float,float,float) DS13_SOFT;
typedef void (*Pointer)(int32_t,u32,int32_t,const void*) DS13_SOFT;
typedef void (*Box)(int32_t,int32_t,int32_t,int32_t) DS13_SOFT;
typedef void (*Draw)(u32,int32_t,int32_t) DS13_SOFT;
static void *fn(const char *name){for(unsigned i=0;i<binding_count;++i)if(!strcmp(bindings[i].name,name))return (void*)bindings[i].address;return NULL;}
static const float quad[]={-1,-1,0,1,-1,0,-1,1,0,1,1,0};
static int draw_frame(void){
    u16 w,h;void *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);
    if(w!=240 || h!=400 || gfxGetScreenFormat(GFX_TOP)!=GSP_BGR8_OES)return -1;
    ds_runtime_init(8*1024*1024);
    if(ds13_init(&ctx,pixels,400,240,BYTES,DS13_BGR8_CTR) || ds13_current(&ctx))return -1;
    ds13_observer(&ctx,observed,NULL);binding_count=ds13_bindings(bindings,128);
    if(binding_count!=99 || ds22_client_range(&ctx,quad,sizeof(quad)))return -1;
    screen("02 ATTACH / PREPARE\nInitial neutral texture upload\ncan still block in SDK.");log_phase("ATTACH BEGIN");
    if(ds34_attach(&ctx))return -1;
    log_phase("ATTACH OK");
    ((Pointer)fn("glVertexPointer"))(3,0x1406,0,quad);((One)fn("glEnableClientState"))(0x8074);
    ((One)fn("glDisable"))(0xc11);((Color)fn("glClearColor"))(104/255.f,176/255.f,216/255.f,1);((One)fn("glClear"))(0x4100);
    ((Box)fn("glScissor"))(40,40,64,80);((One)fn("glEnable"))(0xc11);((Color)fn("glColor4f"))(1,1,1,1);((Draw)fn("glDrawArrays"))(5,0,4);
    if(setup_failed || ctx.error)return -1;
    return ds34_present(&ctx);
}
static int capture_frame(void){
    if(ctx.layout!=DS13_BGR8_CTR || ctx.capacity!=BYTES)return -1;
    if(R_FAILED(GSPGPU_InvalidateDataCache(ctx.pixels,BYTES)))return -1;
    for(unsigned x=0;x<400;++x)for(unsigned y=0;y<240;++y){
        const u8 bg[]={216,176,104},fg[]={255,255,255};const u8 *want=x>=40 && x<104 && y>=40 && y<120?fg:bg;
        if(memcmp(ctx.pixels+(x*240+y)*3,want,3))return -1;
    }
    DS34Audit audit;if(ds34_sequence_audit(&audit))return -1;
    char out[192];path(out,"frame.raw");FILE *f=fopen(out,"wb");if(!f)return -1;int bad=fwrite(ctx.pixels,1,BYTES,f)!=BYTES;if(fclose(f))bad=1;return bad?-1:0;
}
static int make_folder(void){
    if((mkdir("sdmc:/3ds",0777) && errno!=EEXIST) || (mkdir(ROOT,0777) && errno!=EEXIST))return -1;
    for(unsigned i=1;i<=9999;++i){snprintf(folder,sizeof(folder),ROOT"run-%04u/",i);if(!mkdir(folder,0777))return 0;if(errno!=EEXIST)return -1;}return -1;
}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);
    bool new3ds=false;Result model=APT_CheckNew3DS(&new3ds);s64 info=0;int emulator=svcGetSystemInfo(&info,0x20000,0)==0;
    if(R_FAILED(model) || !new3ds || make_folder()){printf("New3DS / writable SD required\n");goto wait;}
#ifdef GX_WATCH_FAULT
    if(!emulator){printf("Emulator-only fault build\n");goto wait;}fault=1;
#endif
    char out[192];path(out,"gpu-test.log");journal=fopen(out,"w");if(!journal)goto wait;
    fprintf(journal,"DS34 GX Watch 0.2.0 environment=%s fault=%d layout=1 bytes=288000 flags=1000\n",emulator?"emulator":"native",fault);fflush(journal);
    path(out,"ready.txt");FILE *ready=fopen(out,"w");if(!ready)goto wait;fputs("A begins one frame; fresh run directory\n",ready);fclose(ready);
    screen("01 READY\nA: one frame + passive observation\nSTART: exit without rendering.");
    while(aptMainLoop()){
        hidScanInput();u32 keys=hidKeysDown();if(keys&KEY_START)goto finish;
        if(keys&KEY_A){
            int present=draw_frame();gw_close();
            screen("04 RAM WINDOW CLOSED\n05 SAVING OBSERVATION TO SD\nIf stuck here: SD/persistence stage.");log_phase("WINDOW CLOSED; SD SAVE BEGIN");
            path(out,"observation.json");int saved=gw_save(out)==0;
            path(out,"first-frame.pica");int pica=gw_save_pica(out)==0;
            int pixels=present==0 && capture_frame()==0;u32 gpu[4],cpu[4];ds34_stats(gpu);ds22_stats(&ctx,cpu);
            path(out,"result.json");FILE *f=fopen(out,"w");
            if(f){fprintf(f,"{\"version\":\"0.2.0\",\"environment\":\"%s\",\"fault\":%s,\"observation_saved\":%s,\"pica_saved\":%s,\"render_verified\":%s,\"present_return\":%d,\"initial_error_before_End\":%lu,\"GL_error_after_diagnostic_wait\":%lu,\"gpu_draws\":%lu,\"gpu_triangles\":%lu,\"cpu_fragments\":%lu,\"cpu_samples\":%lu,\"layout\":1,\"bytes\":288000,\"game_called\":false,\"GPU_fixed_claimed\":false}\n",
                emulator?"emulator":"native",fault?"true":"false",saved?"true":"false",pica?"true":"false",pixels?"true":"false",present,(unsigned long)error_before_end,(unsigned long)ctx.error,
                (unsigned long)gpu[0],(unsigned long)gpu[1],(unsigned long)cpu[2],(unsigned long)cpu[3]);fclose(f);}
            log_phase("SD SAVE RETURNED");
            const GwData *d=gw_data();const GwSample *s=&d->samples[d->decision];
            screen(saved?"06 OBSERVATION SAVED\nThis is NOT a GPU fix.\nSTART: checked exit.":"06 SAVE FAILED\nPhotograph this screen.");
            printf("PSC0/P3D/PPF: %lu/%lu/%lu\nQ total/sub/done: %lu/%lu/%lu\nIdle:%lu timeout:%lu NB:%lu\nPixel check:%s\n",
                (unsigned long)s->counts[0],(unsigned long)s->counts[1],(unsigned long)s->counts[2],(unsigned long)s->queue.total,(unsigned long)s->queue.submitted,(unsigned long)s->queue.completed,
                (unsigned long)s->idle,(unsigned long)d->window_timeout,(unsigned long)d->nonblock_result,pixels?"OK":"not confirmed");flush_bottom();break;
        }
        flush_bottom();svcSleepThread(16666667);
    }
wait:;
    u32 last_serial=gw_data()->event_committed;int last_idle=gw_idle();unsigned late=0;u64 last_saved=svcGetSystemTick();
    while(aptMainLoop()){
        hidScanInput();if(hidKeysDown()&KEY_START)break;
        u32 serial=__atomic_load_n(&gw_data()->event_committed,__ATOMIC_ACQUIRE);int idle=gw_idle();
        if(journal && late<8 && (serial!=last_serial || idle!=last_idle) && svcGetSystemTick()-last_saved>SYSCLOCK_ARM11/4){
            gw_sample(GW_LATE);char name[48];snprintf(name,sizeof(name),"late-%02u.json",++late);char late_path[192];path(late_path,name);gw_save(late_path);last_serial=serial;last_idle=idle;last_saved=svcGetSystemTick();
        }
        flush_bottom();svcSleepThread(16666667);
    }
finish:
    if(!gw_safe_exit()){printf("GPU busy or completion uncertain.\nMemory retained. START: recheck.\nDo not rerun. Keep this folder.\n");flush_bottom();log_phase("EXIT DEFERRED BUSY OR COMPLETION UNCERTAIN");goto wait;}
    log_phase("EXIT BEGIN");gw_remove();if(gw_has_queue())C3D_Fini();
    log_phase("EXIT GPU DRAINED");
    if(journal){char exit_path[192];path(exit_path,"exit.txt");FILE *f=fopen(exit_path,"w");if(f){fputs("GPU drained; returning to HOME\n",f);fclose(f);}fclose(journal);}gfxExit();return 0;
}
