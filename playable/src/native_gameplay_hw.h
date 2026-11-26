extern unsigned hq_good_count,hq_fallback_count;
/* Included after the unchanged gameplay router. UI and observation run on MAIN. */
#include "native_gameplay_hw_policy.h"
static HWPolicy hw_policy;
static u64 hw_last_callback_ms;
static GameplayState hw_last_state;
static u32 hw_have_state;
extern void ds_hw_io_init(void),ds_hw_io_cleanup(void);
extern u32 ds_hw_io_bytes(void),ds_hw_io_denied(void);
extern char ds_hw_pages_root[128],ds_hw_morton_root[128],ds_hw_appdata_root[96],ds_hw_run_root[128];
static volatile u32 hw6_resource_pending;
static u64 hw6_callback_ticks,hw6_present_ticks;
/* Sparse diagnostics. All new output is on MAIN and charged conservatively.
 * No pixel buffers, file handles, threads, allocation or donor writes. */
static u32 hw6_changes,hw6_hearts,hw6_bytes,hw6_suppressed,hw6_admitted;
static u64 hw6_heartbeat,hw6_diag_ticks;
static u32 hw6_last_key[16];
static int hw6_state_changed(GameplayState s){
    u32 key[16]={s.valid,s.reason,s.blockers,s.ready,s.world,s.world_phase,s.hud_phase,s.hud_mode,
        s.player_phase,s.player_flags,s.modal,s.transition,s.world44,s.scene,s.player,s.root};
    int changed=!hw_have_state || memcmp(key,hw6_last_key,sizeof(key));
    if(changed)memcpy(hw6_last_key,key,sizeof(key));
    return changed || (hw_have_state && (s.stick!=hw_last_state.stick || s.position_valid!=hw_last_state.position_valid));
}
static int hw6_charge(u32 bytes){
    if(bytes>253952u-hw6_bytes){++hw6_suppressed;return 0;}
    hw6_bytes+=bytes;return 1;
}
static void hw6_milestone(const char *name){
    u64 t=svcGetSystemTick();
    if(hw6_charge(192))report("HW6_MILESTONE name=%s cb=%lu wall_ms=%llu\n",name,(unsigned long)current_frame,(unsigned long long)loader_now_ms());
    hw6_diag_ticks+=svcGetSystemTick()-t;
}
static void hw6_publish_state(GameplayState s,const char *boundary,int changed){
    u64 now=loader_now_ms();int heart=!strcmp(boundary,"after") && scene_started && hw6_hearts<100 && now-hw6_heartbeat>=60000;
    if(!changed && !heart)return;
    if(changed && hw6_changes>=256){++hw6_suppressed;return;}
    if(!hw6_charge(640))return;
    if(changed)++hw6_changes;
    if(heart){++hw6_hearts;hw6_heartbeat=now;}
    u64 t=svcGetSystemTick();
    report("HW6_STATE cb=%lu b=%s why=%s wall_ms=%llu valid=%02lx evaluated=%02lx ready=%d reason=%lu blockers=%02lx world=%08lx wp=%lu hp=%lu hm=%lu actor=%lu flags=%08lx eligible=%d modal=%08lx transition=%lu subsystem_ok=%d scene=%08lx player=%08lx body=%08lx stick=%08lx oracle=%lu fade_raw=%lu/%lu dt_available=0 game_time_available=0 playhead_available=0\n",
        (unsigned long)current_frame,boundary,changed?"change":"heartbeat",(unsigned long long)now,
        (unsigned long)s.valid,(unsigned long)((s.valid&64)?255:0),s.ready,(unsigned long)s.reason,(unsigned long)s.blockers,
        (unsigned long)s.world,(unsigned long)s.world_phase,(unsigned long)s.hud_phase,(unsigned long)s.hud_mode,
        (unsigned long)s.player_phase,(unsigned long)s.player_flags,(s.valid&64)?!(s.blockers&(64|128)):-1,
        (unsigned long)s.modal,(unsigned long)s.transition,(s.valid&64)?!(s.blockers&4):-1,
        (unsigned long)s.scene,(unsigned long)s.player,(unsigned long)s.root,(unsigned long)s.stick,(unsigned long)s.position_valid,
        (unsigned long)s.fade_elapsed_raw,(unsigned long)s.fade_duration_raw);
    hw6_diag_ticks+=svcGetSystemTick()-t;
}
static const char *hw6_stop_name(unsigned code){
    switch(code){case 1:return "HW6_TOTAL_BUDGET";case 2:return "HW6_READY_NOT_REACHED_WITHIN_BUDGET";
    case 3:return "HW6_MENU_MILESTONE_BUDGET";case 4:return "HW6_CINEMATIC_RESOURCE_BUDGET";
    case 5:return "HW6_CINEMATIC_CALLBACK_CAP";case 6:return "HW6_READY_CALLBACK_CAP";
    case 7:return "HW6_POST_READY_BUDGET";case 8:return "HW6_MARK_WAIT_BUDGET";
    case 9:return "HW6_MOVEMENT_CALLBACK_CAP";case 10:return "HW6_SCENARIO_COMPLETE";default:return "HW6_NONE";}
}
static int hw6_check_budget(void){
    unsigned stop=hw6_poll(&hw_policy,loader_now_ms(),callbacks_completed);
    if(!stop)return 0;
    hw_policy.stop=stop;failure_reason=hw6_stop_name(stop);return 1;
}
static int hw6_before_callback(void){return hw6_check_budget();}
static void hw6_end(void){
    report("HW6_END cb=%lu stop=%s ready_seen=%lu admitted=%lu marked=%lu phase=%lu window_callbacks=%lu suppressed=%lu charged_bytes=%lu diagnostic_us=%llu dt_available=0 game_time_available=0 playhead_available=0 FRAME=FAIL\n",
        (unsigned long)callbacks_completed,failure_reason,(unsigned long)hw_policy.ready_seen,(unsigned long)hw6_admitted,
        (unsigned long)hw_policy.marked,(unsigned long)hw_policy.phase,(unsigned long)hw_policy.window_callbacks,
        (unsigned long)hw6_suppressed,(unsigned long)hw6_bytes,(unsigned long long)(hw6_diag_ticks*1000000/SYSCLOCK_ARM11));
}

