/* Opt-in only. Included AFTER the unchanged menu adapter; borrows menu_touch.
 * All calls here run on MAIN immediately before original NativeOnDrawFrame. */
#include "native_gameplay_pad.h"
#include "native_gameplay_observer.h"
#include "native_gameplay_freshness.h"
static GameplayPad gameplay_pad;
static u32 gameplay_begin,gameplay_count,gameplay_identity,gameplay_ax,gameplay_ay;
static int gameplay_previous_ready,gameplay_menu_neutral;
static GameplayState gameplay_pre;
static int hw6_input_cx,hw6_input_cy;static u32 hw6_input_frame;
static u32 gameplay_input_reason,gameplay_stale_inactive,gameplay_stale_active,gameplay_diag_lines;
static const char *gameplay_reason_name(u32 code){
    switch(code){
        case GP_INPUT_THREAD:return "THREAD";case GP_INPUT_COLLECTOR:return "COLLECTOR_STOPPED";
        case GP_INPUT_FIFO:return "HID_STATE";case GP_INPUT_CLOCK:return "CLOCK_FUTURE";
        case GP_INPUT_TOUCH:return "DS23_STATE";case GP_INPUT_MENU:return "MENU_ADAPTER";
        case GP_INPUT_SAMPLE:return "DS23_SAMPLE";case GP_INPUT_RELEASE:return "DS23_RELEASE";
        case GP_INPUT_STALE_RELEASE:return "STALE_RELEASE";case GP_INPUT_STALE_INACTIVE:return "STALE_INACTIVE";
        case GP_INPUT_FRESH_NEUTRAL:return "WAIT_FRESH_NEUTRAL";default:return "OK";
    }
}
static void gameplay_input_diagnostic(u32 code,GameplayState s,const GameplayHidSnapshot *h,int fatal){
    gameplay_input_reason=code;
    /* At most8 soft messages plus one per120 callbacks; hard failures always
     * get their complete record. Existing journal only, no new queue/file. */
    if(!fatal && !menu_touch.active && gameplay_diag_lines>=8 && current_frame%120)return;
    ++gameplay_diag_lines;
    double age=h->latest.ticks && h->now>=h->latest.ticks?(double)(h->now-h->latest.ticks)*1000/SYSCLOCK_ARM11:-1;
    report("GP_INPUT code=%lu name=%s fatal=%d frame=%lu route=%s readiness=%lu world_phase=%lu hud_phase=%lu/%lu age_ms=%.3f now=%llu snapshot=%llu collector=%lu/%lu scans=%lu invalid=%lu overflow=%lu fifo=%lu/%lu index=%lu pointer=%lu gesture=%d armed=%d stale=%lu/%lu\n",
        (unsigned long)code,gameplay_reason_name(code),fatal,(unsigned long)current_frame,s.ready?"gameplay":"intro_menu",
        (unsigned long)s.reason,(unsigned long)s.world_phase,(unsigned long)s.hud_phase,(unsigned long)s.hud_mode,age,
        (unsigned long long)h->now,(unsigned long long)h->latest.ticks,(unsigned long)h->alive,(unsigned long)h->stop,
        (unsigned long)h->scans,(unsigned long)h->invalid,(unsigned long)h->overflow,(unsigned long)h->count,(unsigned long)h->head,
        (unsigned long)h->latest.index,(unsigned long)menu_touch.active,gameplay_pad.phase,gameplay_pad.armed,
        (unsigned long)gameplay_stale_inactive,(unsigned long)gameplay_stale_active);
}
static int gameplay_input_fail(u32 code,GameplayState s,const GameplayHidSnapshot *h){
    gameplay_input_diagnostic(code,s,h,1);
    failure_reason=gameplay_reason_name(code);return -1;
}
static int gameplay_anchor(GameplayState s,u32 *ax,u32 *ay){
    /* Find an interior point of THIS Universal SD stick's actual predicate,
     * in source320x240 coordinates. No Xperia coordinates/module1100. */
    u32 filter=gameplay_word(s.stick,0x10);
    for(int y=180;y>=60;y-=20)for(int x=80;x>=20;x-=20){
        int px=x*(int)bridge.platform.width/320,py=y*(int)bridge.platform.height/240;
        int activation_px=(x+(int)GAMEPLAY_ACTIVATION_SOURCE_DX)*(int)bridge.platform.width/320;
        if(gameplay_hit(filter,px,py,0)>0 && gameplay_hit(filter,px,py-32,0)>0 && gameplay_hit(filter,px,py+32,0)>0 &&
           gameplay_hit(filter,activation_px,py,0)>0 && gameplay_hit(filter,activation_px,py-32,0)>0 &&
           gameplay_hit(filter,activation_px,py+32,0)>0){*ax=(u32)x;*ay=(u32)y;return 1;}
    }
    return 0;
}
static void hw_publish(GameplayState,const char *);
static void gameplay_publish(GameplayState s,const char *boundary){hw_publish(s,boundary);}
static int gameplay_release(void){
    p7_camera_release();
    gameplay_pad.phase=gameplay_pad.armed=0;
    return ds23_touch_sample_hold(&menu_touch,0,0,0)<0?-1:0;
}
static int gameplay_input_sample(u32 held){
    GameplayHidSnapshot h={0};GameplayState absent={0};
    u32 thread=0;Result thread_result=svcGetThreadId(&thread,CUR_THREAD_HANDLE);
    if(R_FAILED(thread_result) || thread!=main_thread_id){h.now=svcGetSystemTick();return gameplay_input_fail(GP_INPUT_THREAD,absent,&h);}
    LightLock_Lock(&hid_fifo_lock);
    h.latest=hid_fifo.latest;h.scans=hid_fifo.scans;h.invalid=hid_fifo.invalid;h.overflow=hid_fifo.overflow;
    h.count=hid_fifo.count;h.head=hid_fifo.head;h.initialized=hid_fifo.initialized;
    LightLock_Unlock(&hid_fifo_lock);
    h.alive=hid_collector_thread!=NULL;h.stop=__atomic_load_n(&hid_collector_stop,__ATOMIC_ACQUIRE);
    h.now=svcGetSystemTick(); /* Same clock domain as collector; AFTER the copy. */
    int error=gameplay_snapshot_error(&h);
    if(error)return gameplay_input_fail((u32)error,absent,&h);
    if(!menu_input_attached || menu_touch.magic!=0x44533233u || menu_touch.bridge!=&bridge ||
       bridge.magic!=0x44533130u || !menu_touch.emit || menu_touch.active>1 ||
       menu_touch.source_width!=320 || menu_touch.source_height!=240 ||
       (menu_touch.active && (menu_touch.x>=320 || menu_touch.y>=240)))return gameplay_input_fail(GP_INPUT_TOUCH,absent,&h);
    int fresh=gameplay_snapshot_fresh(&h);
    GameplayState s=gameplay_observe();
    int ready=s.ready;
    if(ready && gameplay_previous_ready && gameplay_identity!=s.stick){
        if(gameplay_release())return gameplay_input_fail(GP_INPUT_RELEASE,s,&h);
        gameplay_pad.mode=0;gameplay_previous_ready=0;
        if(gameplay_begin){if(p9_developer){failure_reason="GAMEPLAY stick identity changed";return 1;}gameplay_begin=0;}
    }
    if(ready && !gameplay_previous_ready){
        ready=gameplay_anchor(s,&gameplay_ax,&gameplay_ay);
        if(!ready){s.ready=0;s.reason=7;}
        gameplay_identity=s.stick;
    }
    gameplay_publish(s,"before");gameplay_pre=s;
    if(ready!=gameplay_previous_ready){
        gameplay_menu_neutral=0;gameplay_previous_ready=ready;
        if(gameplay_release())return gameplay_input_fail(GP_INPUT_RELEASE,s,&h);
        gameplay_pad.mode=0;
        if(gameplay_begin && !ready){if(p9_developer){failure_reason="GAMEPLAY readiness lost; gesture released";return 1;}gameplay_begin=0;}
    }
    if(ready){
        u32 ignored;if(hid_menu_sample(0,1,&ignored))return gameplay_input_fail(GP_INPUT_MENU,s,&h);
        if(menu_back){menu_key_up(&bridge.base.env,NULL,600,4,0);menu_back=0;}
        if(!gameplay_begin){gameplay_begin=current_frame;report("GAMEPLAY_ADMIT frame=%lu anchor=%lu,%lu source=320x240 native=%lux%lu pointer=0 module=1000 cap=hardware\n",(unsigned long)current_frame,(unsigned long)gameplay_ax,(unsigned long)gameplay_ay,(unsigned long)bridge.platform.width,(unsigned long)bridge.platform.height);}
#if GAMEPLAY_DIAGNOSTIC
        if(gameplay_count>=32){if(gameplay_release())return gameplay_input_fail(GP_INPUT_RELEASE,s,&h);failure_reason="GAMEPLAY diagnostic callback cap32";return 1;}
#endif
        if(!fresh){
            ++gameplay_stale_active;
            gameplay_input_diagnostic(GP_INPUT_STALE_RELEASE,s,&h,0);
            /* UP is processed by the next original draw, never reuse stale
             * axes. A new gesture needs fresh neutral, then fresh deflection. */
            if(gameplay_release())return gameplay_input_fail(GP_INPUT_RELEASE,s,&h);
            return 0;
        }
        if(gameplay_input_reason==GP_INPUT_STALE_RELEASE)gameplay_input_diagnostic(GP_INPUT_FRESH_NEUTRAL,s,&h,0);
        p7_camera_before();
        u32 old=menu_touch.events;
        hw6_input_cx=h.latest.cx;hw6_input_cy=h.latest.cy;hw6_input_frame=current_frame;
        u64 p7_dispatch=svcGetSystemTick();
        int r=gameplay_pad_sample(&gameplay_pad,&menu_touch,1,h.latest.cx,h.latest.cy,gameplay_ax,gameplay_ay);
        /* Same DOWN -> activation MOVE -> target MOVE, in original order.
         * Only the first fresh, armed deflection uses this bounded burst. */
        if(!r && gameplay_pad.phase==1){
            r=gameplay_pad_sample(&gameplay_pad,&menu_touch,1,h.latest.cx,h.latest.cy,gameplay_ax,gameplay_ay);
            if(!r)r=gameplay_pad_sample(&gameplay_pad,&menu_touch,1,h.latest.cx,h.latest.cy,gameplay_ax,gameplay_ay);
        }
        report("P7_INPUT cb=%lu sample_age_us=%llu JNI_batch_us=%llu events=%lu phase=%d\n",(unsigned long)current_frame,
          (unsigned long long)((p7_dispatch-h.latest.ticks)*1000000/SYSCLOCK_ARM11),
          (unsigned long long)((svcGetSystemTick()-p7_dispatch)*1000000/SYSCLOCK_ARM11),
          (unsigned long)(menu_touch.events-old),gameplay_pad.phase);
        report("GAMEPLAY_INPUT frame=%lu step=%lu collector_circle=%d,%d phase=%d armed=%d events=%lu source_xy=%lu,%lu\n",(unsigned long)current_frame,(unsigned long)gameplay_count,h.latest.cx,h.latest.cy,gameplay_pad.phase,gameplay_pad.armed,(unsigned long)(menu_touch.events-old),(unsigned long)menu_touch.x,(unsigned long)menu_touch.y);
        if(menu_touch.events!=old)gameplay_publish(gameplay_observe(),"after_input");
        if(!r)p7_camera_sample(1);
        return r?gameplay_input_fail(GP_INPUT_SAMPLE,s,&h):0;
    }
    if(!fresh){++gameplay_stale_inactive;gameplay_input_diagnostic(GP_INPUT_STALE_INACTIVE,s,&h,0);}
    /* No gameplay-specific freshness gate or neutral barrier before the first
     * gameplay mode. The original menu owns its existing button FIFO. */
    if(gameplay_begin && !gameplay_menu_neutral){
        u32 ignored;if(hid_menu_sample(0,1,&ignored))return gameplay_input_fail(GP_INPUT_MENU,s,&h);
        if(fresh && gameplay_neutral(h.latest.cx,h.latest.cy))gameplay_menu_neutral=1;
        return 0;
    }
    return menu_input_sample(held)?gameplay_input_fail(GP_INPUT_MENU,s,&h):0;
}
static void gameplay_after_callback(void){
    if(gameplay_begin)++gameplay_count;
    GameplayState s=gameplay_observe();gameplay_publish(s,"after");
}
