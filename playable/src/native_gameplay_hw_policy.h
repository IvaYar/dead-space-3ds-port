extern int p9_developer;
/* HW06 finite observation policy. Never writes donor objects or synthesizes input. */
#ifndef NATIVE_GAMEPLAY_HW_POLICY_H
#define NATIVE_GAMEPLAY_HW_POLICY_H
#include <stdint.h>
#define HW_WRITE_LIMIT (512u*1024u*1024u)
#define HW_EXIT_RESERVE (256u*1024u)
#define HW_LOG_LIMIT (2u*1024u*1024u)
#define HW6_TOTAL_MS 6300000u
#define HW6_READY_MS 5700000u
#define HW6_POST_MS 600000u
#define HW6_MARK_MS 120000u
#define HW6_WINDOW_CALLBACKS 96u
typedef struct {
    uint64_t scene_ms,ready_ms,marked_ms;
    uint32_t a_cb,cin_cb,flags,ready_seen,ready_callbacks,window_callbacks,marked;
    uint32_t phase,count,neutral,stop;
} HWPolicy;
enum {HW6_ACK=1,HW6_MODAL=2,HW6_CIN=4};
static inline unsigned hw6_poll(const HWPolicy *p,uint64_t now,uint32_t cb){
    if(!p->a_cb)return 0;
    uint64_t dt=now-p->scene_ms;
    if(dt>=HW6_TOTAL_MS && (!p->ready_seen || p9_developer))return 1;
    /* A returned callback may overshoot; observing first readiness after its
     * deadline is evidence, never permission to bypass the readiness limit. */
    if(p->ready_seen && p->ready_ms-p->scene_ms>=HW6_READY_MS)return 2;
    if(p->ready_seen){
        if(!p9_developer)return now-p->ready_ms>=14400000u?7:0; /* bounded four-hour playable session */
        if(now-p->ready_ms>=HW6_POST_MS)return 7;
        if(!p->marked && now-p->ready_ms>=HW6_MARK_MS)return 8;
        if(p->marked && p->window_callbacks>=HW6_WINDOW_CALLBACKS)return 9;
        if(p->phase==6)return 10;
        return 0;
    }
    if(dt>=HW6_READY_MS)return 2;
    if((p->flags&(HW6_ACK|HW6_MODAL))!=(HW6_ACK|HW6_MODAL) && (dt>=480000u || cb-p->a_cb>=64u))return 3;
    if(!(p->flags&HW6_CIN) && (dt>=600000u || cb-p->a_cb>=96u))return 4;
    if(p->cin_cb && cb-p->cin_cb>=700u)return 5;
    if(cb-p->a_cb>=800u)return 6;
    return 0;
}
static inline void hw6_observe_policy(HWPolicy *p,uint64_t now,uint32_t cb,uint32_t flags,int ready){
    if(!p->a_cb)return;
    if((flags&HW6_CIN) && !(p->flags&HW6_CIN))p->cin_cb=cb;
    p->flags|=flags;
    if(ready){if(!p->ready_seen){p->ready_seen=1;p->ready_ms=now;}++p->ready_callbacks;}
}
/* phase1 baseline,2 forward,3 stop,4 backward,5 stop,6 complete. Counts delivered
 * control callbacks, never requires motion to advance: a complete zero-motion
 * attempt must remain classifiable as FAIL by the offline analyzer. */
static inline void hw6_motion(HWPolicy *p,uint64_t now,int mark,int neutral,int valid,int cy,int pad_phase,int owner){
    if(!p->ready_seen)return;
    if(!p->marked){
        if(valid && neutral && owner==-1)++p->neutral;else p->neutral=0;
        if(mark && p->neutral>=3){p->marked=1;p->marked_ms=now;p->phase=1;p->count=0;}
        return;
    }
    ++p->window_callbacks;
    if(!valid){p->count=0;return;}
    if(p->phase==1 || p->phase==3 || p->phase==5){
        if(neutral && owner==-1)++p->count;else p->count=0;
        if(p->count>=(p->phase==1?3u:5u)){++p->phase;p->count=0;}
    }else if(p->phase==2 || p->phase==4){
        if(pad_phase==3 && (p->phase==2?cy>24:cy< -24))++p->count;else p->count=0;
        if(p->count>=7){++p->phase;p->count=0;}
    }
}
static inline int hw_budget_take(uint32_t *used,uint32_t bytes,int cleanup){
    uint32_t limit=HW_WRITE_LIMIT+(cleanup?HW_EXIT_RESERVE:0);
    if(*used>limit || bytes>limit-*used)return -1;
    *used+=bytes;return 0;
}
#endif
