/* Single-thread unit boundary. Contention and actual threads are tested in Azahar. */
#include "ds7.h"
#include <stdlib.h>
static DS7TLS local[17];
static int selected;
static int depth,heap_depth;
static unsigned waited;
void ds7_platform_init(void) { depth=heap_depth=selected=0; waited=0; for(int i=0;i<17;++i) { local[i].record=NULL; local[i].error=0; } }
void ds7_gate_lock(void) { if(depth) abort(); ++depth; }
void ds7_gate_unlock(void) { if(depth!=1) abort(); --depth; }
int ds7_test_gate_depth(void) { return depth; }
int *ds7_test_tls_selector_address(void) { return &selected; }
void ds7_platform_yield(void) { }
void ds7_heap_lock(void) { ++heap_depth; }
void ds7_heap_unlock(void) { if(heap_depth<=0) abort(); --heap_depth; }
DS7TLS *ds7_tls(void) { return &local[selected]; }
void ds7_test_select_tls(int which) { selected=which; }
int ds7_cv_wait(int32_t *cv,int64_t timeout) { (void)cv; (void)timeout; ++waited; return 110; }
int ds7_clock_now(DS6Time *out) { out->sec=1000; out->nsec=0; return 0; }
void ds7_cv_wake(int32_t *cv,int all) { (void)cv; (void)all; }
void *ds7_spawn(void (*entry)(void *),void *arg,uint32_t stack) { (void)entry;(void)arg;(void)stack; return NULL; }
int ds7_native_join(void *thread,int64_t timeout) { (void)thread;(void)timeout; return 110; }
void ds7_native_free(void *thread) { (void)thread; }
void ds7_native_exit(void) { abort(); }
void ds7_bad_main_exit(void) { abort(); }
unsigned ds7_test_wait_calls(void) { return waited; }
int ds7_test_heap_depth(void) { return heap_depth; }
