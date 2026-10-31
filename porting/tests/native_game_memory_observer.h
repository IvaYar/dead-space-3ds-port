/* Allocation observations only: every argument/result/owner is preserved.
 * Counters cover linked external allocation calls; libc-internal transients
 * can evade wrappers. Kernel commit and reserved budgets are separate metrics. */
#ifndef NATIVE_GAME_MEMORY_OBSERVER_H
#define NATIVE_GAME_MEMORY_OBSERVER_H
#include <malloc.h>

static u32 observed_normal_live,observed_normal_footprint,observed_normal_request;
static u32 observed_linear_used,observed_linear_other,observed_linear_request;
static u32 observed_vram_used,observed_vram_request,observed_arena_size;
static void *observed_arena;
static void observe_max(u32 *value,u32 candidate){
    u32 previous=__atomic_load_n(value,__ATOMIC_RELAXED);
    while(previous<candidate && !__atomic_compare_exchange_n(value,&previous,candidate,0,__ATOMIC_RELAXED,__ATOMIC_RELAXED)){}
}
static void observe_normal(size_t request){
    struct mallinfo m=mallinfo();
    observe_max(&observed_normal_live,(u32)m.uordblks);
    observe_max(&observed_normal_footprint,(u32)m.arena);
    observe_max(&observed_normal_request,(u32)request);
}
static void observe_linear(size_t request,void *arena_block){
    if(arena_block){observed_arena=arena_block;observed_arena_size=linearGetSize(arena_block);}
    u32 used=DS_GAME_LINEAR_BYTES-linearSpaceFree();
    observe_max(&observed_linear_used,used);
    if(used>=observed_arena_size)observe_max(&observed_linear_other,used-observed_arena_size);
    if(!arena_block)observe_max(&observed_linear_request,(u32)request);
}
static void observe_vram(size_t request){
    observe_max(&observed_vram_used,6*1024*1024-vramSpaceFree());
    observe_max(&observed_vram_request,(u32)request);
}
void *__real_malloc(size_t);
void *__real_calloc(size_t,size_t);
void *__real_realloc(void *,size_t);
void *__real_memalign(size_t,size_t);
void __real_free(void *);
void *__wrap_malloc(size_t n){void *p=__real_malloc(n);observe_normal(n);return p;}
void *__wrap_calloc(size_t n,size_t s){void *p=__real_calloc(n,s);observe_normal(n*s);return p;}
void *__wrap_realloc(void *p,size_t n){p=__real_realloc(p,n);observe_normal(n);return p;}
void *__wrap_memalign(size_t a,size_t n){void *p=__real_memalign(a,n);observe_normal(n);return p;}
void __wrap_free(void *p){observe_normal(0);__real_free(p);}
void *__real_linearAlloc(size_t);
void *__real_linearMemAlign(size_t,size_t);
void __real_linearFree(void *);
void *__wrap_linearAlloc(size_t n){void *p=__real_linearAlloc(n);observe_linear(n,NULL);return p;}
void *__wrap_linearMemAlign(size_t n,size_t a){
    void *p=__real_linearMemAlign(n,a);
    observe_linear(n,p && n==DS_GAME_ARENA_BYTES && a==4096?p:NULL);return p;
}
void __wrap_linearFree(void *p){observe_linear(0,NULL);__real_linearFree(p);if(p==observed_arena){observed_arena=NULL;observed_arena_size=0;}}
void *__real_vramAlloc(size_t);
void *__real_vramMemAlign(size_t,size_t);
void __real_vramFree(void *);
void *__wrap_vramAlloc(size_t n){void *p=__real_vramAlloc(n);observe_vram(n);return p;}
void *__wrap_vramMemAlign(size_t n,size_t a){void *p=__real_vramMemAlign(n,a);observe_vram(n);return p;}
void __wrap_vramFree(void *p){observe_vram(0);__real_vramFree(p);}
#endif
