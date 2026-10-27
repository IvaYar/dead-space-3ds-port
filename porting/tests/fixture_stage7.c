/* Original Android ARM softfp thread/synchronization test; no EA code. */
#include "ds7.h"
#define DECL(ret,name,args) extern ret name args
DECL(int,pthread_attr_init,(DS7Attr *)); DECL(int,pthread_attr_destroy,(DS7Attr *));
DECL(int,pthread_attr_setdetachstate,(DS7Attr *,int)); DECL(int,pthread_attr_setstacksize,(DS7Attr *,size_t));
DECL(int,pthread_attr_getstack,(const DS7Attr *,void **,size_t *)); DECL(int,pthread_attr_setschedparam,(DS7Attr *,const int *));
DECL(int,pthread_mutexattr_init,(int *)); DECL(int,pthread_mutexattr_destroy,(int *));
DECL(int,pthread_mutexattr_settype,(int *,int)); DECL(int,pthread_mutexattr_setpshared,(int *,int));
DECL(int,pthread_mutex_init,(uint32_t *,const int *)); DECL(int,pthread_mutex_destroy,(uint32_t *));
DECL(int,pthread_mutex_lock,(uint32_t *)); DECL(int,pthread_mutex_trylock,(uint32_t *)); DECL(int,pthread_mutex_unlock,(uint32_t *));
DECL(int,pthread_cond_init,(uint32_t *,const int *)); DECL(int,pthread_cond_destroy,(uint32_t *));
DECL(int,pthread_cond_signal,(uint32_t *)); DECL(int,pthread_cond_broadcast,(uint32_t *));
DECL(int,pthread_cond_wait,(uint32_t *,uint32_t *)); DECL(int,pthread_cond_timedwait,(uint32_t *,uint32_t *,const DS6Time *));
DECL(int,pthread_create,(uint32_t *,const DS7Attr *,DS7Start,void *)); DECL(uint32_t,pthread_self,(void));
DECL(void,pthread_exit,(void *)) __attribute__((noreturn)); DECL(int,pthread_join,(uint32_t,void **)); DECL(int,pthread_detach,(uint32_t));
DECL(int,pthread_getschedparam,(uint32_t,int *,int *)); DECL(int,pthread_setschedparam,(uint32_t,int,const int *));
DECL(int,pthread_key_create,(uint32_t *,DS7Destroy)); DECL(int,pthread_key_delete,(uint32_t));
DECL(void *,pthread_getspecific,(uint32_t)); DECL(int,pthread_setspecific,(uint32_t,const void *));
DECL(int,sem_init,(uint32_t *,int,unsigned)); DECL(int,sem_destroy,(uint32_t *)); DECL(int,sem_getvalue,(uint32_t *,int *));
DECL(int,sem_post,(uint32_t *)); DECL(int,sem_wait,(uint32_t *)); DECL(int,sem_trywait,(uint32_t *)); DECL(int,sem_timedwait,(uint32_t *,const DS6Time *));
DECL(int,probe_wait_thread,(uint32_t,int32_t)); DECL(int *,__errno,(void));
DECL(void *,malloc,(size_t)); DECL(void,free,(void *)); DECL(void *,memset,(void *,int,size_t));
DECL(float,sqrtf,(float)); DECL(int,clock_gettime,(int,DS6Time *)); DECL(int,usleep,(unsigned));
static volatile int constructor_marker=42;
__attribute__((constructor)) static void must_not_run(void) { constructor_marker=99; }
static uint32_t recursive=0x4000,errorcheck,mutex,condition,ready,done,key;
static uint32_t worker_ids[2],worker_errors[2],destructor_calls[2];
static int start,counter;
static void DS_IO_SOFT destructor(void *value) {
    unsigned index=(unsigned)value-1;
    if(index>=2) return;
    if(pthread_self()!=worker_ids[index]) worker_errors[index]|=32;
    void *block=malloc(8); if(!block) worker_errors[index]|=64; else free(block);
    ++destructor_calls[index];
    if(destructor_calls[index]==1) pthread_setspecific(key,value);
}
static void *DS_IO_SOFT worker(void *value) {
    unsigned index=(unsigned)value-1;
    worker_ids[index]=pthread_self();
    if(pthread_getspecific(key)) worker_errors[index]|=1;
    pthread_setspecific(key,value); *__errno()=100+(int)index;
    pthread_mutex_lock(&mutex); sem_post(&ready);
    while(!start) if(pthread_cond_wait(&condition,&mutex)) worker_errors[index]|=2;
    pthread_mutex_unlock(&mutex);
    for(int i=0;i<500;++i) {
        unsigned char *block=malloc(64);
        if(!block) worker_errors[index]|=4;
        else { memset(block,(int)index+17,64); if(block[0]!=index+17 || block[63]!=index+17) worker_errors[index]|=4; free(block); }
        if(sqrtf(2.25f)!=1.5f || *__errno()!=100+(int)index) worker_errors[index]|=8;
        pthread_mutex_lock(&mutex); ++counter; if(!(i&63)) usleep(0); pthread_mutex_unlock(&mutex);
        if(!(i&31)) usleep(0);
    }
    if(pthread_getspecific(key)!=value) worker_errors[index]|=16;
    sem_post(&done);
    if(index) pthread_exit((void *)0x202);
    return (void *)0x201;
}
static void *DS_IO_SOFT short_worker(void *value) { sem_post(&done); return value; }
static DS6Time deadline(void) { DS6Time now={0,0}; clock_gettime(0,&now); now.sec+=5; return now; }
int probe_threads(uint32_t *out) {
    int check=0,failed=0,priority=0,policy=-1,attribute=0,value=0;
    DS7Attr attr; void *base=NULL,*result=NULL; size_t size=0;
    uint32_t ids[2]={0},detached=0; DS6Time past={0,0};
#define CHECK(condition_) do { ++check; if(!(condition_)) { failed=check; goto finish; } } while(0)
    CHECK(sizeof(DS7Attr)==24 && constructor_marker==42 && pthread_self()!=0);
    CHECK(!pthread_attr_init(&attr) && !pthread_attr_setstacksize(&attr,65536));
    CHECK(!pthread_attr_getstack(&attr,&base,&size) && !base && size==65536);
    CHECK(pthread_attr_setstacksize(&attr,8193)==22 && !pthread_attr_setschedparam(&attr,&priority));
    CHECK(!pthread_getschedparam(pthread_self(),&policy,&priority) && !policy && !priority);
    CHECK(!pthread_setschedparam(pthread_self(),0,&priority));
    CHECK(!pthread_mutex_lock(&recursive) && !pthread_mutex_lock(&recursive));
    CHECK(!pthread_mutex_unlock(&recursive) && !pthread_mutex_unlock(&recursive) && !pthread_mutex_destroy(&recursive));
    CHECK(!pthread_mutexattr_init(&attribute) && !pthread_mutexattr_settype(&attribute,2));
    CHECK(pthread_mutexattr_setpshared(&attribute,1)==95 && !pthread_mutex_init(&errorcheck,&attribute));
    CHECK(!pthread_mutex_lock(&errorcheck) && pthread_mutex_lock(&errorcheck)==35 && pthread_mutex_trylock(&errorcheck)==16);
    CHECK(pthread_mutex_destroy(&errorcheck)==16 && !pthread_mutex_unlock(&errorcheck) && !pthread_mutex_destroy(&errorcheck));
    CHECK(!pthread_mutexattr_destroy(&attribute) && !pthread_mutex_init(&mutex,NULL) && !pthread_cond_init(&condition,NULL));
    CHECK(!pthread_mutex_lock(&mutex) && pthread_cond_timedwait(&condition,&mutex,&past)==110);
    CHECK(pthread_mutex_trylock(&mutex)==16 && !pthread_mutex_unlock(&mutex));
    CHECK(!sem_init(&ready,0,0) && !sem_init(&done,0,0));
    CHECK(sem_trywait(&ready)==-1 && *__errno()==11);
    CHECK(sem_timedwait(&ready,&past)==-1 && *__errno()==110);
    CHECK(!sem_post(&ready) && !sem_getvalue(&ready,&value) && value==1 && !sem_wait(&ready));
    CHECK(!pthread_key_create(&key,destructor) && !pthread_setspecific(key,(void *)0xabc));
    *__errno()=31337;
    CHECK(!pthread_create(&ids[0],&attr,worker,(void *)1) && !pthread_create(&ids[1],&attr,worker,(void *)2));
    DS6Time until=deadline();
    CHECK(!sem_timedwait(&ready,&until) && !sem_timedwait(&ready,&until));
    CHECK(!pthread_mutex_lock(&mutex) && !pthread_cond_signal(&condition));
    start=1; CHECK(!pthread_cond_broadcast(&condition) && !pthread_mutex_unlock(&mutex));
    until=deadline(); CHECK(!sem_timedwait(&done,&until) && !sem_timedwait(&done,&until));
    CHECK(!probe_wait_thread(ids[0],5000) && !probe_wait_thread(ids[1],5000));
    CHECK(!pthread_join(ids[0],&result) && result==(void *)0x201);
    CHECK(!pthread_join(ids[1],&result) && result==(void *)0x202);
    CHECK(counter==1000 && !worker_errors[0] && !worker_errors[1]);
    CHECK(destructor_calls[0]==2 && destructor_calls[1]==2 && worker_ids[0]!=worker_ids[1]);
    CHECK(*__errno()==31337 && pthread_getspecific(key)==(void *)0xabc);
    CHECK(!pthread_key_delete(key));
    CHECK(!pthread_create(&detached,&attr,short_worker,(void *)0x203) && !pthread_detach(detached));
    until=deadline(); CHECK(!sem_timedwait(&done,&until));
    int waited=probe_wait_thread(detached,5000); CHECK(waited==0 || waited==3);
    CHECK(!pthread_attr_setdetachstate(&attr,1) && !pthread_create(&detached,&attr,short_worker,(void *)0x204));
    until=deadline(); CHECK(!sem_timedwait(&done,&until));
    waited=probe_wait_thread(detached,5000); CHECK(waited==0 || waited==3);
    CHECK(!pthread_attr_destroy(&attr));
    CHECK(!pthread_cond_destroy(&condition) && !pthread_mutex_destroy(&mutex));
    CHECK(!sem_destroy(&ready) && !sem_destroy(&done));
finish:
    out[0]=(uint32_t)failed; out[1]=(uint32_t)check; out[2]=(uint32_t)counter;
    out[3]=destructor_calls[0]+destructor_calls[1]; out[4]=worker_errors[0]|worker_errors[1]; out[5]=(uint32_t)constructor_marker;
    return failed;
#undef CHECK
}
/* Used only by the separately compiled timeout integration test. */
static void *DS_IO_SOFT slow_worker(void *value) {
    (void)value; for(int i=0;i<100;++i) usleep(100000); return NULL;
}
int probe_stall(uint32_t *out) {
    uint32_t id; out[5]=(uint32_t)constructor_marker;
    return pthread_create(&id,NULL,slow_worker,NULL);
}
