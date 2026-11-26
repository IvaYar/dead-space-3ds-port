/* Diagnostic-only, returned original callbacks, completed TOP transfers.
 * A content change is not a simulation update or a full-image fidelity proof.
 * No extra GPU submission/drain; the normal successful present already joined
 * its transfer before this observer reads the transferred allocation. */
#ifndef DS_PERF_DIAGNOSTIC
#define DS_PERF_DIAGNOSTIC 0
#endif
#if DS_PERF_DIAGNOSTIC
static u32 perf_intervals[128],perf_rows,perf_frames,perf_changed,perf_hash,perf_draws;
static u64 perf_first,perf_last,perf_hash_ticks;
static char perf_hud_text[160];
static const char *performance_hud(void){return perf_hud_text;}
static void performance_note(u64 callback){
    if(!gameplay_begin || !hw_policy.ready_seen || perf_rows>=256)return;
    u64 start=svcGetSystemTick();
    if(!graphics.pixels || graphics.capacity!=BYTES || graphics.layout!=DS13_BGR8_CTR)return;
    if(R_FAILED(GSPGPU_InvalidateDataCache(graphics.pixels,BYTES))){
        report("P10_PERF readback_failed=1 content_fps=UNKNOWN\n");perf_rows=256;return;
    }
    /* Reuse the existing validated byte-table CRC, without adding a second
     * table or charging the observation to original renderer scopes. */
    u32 hash=menu_page_crc_exact(graphics.pixels,BYTES),stats[4];ds34_stats(stats);
    u64 now=svcGetSystemTick();perf_hash_ticks+=now-start;
    if(!perf_first){perf_first=perf_last=now;perf_hash=hash;perf_draws=stats[0];return;}
    u64 elapsed=now-perf_last;perf_last=now;
    u64 us=elapsed*1000000/SYSCLOCK_ARM11;
    perf_intervals[perf_frames&127u]=us>UINT32_MAX?UINT32_MAX:(u32)us;
    ++perf_frames;++perf_rows;
    /* Count every completed callback separately from newly submitted geometry
     * and changed framebuffer content. Duplicate renders remain observable. */
    perf_changed+=hash!=perf_hash;perf_hash=hash;
    u32 submitted=stats[0]-perf_draws;perf_draws=stats[0];
    if(perf_rows%16)return;
    u32 sorted[128],n=perf_frames<128?perf_frames:128;
    for(u32 i=0;i<n;++i){u32 value=perf_intervals[i],j=i;while(j && sorted[j-1]>value){sorted[j]=sorted[j-1];--j;}sorted[j]=value;}
    double seconds=(double)(now-perf_first)/SYSCLOCK_ARM11;
    u64 renderer=menu_ops[0].ticks+menu_ops[1].ticks;
    u64 other=0;for(unsigned i=2;i<7;++i)other+=menu_ops[i].ticks;
    report("P10_PERF cb=%lu samples=%lu completed_callbacks=%lu content_changes=%lu seconds=%.6f callback_hz=%.3f changed_image_hz=%.3f interval_median_us=%lu interval_p95_us=%lu callback_us=%llu renderer_us=%llu unwrapped_residual_us=%llu gpu_wait_total_us=%llu last_draw_delta=%lu crc=%08lx observer_total_us=%llu image_fidelity=UNRESOLVED simulation_hz=UNKNOWN\n",
        (unsigned long)current_frame,(unsigned long)perf_rows,(unsigned long)perf_frames,(unsigned long)perf_changed,seconds,perf_frames/seconds,perf_changed/seconds,
        (unsigned long)sorted[(n-1)/2],(unsigned long)sorted[(95*n+99)/100-1],
        (unsigned long long)(callback*1000000/SYSCLOCK_ARM11),(unsigned long long)(renderer*1000000/SYSCLOCK_ARM11),
        (unsigned long long)((callback>=renderer+other?callback-renderer-other:0)*1000000/SYSCLOCK_ARM11),
        (unsigned long long)(gpu_wait_ticks*1000000/SYSCLOCK_ARM11),(unsigned long)submitted,(unsigned long)hash,
        (unsigned long long)(perf_hash_ticks*1000000/SYSCLOCK_ARM11));
    snprintf(perf_hud_text,sizeof(perf_hud_text),"\x1b[25;1HCompleted:%.2f/s  Changed:%.2f/s\nFrame median:%lu p95:%lu ms\nHash observer:%llu ms total\n",perf_frames/seconds,perf_changed/seconds,(unsigned long)(sorted[(n-1)/2]/1000),(unsigned long)(sorted[(95*n+99)/100-1]/1000),(unsigned long long)(perf_hash_ticks*1000/SYSCLOCK_ARM11));
    printf("%s",perf_hud_text);
    u16 w,h;void *bottom=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,&w,&h);GSPGPU_FlushDataCache(bottom,(u32)w*h*3);
}
#else
static inline const char *performance_hud(void){return "";}
static inline void performance_note(u64 callback){(void)callback;}
#endif
