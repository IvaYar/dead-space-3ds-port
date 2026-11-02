/* New3DS buttons -> original Android pointer pipeline, on render thread. */
#include "ds23_touch.h"
static DS23Touch menu_touch;
typedef void (*MenuKey)(DSJniHandle *,void *,int32_t,int32_t,int32_t) DS_JNI_SOFT;
static MenuKey menu_key_down,menu_key_up;
static int menu_input_attached,menu_pulse,menu_back;
static u32 menu_previous_keys,menu_confirmation_frame,menu_last_pointer_frame;
static DS23Pointer menu_original_pointer;
static u32 menu_tap_id,menu_request_id,menu_request_selection;
static void DS_JNI_SOFT menu_pointer_trace(DSJniHandle *env,void *object,int32_t event,int32_t module,int32_t id,float x,float y){
    u64 t=svcGetSystemTick();
    report("HIDCOMPAT ms=%.3f frame=%lu id=%lu event=%08lx module=%ld x=%.1f y=%.1f ENTER\n",hid_time_ms(t),(unsigned long)current_frame,(unsigned long)menu_tap_id,(unsigned long)event,(long)module,(double)x,(double)y);
    menu_original_pointer(env,object,event,module,id,x,y);
    report("HIDORIGINAL ms=%.3f frame=%lu id=%lu event=%08lx RETURN duration_ms=%.3f\n",hid_time_ms(svcGetSystemTick()),(unsigned long)current_frame,(unsigned long)menu_tap_id,(unsigned long)event,(double)(svcGetSystemTick()-t)*1000/SYSCLOCK_ARM11);
}
static int menu_input_init(void){
    menu_original_pointer=(DS23Pointer)exported("Java_com_ea_blast_TouchSurfaceAndroid_NativeOnPointerEvent");
    if(ds23_touch_init(&menu_touch,&bridge,320,240,menu_pointer_trace))return -1;
    menu_key_down=(MenuKey)exported("Java_com_ea_blast_KeyboardAndroid_NativeOnKeyDown");
    menu_key_up=(MenuKey)exported("Java_com_ea_blast_KeyboardAndroid_NativeOnKeyUp");
    if(!menu_key_down || !menu_key_up)return -1;
    menu_input_attached=1;return 0;
}
static int menu_input_sample(u32 held){
    (void)held;MenuEngineState s=menu_engine_state();
    if(hid_menu_sample(s.ready,!menu_touch.active && !menu_pulse && !menu_request_id,&held))return -1;
    u32 down=held&~menu_previous_keys;menu_previous_keys=held;
    if(current_frame%120==0 || (down&(KEY_A|KEY_B|KEY_DUP|KEY_DDOWN)) ||
       (menu_last_pointer_frame && current_frame<=menu_last_pointer_frame+5))
        report("MENUSTATE frame=%lu layer=%08lx phase=%lu transition=%lu closing=%lu ready=%d selection=%lu held=%08lx down=%08lx widgets=%08lx/%lu,%08lx/%lu\n",
            (unsigned long)current_frame,(unsigned long)s.layer,(unsigned long)s.phase,(unsigned long)s.transition,(unsigned long)s.closing,s.ready,(unsigned long)s.selection,(unsigned long)held,(unsigned long)down,(unsigned long)s.normal,(unsigned long)s.normal_state,(unsigned long)s.easy,(unsigned long)s.easy_state);
    /* Native keyboard BACK4, module600, isSystemKey0, as in Android DEX.
     * The first LayerDifficulty deliberately ignores BTN_BACK (a590c).
     * Deliver the original event; never force a manual pop or scene change. */
    int back=(held&KEY_B) && s.ready;
    if(back!=menu_back){
        (back?menu_key_down:menu_key_up)(&bridge.base.env,NULL,600,4,0);menu_back=back;
        report("CONTROL frame=%lu B=%d module=600 key=4\n",(unsigned long)current_frame,back);
        report("HIDORIGINAL ms=%.3f frame=%lu id=%lu BACK=%d RETURN\n",hid_time_ms(svcGetSystemTick()),(unsigned long)current_frame,(unsigned long)hid_event_id,back);
    }
#if !MENU_ALLOW_SCENE
    if(menu_confirmation_frame && current_frame>menu_confirmation_frame)
        return ds23_touch_sample(&menu_touch,0,0,0)<0?-1:0;
#endif
    u32 pressed=0,x=0,y=0;
    const char *button="none",*reason="not_ready";
    if(menu_pulse){menu_pulse=0;reason="release";}
    else if(menu_touch.active){reason="release";}
    else if(s.ready && !(held&KEY_B) && (down&KEY_A ||
        (down&KEY_DUP && s.selection!=1) || (down&KEY_DDOWN && s.selection!=2))){
        pressed=1;menu_pulse=1;
        button=(down&KEY_A)?"A":(down&KEY_DUP)?"UP":"DOWN";
        x=(down&KEY_A)?284:160;
        y=(down&KEY_A)?225:(down&KEY_DUP)?103:134;
        if(down&KEY_A)menu_confirmation_frame=current_frame;
        menu_last_pointer_frame=current_frame;menu_tap_id=hid_event_id;
        menu_request_id=hid_event_id;menu_request_selection=(down&KEY_A)?0:(down&KEY_DUP)?1:2;
        report("HIDMAP ms=%.3f frame=%lu id=%lu raw_to_pointer=%lu,%lu target_selection=%lu\n",hid_time_ms(svcGetSystemTick()),(unsigned long)current_frame,(unsigned long)hid_event_id,(unsigned long)x,(unsigned long)y,(unsigned long)menu_request_selection);
        report("CONTROL frame=%lu button=%s pointer=%lu,%lu original_selection=%lu\n",(unsigned long)current_frame,button,(unsigned long)x,(unsigned long)y,(unsigned long)s.selection);
    }else if(s.ready)reason="selected_row_or_no_edge";
    if(!pressed && (down&(KEY_A|KEY_DUP|KEY_DDOWN) || (down&KEY_B && !s.ready)))
        report("HID_REJECT frame=%lu mask=%08lx reason=%s\n",(unsigned long)current_frame,(unsigned long)down,reason);
    return ds23_touch_sample(&menu_touch,pressed,x,y)<0?-1:0;
}
static int menu_input_close(void){
    if(!menu_input_attached)return 0;
    if(menu_back)menu_key_up(&bridge.base.env,NULL,600,4,0);
    int r=ds23_touch_close(&menu_touch);menu_input_attached=menu_pulse=menu_back=0;
    menu_previous_keys=menu_confirmation_frame=menu_last_pointer_frame=0;return r;
}

static void menu_input_ack(void){
    if(!menu_request_id)return;
    MenuEngineState s=menu_engine_state();
    if((menu_request_selection && s.ready && s.selection==menu_request_selection) ||
       (!menu_request_selection && s.phase==3 && s.closing)){
        report("HIDACK ms=%.3f frame=%lu id=%lu phase=%lu closing=%lu selection=%lu\n",hid_time_ms(svcGetSystemTick()),(unsigned long)current_frame,(unsigned long)menu_request_id,(unsigned long)s.phase,(unsigned long)s.closing,(unsigned long)s.selection);menu_request_id=0;
    }
}
