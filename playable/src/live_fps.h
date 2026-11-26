/* CPU-only bounded observation. No CRC/readback/heap/SD IO in the hot path. */
#if DS_P8_HUD
#define LIVE_CAP 128u
static struct {u64 tick[LIVE_CAP],last_update,first;u32 head,count,generation,enabled,updates;u64 hud_ticks;} live;
void ds34_generation_note(u32 generation){
    if(!live.enabled)return;
    u64 now=svcGetSystemTick();live.generation=generation;live.tick[live.head]=now;live.head=(live.head+1)&(LIVE_CAP-1);if(live.count<LIVE_CAP)++live.count;if(!live.first)live.first=now;
}
static void live_fps_init(void){FILE *f=fopen(ROOT "fps-off.txt","rb");live.enabled=f==NULL;if(f)fclose(f);live.generation=ds34_completed_generation();}
static __attribute__((noinline)) void live_fps_note(void){
    if(!live.enabled)return;
    u32 generation=live.generation;u64 now=svcGetSystemTick();
    if(now-live.last_update<SYSCLOCK_ARM11/2)return;
    live.last_update=now;u64 begin=svcGetSystemTick(),cutoff=now>2ull*SYSCLOCK_ARM11?now-2ull*SYSCLOCK_ARM11:0;
    u32 oldest=(live.head+LIVE_CAP-live.count)&(LIVE_CAP-1),n=live.count;
    /* Keep one sample preceding the sliding boundary for a full interval. */
    while(n>2 && live.tick[(oldest+1)&(LIVE_CAP-1)]<cutoff){oldest=(oldest+1)&(LIVE_CAP-1);--n;}
    union {u32 intervals[LIVE_CAP];char text[512];} scratch;
    char *text=scratch.text;
    if(n<2 || now<=live.tick[oldest])snprintf(text,sizeof(scratch.text),"DEAD SPACE 3DS\n\nRender FPS: --\nWaiting for completed frames\nCPU: New3DS (requested)\nSTART: safe exit");
    else{
        u32 *intervals=scratch.intervals,used=0;u64 prev=live.tick[oldest];
        for(u32 i=1;i<n;++i){u64 t=live.tick[(oldest+i)&(LIVE_CAP-1)],us=(t-prev)*1000000/SYSCLOCK_ARM11;u32 value=us>UINT32_MAX?UINT32_MAX:(u32)us,j=used++;
            while(j && intervals[j-1]>value){intervals[j]=intervals[j-1];--j;}intervals[j]=value;prev=t;}
        u64 span=now-live.tick[oldest];
        u32 fps100=(u64)(n-1)*SYSCLOCK_ARM11*100/span;
        u32 seconds100=span*100/SYSCLOCK_ARM11;
        u32 median=intervals[(used-1)/2]/1000;
        /* Integer formatting avoids newlib dtoa's hidden allocations. */
        snprintf(text,sizeof(scratch.text),"DEAD SPACE 3DS\n\nRender FPS: %lu.%02lu\nFrame median: %lu ms\nWindow: %lu.%02lu s\nCompleted generations: %lu\nCPU: New3DS (requested)\nState: %s\n\nCircle Pad: move\nC-Stick: camera\nSTART: safe exit",(unsigned long)(fps100/100),(unsigned long)(fps100%100),(unsigned long)median,(unsigned long)(seconds100/100),(unsigned long)(seconds100%100),(unsigned long)generation,gameplay_begin?"gameplay":"menu/loading");
    }
    screen(text);live.hud_ticks+=svcGetSystemTick()-begin;++live.updates;
}
static void live_fps_finish(void){report("P8HUD enabled=%lu updates=%lu hud_us=%llu generation=%lu count=%lu\n",(unsigned long)live.enabled,(unsigned long)live.updates,(unsigned long long)(live.hud_ticks*1000000/SYSCLOCK_ARM11),(unsigned long)live.generation,(unsigned long)live.count);}
#else
static void live_fps_init(void){}
static void live_fps_note(void){}
static void live_fps_finish(void){}
#endif
