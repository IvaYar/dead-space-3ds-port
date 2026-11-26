/* Snapshot of the existing collector, no new queue. All timestamps are raw
 * svcGetSystemTick units. Caller captures now AFTER copying under the lock. */
enum {
    GP_INPUT_OK=0,GP_INPUT_THREAD=1,GP_INPUT_COLLECTOR=2,GP_INPUT_FIFO=3,
    GP_INPUT_CLOCK=4,GP_INPUT_TOUCH=5,GP_INPUT_MENU=6,GP_INPUT_SAMPLE=7,
    GP_INPUT_RELEASE=8,GP_INPUT_STALE_RELEASE=9,GP_INPUT_STALE_INACTIVE=10,
    GP_INPUT_FRESH_NEUTRAL=11
};
typedef struct {
    HidTransition latest;
    u64 now;
    u32 scans,invalid,overflow,count,head,initialized,alive,stop;
} GameplayHidSnapshot;
static int gameplay_snapshot_error(const GameplayHidSnapshot *s){
    if(!s->alive || s->stop)return GP_INPUT_COLLECTOR;
    if(s->overflow || s->count>HID_FIFO_CAPACITY || s->head>=HID_FIFO_CAPACITY ||
       s->initialized>1 || (s->scans && !s->initialized) ||
       (s->initialized && (!s->scans || !s->latest.ticks || s->latest.index>7)))return GP_INPUT_FIFO;
    if(s->latest.ticks>s->now)return GP_INPUT_CLOCK;
    return GP_INPUT_OK;
}
static int gameplay_snapshot_fresh(const GameplayHidSnapshot *s){
    /* Preserve the original250ms bound. Missing/future data never commands. */
    return s->initialized && s->latest.ticks && s->now>=s->latest.ticks &&
        s->now-s->latest.ticks<=SYSCLOCK_ARM11/4;
}
