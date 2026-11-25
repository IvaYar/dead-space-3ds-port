/* Pure one-pointer state machine; one call per original render callback.
 * Borrow the menu's DS23. Positive libctru cy means up; Android y grows down. */
typedef struct {int mode,armed,phase;u32 x,y;} GameplayPad;
#define GAMEPLAY_ACTIVATION_SOURCE_DX 12u
static int gameplay_neutral(int cx,int cy){return cx*cx+cy*cy<=24*24;}
static int gameplay_axis(int value){return value>156?156:value< -156?-156:value;}
static int gameplay_pad_sample(GameplayPad *p,DS23Touch *touch,int ready,int cx,int cy,u32 ax,u32 ay){
    if(p->mode!=ready){
        p->mode=ready;p->armed=p->phase=0;
        return ds23_touch_sample_hold(touch,0,0,0)<0?-1:0;
    }
    if(!ready)return 0;
    if(!p->armed){if(gameplay_neutral(cx,cy))p->armed=1;return 0;}
    if(gameplay_neutral(cx,cy)){
        p->phase=0;return ds23_touch_sample_hold(touch,0,0,0)<0?-1:0;
    }
    /* Source x80 DOWN -> x92 activation; DS23 alone scales to native100/115.
     * Original surface drops identical XY. Activation rebases the original
     * stick; control uses that SAME new anchor to avoid lateral steering. */
    if(!p->phase){p->x=ax;p->y=ay;p->phase=1;}
    else if(p->phase==1){p->x=ax+GAMEPLAY_ACTIVATION_SOURCE_DX;p->phase=2;}
    else {
        int x=(int)(ax+GAMEPLAY_ACTIVATION_SOURCE_DX)+gameplay_axis(cx)*32/156;
        int y=(int)ay-gameplay_axis(cy)*32/156;
        p->x=x<0?0:x>319?319:(u32)x;p->y=y<0?0:y>239?239:(u32)y;
        p->phase=3;
    }
    return ds23_touch_sample_hold(touch,1,p->x,p->y)<0?-1:0;
}
