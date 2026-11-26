/* Universal SD 1.1.33 only, read-only object observations at main boundaries.
 * Offsets/position v2 are checked by test_native_gameplay_observer.py.
 * No hooks, donor writes, controller setters or lifecycle calls. */
typedef struct {
    u32 world,hud,player,stick,root,reason,world_phase,hud_phase,hud_mode,player_phase;
    u32 modal,transition,world44,player_flags,blockers,position_valid,body_vtable,provider,userdata,backlink,tutorial;
    u32 stick_snapshot_valid,gesture,normalized,deadzone,run_threshold,relative_mode,curve,invert_y;
    int stick_anchor_x,stick_anchor_y;
    int ready,owner;float analog[4],position[4];
    u32 scene,valid,fade_elapsed_raw,fade_duration_raw;
} GameplayState;
static u32 gameplay_word(u32 p,u32 off){return *(const u32 *)(p+off);}
static int gameplay_class(u32 p,u32 bytes,u32 vt){return menu_state_span(p,bytes) && gameplay_word(p,0)==(u32)image+vt;}
/* Evaluate only verified original read-only hit predicates. Unknown classes,
 * excessive depth/count, malformed spans fail closed. No donor calls. */
static int gameplay_hit(u32 p,int x,int y,u32 depth){
    if(depth>6 || !menu_state_span(p,0x24))return -1;
    u32 vt=gameplay_word(p,0);
    if(vt<(u32)image || vt-(u32)image>info.image_size-12)return -1;
    if(!*(const u8 *)(p+8))return 0;
    u32 fn=gameplay_word(vt,8)-(u32)image;
    if(fn==0x79378){
        int a=(int)gameplay_word(p,12),b=(int)gameplay_word(p,16);
        int w=(int)gameplay_word(p,20),h=(int)gameplay_word(p,24);
        return a>=-4096 && b>=-4096 && w>0 && w<=4096 && h>0 && h<=4096 && x>=a && x<a+w && y>=b && y<b+h;
    }
    if(fn==0x79414){
        int a=(int)gameplay_word(p,12),b=(int)gameplay_word(p,16),r=(int)gameplay_word(p,20);
        if(a< -4096 || a>4096 || b< -4096 || b>4096 || r<=0 || r>4096)return -1;
        return (x-a)*(x-a)+(y-b)*(y-b)<r*r;
    }
    if(fn==0x7e4f4){
        u32 op=gameplay_word(p,12),a=gameplay_word(p,16),b=gameplay_word(p,28);
        if(op>2 || !a || !b)return -1;
        int aa=gameplay_hit(a,x,y,depth+1),bb=gameplay_hit(b,x,y,depth+1);
        if(aa<0 || bb<0)return -1;
        return op==0?(aa||bb):op==1?(aa&&bb):(aa&&!bb);
    }
    if(fn==0x7e5fc){
        u32 a=gameplay_word(p,12),b=gameplay_word(p,16);
        if(b<a || (b-a)%12 || b-a>12*16 || !menu_state_span(a,b-a))return -1;
        int hit=0;
        for(;a<b;a+=12){int r=gameplay_hit(gameplay_word(a,0),x,y,depth+1);if(r<0)return -1;hit|=r;}
        return hit;
    }
    return -1;
}
static GameplayState gameplay_observe(void){
    GameplayState s={0};s.owner=-2;s.reason=1;
    u32 app=*(const u32 *)(image+0x44a1b4);
    if(!menu_state_span(app,0xdc))return s;
    s.valid=1;
    s.modal=gameplay_word(app,0xd8);
    s.world=gameplay_word(app,0xcc);
    if(!gameplay_class(s.world,0x179c,0x427e60))return s;
    s.valid|=2;
    s.fade_elapsed_raw=gameplay_word(s.world,0x1c);s.fade_duration_raw=gameplay_word(s.world,0x20);
    s.transition=gameplay_word(s.world,0x18);s.world44=gameplay_word(s.world,0x44);
    s.reason=2;s.world_phase=gameplay_word(s.world,0x16a0);
    s.hud=s.world+0x260;s.hud_phase=gameplay_word(s.hud,0x298);s.hud_mode=gameplay_word(s.hud,0x2a4);
    u32 scene=gameplay_word(s.world,0x58);s.scene=scene;
    if(!menu_state_span(scene,0xd8) || !gameplay_class(s.hud,0x1440,0x426e70))return s;
    s.valid|=4;
    s.player=gameplay_word(scene,0xd4);
    if(!gameplay_class(s.player,0x5d8,0x4312a8))return s;
    s.valid|=8;
    s.reason=3;s.player_phase=gameplay_word(s.player,0x210);
    s.player_flags=gameplay_word(s.player,0x1b4);s.tutorial=gameplay_word(s.hud,0x1a4);
    s.root=gameplay_word(s.player,0x58);
    /* Player owns the original physics body, not a parent-relative model node.
     * 14d428 -> 223e30 builds it;14d6d8 installs userdata->player backlink.
     * Body matrix is at +4: three basis rows, then xyz at +34/+38/+3c.
     * +10/+20/+30 are padding, NOT translation. See ARM oracle-v2 audit. */
    if(!menu_state_span(s.root,0x20c))return s;
    s.body_vtable=gameplay_word(s.root,0);s.provider=gameplay_word(s.root,0x1e8);
    s.userdata=gameplay_word(s.root,0xe4);
    if(menu_state_span(s.userdata,12))s.backlink=gameplay_word(s.userdata,4);
    memcpy(s.analog,(const void *)(s.player+0x1bc),sizeof(s.analog));
    if(s.body_vtable!=(u32)image+0x437130 || s.backlink!=s.player)return s;
    typedef u32 (*PositionPointer)(u32) DS_IO_SOFT;
    typedef void (*TransformPoint)(float *,u32,const float *) DS_IO_SOFT;
    u32 pos=((PositionPointer)(image+0x7ea50))(s.player);
    if(pos!=s.root+0x34)return s;
    memcpy(s.position,(const void *)pos,sizeof(s.position));
    const float origin[4]={0,0,0,0};float transformed[4];
    ((TransformPoint)(image+0x1f57f0))(transformed,s.root+4,origin);
    for(u32 i=0;i<4;++i)if(s.position[i]!=transformed[i])return s;
    if(gameplay_word(s.root,0x10) || gameplay_word(s.root,0x20) || gameplay_word(s.root,0x30) || s.position[3]!=0)return s;
    for(u32 i=0;i<3;++i)if(!(s.position[i]>-1000000 && s.position[i]<1000000 && s.analog[i]>=-2 && s.analog[i]<=2))return s;
    s.valid|=16;
    s.position_valid=2; /* v2: checked original body world/scene translation */
    s.reason=4;
    if(!gameplay_class(s.hud+0x10,0xec,0x4272b0))return s;
    s.stick=gameplay_word(s.hud+0x10,0xd4);
    if(!gameplay_class(s.stick,0x6c,0x4270a8))return s;
    /* All fields lie in the already validated0x6c stick span. Observe only;
     * curve is recorded as an opaque pointer, never dereferenced. */
    s.valid|=32;
    s.stick_snapshot_valid=1;s.gesture=*(const u8 *)(s.stick+0x1c);
    s.stick_anchor_x=(int)gameplay_word(s.stick,0x24);s.stick_anchor_y=(int)gameplay_word(s.stick,0x28);
    s.normalized=*(const u8 *)(s.stick+0x3d);s.deadzone=gameplay_word(s.stick,0x40);
    s.run_threshold=gameplay_word(s.stick,0x4c);s.relative_mode=*(const u8 *)(s.stick+0x54);
    s.curve=gameplay_word(s.stick,0x58);s.invert_y=*(const u8 *)(s.stick+0x60);
    s.owner=(int)gameplay_word(s.stick,0x20);
    s.reason=5;
    if(gameplay_word(s.hud,4)!=scene || gameplay_word(s.hud+0x10,0x10)!=scene ||
       gameplay_word(s.stick,8)!=s.player || gameplay_word(s.stick,0x50)!=1 || !*(const u8 *)(s.stick+4) ||
       s.owner< -1 || s.owner>0)return s;
    /* World+44 owns the physics/collision subsystem (b5ca4 ->21d628,
     * allocation0x11c, vtable437088). It must exist and retain its class.
     * A missing/disposed/corrupt subsystem is never a gameplay bypass.
     * LayerDifficulty's closing byte does not describe LayerGameWorld. */
    s.valid|=64;
    s.reason=6;
    if(s.modal)s.blockers|=1;
    if(s.transition)s.blockers|=2;
    if(!gameplay_class(s.world44,0x11c,0x437088))s.blockers|=4;
    if(s.world_phase!=1 && s.world_phase!=2)s.blockers|=8;
    if(s.hud_phase>1)s.blockers|=16;
    if(s.hud_mode>1)s.blockers|=32;
    if(s.player_flags&2)s.blockers|=64;
    switch(s.player_phase){case 1:case 8:case 9:case 10:case 11:case 12:case 13:case 14:case 15:case 16:case 17:case 25:case 26:case 27:case 29:case 30:case 31:s.blockers|=128;break;default:break;}
    if(s.blockers)return s;
    s.reason=0;s.ready=1;return s;
}
