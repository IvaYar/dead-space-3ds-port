#include <3ds.h>
#include <stdlib.h>
#include "ds7.h"
static LightLock state_gate;
static RecursiveLock memory_gate;
static _Thread_local DS7TLS local;
void ds7_platform_init(void) { LightLock_Init(&state_gate); RecursiveLock_Init(&memory_gate); }
void ds7_gate_lock(void) { LightLock_Lock(&state_gate); }
void ds7_gate_unlock(void) { LightLock_Unlock(&state_gate); }
void ds7_platform_yield(void) { svcSleepThread(0); }
void ds7_heap_lock(void) { RecursiveLock_Lock(&memory_gate); }
void ds7_heap_unlock(void) { RecursiveLock_Unlock(&memory_gate); }
DS7TLS *ds7_tls(void) { return &local; }
int ds7_cv_wait(int32_t *cv,int64_t timeout) {
    if(timeout<0) { CondVar_Wait(cv,&state_gate); return 0; }
    return CondVar_WaitTimeout(cv,&state_gate,timeout)?110:0;
}
int ds7_clock_now(DS6Time *out) { return ds6_native_clock(0,out); }
void ds7_cv_wake(int32_t *cv,int all) { CondVar_WakeUp(cv,all?ARBITRATION_SIGNAL_ALL:1); }
typedef struct { Thread thread; Handle handle; } NativeThread;
void *ds7_spawn(void (*entry)(void *),void *arg,uint32_t stack) {
    NativeThread *native=malloc(sizeof(*native));
    if(!native) return NULL;
    /* Android default pthread priority inherits the caller's scheduling class.
     * A fixed lower native priority can starve a worker during donor polling. */
    s32 priority;
    if(R_FAILED(svcGetThreadPriority(&priority,CUR_THREAD_HANDLE))){free(native);return NULL;}
    native->thread=threadCreate(entry,arg,stack,priority,0,false);
    if(!native->thread) { free(native); return NULL; }
    /* Caller holds the state gate. A child cannot finish its TLS teardown until
     * that gate is released, so libctru still exposes its original handle here. */
    native->handle=threadGetHandle(native->thread);
    return native;
}
int ds7_native_join(void *thread,int64_t timeout) {
    /* Require kernel termination, including when libctru's finished flag was
     * set just before svcExitThread. Positive informational results are not completion. */
    NativeThread *native=thread;
    Result result=svcWaitSynchronization(native->handle,timeout<0?U64_MAX:(uint64_t)timeout);
    return result==0?0:110;
}
void ds7_native_free(void *thread) { NativeThread *native=thread; threadFree(native->thread); free(native); }
void ds7_native_exit(void) { threadExit(0); }
void ds7_bad_main_exit(void) { svcBreak(USERBREAK_PANIC); for(;;) svcSleepThread(1000000000); }