static void hw_publish(GameplayState s,const char *boundary){
    /* Preserve exact before/after_input/after semantics. One compact journal,
     * no repeated state-file open. First observation plus all admitted samples. */
    int changed=hw6_state_changed(s);
    hw6_publish_state(s,boundary,changed);
    if(!s.ready && !gameplay_begin && current_frame%120 && hw_have_state && !changed)return;
    hw_last_state=s;hw_have_state=1;
    GameplayHidSnapshot h={0};
    LightLock_Lock(&hid_fifo_lock);h.latest=hid_fifo.latest;LightLock_Unlock(&hid_fifo_lock);
    h.now=svcGetSystemTick();
    double age=h.latest.ticks && h.now>=h.latest.ticks?(double)(h.now-h.latest.ticks)*1000/SYSCLOCK_ARM11:-1;
    report("HW_SAMPLE {\"frame\":%lu,\"boundary\":\"%s\",\"ready\":%d,\"reason\":%lu,\"blockers\":%lu,\"step\":%lu,\"marked\":%lu,\"axes\":[%d,%d],\"age_ms\":%.3f,\"stick\":%lu,\"owner\":%d,\"gesture\":%lu,\"anchor\":[%d,%d],\"analog\":[%.9g,%.9g,%.9g],\"position\":[%.9g,%.9g,%.9g],\"oracle\":%lu,\"player\":%lu,\"body\":%lu}\n",
        (unsigned long)current_frame,boundary,s.ready,(unsigned long)s.reason,(unsigned long)s.blockers,
        (unsigned long)gameplay_count,(unsigned long)hw_policy.marked,h.latest.cx,h.latest.cy,age,
        (unsigned long)s.stick,s.owner,(unsigned long)s.gesture,s.stick_anchor_x,s.stick_anchor_y,
        (double)s.analog[0],(double)s.analog[1],(double)s.analog[2],
        (double)s.position[0],(double)s.position[1],(double)s.position[2],(unsigned long)s.position_valid,
        (unsigned long)s.player,(unsigned long)s.root);
}

