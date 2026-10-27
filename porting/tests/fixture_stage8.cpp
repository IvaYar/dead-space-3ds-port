/* Original ARM C++ lifecycle probe. No game code or C++ standard library. */
#include <stdint.h>
#include <stddef.h>
struct Time { int32_t sec,nsec; };
struct Stats { uint32_t acquires,releases,aborts,waits,guards,registered,called,pending,running,failures; };
extern "C" {
/* Modern GCC owns a hidden token per DSO; the legacy donor imports its token. */
void *__dso_handle=&__dso_handle;
void *malloc(size_t); void free(void *);
int pthread_create(uint32_t *,const void *,void *(*)(void *),void *);
int pthread_join(uint32_t,void **); int probe_wait_thread(uint32_t,int32_t);
int sem_init(uint32_t *,int,unsigned); int sem_post(uint32_t *);
int sem_timedwait(uint32_t *,const Time *); int sem_destroy(uint32_t *);
int clock_gettime(int,Time *); int usleep(unsigned);
int __cxa_guard_acquire(uint32_t *); void __cxa_guard_release(uint32_t *); void __cxa_guard_abort(uint32_t *);
int __cxa_atexit(void (*)(void *),void *,void *); void __cxa_finalize(void *);
void probe_cpp_stats(Stats *);
}
static uint32_t constructed,construction_order,destroyed,destruction_order,errors;
static uint32_t entered,proceed,attempt;
static uint32_t manual[16],manual_count;
static uint8_t dso_a,dso_b,dso_c;
static int wait_sem(uint32_t *sem) {
    Time until; if(clock_gettime(0,&until)) return -1;
    until.sec+=4; return sem_timedwait(sem,&until);
}
class Object {
    uint32_t id; uint32_t *memory;
public:
    explicit Object(uint32_t value):id(value),memory(static_cast<uint32_t *>(malloc(8))) {
        if(!memory) errors|=1; else *memory=id;
        ++constructed; construction_order=construction_order*10+id;
        if(id==3 && (sem_post(&entered) || wait_sem(&proceed))) errors|=2;
    }
    ~Object() {
        if(!memory || *memory!=id) errors|=4;
        free(memory); memory=0; ++destroyed; destruction_order=destruction_order*10+id;
    }
    uint32_t value() const { return memory?*memory:0; }
};
Object first(1),second(2);
static Object &local_object() { static Object third(3); return third; }
extern "C" void probe_dt_init() { construction_order=9; }
extern "C" void probe_snapshot(uint32_t *out) {
    out[0]=constructed; out[1]=construction_order; out[2]=destroyed; out[3]=destruction_order; out[4]=errors;
}
static void *worker(void *argument) {
    if(argument && sem_post(&attempt)) errors|=8;
    return reinterpret_cast<void *>(local_object().value());
}
static void mark(void *value) { if(manual_count<16) manual[manual_count++]=reinterpret_cast<uint32_t>(value); else errors|=16; }
static void reentrant(void *value) {
    mark(value);
    if(__cxa_atexit(mark,reinterpret_cast<void *>(50),&dso_c)) errors|=32;
    __cxa_finalize(&dso_c);
}
extern "C" int probe_cpp(uint32_t *out) {
    uint32_t checks=0; int failure=0;
#define CHECK(value) do { ++checks; if(!(value)) { failure=__LINE__; goto done; } } while(0)
    uint32_t ids[2]={0,0},guard=0x80000000u; void *result;
    Stats state;
    CHECK(constructed==2 && construction_order==912 && !destroyed && !errors);
    CHECK(__cxa_guard_acquire(&guard)==1);
    __cxa_guard_abort(&guard); CHECK(guard==0x80000000u);
    CHECK(__cxa_guard_acquire(&guard)==1);
    __cxa_guard_release(&guard); CHECK(guard==0x80000001u);
    CHECK(__cxa_guard_acquire(&guard)==0);
    CHECK(!sem_init(&entered,0,0)); CHECK(!sem_init(&proceed,0,0)); CHECK(!sem_init(&attempt,0,0));
    CHECK(!pthread_create(&ids[0],0,worker,0));
    CHECK(!wait_sem(&entered));
    CHECK(!pthread_create(&ids[1],0,worker,reinterpret_cast<void *>(1)));
    CHECK(!wait_sem(&attempt));
    /* Force a real competing guard acquisition before letting the constructor finish. */
    for(unsigned i=0;i<2000;++i) { probe_cpp_stats(&state); if(state.waits) break; usleep(1000); }
    CHECK(state.waits && state.guards==1);
    CHECK(!sem_post(&proceed));
    for(unsigned i=0;i<2;++i) {
        CHECK(!probe_wait_thread(ids[i],5000)); CHECK(!pthread_join(ids[i],&result)); ids[i]=0;
        CHECK(reinterpret_cast<uint32_t>(result)==3);
    }
    CHECK(local_object().value()==3 && constructed==3 && construction_order==9123 && !destroyed);
    CHECK(!sem_destroy(&entered)); CHECK(!sem_destroy(&proceed)); CHECK(!sem_destroy(&attempt));
    CHECK(!__cxa_atexit(mark,reinterpret_cast<void *>(10),&dso_a));
    CHECK(!__cxa_atexit(mark,reinterpret_cast<void *>(20),&dso_a));
    CHECK(!__cxa_atexit(mark,reinterpret_cast<void *>(30),&dso_b));
    __cxa_finalize(&dso_a); __cxa_finalize(&dso_a);
    CHECK(manual_count==2 && manual[0]==20 && manual[1]==10 && !destroyed);
    __cxa_finalize(&dso_b); CHECK(manual_count==3 && manual[2]==30);
    CHECK(!__cxa_atexit(mark,reinterpret_cast<void *>(60),&dso_c));
    CHECK(!__cxa_atexit(reentrant,reinterpret_cast<void *>(40),&dso_c));
    __cxa_finalize(&dso_c);
    CHECK(manual_count==6 && manual[3]==40 && manual[4]==50 && manual[5]==60);
    CHECK(!errors);
done:
    /* Shutdown is owned by the host. Even a failed probe cannot unload live workers. */
    out[0]=failure; out[1]=checks; out[2]=constructed; out[3]=construction_order; out[4]=errors; out[5]=manual_count;
    return failure;
}
static void *stall(void *) { for(unsigned i=0;i<100;++i) usleep(100000); return 0; }
extern "C" int probe_stall(uint32_t *out) {
    uint32_t id; out[0]=1; return pthread_create(&id,0,stall,0)?2:1;
}
