/* HW03 observation only. No GPU commands, queue mutation, allocation or IRQ IO. */
#ifndef NATIVE_GAMEPLAY_HW03_GPU_H
#define NATIVE_GAMEPLAY_HW03_GPU_H
static volatile u32 h3_generation,h3_open,h3_end_count;
static volatile u32 h3_submit_type,h3_submit_rc,h3_bad_type,h3_bad_rc,h3_bad_seen;
static volatile u32 h3_flush_rc,h3_flush_bad_rc,h3_flush_bad_seen;
static volatile u32 h3_sensor_rc,h3_sensor_calls;
static u32 h3_info_bytes,h3_fail_bytes;
static int h3_wait_bool=-1,h3_timeout;
static u64 h3_wait_start,h3_wait_end;
typedef struct {u32 n,cur,last,max,type[3],valid,fc[2],ev[3];} H3GpuSample;
static H3GpuSample hw03_sample(void){
    H3GpuSample s={0};gxCmdQueue_s *q=queue;
    if(q){
        /* q/entries originate in linked Citro3D. Counts can advance asynchronously.
         * Load once; validate bounds before reading at most three entry types.
         * This is an observational sample, not an atomic completion witness. */
        s.n=__atomic_load_n(&q->numEntries,__ATOMIC_ACQUIRE);
        s.cur=__atomic_load_n(&q->curEntry,__ATOMIC_ACQUIRE);
        s.last=__atomic_load_n(&q->lastEntry,__ATOMIC_ACQUIRE);
        s.max=q->maxEntries;
        if(q->entries && s.max<=32 && s.n<=s.max && s.cur<=s.n && s.last<=s.n){
            s.valid=1;
            for(unsigned i=0;i<3 && s.last+i<s.n;++i)s.type[i]=q->entries[s.last+i].type;
        }
    }
    s.fc[0]=C3D_FrameCounter(0);s.fc[1]=C3D_FrameCounter(1);
    for(unsigned i=0;i<3;++i)s.ev[i]=__atomic_load_n(&events[i],__ATOMIC_ACQUIRE);
    return s;
}
static void hw03_line(int failure,const char *fmt,...){
    u32 tid=0;if(R_FAILED(svcGetThreadId(&tid,CUR_THREAD_HANDLE)) || tid!=main_thread_id)return;
    u32 *used=failure?&h3_fail_bytes:&h3_info_bytes,limit=failure?6144u:2048u;
    char line[896];va_list ap;va_start(ap,fmt);int n=vsnprintf(line,sizeof(line),fmt,ap);va_end(ap);
    if(n<0 || (unsigned)n>=sizeof(line) || (unsigned)n>limit-*used)return;
    *used+=(u32)n;report("%s",line);
}
static void hw03_gpu_record(const char *why,int failure,int result,u64 start,u64 end,H3GpuSample before){
    H3GpuSample s=hw03_sample();
    hw03_line(failure,"GPU_DIAG reason=%s cb=%lu gen=%lu open=%lu ends=%lu rc=%d wait_bool=%d timeout=%d ticks=%llu,%llu elapsed_us=%llu q0=%lu,%lu,%lu,%lu q1=%lu,%lu,%lu,%lu qvalid=%lu types=%lu,%lu,%lu fc0=%lu,%lu fc1=%lu,%lu ev0=%lu,%lu,%lu ev1=%lu,%lu,%lu submits=%lu failed=%lu last_type=%lu last_Result=%08lx bad_seen=%lu bad_type=%lu bad_Result=%08lx flush_Result=%08lx flush_bad_seen=%lu flush_bad_Result=%08lx sensor_calls=%lu sensor_Result=%08lx phases=%08lx\n",
        why,(unsigned long)current_frame,(unsigned long)h3_generation,(unsigned long)h3_open,(unsigned long)h3_end_count,
        result,h3_wait_bool,h3_timeout,(unsigned long long)start,(unsigned long long)end,
        (unsigned long long)((end-start)*1000000/SYSCLOCK_ARM11),
        (unsigned long)before.n,(unsigned long)before.cur,(unsigned long)before.last,(unsigned long)before.max,
        (unsigned long)s.n,(unsigned long)s.cur,(unsigned long)s.last,(unsigned long)s.max,(unsigned long)s.valid,
        (unsigned long)s.type[0],(unsigned long)s.type[1],(unsigned long)s.type[2],
        (unsigned long)before.fc[0],(unsigned long)before.fc[1],(unsigned long)s.fc[0],(unsigned long)s.fc[1],
        (unsigned long)before.ev[0],(unsigned long)before.ev[1],(unsigned long)before.ev[2],
        (unsigned long)s.ev[0],(unsigned long)s.ev[1],(unsigned long)s.ev[2],
        (unsigned long)submits,(unsigned long)failed_submits,(unsigned long)h3_submit_type,(unsigned long)h3_submit_rc,
        (unsigned long)h3_bad_seen,(unsigned long)h3_bad_type,(unsigned long)h3_bad_rc,
        (unsigned long)h3_flush_rc,(unsigned long)h3_flush_bad_seen,(unsigned long)h3_flush_bad_rc,
        (unsigned long)h3_sensor_calls,(unsigned long)h3_sensor_rc,(unsigned long)h3_shutdown.done);
}
static void hw03_commands(void){
    /* Existing HW02 CPU capture, bounded summary only. Never read live GPU memory. */
    u32 off=0,lists=0;
    for(unsigned entry=0;entry<8 && off<=command_bytes && command_bytes-off>=36;++entry){
        u32 words[8],n;memcpy(words,command_capture+off,32);memcpy(&n,command_capture+off+32,4);off+=36;
        if(n>command_bytes-off)break;
        hw03_line(1,"GPU_CMD entry=%u type=%lu bytes=%lu capture_overflow=%lu\n",entry,(unsigned long)(words[0]&255),(unsigned long)n,(unsigned long)command_overflow);
        if(n && lists++<2)for(u32 j=0;j<n/4 && j<32;j+=4){
            u32 v[4]={0};unsigned count=n/4-j;if(count>4)count=4;memcpy(v,command_capture+off+j*4,count*4);
            hw03_line(1,"GPU_WORDS entry=%u word=%lu count=%u data=%08lx,%08lx,%08lx,%08lx\n",entry,(unsigned long)j,count,(unsigned long)v[0],(unsigned long)v[1],(unsigned long)v[2],(unsigned long)v[3]);
        }
        off+=n;
    }
}
extern Result __real_GSPGPU_FlushDataCache(const void *,u32);
Result __wrap_GSPGPU_FlushDataCache(const void *p,u32 n){
    Result r=__real_GSPGPU_FlushDataCache(p,n);h3_flush_rc=(u32)r;
    if(R_FAILED(r) && !h3_flush_bad_seen){h3_flush_bad_rc=(u32)r;__atomic_store_n(&h3_flush_bad_seen,1,__ATOMIC_RELEASE);}return r;
}
extern Result __real_HIDUSER_DisableAccelerometer(void);
Result __wrap_HIDUSER_DisableAccelerometer(void){
    Result r=__real_HIDUSER_DisableAccelerometer();h3_sensor_rc=(u32)r;++h3_sensor_calls;return r;
}
#endif
