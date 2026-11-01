/* Original Android input callbacks only. Call on the render thread. */
#include "ds23_touch.h"
typedef void (*MenuKey)(DSJniHandle *,void *,int32_t,int32_t,int32_t) DS_JNI_SOFT;
static DS23Touch menu_touch;
static MenuKey menu_key_down,menu_key_up;
static int menu_input_attached,menu_pulse,menu_back;
static u32 menu_previous_keys;
static u32 menu_confirmation_frame;
static u32 menu_observed_selection,menu_last_pointer_frame;
/* These are observations of this original menu, never an image PASS oracle.
 * An already-selected row can activate the original scene. Until a stable
 * rendered selection is known, navigation emits nothing. */
static void menu_input_observe(u32 crc){
    if(menu_last_pointer_frame && current_frame<menu_last_pointer_frame+4)return;
    menu_observed_selection=(crc==0x7296717du || crc==0x223b5e75u)?1:crc==0x0ded835du?2:0;
}
static int menu_input_init(void){
    if(ds23_touch_init(&menu_touch,&bridge,320,240,
        (DS23Pointer)exported("Java_com_ea_blast_TouchSurfaceAndroid_NativeOnPointerEvent")))return -1;
    menu_key_down=(MenuKey)exported("Java_com_ea_blast_KeyboardAndroid_NativeOnKeyDown");
    menu_key_up=(MenuKey)exported("Java_com_ea_blast_KeyboardAndroid_NativeOnKeyUp");
    if(!menu_key_down || !menu_key_up)return -1;
    menu_input_attached=1;return 0;
}
static int menu_input_sample(u32 held){
    /* The accelerometer backend also calls hidScanInput. Own button edges
     * here so its HID scan cannot consume a menu press before this sample. */
    u32 down=held&~menu_previous_keys;menu_previous_keys=held;
    /* Physical keyboard module600, DEX (III)V: module,keyCode,isSystemKey.
     * B sends Android BACK4; Android's IsSystemKey list excludes BACK. */
    int back=(held&KEY_B)!=0;
    if(back!=menu_back){
        (back?menu_key_down:menu_key_up)(&bridge.base.env,NULL,600,4,0);
        menu_back=back;
        report("CONTROL frame=%lu B=%d module=600 key=4\n",(unsigned long)current_frame,back);
    }
#if !MENU_ALLOW_SCENE
    if(menu_confirmation_frame && current_frame>menu_confirmation_frame)
        return ds23_touch_sample(&menu_touch,0,0,0)<0?-1:0;
#endif
    u32 pressed=0,x=0,y=0;
    if(menu_pulse){menu_pulse=0;} /* Release a button tap exactly once. */
    else if(menu_touch.active){pressed=0;}
    else if(menu_observed_selection && (down&KEY_A ||
        (down&KEY_UP && menu_observed_selection!=1) || (down&KEY_DOWN && menu_observed_selection!=2))){
        pressed=1;menu_pulse=1;
        x=(down&KEY_A)?284:160;y=(down&KEY_A)?225:(down&KEY_UP)?103:134;
        if(down&KEY_A)menu_confirmation_frame=current_frame;
        menu_last_pointer_frame=current_frame;menu_observed_selection=0;
        report("CONTROL frame=%lu button=%s pointer=%lu,%lu\n",(unsigned long)current_frame,
            (down&KEY_A)?"A":(down&KEY_UP)?"UP":"DOWN",(unsigned long)x,(unsigned long)y);
    }
    return ds23_touch_sample(&menu_touch,pressed,x,y)<0?-1:0;
}
static int menu_input_close(void){
    if(!menu_input_attached)return 0;
    if(menu_back)menu_key_up(&bridge.base.env,NULL,600,4,0);
    int r=ds23_touch_close(&menu_touch);menu_input_attached=menu_back=menu_pulse=0;menu_previous_keys=menu_confirmation_frame=menu_observed_selection=menu_last_pointer_frame=0;return r;
}
