/* Bounded waits for the native fixture only. Production DS34 keeps SDK waits. */
#include <3ds.h>
#include <citro3d.h>
#include "ds34_gpu.h"
#include "gpu_hardware_diag.h"
#include <string.h>

#define WAIT_MS 2000u
static FILE *logfile;
static uint64_t epoch;
static uint32_t sequence,submissions;
static int timed_out,frame_open;
static const char *timeout_phase="none";
#ifdef DS34_DIAGNOSTIC_FAULTS
static char fault[32];
static unsigned exit_checks;
#endif

void ds34_diagnostic_mark(const char *phase){
    if(logfile){
        fprintf(logfile,"PHASE %lu ms=%llu vb=%lu,%lu %s\n",(unsigned long)++sequence,
            (unsigned long long)(osGetTime()-epoch),(unsigned long)C3D_FrameCounter(0),
            (unsigned long)C3D_FrameCounter(1),phase);
        fflush(logfile);
    }
}
void gpu_diag_init(FILE *journal,int emulator){
    logfile=journal;epoch=osGetTime();gpu_queue_init(journal);
    (void)emulator;
#ifdef DS34_DIAGNOSTIC_FAULTS
    /* This seam is absent from the distributable CIA and never active natively. */
    if(emulator){FILE *f=fopen(GPU_HARDWARE_ROOT "diag-fault.txt","r");
        if(f){if(!fgets(fault,sizeof(fault),f))fault[0]=0;fclose(f);fault[strcspn(fault,"\r\n")]=0;}}
    if(fault[0]){fprintf(logfile,"EMULATOR FAULT INJECTION: %s\n",fault);fflush(logfile);}
#endif
    ds34_diagnostic_mark("DIAGNOSTICS READY timeout_ms=2000");
}
static int timeout(const char *phase){
    timed_out=1;timeout_phase=phase;ds34_diagnostic_mark(phase);
    gpu_queue_snapshot("TIMEOUT");
    printf("GPU WAIT TIMEOUT: %s\nLog saved. START: checked exit.\n",phase);return -1;
}
int ds34_diagnostic_sync(void){
    if(timed_out)return -1;
    ds34_diagnostic_mark("VBLANK WAIT BEGIN");
    uint32_t start[2]={C3D_FrameCounter(0),C3D_FrameCounter(1)};
    uint64_t deadline=osGetTime()+WAIT_MS;
    for(;;){
        uint32_t now[2]={C3D_FrameCounter(0),C3D_FrameCounter(1)};
#ifdef DS34_DIAGNOSTIC_FAULTS
        if(!strcmp(fault,"vblank0"))now[0]=start[0];
        if(!strcmp(fault,"vblank1"))now[1]=start[1];
#endif
        if(now[0]!=start[0] && now[1]!=start[1])break;
        if(osGetTime()>=deadline)return timeout("VBLANK WAIT TIMEOUT");
        svcSleepThread(1000000); /* No indefinite gspWaitForAnyEvent. */
    }
    ds34_diagnostic_mark("VBLANK WAIT OK");return 0;
}
int ds34_diagnostic_begin(uint32_t flags){
    if(timed_out)return 0;
    if((flags&C3D_FRAME_SYNCDRAW) && ds34_diagnostic_sync())return 0;
    ds34_diagnostic_mark("GX QUEUE WAIT BEGIN");
    uint64_t deadline=osGetTime()+WAIT_MS;
    for(;;){
        int inject=0;
#ifdef DS34_DIAGNOSTIC_FAULTS
        inject=submissions && !strcmp(fault,"queue-after-submit");
#endif
        /* Never pass SYNCDRAW here: its SDK implementation blocks in FrameSync.
         * Success proves queue completion before the SDK clears the queue. */
        if(!inject && C3D_FrameBegin(C3D_FRAME_NONBLOCK)){frame_open=1;break;}
        if(osGetTime()>=deadline){timeout("GX QUEUE WAIT TIMEOUT");return 0;}
        svcSleepThread(1000000);
    }
    ds34_diagnostic_mark("GX QUEUE WAIT OK");return 1;
}
void ds34_diagnostic_end(void){
    ds34_diagnostic_mark("FRAME END BEGIN");C3D_FrameEnd(0);frame_open=0;++submissions;
    ds34_diagnostic_mark("FRAME END OK");
    gpu_queue_snapshot("FRAME END RETURNED");
}
int gpu_diag_timed_out(void){return timed_out;}
const char *gpu_diag_timeout_phase(void){return timeout_phase;}
int gpu_diag_can_exit(void){
    if(!timed_out || frame_open)return 1;
    ds34_diagnostic_mark("EXIT PRECHECK BEGIN");gpu_queue_snapshot("EXIT PRECHECK");
    /* A timeout is not a GPU completion signal. Keep every allocation alive
     * and do not enter C3D_Fini's unbounded queue wait while GPU remains busy. */
    int inject=0;
#ifdef DS34_DIAGNOSTIC_FAULTS
    inject=!strcmp(fault,"queue-after-submit") && exit_checks++==0;
#endif
    if(!inject && C3D_FrameBegin(C3D_FRAME_NONBLOCK)){
        frame_open=1;ds34_diagnostic_mark("EXIT QUEUE IDLE");return 1;
    }
    ds34_diagnostic_mark("EXIT DEFERRED: GX QUEUE STILL BUSY");return 0;
}