static int hw_after_callback(void){
    GameplayState s=gameplay_observe();u64 t=svcGetSystemTick(),now=loader_now_ms(),diag0=hw6_diag_ticks;
    u32 flags=__atomic_load_n(&hw6_resource_pending,__ATOMIC_ACQUIRE);
    if(menu_confirmation_frame && !menu_request_id)flags|=HW6_ACK;
    if((s.valid&1) && !s.modal)flags|=HW6_MODAL;
    u32 previous=hw_policy.flags,was_ready=hw_policy.ready_seen,was_marked=hw_policy.marked;
    hw6_observe_policy(&hw_policy,now,current_frame,flags,s.ready);
    if((hw_policy.flags&HW6_ACK) && !(previous&HW6_ACK))hw6_milestone("MENU_ACK");
    if((hw_policy.flags&HW6_MODAL) && !(previous&HW6_MODAL))hw6_milestone("MODAL_CLEARED");
    if((hw_policy.flags&HW6_CIN) && !(previous&HW6_CIN))hw6_milestone("CINEMATIC_RESOURCE_OPEN_OBSERVED");
    if(!was_ready && hw_policy.ready_seen)hw6_milestone("FIRST_READY");
    if(gameplay_begin && !hw6_admitted){hw6_admitted=1;hw6_milestone("GAMEPLAY_ADMITTED_AND_CALLBACK_COMPLETED");}
    u32 mark=__atomic_fetch_and(&hid_latched_control,~(u32)KEY_X,__ATOMIC_ACQ_REL)&KEY_X;
    int valid=hw6_input_frame==current_frame;
    u32 phase=hw_policy.phase;
    if(hw_policy.marked && hw6_charge(192))report("HW6_STEP cb=%lu phase=%lu input_valid=%d cx=%d cy=%d pad=%d owner=%d\n",(unsigned long)current_frame,(unsigned long)phase,valid,hw6_input_cx,hw6_input_cy,gameplay_pad.phase,s.owner);
    if(p9_developer && s.ready)hw6_motion(&hw_policy,now,mark!=0,gameplay_neutral(hw6_input_cx,hw6_input_cy),valid,hw6_input_cy,gameplay_pad.phase,s.owner);
    if(!was_marked && hw_policy.marked){hw6_milestone("TEST_MARKED");report("HW_MARK frame=%lu manual_window=1 callbacks=96 ms=600000\n",(unsigned long)current_frame);}
    if(phase!=hw_policy.phase && hw_policy.phase==6)hw6_milestone("TEST_COMPLETE");
    /* Bounded scene has <=800 pre-ready plus96 marked callbacks. Recording
     * these small timing rows permits actual median/p95 callback comparison. */
    if(scene_started){
        if(hw6_charge(192))report("HW6_TIME cb=%lu callback_us=%llu present_us=%llu observation_us=%llu wall_ms=%llu\n",(unsigned long)current_frame,(unsigned long long)(hw6_callback_ticks*1000000/SYSCLOCK_ARM11),(unsigned long long)(hw6_present_ticks*1000000/SYSCLOCK_ARM11),(unsigned long long)(hw6_diag_ticks*1000000/SYSCLOCK_ARM11),(unsigned long long)now);
    }
    if(s.ready){
        if(!p9_verbose_end)p9_verbose_end=current_frame+128;
        static const char *const instructions[]={"Center >=3 callbacks; X within120s","NEUTRAL: keep centered","FORWARD: hold Circle Pad up","STOP: release Circle Pad","BACKWARD: hold Circle Pad down","STOP: release Circle Pad","TEST COMPLETE / preparing shutdown"};
        char text[480];
        snprintf(text,sizeof(text),"Dead Space / HQ\nOriginal gameplay\ncb:%lu ready:%lu diagnostic:%lu\n%s [%lu]\ncontroller %.2f %.2f %.2f\nXYZ %.4f %.4f %.4f oracle:%lu\nHQ:%lu fallback:%lu\nCallback:%llu ms\nHOME/START: cooperative exit",
            (unsigned long)current_frame,(unsigned long)hw_policy.ready_callbacks,(unsigned long)hw_policy.window_callbacks,p9_developer?instructions[hw_policy.phase<=6?hw_policy.phase:0]:"Circle Pad: move / C-Stick: camera",(unsigned long)hw_policy.count,
            (double)s.analog[0],(double)s.analog[1],(double)s.analog[2],(double)s.position[0],(double)s.position[1],(double)s.position[2],(unsigned long)s.position_valid,(unsigned long)hq_good_count,(unsigned long)hq_fallback_count,(unsigned long long)hw_last_callback_ms);
        if(p9_developer || !DS_P8_HUD)screen(text);
    }else if(menu_confirmation_frame && current_frame%30==0){
        char text[192];snprintf(text,sizeof(text),"HW06 original transition / FRAME FAIL\ncb:%lu reason:%lu blockers:%02lx\nReadiness deadline95m; total105m\nHOME/START: cooperative exit",(unsigned long)current_frame,(unsigned long)s.reason,(unsigned long)s.blockers);screen(text);
    }
    hw6_diag_ticks=diag0+svcGetSystemTick()-t; /* Nested milestone writes counted once. Includes the phase UI. */
    if(hw_log_error || ds_hw_io_denied()){failure_reason="HW bounded output envelope failed; returned callback";return -1;}
    return hw6_check_budget()?-1:0;
}
