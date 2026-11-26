/* Same dependency order as HW02. Each successful destructive phase runs once. */
static u32 h3_jni_freed,h3_stdio_closed,h3_appdata_closed;
static int hw03_cleanup_phase(unsigned p,void *user){
    (void)user;
    switch(p){
    case H3_RELEASE_INPUT:return menu_input_attached?gameplay_release():0;
    case H3_CLOSE_INPUT:return menu_input_close();
    case H3_LOADERS:return native_drain_loaders();
    case H3_LIFECYCLE:
        if(!lifecycle_stopped){
            lifecycle("MainActivity_NativeOnPause",0,0);native_thread_snapshot("after_pause");
            lifecycle("MainActivity_NativeOnStop",0,0);native_thread_snapshot("after_stop");lifecycle_stopped=1;
        }return 0;
    case H3_DESTRUCTORS:native_destructor_snapshot();return 0;
    case H3_AUDIO_WORKERS:return native_stop_audio_workers();
    case H3_JOB_WORKERS:return native_stop_job_workers();
    case H3_PERIODIC:return native_stop_periodic_worker();
    case H3_QUIET:
        native_thread_snapshot("after_quiesce");ds7_stats(&thread_snapshot);
        return thread_snapshot.active_threads || thread_snapshot.finished_threads?-1:0;
    case H3_AUDIO_RELEASE:{
        typedef void (*AudioRelease)(void *,void *) DS_IO_SOFT;
        ((AudioRelease)exported("Java_com_ea_EAAudioCore_AndroidEAAudioCore_Release"))(&bridge.base.env,NULL);
        extern void scene_audio_stats(uint64_t [2]);uint64_t stats[2];scene_audio_stats(stats);
        report("AUDIO_SINK writes=%llu samples=%llu released_after_workers=1\n",(unsigned long long)stats[0],(unsigned long long)stats[1]);return 0;
    }
    case H3_JNI:h3_jni_freed=ds10_cleanup(&bridge);return h3_jni_freed==UINT32_MAX?-1:0;
    case H3_STDIO:h3_stdio_closed=ds6_cleanup();return 0;
    case H3_APPDATA:h3_appdata_closed=ds24_shutdown();return 0;
    case H3_IO:{
        int r=hw03_close_io(&h3_shutdown,&io);u32 directories=ds20_active();
        report("RESOURCES JNI=%lu stdio=%lu appdata=%lu IOactive=%lu opens/closes=%lu/%lu dirs=%lu\n",(unsigned long)h3_jni_freed,(unsigned long)h3_stdio_closed,(unsigned long)h3_appdata_closed,(unsigned long)io.active,(unsigned long)io.opens,(unsigned long)io.closes,(unsigned long)directories);
        return r || directories?-1:0;
    }
    case H3_JOIN:{
        u32 live=ds7_shutdown(100000000);report("SHUTDOWN live workers=%lu\n",(unsigned long)live);
        native_thread_snapshot("after_join");if(live)return -1;ds7_stats(&thread_snapshot);return 0;
    }
    case H3_SENSOR:{int r=sensor_attached?ds12_sensor_close(&sensor):0;if(r)return r;sensor_attached=0;return 0;}
    case H3_GPU_FINISH:if(gpu_started)ds34_native_finish();return 0;
    case H3_GPU_DRAIN:return gpu_started?hw03_run_drain("CLEANUP_GPU_DRAIN_FAIL"):0;
    case H3_GPU_FINI:if(gpu_started){C3D_Fini();queue=NULL;gpu_started=0;}return 0;
    case H3_AFTER:memory_sample("after_shutdown");return 0;
    case H3_EXIT:{
        char out[192];path(out,"exit.txt");FILE *f=fopen(out,"w");if(!f)return -1;
        int wrote=fputs("Workers stopped; GPU drained; returning to HOME\n",f)>=0;
        return fclose(f) || !wrote?-1:0;
    }
    default:return -100;
    }
}
static void hw03_cleanup_record(const char *why,unsigned p,int rc){
    H3GpuSample s=hw03_sample();u64 now=svcGetSystemTick();
    hw03_line(1,"CLEANUP_DIAG reason=%s phase=%u rc=%d done=%08lx IOactive=%lu opens=%lu closes=%lu io_failed=%lu sensor_attached=%d gpu_started=%d journal_independent=SDK_stdio\n",why,p,rc,(unsigned long)h3_shutdown.done,(unsigned long)io.active,(unsigned long)io.opens,(unsigned long)io.closes,(unsigned long)h3_shutdown.io_failed,sensor_attached,gpu_started);
    hw03_gpu_record(why,1,rc,now,now,s);
}
