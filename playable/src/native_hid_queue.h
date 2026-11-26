/* Pure bounded transition FIFO. Caller serializes producer/consumer. */
#define HID_FIFO_CAPACITY 64u
typedef struct {u64 ticks;u32 id,held,down,up,index,epoch; s16 cx,cy;} HidTransition;
typedef struct {
    HidTransition entries[HID_FIFO_CAPACITY],latest;
    u32 head,count,serial,previous,seen,overflow,initialized,invalid,epoch,scans;
    u64 last_sample,maximum_gap;
    u32 ready;
    u64 last_ready_sample,maximum_ready_gap;
} HidFifo;
static void hid_fifo_sample(HidFifo *q,u32 held,u64 ticks,u32 index,s16 cx,s16 cy){
    ++q->scans;
    if(q->last_sample && ticks-q->last_sample>q->maximum_gap)q->maximum_gap=ticks-q->last_sample;
    q->last_sample=ticks;
    if(q->ready){
        if(q->last_ready_sample && ticks-q->last_ready_sample>q->maximum_ready_gap)q->maximum_ready_gap=ticks-q->last_ready_sample;
        q->last_ready_sample=ticks;
    }else q->last_ready_sample=0;
    u32 before=q->initialized?q->previous:held;
    q->latest=(HidTransition){ticks,q->serial,held,held&~before,before&~held,index,q->epoch,cx,cy};
    q->previous=held;
    if(q->initialized && held==before)return;
    q->initialized=1;q->seen|=q->latest.down;q->latest.id=++q->serial;
    if(q->count==HID_FIFO_CAPACITY){++q->overflow;return;}
    q->entries[(q->head+q->count)%HID_FIFO_CAPACITY]=q->latest;++q->count;
}
static int hid_fifo_take(HidFifo *q,HidTransition *out){
    if(!q->count)return 0;
    *out=q->entries[q->head];q->head=(q->head+1)%HID_FIFO_CAPACITY;--q->count;return 1;
}
static u32 hid_fifo_barrier(HidFifo *q){u32 n=q->count;q->count=0;q->head=0;++q->epoch;return n;}
static u32 hid_nav_mask(u32 raw){
    u32 out=raw&(KEY_A|KEY_B|KEY_START);
    if(raw&(KEY_DUP|KEY_CPAD_UP))out|=KEY_DUP;
    if(raw&(KEY_DDOWN|KEY_CPAD_DOWN))out|=KEY_DDOWN;
    if((out&(KEY_DUP|KEY_DDOWN))==(KEY_DUP|KEY_DDOWN))out&=~(u32)(KEY_DUP|KEY_DDOWN);
    return out;
}
