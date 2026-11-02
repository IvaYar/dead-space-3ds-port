/* This observer never calls hidScanInput, SDK key getters, donor or stdio.
 * The SDK/sensor HID handling remains on its original path. */
#include "native_hid_queue.h"
static LightLock hid_fifo_lock;
static HidFifo hid_fifo;
static Thread hid_collector_thread;
static u32 hid_collector_stop,hid_latched_control,hid_menu_ready,hid_virtual_held;
static u32 hid_event_id,hid_event_epoch,hid_last_sdk_down,hid_last_sdk_held;
static u64 hid_event_ticks;
static u64 hid_boot_ticks;
static u64 hid_last_main_sample,hid_max_main_gap;
static double hid_time_ms(u64 ticks){return (double)(ticks-hid_boot_ticks)*1000/SYSCLOCK_ARM11;}
static int hid_shared_sample(u32 *held,u32 *index,s16 *cx,s16 *cy){
    /* SDK hidScanInput uses shared+0x28+index*16 for held and +0x34
     * for Circle Pad. Validate the publication index/ticks on both sides. */
    if(!hidSharedMem)return 0;
    for(u32 attempt=0;attempt<3;++attempt){
        u32 i=hidSharedMem[4],t0=hidSharedMem[0],t1=hidSharedMem[1];
        if(i>7 || (s32)t1<0)return 0;
        if(!i && ((s32)hidSharedMem[3]<0 || (hidSharedMem[0]==hidSharedMem[2] && hidSharedMem[1]==hidSharedMem[3])))return 0;
        __sync_synchronize();
        u32 h=hidSharedMem[10+i*4],circle=hidSharedMem[13+i*4];
        __sync_synchronize();
        if(i!=hidSharedMem[4] || t0!=hidSharedMem[0] || t1!=hidSharedMem[1])continue;
        *held=h;*index=i;*cx=(s16)(circle&65535);*cy=(s16)(circle>>16);return 1;
    }return 0;
}
static void hid_collector(void *arg){
    (void)arg;
    while(!__atomic_load_n(&hid_collector_stop,__ATOMIC_ACQUIRE)){
        u32 held,index;s16 cx,cy;
        int valid=hid_shared_sample(&held,&index,&cx,&cy);
        LightLock_Lock(&hid_fifo_lock);
        if(valid){
            u32 previous=hid_fifo.initialized?hid_fifo.previous:held;
            __atomic_fetch_or(&hid_latched_control,(held&~previous)&(KEY_START|KEY_X),__ATOMIC_RELEASE);
            hid_fifo_sample(&hid_fifo,held,svcGetSystemTick(),index,cx,cy);
        }else ++hid_fifo.invalid;
        LightLock_Unlock(&hid_fifo_lock);
        svcSleepThread(4000000);
    }
}
static int hid_collector_start(void){
    LightLock_Init(&hid_fifo_lock);hid_boot_ticks=svcGetSystemTick();
    s32 priority=0x30;if(R_FAILED(svcGetThreadPriority(&priority,CUR_THREAD_HANDLE)))return -1;
    hid_collector_thread=threadCreate(hid_collector,NULL,64*1024,priority,0,false);
    if(!hid_collector_thread)return -1;
    report("HID_COLLECTOR start readonly=1 period_ms=4 stack=65536 core=0 priority=%ld fifo=64\n",(long)priority);return 0;
}
static int hid_collector_finish(void){
    if(!hid_collector_thread)return 0;
    __atomic_store_n(&hid_collector_stop,1,__ATOMIC_RELEASE);
    Result r=threadJoin(hid_collector_thread,1000000000);
    report("HID_COLLECTOR join result=%08lx\n",(unsigned long)r);
    if(R_FAILED(r))return -1;
    threadFree(hid_collector_thread);hid_collector_thread=NULL;
    char name[192];path(name,"hid-capture.json");FILE *f=fopen(name,"w");
    if(f){fprintf(f,"{\"collector_joined\":true,\"thread_freed\":true,\"scans\":%lu,\"invalid_samples\":%lu,\"transitions\":%lu,\"overflow\":%lu,\"max_raw_sample_gap_ms\":%.3f,\"max_ready_raw_sample_gap_ms\":%.3f,\"max_game_main_sample_gap_ms\":%.3f,\"last_raw_held\":%lu,\"period_ms\":4,\"capacity\":64}\n",(unsigned long)hid_fifo.scans,(unsigned long)hid_fifo.invalid,(unsigned long)hid_fifo.serial,(unsigned long)hid_fifo.overflow,(double)hid_fifo.maximum_gap*1000/SYSCLOCK_ARM11,(double)hid_fifo.maximum_ready_gap*1000/SYSCLOCK_ARM11,(double)hid_max_main_gap*1000/SYSCLOCK_ARM11,(unsigned long)hid_fifo.latest.held);fclose(f);}
    report("HID_COLLECTOR freed before donor shutdown and gfxExit\n");return 0;
}
static void hid_trace_raw(const HidTransition *e,const char *stage_name){
    report("HIDRAW ms=%.3f id=%lu stage=%s epoch=%lu index=%lu held=%08lx down=%08lx up=%08lx circle=%d,%d\n",
        hid_time_ms(e->ticks),(unsigned long)e->id,stage_name,(unsigned long)e->epoch,(unsigned long)e->index,
        (unsigned long)e->held,(unsigned long)e->down,(unsigned long)e->up,e->cx,e->cy);
}
static void hid_preflight_file(const char *state){
    LightLock_Lock(&hid_fifo_lock);u32 seen=hid_fifo.seen,scans=hid_fifo.scans,invalid=hid_fifo.invalid,overflow=hid_fifo.overflow;LightLock_Unlock(&hid_fifo_lock);
    char name[192];path(name,"hid-preflight.json");FILE *f=fopen(name,"w");
    if(f){fprintf(f,"{\"state\":\"%s\",\"required_mask\":243,\"seen_mask\":%lu,\"raw_buttons_passed\":%s,\"scans\":%lu,\"invalid_samples\":%lu,\"overflow\":%lu,\"engine_loaded\":false}\n",state,(unsigned long)seen,(seen&0xf3u)==0xf3u?"true":"false",(unsigned long)scans,(unsigned long)invalid,(unsigned long)overflow);fclose(f);}
}
static int hid_preflight(void){
    screen("RAW HID CHECK - engine NOT loaded\nPress/release D-pad U/D/L/R, A, B\nCircle Pad shown separately\nSTART: exit now (no game load)\nX: load game after all six checks");
    hid_preflight_file("waiting");u32 last_seen=~0u;u64 display=0;
    report("HIDMASK DDOWN=%08lx DUP=%08lx CPAD_DOWN=%08lx GENERIC_DOWN=%08lx START=%08lx\n",(unsigned long)KEY_DDOWN,(unsigned long)KEY_DUP,(unsigned long)KEY_CPAD_DOWN,(unsigned long)KEY_DOWN,(unsigned long)KEY_START);
    while(app_main_loop()){
        hidScanInput();u32 sdk_down=hidKeysDown(),sdk_held=hidKeysHeld();
        HidTransition e,last;u32 seen,overflow;
        for(u32 budget=0;budget<HID_FIFO_CAPACITY;++budget){LightLock_Lock(&hid_fifo_lock);int got=hid_fifo_take(&hid_fifo,&e);LightLock_Unlock(&hid_fifo_lock);if(!got)break;hid_trace_raw(&e,"preflight");}
        LightLock_Lock(&hid_fifo_lock);seen=hid_fifo.seen;overflow=hid_fifo.overflow;last=hid_fifo.latest;LightLock_Unlock(&hid_fifo_lock);
        u32 control=__atomic_exchange_n(&hid_latched_control,0,__ATOMIC_ACQ_REL);
        if(sdk_down || seen!=last_seen){report("HIDSDK ms=%.3f stage=preflight down=%08lx held=%08lx raw=%08lx seen=%08lx\n",hid_time_ms(svcGetSystemTick()),(unsigned long)sdk_down,(unsigned long)sdk_held,(unsigned long)last.held,(unsigned long)seen);hid_preflight_file("waiting");}
        last_seen=seen;
        if((sdk_held|control)&KEY_START){close_origin="START";hid_preflight_file("START_exit");report("HID_PREFLIGHT START exit engine_loaded=0\n");return 0;}
        if((sdk_down|control)&KEY_X){
            if((seen&0xf3u)==0xf3u && !(last.held&0xf3u) && !overflow){
                hid_preflight_file("passed_engine_requested");
                LightLock_Lock(&hid_fifo_lock);u32 discarded=hid_fifo_barrier(&hid_fifo);LightLock_Unlock(&hid_fifo_lock);
                report("HID_PREFLIGHT PASS original engine requested; barrier discarded=%lu\n",(unsigned long)discarded);return 1;
            }
            report("HID_PREFLIGHT X blocked missing=%08lx held=%08lx overflow=%lu\n",(unsigned long)(0xf3u&~seen),(unsigned long)last.held,(unsigned long)overflow);
        }
        u64 now=svcGetSystemTick();
        if(now-display>SYSCLOCK_ARM11/10){
            printf("\x1b[8;1Hraw=%08lx SDKheld=%08lx\nSDKdown=%08lx CPAD=%d,%d\nU:%c D:%c L:%c R:%c A:%c B:%c\n%s                    \n",(unsigned long)last.held,(unsigned long)sdk_held,(unsigned long)sdk_down,last.cx,last.cy,
                seen&KEY_DUP?'Y':'-',seen&KEY_DDOWN?'Y':'-',seen&KEY_DLEFT?'Y':'-',seen&KEY_DRIGHT?'Y':'-',seen&KEY_A?'Y':'-',seen&KEY_B?'Y':'-',(seen&0xf3u)==0xf3u?"RAW PASS: X loads / START exits":"Still waiting for raw buttons");display=now;
        }svcSleepThread(4000000);
    }hid_preflight_file("APT_exit");return 0;
}
static void hid_main_snapshot(u32 sdk_down,u32 sdk_held){
    u64 now=svcGetSystemTick();if(hid_last_main_sample && now-hid_last_main_sample>hid_max_main_gap)hid_max_main_gap=now-hid_last_main_sample;hid_last_main_sample=now;
    hid_last_sdk_down=sdk_down;hid_last_sdk_held=sdk_held;
    if(sdk_down || (sdk_held&KEY_START))report("HIDSDK ms=%.3f frame=%lu down=%08lx held=%08lx\n",hid_time_ms(svcGetSystemTick()),(unsigned long)current_frame,(unsigned long)sdk_down,(unsigned long)sdk_held);
}
static int hid_menu_sample(int ready,int allow_press,u32 *held){
    HidTransition e,dropped[HID_FIFO_CAPACITY];u32 overflow,discarded=0;int changed=0;
    LightLock_Lock(&hid_fifo_lock);
    if((u32)ready!=hid_menu_ready){changed=1;while(discarded<HID_FIFO_CAPACITY && hid_fifo_take(&hid_fifo,&dropped[discarded]))++discarded;hid_fifo_barrier(&hid_fifo);hid_virtual_held=0;hid_menu_ready=(u32)ready;hid_fifo.ready=(u32)ready;}
    overflow=hid_fifo.overflow;int got=0;
    if(hid_fifo.count && (allow_press || !((hid_nav_mask(hid_fifo.entries[hid_fifo.head].held)&~hid_virtual_held)&(KEY_A|KEY_DUP|KEY_DDOWN)))){
        got=hid_fifo_take(&hid_fifo,&e);
    }
    hid_event_epoch=hid_fifo.epoch;
    LightLock_Unlock(&hid_fifo_lock);
    for(u32 i=0;i<discarded;++i)hid_trace_raw(&dropped[i],"barrier_rejected");
    if(changed)report("HID_BARRIER ms=%.3f ready=%d epoch=%lu discarded=%lu\n",hid_time_ms(svcGetSystemTick()),ready,(unsigned long)hid_event_epoch,(unsigned long)discarded);
    if(changed && ready)screen("ORIGINAL MENU READY / FRAME FAIL\nD-pad UP/DOWN: select; A: confirm + exit\nB: original BACK (first screen ignores)\nSTART: safe exit\nRaw HID capture active during callbacks");
    if(overflow){report("HID_OVERFLOW count=%lu; fail closed\n",(unsigned long)overflow);return -1;}
    if(got){
        hid_trace_raw(&e,"game");
        if(ready){hid_virtual_held=hid_nav_mask(e.held);hid_event_id=e.id;hid_event_ticks=e.ticks;}
        report("HIDHOST ms=%.3f frame=%lu id=%lu ready=%d raw=%08lx mapped=%08lx SDKdown=%08lx SDKheld=%08lx age_ms=%.3f\n",hid_time_ms(svcGetSystemTick()),(unsigned long)current_frame,(unsigned long)e.id,ready,(unsigned long)e.held,(unsigned long)(ready?hid_virtual_held:0),(unsigned long)hid_last_sdk_down,(unsigned long)hid_last_sdk_held,(double)(svcGetSystemTick()-e.ticks)*1000/SYSCLOCK_ARM11);
    }
    *held=ready?hid_virtual_held:0;return 0;
}
