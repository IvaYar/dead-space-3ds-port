/* Independent original Xperia touchpad, never touches the DS23 screen owner.
 * One bounded UP/DOWN/MOVE pulse per original callback; no input event queue. */
static int p7_camera_enabled=1,p7_camera_armed,p7_camera_active;
static float p7_camera_x,p7_camera_y;
static u32 p7_camera_events,p7_camera_pulses;
static void p7_camera_emit(u32 event,float x,float y){
    menu_original_pointer(&bridge.base.env,NULL,(int32_t)event,1100,2,x,y);
    ++p7_camera_events;
    report("P7_CAMERA event=%08lx module=1100 id=2 x=%.5g y=%.5g cb=%lu\n",(unsigned long)event,(double)x,(double)y,(unsigned long)current_frame);
}
static void p7_camera_release(void){
    if(p7_camera_active)p7_camera_emit(DS23_UP,p7_camera_x,p7_camera_y);
    p7_camera_active=p7_camera_armed=0;
}
static void p7_camera_init(void){
    char p[192];snprintf(p,sizeof(p),"%scstick-off.txt",ROOT);FILE *f=fopen(p,"r");
    if(f){p7_camera_enabled=0;fclose(f);}
    report("P7_CAMERA enabled=%d path=original_Xperia_module1100 right_pointer=2 deadzone=12 range=156\n",p7_camera_enabled);
}
static float p7_camera_axis(int v){
    int a=v<0?-v:v;if(a<=12)return 0;if(a>156)a=156;
    return (float)(v<0?-(a-12):a-12)/144;
}
static void p7_camera_before(void){
    /* Release the previous right-pad pulse before a new left-pad DOWN.
     * Original event order keeps the movement slot stable at owner0. */
    if(p7_camera_active){p7_camera_emit(DS23_UP,p7_camera_x,p7_camera_y);p7_camera_active=0;}
}
static void p7_camera_sample(int ready){
    P7CStick s;LightLock_Lock(&hid_fifo_lock);s=p7_cstick;LightLock_Unlock(&hid_fifo_lock);
    u64 now=svcGetSystemTick();
    int fresh=s.valid && s.sampled && now>=s.sampled && now-s.sampled<=SYSCLOCK_ARM11/4;
    float x=p7_camera_axis(s.x),y=p7_camera_axis(s.y);
    if(!p7_camera_enabled || !ready || !fresh){p7_camera_release();return;}
    if(!p7_camera_armed){if(x==0 && y==0)p7_camera_armed=1;return;}
    /* Finish previous gesture before a new pulse, including neutral. */
    if(p7_camera_active){p7_camera_emit(DS23_UP,p7_camera_x,p7_camera_y);p7_camera_active=0;}
    if(x==0 && y==0)return;
    float w=960,h=544; /* Verified Xperia touchpad input domain, separate from LCD. */
    float bx=w*.81875f,by=h*(180.0f/544.0f);
    p7_camera_x=bx+w*(155.0f/960.0f)*x;
    p7_camera_y=by+h*(105.0f/544.0f)*y; /* Xperia pad Y differs from Android touchscreen Y: positive HID means look UP. */
    p7_camera_emit(DS23_DOWN,bx,by);p7_camera_emit(DS23_MOVE,p7_camera_x,p7_camera_y);
    p7_camera_active=1;++p7_camera_pulses;
    report("P7_CSTICK cb=%lu raw=%d,%d age_us=%llu pulses=%lu\n",(unsigned long)current_frame,s.x,s.y,(unsigned long long)((now-s.sampled)*1000000/SYSCLOCK_ARM11),(unsigned long)p7_camera_pulses);
}
