/* CLEAR-only successor of control v0.1.0. Original GPU packets are unchanged. */
#include <3ds.h>
#include <citro3d.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include "citro3d_event_observer.h"

#define ROOT CLEAR_EVENTS_ROOT
#define WAIT_MS 2000u
u32 __stacksize__=256*1024;
static FILE *journal;
static gxCmdQueue_s *queue;
static C3D_RenderTarget *target;
static int initialized,frame_open,emulator,timed_out,completed,io_failed;
static const char *failure="none";
typedef struct {u32 words[8],result,ready;} Submission;
static Submission submissions[8];
static u32 submit_count,printed;
extern void __real_gxCmdQueueRun(gxCmdQueue_s *q);
extern Result __real_gspSubmitGxCommand(const u32 words[8]);
static void mark(const char *phase){if(journal){fprintf(journal,"PHASE ms=%llu vb=%lu,%lu %s\n",
    (unsigned long long)osGetTime(),(unsigned long)C3D_FrameCounter(0),(unsigned long)C3D_FrameCounter(1),phase);fflush(journal);}}
static void checkpoint(const char *phase){
    if(clear_events_checkpoint(phase))io_failed=1;
    u32 end=__atomic_load_n(&submit_count,__ATOMIC_ACQUIRE);
    while(printed<end && printed<8){Submission *s=&submissions[printed];
        if(!__atomic_load_n(&s->ready,__ATOMIC_ACQUIRE))break;
        fprintf(journal,"SUBMIT %lu result=%08lx",(unsigned long)printed,(unsigned long)s->result);
        for(unsigned i=0;i<8;++i)fprintf(journal," %08lx",(unsigned long)s->words[i]);
        fputc('\n',journal);++printed;
    }
    fflush(journal);
}
Result __wrap_gspSubmitGxCommand(const u32 words[8]){
    u32 n=__atomic_fetch_add(&submit_count,1,__ATOMIC_RELAXED);
    if(n<8)memcpy(submissions[n].words,words,32);
    Result rc=__real_gspSubmitGxCommand(words);
    if(n<8){submissions[n].result=(u32)rc;__atomic_store_n(&submissions[n].ready,1,__ATOMIC_RELEASE);}
    return rc;
}
void __wrap_gxCmdQueueRun(gxCmdQueue_s *q){
    queue=q;clear_events_track(q);
    if(q->numEntries)checkpoint("before-submit");
    __real_gxCmdQueueRun(q);
    if(q->numEntries)checkpoint("after-submit");
}
static int fail(const char *reason){failure=reason;mark(reason);checkpoint(timed_out?"timeout":"failure");return -1;}
static int begin_frame(int retire){
    if(frame_open)return 0;
    mark("VBLANK WAIT BEGIN");u32 a=C3D_FrameCounter(0),b=C3D_FrameCounter(1);u64 deadline=osGetTime()+WAIT_MS;
    while(C3D_FrameCounter(0)==a || C3D_FrameCounter(1)==b){
        if(osGetTime()>=deadline){timed_out=1;return fail("VBLANK TIMEOUT");}svcSleepThread(1000000);
    }
    mark("VBLANK WAIT OK");mark("GX WAIT BEGIN");deadline=osGetTime()+WAIT_MS;
    for(;;){
        int injected=0;
#ifdef CLEAR_EVENTS_FAULT
        injected=emulator && retire;
#endif
        (void)retire;
        if(!injected && C3D_FrameBegin(C3D_FRAME_NONBLOCK)){frame_open=1;mark("GX WAIT OK");return 0;}
        if(osGetTime()>=deadline){timed_out=1;return fail("GX QUEUE TIMEOUT");}svcSleepThread(1000000);
    }
}
static int save(const char *name,const void *data,size_t size){
    char path[160];snprintf(path,sizeof(path),ROOT"%s",name);FILE *f=fopen(path,"wb");if(!f)return -1;
    size_t n=fwrite(data,1,size,f);int bad=fclose(f);return n==size && !bad?0:-1;
}
static int near(u16 value,int r,int g,int b){
    int delta[3]={((value>>11)&31)*255/31-r,((value>>5)&63)*255/63-g,(value&31)*255/31-b};
    for(unsigned i=0;i<3;++i)if(delta[i]<-8 || delta[i]>8)return 0;
    return 1;
}
static int run(void){
    mark("C3D INIT BEGIN");if(!C3D_Init(C3D_DEFAULT_CMDBUF_SIZE))return fail("C3D INIT FAILED");initialized=1;mark("C3D INIT OK");
#ifdef CLEAR_EVENTS_FAULT
    if(!emulator || !clear_events_software_selfcheck())return fail("OBSERVER SELFTEST FAILED");
    mark("OBSERVER SOFTWARE SELFTEST PASS; not GPU events");
#endif
    clear_events_install(journal);
    target=C3D_RenderTargetCreate(240,400,GPU_RB_RGB8,GPU_RB_DEPTH24_STENCIL8);if(!target)return fail("TARGET ALLOCATION FAILED");
    u32 flags=GX_TRANSFER_FLIP_VERT(0)|GX_TRANSFER_OUT_TILED(0)|GX_TRANSFER_RAW_COPY(0)|GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGB8)|GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB565)|GX_TRANSFER_SCALING(GX_TRANSFER_SCALE_NO);
    C3D_RenderTargetSetOutput(target,GFX_TOP,GFX_LEFT,flags);
    if(begin_frame(0))return -1;
    u16 w,h;u8 *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);if((u32)w*h*2!=192000)return fail("FRAMEBUFFER SIZE FAILED");
    mark("CLEAR BEGIN");C3D_RenderTargetClear(target,C3D_CLEAR_ALL,0x102030,0);mark("CLEAR QUEUED");
    C3D_FrameDrawOn(target);
    mark("FRAME END BEGIN");C3D_FrameEnd(0);frame_open=0;mark("FRAME END RETURNED");
    if(begin_frame(1))return -1;
    checkpoint("retired");
    mark("READBACK INVALIDATE BEGIN");Result rc=GSPGPU_InvalidateDataCache(pixels,192000);if(R_FAILED(rc))return fail("READBACK INVALIDATE FAILED");
    mark("READBACK INVALIDATE OK");
    for(unsigned i=0;i<192000;i+=2)if(!near((u16)(pixels[i]|pixels[i+1]<<8),16,32,48))return fail("PIXEL CHECK FAILED");
    if(save("clear.raw",pixels,192000))return fail("PIXEL CAPTURE FAILED");
    completed=1;mark("CLEAR PASS");return io_failed?-1:0;
}
static void flush_console(void){u16 w,h;void *p=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,&w,&h);GSPGPU_FlushDataCache(p,(u32)w*h*2);}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);bool newer=false;s64 info=0;emulator=svcGetSystemInfo(&info,0x20000,0)==0;
    printf("CITRO3D CLEAR IRQ v" CLEAR_EVENTS_VERSION "\nCLEAR only. No triangle.\n");
    if(R_FAILED(APT_CheckNew3DS(&newer)) || !newer){printf("New3DS required\n");goto wait;}
