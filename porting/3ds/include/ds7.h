#ifndef DS7_H
#define DS7_H
#include "ds6.h"
typedef struct { uint32_t flags,stack; uint32_t size,guard; int32_t policy,priority; } DS7Attr;
_Static_assert(sizeof(DS7Attr)==24,"Android ARM pthread_attr_t");
typedef void *(*DS7Start)(void *) DS_IO_SOFT;
typedef void (*DS7Destroy)(void *) DS_IO_SOFT;
typedef struct { int32_t error; void *record; } DS7TLS;
typedef struct { uint32_t active_threads,finished_threads,mutexes,conditions,semaphores,keys; } DS7Stats;
typedef struct {uint32_t token,entry,wait_kind,wait_object;} DS7DebugThread;
/* Diagnostic observations only; no synchronization decisions may use them. */
void ds7_debug_threads(DS7DebugThread out[17]);
/* Native backend owns the one state gate and provides atomic condition waits. */
void ds7_platform_init(void);
void ds7_gate_lock(void);
void ds7_gate_unlock(void);
void ds7_platform_yield(void);
typedef void (*DS7Observe)(uint32_t event,uint32_t thread,uint32_t detail);
void ds7_observer(DS7Observe);
int ds7_cv_wait(int32_t *cv,int64_t timeout);
int ds7_clock_now(DS6Time *out);
void ds7_cv_wake(int32_t *cv,int all);
void ds7_heap_lock(void);
void ds7_heap_unlock(void);
DS7TLS *ds7_tls(void);
void *ds7_spawn(void (*entry)(void *),void *arg,uint32_t stack);
int ds7_native_join(void *thread,int64_t timeout);
void ds7_native_free(void *thread);
void ds7_native_exit(void) __attribute__((noreturn));
void ds7_bad_main_exit(void) __attribute__((noreturn));
int ds7_init(void);
/* Returns live threads after bounded joins. Never unload module if nonzero. */
uint32_t ds7_shutdown(int64_t timeout_ns);
void ds7_stats(DS7Stats *out);
uint32_t ds7_bindings(DSBinding *out,uint32_t capacity);
int DS_IO_SOFT ds7_probe_wait_thread(uint32_t id,int32_t milliseconds);
#endif
