/* New3DS buttons -> original Android pointer pipeline, on render thread. */
#include "ds23_touch.h"
static DS23Touch menu_touch;
typedef void (*MenuKey)(DSJniHandle *,void *,int32_t,int32_t,int32_t) DS_JNI_SOFT;
static MenuKey menu_key_down,menu_key_up;
static int menu_input_attached,menu_pulse,menu_back;
static u32 menu_previous_keys,menu_confirmation_frame,menu_last_pointer_frame;
static int menu_input_init(void){
    if(ds23_touch_init(&menu_touch,&bridge,320,240,
        (DS23Pointer)exported("Java_com_ea_blast_TouchSurfaceAndroid_NativeOnPointerEvent")))return -1;
    menu_key_down=(MenuKey)exported("Java_com_ea_blast_KeyboardAndroid_NativeOnKeyDown");
    menu_key_up=(MenuKey)exported("Java_com_ea_blast_KeyboardAndroid_NativeOnKeyUp");
    if(!menu_key_down || !menu_key_up)return -1;
    menu_input_attached=1;return 0;
}
static int menu_input_sample(u32 held){
    u32 down=held&~menu_previous_keys;menu_previous_keys=held;
    MenuEngineState s=menu_engine_state();
    if(current_frame%120==0 || (down&(KEY_A|KEY_B|KEY_UP|KEY_DOWN)) ||
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
    }
#if !MENU_ALLOW_SCENE
    if(menu_confirmation_frame && current_frame>menu_confirmation_frame)
        return ds23_touch_sample(&menu_touch,0,0,0)<0?-1:0;
#endif
    u32 pressed=0,x=0,y=0;
    const char *button="none",*reason="not_ready";
    if(menu_pulse){menu_pulse=0;reason="release";}
    else if(menu_touch.active){reason="release";}
    else if(menu_last_pointer_frame && current_frame<menu_last_pointer_frame+4){reason="pending";}
    else if(s.ready && !(held&KEY_B) && (down&KEY_A ||
        (down&KEY_UP && s.selection!=1) || (down&KEY_DOWN && s.selection!=2))){
        pressed=1;menu_pulse=1;
        button=(down&KEY_A)?"A":(down&KEY_UP)?"UP":"DOWN";
        x=(down&KEY_A)?284:160;
        y=(down&KEY_A)?225:(down&KEY_UP)?103:134;
        if(down&KEY_A)menu_confirmation_frame=current_frame;
        menu_last_pointer_frame=current_frame;
        report("CONTROL frame=%lu button=%s pointer=%lu,%lu original_selection=%lu\n",(unsigned long)current_frame,button,(unsigned long)x,(unsigned long)y,(unsigned long)s.selection);
    }else if(s.ready)reason="selected_row_or_no_edge";
    if(!pressed && (down&(KEY_A|KEY_UP|KEY_DOWN) || (down&KEY_B && !s.ready)))
        report("HID_REJECT frame=%lu mask=%08lx reason=%s\n",(unsigned long)current_frame,(unsigned long)down,reason);
    return ds23_touch_sample(&menu_touch,pressed,x,y)<0?-1:0;
}
static int menu_input_close(void){
    if(!menu_input_attached)return 0;
    if(menu_back)menu_key_up(&bridge.base.env,NULL,600,4,0);
    int r=ds23_touch_close(&menu_touch);menu_input_attached=menu_pulse=menu_back=0;
    menu_previous_keys=menu_confirmation_frame=menu_last_pointer_frame=0;return r;
}
