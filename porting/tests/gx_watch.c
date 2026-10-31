/* Memory-only observers. No stdio, filesystem, allocation or SDK callback replacement. */
#include "gx_watch.h"
#include <string.h>
static GwData data;
static gxCmdQueue_s *tracked;
static const GSPGPU_Event ids[GW_EVENTS]={GSPGPU_EVENT_PSC0,GSPGPU_EVENT_P3D,GSPGPU_EVENT_PPF,GSPGPU_EVENT_PSC1,GSPGPU_EVENT_DMA};
extern u32 __ctru_linear_heap,__ctru_linear_heap_size;
extern void __real_gxCmdQueueRun(gxCmdQueue_s *);
extern void __real_gxCmdQueueClear(gxCmdQueue_s *);
extern Result __real_gspSubmitGxCommand(const u32 *);
static GwQueue read_queue(gxCmdQueue_s *q){
    volatile gxCmdQueue_s *v=q;GwQueue out={0};
    if(v){out.total=v->numEntries;out.submitted=v->curEntry;out.completed=v->lastEntry;out.capacity=v->maxEntries;}return out;
}
static int same_queue(GwQueue a,GwQueue b){return a.total==b.total && a.submitted==b.submitted && a.completed==b.completed && a.capacity==b.capacity;}
static void record_event(unsigned id){
    u32 n=__atomic_fetch_add(&data.event_reserved,1,__ATOMIC_RELAXED);
    if(n>=GW_EVENT_RECORDS){__atomic_store_n(&data.overflow,1,__ATOMIC_RELEASE);return;}
    GwEvent *e=&data.events[n];u64 tick=svcGetSystemTick();e->id=id;e->lo=tick;e->hi=tick>>32;e->run=1;
    e->queue=read_queue(__atomic_load_n(&tracked,__ATOMIC_ACQUIRE));
    __atomic_store_n(&e->commit,n+1,__ATOMIC_RELEASE);
    /* Only the SDK GSP thread produces event callbacks. */
    __atomic_store_n(&data.event_committed,n+1,__ATOMIC_RELEASE);
}
static void psc0(void *unused){(void)unused;record_event(0);}
static void p3d(void *unused){(void)unused;record_event(1);}
static void ppf(void *unused){(void)unused;record_event(2);}
static void psc1(void *unused){(void)unused;record_event(3);}
static void dma(void *unused){(void)unused;record_event(4);}
static void capture_pica(gxCmdQueue_s *q){
    if(data.pica_bytes || !q || !q->entries || q->numEntries>32)return;
    for(unsigned i=0;i<q->numEntries;++i)if(q->entries[i].type==1){
        uintptr_t address=q->entries[i].args[0];u32 bytes=q->entries[i].args[1];
        if(address<__ctru_linear_heap || !bytes || bytes>GW_PICA_BYTES || (address&7) || (bytes&3) ||
            address-__ctru_linear_heap>__ctru_linear_heap_size || bytes>__ctru_linear_heap_size-(address-__ctru_linear_heap)){
            data.pica_rejected=1;return;
        }
        memcpy(data.pica,(void*)address,bytes);data.pica_address=address;data.pica_bytes=bytes;return;
    }
}
static void record_queue(unsigned kind,gxCmdQueue_s *q){
    __atomic_store_n(&tracked,q,__ATOMIC_RELEASE);
    if(!__atomic_load_n(&data.armed,__ATOMIC_ACQUIRE))return;
    u32 n=__atomic_fetch_add(&data.run_reserved,1,__ATOMIC_RELAXED);
    if(n>=GW_QUEUE_RECORDS){__atomic_store_n(&data.overflow,1,__ATOMIC_RELEASE);return;}
    GwRun *r=&data.runs[n];u64 tick=svcGetSystemTick();r->lo=tick;r->hi=tick>>32;r->kind=kind;r->run=1;r->queue=read_queue(q);
    if(q->entries && r->queue.total<=32 && r->queue.total<=r->queue.capacity)
        for(unsigned i=0;i<r->queue.total;++i)for(unsigned j=0;j<8;++j)r->words[i][j]=q->entries[i].data[j];
    else if(r->queue.total)__atomic_store_n(&data.overflow,1,__ATOMIC_RELEASE);
    __atomic_store_n(&r->commit,n+1,__ATOMIC_RELEASE);
}
void __wrap_gxCmdQueueRun(gxCmdQueue_s *q){
    record_queue(0,q);if(__atomic_load_n(&data.armed,__ATOMIC_ACQUIRE))capture_pica(q);
    __real_gxCmdQueueRun(q);record_queue(1,q);
}
void __wrap_gxCmdQueueClear(gxCmdQueue_s *q){record_queue(2,q);__real_gxCmdQueueClear(q);}
Result __wrap_gspSubmitGxCommand(const u32 *words){
    if(!__atomic_load_n(&data.armed,__ATOMIC_ACQUIRE))return __real_gspSubmitGxCommand(words);
    u32 n=__atomic_fetch_add(&data.submit_reserved,1,__ATOMIC_RELAXED);
    if(n>=GW_SUBMITS){__atomic_store_n(&data.overflow,1,__ATOMIC_RELEASE);return __real_gspSubmitGxCommand(words);}
    GwSubmit *s=&data.submits[n];u64 tick=svcGetSystemTick();s->lo=tick;s->hi=tick>>32;s->run=1;
    for(unsigned i=0;i<8;++i)s->words[i]=words[i];
    __atomic_store_n(&s->entered,n+1,__ATOMIC_RELEASE);
    Result result=__real_gspSubmitGxCommand(words);tick=svcGetSystemTick();s->end_lo=tick;s->end_hi=tick>>32;s->result=result;
    __atomic_store_n(&s->returned,1,__ATOMIC_RELEASE);return result;
}
void gw_arm(int fault){
    /* Called once, after attach and the initial queue retirement, before End. */
    memset(&data,0,sizeof(data));data.fault=fault;
    __atomic_store_n(&data.armed,1,__ATOMIC_RELEASE);__atomic_store_n(&data.critical,1,__ATOMIC_RELEASE);
    gspSetEventCallback(ids[0],psc0,NULL,false);gspSetEventCallback(ids[1],p3d,NULL,false);
    gspSetEventCallback(ids[2],ppf,NULL,false);gspSetEventCallback(ids[3],psc1,NULL,false);gspSetEventCallback(ids[4],dma,NULL,false);
    gw_sample(GW_ARM);
}
int gw_critical(void){return __atomic_load_n(&data.critical,__ATOMIC_ACQUIRE)!=0;}
int gw_has_queue(void){return __atomic_load_n(&tracked,__ATOMIC_ACQUIRE)!=NULL;}
int gw_idle(void){gxCmdQueue_s *q=__atomic_load_n(&tracked,__ATOMIC_ACQUIRE);return !q || gxCmdQueueWait(q,0);}
int gw_safe_exit(void){
    if(!gw_idle())return 0;
    if(!__atomic_load_n(&data.armed,__ATOMIC_ACQUIRE))return 1;
    if(__atomic_load_n(&data.overflow,__ATOMIC_ACQUIRE))return 0;
    u32 mask=0,end=__atomic_load_n(&data.event_committed,__ATOMIC_ACQUIRE);
    for(unsigned i=0;i<end && i<GW_EVENT_RECORDS;++i){
        const GwEvent *e=&data.events[i];
        if(__atomic_load_n(&e->commit,__ATOMIC_ACQUIRE)==i+1 && e->id<3)mask|=1u<<e->id;
    }
    return mask==7; /* Do not free GPU buffers on ambiguous aggregate accounting. */
}
void gw_blocked_io(void){__atomic_fetch_add(&data.io_blocked,1,__ATOMIC_RELAXED);}
const GwData *gw_data(void){return &data;}
void gw_sample(unsigned phase){
    if(data.sample_count>=GW_SAMPLES){__atomic_store_n(&data.overflow,1,__ATOMIC_RELEASE);return;}
    __atomic_store_n(&data.stage,phase,__ATOMIC_RELEASE);
    GwSample *s=&data.samples[data.sample_count++];u64 tick=svcGetSystemTick();s->phase=phase;s->stage=phase;s->lo=tick;s->hi=tick>>32;
    gxCmdQueue_s *q=__atomic_load_n(&tracked,__ATOMIC_ACQUIRE);s->queue_address=(u32)(uintptr_t)q;
    u32 first=__atomic_load_n(&data.event_committed,__ATOMIC_ACQUIRE);s->queue=read_queue(q);
    for(unsigned i=0;i<first && i<GW_EVENT_RECORDS;++i){
        GwEvent *e=&data.events[i];if(__atomic_load_n(&e->commit,__ATOMIC_ACQUIRE)==i+1 && e->id<GW_EVENTS)++s->counts[e->id];
    }
    s->vblank[0]=C3D_FrameCounter(0);s->vblank[1]=C3D_FrameCounter(1);s->idle=gw_idle();
    GwQueue second=read_queue(q);u32 last=__atomic_load_n(&data.event_committed,__ATOMIC_ACQUIRE);
    s->queue_stable=same_queue(s->queue,second);s->event_consistent=first==last && !__atomic_load_n(&data.overflow,__ATOMIC_ACQUIRE);s->event_serial=first;
}
void gw_observe(unsigned timeout_ms){
    u64 started=svcGetSystemTick(),hz=SYSCLOCK_ARM11,last_sample=started,last_change=started;
    GwQueue old=read_queue(__atomic_load_n(&tracked,__ATOMIC_ACQUIRE));u32 serial=__atomic_load_n(&data.event_committed,__ATOMIC_ACQUIRE);
    u32 vb[2]={C3D_FrameCounter(0),C3D_FrameCounter(1)},last_vb[2]={vb[0],vb[1]};gw_sample(GW_SYNC_ENTER);
    for(;;){
        u64 now=svcGetSystemTick();GwQueue current=read_queue(__atomic_load_n(&tracked,__ATOMIC_ACQUIRE));
        u32 next=__atomic_load_n(&data.event_committed,__ATOMIC_ACQUIRE);u32 a=C3D_FrameCounter(0),b=C3D_FrameCounter(1);
        int changed=!same_queue(old,current) || serial!=next;
        if(changed)last_change=now;
        if(data.vblank_phases<2 && a!=vb[0] && b!=vb[1]){++data.vblank_phases;vb[0]=a;vb[1]=b;gw_sample(data.vblank_phases==1?GW_VBLANK1:GW_VBLANK2);}
        if(changed || a!=last_vb[0] || b!=last_vb[1] || (now-last_sample)*1000>=10*hz){
            gw_sample(GW_POLL);last_sample=now;old=current;serial=next;last_vb[0]=a;last_vb[1]=b;
        }
        GwSample *s=&data.samples[data.sample_count-1];int notifications=s->counts[0] && s->counts[1] && s->counts[2];
        if(!data.fault && gw_idle() && data.vblank_phases==2 && notifications &&
                (now-started)*1000>=100*hz && (now-last_change)*1000>=20*hz)break;
        if((now-started)*1000>=timeout_ms*hz){data.window_timeout=1;break;}
        svcSleepThread(1000000);
    }
    data.elapsed_ms=(svcGetSystemTick()-started)*1000/hz;
    gw_sample(GW_WAIT_DONE);data.decision=data.sample_count-1;
    gw_sample(GW_SYNC_RETURN);
}
void gw_begin_result(int attempted,int result){data.nonblock_attempted=attempted;data.nonblock_result=result;gw_sample(GW_BEGIN_RETURN);}
void gw_close(void){if(data.armed)gw_sample(GW_CLOSED);__atomic_store_n(&data.critical,0,__ATOMIC_RELEASE);}
void gw_remove(void){if(!data.armed)return;for(unsigned i=0;i<GW_EVENTS;++i)gspSetEventCallback(ids[i],NULL,NULL,false);}
