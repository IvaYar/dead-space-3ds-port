#include "ds7.h"
#include <string.h>
enum { THREADS=16, MUTEXES=64, CONDITIONS=32, SEMAPHORES=32, KEYS=32 };
typedef struct { uint32_t token; int used,done,detached,joining; void *native,*result,*argument; DS7Start entry; DS7Attr attr; void *values[KEYS]; uint32_t generations[KEYS]; } Worker;
typedef struct { uint32_t *object,owner,depth; int kind,waiters; int32_t cv; } Mutex;
typedef struct { uint32_t *object; int waiters; int32_t cv; } Condition;
typedef struct { uint32_t *object,value; int waiters; int32_t cv; } Semaphore;
typedef struct { int used; uint32_t generation; DS7Destroy destructor; } Key;
static Worker workers[THREADS+1];
static Mutex mutexes[MUTEXES];
static Condition conditions[CONDITIONS];
static Semaphore semaphores[SEMAPHORES];
static Key keys[KEYS];
static uint32_t serial;
static int stopping;
static int initialized;
static int unlock_result(int result) { ds7_gate_unlock(); return result; }
static int32_t *thread_errno(void) { return &ds7_tls()->error; }
static Worker *current(void) { return ds7_tls()->record; }
static uint32_t identity(void) { Worker *w=current(); return w?w->token:0; }
static Worker *find_worker(uint32_t id) {
    uint32_t slot=id&255;
    if(slot>THREADS || !workers[slot].used || workers[slot].token!=id) return NULL;
    return &workers[slot];
}
static int valid_attr(const DS7Attr *attr) {
    return attr && attr->size>=8192 && attr->size<=4*1024*1024 && !(attr->size&4095) &&
           !attr->stack && !(attr->flags&~1u) && !attr->policy && !attr->priority;
}
static int DS_IO_SOFT attr_init(DS7Attr *attr) {
    if(!attr) return 22;
    DS7Attr value={0,0,256*1024,0,0,0}; *attr=value; return 0;
}
static int DS_IO_SOFT attr_destroy(DS7Attr *attr) { if(!attr) return 22; memset(attr,0,sizeof(*attr)); return 0; }
static int DS_IO_SOFT attr_detach(DS7Attr *attr,int state) {
    if(!attr || (state!=0 && state!=1)) return 22;
    attr->flags=(attr->flags&~1u)|(uint32_t)state; return 0;
}
static int DS_IO_SOFT attr_stack_size(DS7Attr *attr,size_t size) {
    if(!attr || size<8192 || size>4*1024*1024 || (size&4095)) return 22;
    attr->size=size; return 0;
}
static int DS_IO_SOFT attr_get_stack(const DS7Attr *attr,void **base,size_t *size) {
    if(!attr || !base || !size) return 22;
    *base=(void *)attr->stack; *size=attr->size; return 0;
}
static int DS_IO_SOFT attr_priority(DS7Attr *attr,const int32_t *priority) {
    if(!attr || !priority || *priority!=0) return 22;
    attr->priority=0; return 0;
}
static int DS_IO_SOFT mutexattr_init(int32_t *attr) { if(!attr) return 22; *attr=0; return 0; }
static int DS_IO_SOFT mutexattr_destroy(int32_t *attr) { if(!attr) return 22; *attr=-1; return 0; }
static int DS_IO_SOFT mutexattr_type(int32_t *attr,int type) {
    if(!attr || type<0 || type>2) return 22;
    *attr=(*attr&~15)|type; return 0;
}
static int DS_IO_SOFT mutexattr_shared(int32_t *attr,int shared) {
    if(!attr || (shared!=0 && shared!=1)) return 22;
    if(shared) return 95;
    *attr&=~16; return 0;
}
static Mutex *get_mutex(uint32_t *object,int lazy) {
    if(!object) return NULL;
    uint32_t tag=*object;
    if((tag&0xffffff00u)==0xd7100000u) {
        unsigned index=(tag&255)-1;
        return index<MUTEXES && mutexes[index].object==object?&mutexes[index]:NULL;
    }
    if(!lazy || (tag!=0 && tag!=0x4000 && tag!=0x8000)) return NULL;
    for(int i=0;i<MUTEXES;++i) if(!mutexes[i].object) {
        Mutex *m=&mutexes[i]; memset(m,0,sizeof(*m)); m->object=object; m->kind=(int)(tag>>14);
        *object=0xd7100000u+(uint32_t)i+1; return m;
    }
    return NULL;
}
static int DS_IO_SOFT mutex_init(uint32_t *object,const int32_t *attr) {
    if(!object) return 22;
    int value=attr?*attr:0;
    if(value&16) return 95;
    if(value<0 || (value&15)>2 || (value&~31)) return 22;
    ds7_gate_lock();
    for(int i=0;i<MUTEXES;++i) if(mutexes[i].object==object) return unlock_result(16);
    *object=(uint32_t)(value&15)<<14;
    return unlock_result(get_mutex(object,1)?0:11);
}
static int DS_IO_SOFT mutex_destroy(uint32_t *object) {
    if(!object) return 22;
    ds7_gate_lock(); Mutex *m=get_mutex(object,1);
    if(!m) return unlock_result(22);
    if(m->depth || m->waiters) return unlock_result(16);
    m->object=NULL; *object=0xdead10cc; return unlock_result(0);
}
static int lock_mutex(Mutex *m,int try_only) {
    uint32_t self=identity(); if(!self) return 3;
    if(m->owner==self && m->depth) {
        if(m->kind==1) { if(m->depth==UINT32_MAX) return 11; ++m->depth; return 0; }
        if(try_only) return 16;
        if(m->kind==2) return 35;
    }
    while(m->depth) {
        if(try_only) return 16;
        ++m->waiters; ds7_cv_wait(&m->cv,-1); --m->waiters;
    }
    m->owner=self; m->depth=1; return 0;
}
static int mutex_lock_common(uint32_t *object,int try_only) {
    ds7_gate_lock(); Mutex *m=get_mutex(object,1);
    return unlock_result(m?lock_mutex(m,try_only):22);
}
static int DS_IO_SOFT mutex_lock(uint32_t *object) { return mutex_lock_common(object,0); }
static int DS_IO_SOFT mutex_trylock(uint32_t *object) { return mutex_lock_common(object,1); }
static int release_mutex(Mutex *m) {
    if(!m->depth || m->owner!=identity()) return 1;
    if(!--m->depth) { m->owner=0; ds7_cv_wake(&m->cv,1); }
    return 0;
}
static int DS_IO_SOFT mutex_unlock(uint32_t *object) {
    ds7_gate_lock(); Mutex *m=get_mutex(object,0); return unlock_result(m?release_mutex(m):22);
}
static Condition *get_condition(uint32_t *object,int lazy) {
    if(!object) return NULL;
    uint32_t tag=*object;
    if((tag&0xffffff00u)==0xd7200000u) {
        unsigned index=(tag&255)-1;
        return index<CONDITIONS && conditions[index].object==object?&conditions[index]:NULL;
    }
    if(!lazy || tag) return NULL;
    for(int i=0;i<CONDITIONS;++i) if(!conditions[i].object) {
        Condition *c=&conditions[i]; memset(c,0,sizeof(*c)); c->object=object;
        *object=0xd7200000u+(uint32_t)i+1; return c;
    }
    return NULL;
}
static int DS_IO_SOFT cond_init(uint32_t *object,const int32_t *attr) {
    if(!object) return 22;
    if(attr && *attr) return 95;
    ds7_gate_lock();
    for(int i=0;i<CONDITIONS;++i) if(conditions[i].object==object) return unlock_result(16);
    *object=0; return unlock_result(get_condition(object,1)?0:11);
}
static int DS_IO_SOFT cond_destroy(uint32_t *object) {
    ds7_gate_lock(); Condition *c=get_condition(object,1);
    if(!c) return unlock_result(22);
    if(c->waiters) return unlock_result(16);
    c->object=NULL; *object=0xdead10cc; return unlock_result(0);
}
static int condition_signal(uint32_t *object,int all) {
    ds7_gate_lock(); Condition *c=get_condition(object,1);
    if(!c) return unlock_result(22);
    ds7_cv_wake(&c->cv,all); return unlock_result(0);
}
static int DS_IO_SOFT cond_signal(uint32_t *object) { return condition_signal(object,0); }
static int DS_IO_SOFT cond_broadcast(uint32_t *object) { return condition_signal(object,1); }
static int64_t time_left(const DS6Time *absolute) {
    DS6Time now;
    if(ds7_clock_now(&now)) return -2;
    int64_t left=((int64_t)absolute->sec-now.sec)*INT64_C(1000000000)+absolute->nsec-now.nsec;
    return left>0?left:0;
}
static int condition_wait(uint32_t *object,uint32_t *mutex,const DS6Time *absolute) {
    if(absolute && (absolute->nsec<0 || absolute->nsec>=1000000000)) return 22;
    ds7_gate_lock(); Condition *c=get_condition(object,1); Mutex *m=get_mutex(mutex,0);
    if(!c || !m) return unlock_result(22);
    if(m->owner!=identity() || m->depth!=1) return unlock_result(1);
    ++c->waiters; ++m->waiters; release_mutex(m);
    int64_t left=absolute?time_left(absolute):-1;
    int result=left==-2?5:!left?110:ds7_cv_wait(&c->cv,left);
    int restored=lock_mutex(m,0); --c->waiters; --m->waiters;
    return unlock_result(restored?restored:result);
}
static int DS_IO_SOFT cond_wait(uint32_t *c,uint32_t *m) { return condition_wait(c,m,NULL); }
static int DS_IO_SOFT cond_timedwait(uint32_t *c,uint32_t *m,const DS6Time *t) { return t?condition_wait(c,m,t):22; }
static Semaphore *get_semaphore(uint32_t *object) {
    if(!object || (*object&0xffffff00u)!=0xd7300000u) return NULL;
    unsigned index=(*object&255)-1;
    return index<SEMAPHORES && semaphores[index].object==object?&semaphores[index]:NULL;
}
static int sem_result(int error) { if(error) *ds_io_errno()=error; return error?-1:0; }
static int DS_IO_SOFT sem_init(uint32_t *object,int shared,unsigned value) {
    if(!object || value>INT32_MAX) return sem_result(22);
    if(shared) return sem_result(95);
    ds7_gate_lock();
    for(int i=0;i<SEMAPHORES;++i) if(semaphores[i].object==object) { ds7_gate_unlock(); return sem_result(16); }
    for(int i=0;i<SEMAPHORES;++i) if(!semaphores[i].object) {
        Semaphore *s=&semaphores[i]; memset(s,0,sizeof(*s)); s->object=object; s->value=value;
        *object=0xd7300000u+(uint32_t)i+1; ds7_gate_unlock(); return 0;
    }
    ds7_gate_unlock(); return sem_result(28);
}
static int DS_IO_SOFT sem_destroy(uint32_t *object) {
    ds7_gate_lock(); Semaphore *s=get_semaphore(object);
    int result=!s?22:s->waiters?16:0;
    if(!result) { s->object=NULL; *object=0xdead10cc; }
    ds7_gate_unlock(); return sem_result(result);
}
static int DS_IO_SOFT sem_getvalue(uint32_t *object,int *value) {
    if(!value) return sem_result(22);
    ds7_gate_lock(); Semaphore *s=get_semaphore(object); int result=s?0:22;
    if(s) *value=(int)s->value;
    ds7_gate_unlock(); return sem_result(result);
}
static int DS_IO_SOFT sem_post(uint32_t *object) {
    ds7_gate_lock(); Semaphore *s=get_semaphore(object); int result=!s?22:s->value==INT32_MAX?75:0;
    if(!result) { ++s->value; ds7_cv_wake(&s->cv,0); }
    ds7_gate_unlock(); return sem_result(result);
}
static int semaphore_wait(uint32_t *object,int try_only,const DS6Time *absolute) {
    if(absolute && (absolute->nsec<0 || absolute->nsec>=1000000000)) return sem_result(22);
    ds7_gate_lock(); Semaphore *s=get_semaphore(object); int result=0;
    if(!s) result=22;
    while(!result && !s->value) {
        if(try_only) { result=11; break; }
        int64_t left=absolute?time_left(absolute):-1;
        if(left==-2 || !left) { result=left==-2?5:110; break; }
        ++s->waiters; int waited=ds7_cv_wait(&s->cv,left); --s->waiters;
        if(waited && !s->value) result=waited;
    }
    if(!result) --s->value;
    ds7_gate_unlock(); return sem_result(result);
}
static int DS_IO_SOFT sem_wait(uint32_t *s) { return semaphore_wait(s,0,NULL); }
static int DS_IO_SOFT sem_trywait(uint32_t *s) { return semaphore_wait(s,1,NULL); }
static int DS_IO_SOFT sem_timedwait(uint32_t *s,const DS6Time *t) { return t?semaphore_wait(s,0,t):sem_result(22); }
static int DS_IO_SOFT key_create(uint32_t *id,DS7Destroy destructor) {
    if(!id) return 22;
    ds7_gate_lock();
    for(unsigned i=0;i<KEYS;++i) if(!keys[i].used) {
        Key *key=&keys[i]; key->generation=key->generation%0x7fffff+1; key->used=1; key->destructor=destructor;
        *id=(key->generation<<8)|i; return unlock_result(0);
    }
    return unlock_result(11);
}
static Key *get_key(uint32_t id) {
    unsigned i=id&255;
    return i<KEYS && keys[i].used && keys[i].generation==(id>>8)?&keys[i]:NULL;
}
static int DS_IO_SOFT key_delete(uint32_t id) {
    ds7_gate_lock(); Key *key=get_key(id);
    if(!key) return unlock_result(22);
    key->used=0; key->destructor=NULL; return unlock_result(0);
}
static int DS_IO_SOFT setspecific(uint32_t id,const void *value) {
    ds7_gate_lock(); Key *key=get_key(id); Worker *w=current();
    if(!key || !w) return unlock_result(22);
    w->values[id&255]=(void *)value; w->generations[id&255]=key->generation; return unlock_result(0);
}
static void *DS_IO_SOFT getspecific(uint32_t id) {
    ds7_gate_lock(); Key *key=get_key(id); Worker *w=current();
    void *value=key && w && w->generations[id&255]==key->generation?w->values[id&255]:NULL;
    ds7_gate_unlock(); return value;
}
static void finish(void *value) __attribute__((noreturn));
static void finish(void *value) {
    Worker *w=current(); if(!w || w==&workers[0]) ds7_bad_main_exit();
    for(int pass=0;pass<4;++pass) {
        int called=0;
        for(unsigned i=0;i<KEYS;++i) {
            ds7_gate_lock(); Key *key=&keys[i];
            DS7Destroy destructor=key->used && key->generation==w->generations[i]?key->destructor:NULL;
            void *item=destructor?w->values[i]:NULL; if(item) w->values[i]=NULL;
            ds7_gate_unlock();
            if(item) { called=1; destructor(item); }
        }
        if(!called) break;
    }
    ds7_gate_lock(); w->result=value; w->done=1; ds7_gate_unlock(); ds7_native_exit();
}
static void worker_begin(void *pointer) { Worker *w=pointer; ds7_tls()->record=w; ds7_tls()->error=0; finish(w->entry(w->argument)); }
static int reap_detached(void) {
    int count=0;
    for(int i=1;i<=THREADS;++i) {
        Worker *w=&workers[i];
        if(w->used && w->detached && w->done && !w->joining && !ds7_native_join(w->native,0)) {
            ds7_native_free(w->native); w->used=0; ++count;
        }
    }
    return count;
}
static int DS_IO_SOFT thread_create(uint32_t *id,const DS7Attr *requested,DS7Start entry,void *argument) {
    if(!id || !entry) return 22;
    DS7Attr attr; if(requested) attr=*requested; else attr_init(&attr);
    if(!valid_attr(&attr)) return 22;
    ds7_gate_lock();
    if(stopping) return unlock_result(11);
    reap_detached();
    for(unsigned i=1;i<=THREADS;++i) if(!workers[i].used) {
        Worker *w=&workers[i]; memset(w,0,sizeof(*w)); w->used=1; w->token=((++serial)<<8)|i;
        w->entry=entry; w->argument=argument; w->attr=attr; w->detached=(int)(attr.flags&1);
        w->native=ds7_spawn(worker_begin,w,attr.size);
        if(!w->native) { w->used=0; return unlock_result(11); }
        *id=w->token; return unlock_result(0);
    }
    return unlock_result(11);
}
static uint32_t DS_IO_SOFT thread_self(void) { return identity(); }
static void DS_IO_SOFT thread_exit(void *value) { finish(value); }
static int DS_IO_SOFT thread_join(uint32_t id,void **value) {
    if(id==identity()) return 35;
    ds7_gate_lock(); Worker *w=find_worker(id);
    if(!w) return unlock_result(3);
    if(w==&workers[0] || w->detached || w->joining) return unlock_result(22);
    w->joining=1; void *native=w->native; ds7_gate_unlock();
    int result=ds7_native_join(native,-1);
    ds7_gate_lock(); w->joining=0;
    if(!result) { if(value) *value=w->result; ds7_native_free(native); w->used=0; }
    return unlock_result(result);
}
static int DS_IO_SOFT thread_detach(uint32_t id) {
    ds7_gate_lock(); Worker *w=find_worker(id);
    if(!w) return unlock_result(3);
    if(w==&workers[0] || w->detached || w->joining) return unlock_result(22);
    w->detached=1; reap_detached(); return unlock_result(0);
}
static int DS_IO_SOFT thread_getsched(uint32_t id,int *policy,int *priority) {
    if(!policy || !priority) return 22;
    ds7_gate_lock(); Worker *w=find_worker(id);
    if(!w) return unlock_result(3);
    *policy=0; *priority=0; return unlock_result(0);
}
static int DS_IO_SOFT thread_setsched(uint32_t id,int policy,const int *priority) {
    if(!priority) return 22;
    if(policy!=0) return 95;
    if(*priority) return 22;
    ds7_gate_lock(); return unlock_result(find_worker(id)?0:3);
}
int DS_IO_SOFT ds7_probe_wait_thread(uint32_t id,int32_t milliseconds) {
    if(milliseconds<0 || id==identity()) return 22;
    ds7_gate_lock(); Worker *w=find_worker(id);
    if(!w || w==&workers[0]) return unlock_result(3);
    if(w->joining) return unlock_result(22);
    w->joining=1; void *native=w->native; ds7_gate_unlock();
    int result=ds7_native_join(native,(int64_t)milliseconds*1000000);
    ds7_gate_lock(); w->joining=0; return unlock_result(result);
}
int ds7_init(void) {
    if(initialized) {
        ds7_gate_lock();
        for(int i=1;i<=THREADS;++i) if(workers[i].used) return unlock_result(16);
        ds7_gate_unlock();
    }
    ds7_platform_init();
    memset(workers,0,sizeof(workers)); memset(mutexes,0,sizeof(mutexes)); memset(conditions,0,sizeof(conditions));
    memset(semaphores,0,sizeof(semaphores)); memset(keys,0,sizeof(keys));
    stopping=0;
    workers[0].used=1; workers[0].token=((++serial)<<8); attr_init(&workers[0].attr);
    initialized=1;
    ds7_tls()->record=&workers[0]; ds7_tls()->error=0;
    ds_io_set_errno_provider(thread_errno); ds_runtime_set_lock(ds7_heap_lock,ds7_heap_unlock); return 0;
}
uint32_t ds7_shutdown(int64_t timeout_ns) {
    uint32_t live=0;
    ds7_gate_lock(); stopping=1; ds7_gate_unlock();
    for(int i=1;i<=THREADS;++i) {
        ds7_gate_lock(); Worker *w=&workers[i];
        void *native=w->used && !w->joining?w->native:NULL;
        if(native) w->joining=1; /* Exclude join/detach/reaping while this handle is borrowed. */
        ds7_gate_unlock();
        if(!native) continue;
        int result=ds7_native_join(native,timeout_ns);
        ds7_gate_lock();
        if(!result) { ds7_native_free(native); w->used=0; }
        w->joining=0; ds7_gate_unlock();
    }
    ds7_gate_lock(); for(int i=1;i<=THREADS;++i) live+=workers[i].used!=0; ds7_gate_unlock();
    if(!live) { ds_runtime_set_lock(NULL,NULL); ds_io_set_errno_provider(NULL); ds7_tls()->record=NULL; }
    return live;
}
void ds7_stats(DS7Stats *out) {
    memset(out,0,sizeof(*out)); ds7_gate_lock(); reap_detached();
    for(int i=1;i<=THREADS;++i) if(workers[i].used) { if(workers[i].done) ++out->finished_threads; else ++out->active_threads; }
    for(int i=0;i<MUTEXES;++i) out->mutexes+=mutexes[i].object!=NULL;
    for(int i=0;i<CONDITIONS;++i) out->conditions+=conditions[i].object!=NULL;
    for(int i=0;i<SEMAPHORES;++i) out->semaphores+=semaphores[i].object!=NULL;
    for(int i=0;i<KEYS;++i) out->keys+=keys[i].used!=0;
    ds7_gate_unlock();
}
uint32_t ds7_bindings(DSBinding *out,uint32_t capacity) {
    const DSBinding list[]={
        {"pthread_attr_init",(uint32_t)attr_init},{"pthread_attr_destroy",(uint32_t)attr_destroy},
        {"pthread_attr_setdetachstate",(uint32_t)attr_detach},{"pthread_attr_setstacksize",(uint32_t)attr_stack_size},
        {"pthread_attr_getstack",(uint32_t)attr_get_stack},{"pthread_attr_setschedparam",(uint32_t)attr_priority},
        {"pthread_mutexattr_init",(uint32_t)mutexattr_init},{"pthread_mutexattr_destroy",(uint32_t)mutexattr_destroy},
        {"pthread_mutexattr_settype",(uint32_t)mutexattr_type},{"pthread_mutexattr_setpshared",(uint32_t)mutexattr_shared},
        {"pthread_mutex_init",(uint32_t)mutex_init},{"pthread_mutex_destroy",(uint32_t)mutex_destroy},
        {"pthread_mutex_lock",(uint32_t)mutex_lock},{"pthread_mutex_trylock",(uint32_t)mutex_trylock},{"pthread_mutex_unlock",(uint32_t)mutex_unlock},
        {"pthread_cond_init",(uint32_t)cond_init},{"pthread_cond_destroy",(uint32_t)cond_destroy},
        {"pthread_cond_signal",(uint32_t)cond_signal},{"pthread_cond_broadcast",(uint32_t)cond_broadcast},
        {"pthread_cond_wait",(uint32_t)cond_wait},{"pthread_cond_timedwait",(uint32_t)cond_timedwait},
        {"pthread_create",(uint32_t)thread_create},{"pthread_self",(uint32_t)thread_self},{"pthread_exit",(uint32_t)thread_exit},
        {"pthread_join",(uint32_t)thread_join},{"pthread_detach",(uint32_t)thread_detach},
        {"pthread_getschedparam",(uint32_t)thread_getsched},{"pthread_setschedparam",(uint32_t)thread_setsched},
        {"pthread_key_create",(uint32_t)key_create},{"pthread_key_delete",(uint32_t)key_delete},
        {"pthread_getspecific",(uint32_t)getspecific},{"pthread_setspecific",(uint32_t)setspecific},
        {"sem_init",(uint32_t)sem_init},{"sem_destroy",(uint32_t)sem_destroy},{"sem_getvalue",(uint32_t)sem_getvalue},
        {"sem_post",(uint32_t)sem_post},{"sem_wait",(uint32_t)sem_wait},{"sem_trywait",(uint32_t)sem_trywait},{"sem_timedwait",(uint32_t)sem_timedwait},
        {"probe_wait_thread",(uint32_t)ds7_probe_wait_thread}
    };
    uint32_t count=sizeof(list)/sizeof(list[0]); if(capacity<count) return 0;
    for(uint32_t i=0;i<count;++i) out[i]=list[i];
    return count;
}
