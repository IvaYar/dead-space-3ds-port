/* Read the verified donor's actual modal layer at a returned main boundary.
 * No framebuffer dependence and no writes into the original object graph. */
typedef struct {u32 layer,phase,transition,closing,selection,normal,easy,normal_state,easy_state;int ready;} MenuEngineState;
static int menu_state_span(u32 p,u32 bytes){
    return !(p&3) && p>=(u32)arena && p-(u32)arena<=DS_GAME_ARENA_BYTES && bytes<=DS_GAME_ARENA_BYTES-(p-(u32)arena);
}
static MenuEngineState menu_engine_state(void){
    MenuEngineState s={0};
    /* App singleton slot: original1c4f90. App+d8 is its live modal ref.
     * LayerDifficulty vtable427dd8; a3d20 dispatches widgets only at cc==2.
     * b52c4 owns the base transition18;44 marks a closing layer. */
    u32 app=*(u32 *)(image+0x44a1b4);
    if(!menu_state_span(app,0xdc))return s;
    u32 p=*(u32 *)(app+0xd8);
    if(!menu_state_span(p,0x10c) || *(u32 *)p!=(u32)image+0x427dd8)return s;
    s.layer=p;s.phase=*(u32 *)(p+0xcc);s.transition=*(u32 *)(p+0x18);s.closing=*(u32 *)(p+0x44);
    s.ready=s.phase==2 && !s.transition && !s.closing;
    if(s.ready){
        /* Borrowed wstrings for the original readonly widget-map lookup.
         * c5ffc/c5f80 store checked state4 at widget+64. */
        typedef u32 (*Lookup)(u32 *,u32,const u32 *) DS_IO_SOFT;
        u32 buckets=*(u32 *)(p+0x80),count=*(u32 *)(p+0x84);
        if(!count || count>1024 || !menu_state_span(buckets,(count+1)*4)){s.ready=0;return s;}
        u32 end=*(u32 *)(buckets+count*4),selected=0;
        const u32 names[2]={0x3c3268,0x3c3250},lengths[2]={10,8};
        for(u32 i=0;i<2;++i){
            u32 begin=(u32)image+names[i],key[3]={begin,begin+lengths[i]*2,begin+lengths[i]*2},it[2]={0};
            ((Lookup)(image+0x1ab8c4))(it,p+0x7c,key);
            if(it[0]==end || !menu_state_span(it[0],0x24)){s.ready=0;return s;}
            u32 widget=*(u32 *)(it[0]+0x14);
            if(!menu_state_span(widget,0xe4)){s.ready=0;return s;}
            u32 state=*(u32 *)(widget+0x64);
            if(i==0){s.normal=widget;s.normal_state=state;}else{s.easy=widget;s.easy_state=state;}
            if(state==4){if(selected){s.ready=0;return s;}selected=i+1;}
        }
        s.selection=selected;if(!selected)s.ready=0;
    }
    return s;
}
