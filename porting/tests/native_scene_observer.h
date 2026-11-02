/* Bounded diagnostics at returned original callbacks. No donor mutation. */
static int scene_started;
static u64 scene_begin_ms;
static u32 scene_opens;
static void scene_resource_open(const char *name,int result){
    if(scene_started && scene_opens++<512)report("SCENE_RESOURCE frame=%lu result=%d path=%s\n",(unsigned long)current_frame,result,name);
}
static void scene_observe(void){
    if(!menu_confirmation_frame)return;
    DSRuntimeStats r;ds_runtime_stats(&r);
    if(r.invalid_frees)deferred_gpu_failure="runtime invalid free; retained at boundary";
    if(current_frame<=menu_confirmation_frame+25 || current_frame%120==0 || graphics.error || r.failures){
        report("SCENE_STATE frame=%lu modal=%08lx gl=%lu resident=%lu saves=%lu loads=%lu runtime_failures=%lu invalid_frees=%lu malloc_failed=%lu malloc_caller=%08lx\n",
            (unsigned long)current_frame,(unsigned long)menu_engine_state().layer,(unsigned long)graphics.error,
            (unsigned long)graphics.texture.resident,(unsigned long)graphics.texture.page_saves,(unsigned long)graphics.texture.page_loads,
            (unsigned long)r.failures,(unsigned long)r.invalid_frees,(unsigned long)scene_malloc_failed_request,(unsigned long)scene_malloc_failed_caller);
        memory_sample("scene_boundary");
        u32 app=*(u32 *)(image+0x44a1b4);
        if(menu_state_span(app,0xdc))for(unsigned off=0;off<0xdc;off+=4){
            u32 p=*(u32 *)(app+off);if(!menu_state_span(p,4))continue;
            u32 v=*(u32 *)p;if(v>=(u32)image && v-(u32)image<info.image_size)
                report("SCENE_OBJECT app_offset=%x vtable_offset=%08lx\n",off,(unsigned long)(v-(u32)image));
        }
    }
}
