#ifndef NATIVE_THREAD_PROBE_H
#define NATIVE_THREAD_PROBE_H
#include <stdint.h>
/* Non-owning, synchronized diagnostic snapshot; never used to decide teardown. */
typedef struct {
    uint32_t token,entry,argument,wait_kind,wait_object,done,detached,joining,stack_bytes;
    int32_t kernel_wait;
    uint32_t wait_caller,wait_stack[32];
    uint32_t sleep_seconds,sleep_nanoseconds,sleep_interrupt_returns;
} NativeWorkerProbe;
int32_t ds7_probe_kernel(void *native);
void ds7_probe_workers(NativeWorkerProbe out[17]);
typedef struct {uint32_t callback,object,dso,sequence;} NativeDestructorProbe;
uint32_t ds8_probe_destructors(NativeDestructorProbe out[256]);
int ds7_checkpoint_interrupt(uint32_t token);
#endif
