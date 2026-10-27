#include "ds8.h"
#include <string.h>
enum { GUARDS=64, DESTRUCTORS=256 };
typedef struct { uint32_t *address; DS7TLS *owner; } Guard;
typedef void (*Destroy)(void *) DS_IO_SOFT;
typedef struct { Destroy destroy; void *object,*dso; uint32_t sequence; int state; } Destructor;
static Guard guards[GUARDS];
static Destructor destructors[DESTRUCTORS];
static DS8Stats stats;
static uint32_t sequence,dso_token;
static int initialized;
static int32_t guard_cv,finalize_cv;
static DS7TLS *finalizer;
static unsigned finalize_depth;

/* Guard API has no recoverable error result. Invalid recursion/ownership or
 * diagnostic pool exhaustion stops the process instead of skipping a constructor. */
static void fault(void) __attribute__((noreturn));
static void fault(void) { ++stats.failures; ds7_gate_unlock(); ds7_bad_main_exit(); }
static Guard *find_guard(uint32_t *address) {
    for(unsigned i=0;i<GUARDS;++i) if(guards[i].address==address) return &guards[i];
    return NULL;
}
int ds8_init(void) {
    ds7_gate_lock();
    if(stats.active_guards || stats.pending || stats.running || finalize_depth) { ds7_gate_unlock(); return 16; }
    memset(guards,0,sizeof(guards)); memset(destructors,0,sizeof(destructors)); memset(&stats,0,sizeof(stats));
    sequence=0; guard_cv=finalize_cv=0; finalizer=NULL; finalize_depth=0;
    dso_token=(uint32_t)&dso_token; initialized=1; ds7_gate_unlock(); return 0;
}
void DS_IO_SOFT ds8_stats(DS8Stats *out) { ds7_gate_lock(); *out=stats; ds7_gate_unlock(); }
int DS_IO_SOFT ds8_guard_acquire(uint32_t *guard) {
    ds7_gate_lock();
    if(!initialized || !guard || ((uintptr_t)guard&3)) fault();
    ++stats.acquires;
    for(;;) {
        /* ARM guards are four bytes; only bit zero denotes completed initialization.
         * The acquire load pairs with release, including compiler-emitted inline tests. */
        if(__atomic_load_n(guard,__ATOMIC_ACQUIRE)&1) { ds7_gate_unlock(); return 0; }
        Guard *g=find_guard(guard);
        if(!g) {
            for(unsigned i=0;i<GUARDS;++i) if(!guards[i].address) {
                guards[i].address=guard; guards[i].owner=ds7_tls(); ++stats.active_guards;
                ds7_gate_unlock(); return 1;
            }
            fault();
        }
        if(g->owner==ds7_tls()) fault();
        ++stats.waits;
        ds7_cv_wait(&guard_cv,-1);
        /* Re-find after wake: release/abort may recycle the old reservation. */
    }
}
static void finish_guard(uint32_t *guard,int complete) {
    ds7_gate_lock(); Guard *g=guard?find_guard(guard):NULL;
    if(!initialized || !g || g->owner!=ds7_tls()) fault();
    if(complete) { __atomic_fetch_or(guard,1u,__ATOMIC_RELEASE); ++stats.releases; }
    else ++stats.aborts;
    g->address=NULL; g->owner=NULL; --stats.active_guards;
    ds7_cv_wake(&guard_cv,1); ds7_gate_unlock();
}
void DS_IO_SOFT ds8_guard_release(uint32_t *guard) { finish_guard(guard,1); }
void DS_IO_SOFT ds8_guard_abort(uint32_t *guard) { finish_guard(guard,0); }
int DS_IO_SOFT ds8_atexit(Destroy destroy,void *object,void *dso) {
    ds7_gate_lock();
    if(!initialized || !destroy || sequence==UINT32_MAX) {
        ++stats.failures; ds7_gate_unlock(); *ds_io_errno()=22; return -1;
    }
    for(unsigned i=0;i<DESTRUCTORS;++i) if(!destructors[i].state) {
        Destructor *d=&destructors[i]; d->destroy=destroy; d->object=object; d->dso=dso;
        d->sequence=++sequence; d->state=1; ++stats.registered; ++stats.pending;
        ds7_gate_unlock(); return 0;
    }
    ++stats.failures; ds7_gate_unlock(); *ds_io_errno()=12; return -1;
}
int DS_IO_SOFT ds8_aeabi_atexit(void *object,Destroy destroy,void *dso) { return ds8_atexit(destroy,object,dso); }
void DS_IO_SOFT ds8_finalize(void *dso) {
    ds7_gate_lock();
    if(!initialized) fault();
    DS7TLS *self=ds7_tls();
    while(finalizer && finalizer!=self) ds7_cv_wait(&finalize_cv,-1);
    finalizer=self; ++finalize_depth;
    for(;;) {
        Destructor *next=NULL;
        for(unsigned i=0;i<DESTRUCTORS;++i) {
            Destructor *d=&destructors[i];
            if(d->state==1 && (!dso || dso==d->dso) && (!next || d->sequence>next->sequence)) next=d;
        }
        if(!next) break;
        /* Claim before the callback. Nested finalize cannot execute it twice,
         * and registering more destructors from a callback remains possible. */
        next->state=2; --stats.pending; ++stats.running;
        Destroy destroy=next->destroy; void *object=next->object;
        ds7_gate_unlock(); destroy(object); ds7_gate_lock();
        next->state=0; --stats.running; ++stats.called;
    }
    if(!--finalize_depth) { finalizer=NULL; ds7_cv_wake(&finalize_cv,1); }
    ds7_gate_unlock();
}
uint32_t ds8_bindings(DSBinding *out,uint32_t capacity) {
    const DSBinding list[]={
        {"__cxa_guard_acquire",(uint32_t)ds8_guard_acquire},{"__cxa_guard_release",(uint32_t)ds8_guard_release},
        {"__cxa_guard_abort",(uint32_t)ds8_guard_abort},{"__aeabi_atexit",(uint32_t)ds8_aeabi_atexit},
        {"__cxa_atexit",(uint32_t)ds8_atexit},{"__cxa_finalize",(uint32_t)ds8_finalize},
        {"__dso_handle",(uint32_t)&dso_token},{"probe_cpp_stats",(uint32_t)ds8_stats}
    };
    uint32_t count=sizeof(list)/sizeof(list[0]); if(capacity<count) return 0;
    for(uint32_t i=0;i<count;++i) out[i]=list[i];
    return count;
}