#ifdef CLEAR_EVENTS_FAULT
    if(!emulator){printf("Emulator-only fault build\n");goto wait;}
#endif
    gfxSetScreenFormat(GFX_TOP,GSP_RGB565_OES);gfxSwapBuffers();gspWaitForVBlank();
    if((mkdir("sdmc:/3ds",0777) && errno!=EEXIST) || (mkdir(ROOT,0777) && errno!=EEXIST))goto wait;
    if(remove(ROOT"result.json") && errno!=ENOENT)goto wait;
    journal=fopen(ROOT"control.log","w");if(!journal)goto wait;
    fprintf(journal,"CITRO3D CLEAR IRQ v" CLEAR_EVENTS_VERSION " environment=%s\n",emulator?"emulator":"native");fflush(journal);
    if(save("ready.txt","Press A\n",8))goto wait;
    printf("A: one CLEAR\nSTART: checked exit\n");
    while(aptMainLoop()){
        hidScanInput();u32 keys=hidKeysDown();if(keys&KEY_START)goto finish;
        if(keys&KEY_A){int ok=run()==0;if(io_failed)failure="CHECKPOINT IO FAILED";
            checkpoint("result");FILE *f=fopen(ROOT"result.json","w");
            if(f){fprintf(f,"{\"version\":\"" CLEAR_EVENTS_VERSION "\",\"environment\":\"%s\",\"passed\":%s,\"stages_completed\":%d,\"timeout\":%s,\"failure\":\"%s\",\"checkpoint_io_failed\":%s,\"last_checkpoint\":\"%s\",\"ds34_linked\":false,\"triangle_called\":false}\n",
                emulator?"emulator":"native",ok && !io_failed?"true":"false",completed,timed_out?"true":"false",failure,io_failed?"true":"false",clear_events_last_file());fclose(f);}
            printf("CLEAR OBSERVER %s\n",ok && !io_failed?"PASSED":"FAILED");mark("RESULT SAVED");break;}
        flush_console();gspWaitForVBlank();
    }
wait:;
    u64 next_late=0;
    while(aptMainLoop()){
        if(initialized && clear_events_changed() && svcGetSystemTick()>=next_late){checkpoint("late-events");next_late=svcGetSystemTick()+SYSCLOCK_ARM11/4;}
        hidScanInput();if(hidKeysDown()&KEY_START)goto finish;flush_console();svcSleepThread(16666667);
    }
finish:
    if(initialized){checkpoint("exit-precheck");
        if(!frame_open && !C3D_FrameBegin(C3D_FRAME_NONBLOCK)){printf("GX completion pending; memory retained\nSTART: recheck\n");mark("EXIT DEFERRED");goto wait;}
        clear_events_remove();mark("EXIT BEGIN");C3D_Fini();}
    mark("EXIT GPU DRAINED");if(journal)fclose(journal);gfxExit();return 0;
}
