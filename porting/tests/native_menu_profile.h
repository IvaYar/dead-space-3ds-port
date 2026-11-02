/* Render-thread import timings; no game operations replaced or skipped. */
typedef struct {u32 calls,caller;u64 ticks,maximum,bytes;} MenuOperation;
static MenuOperation menu_ops[12];
#include "native_menu_page_crc.h"
static void (*menu_real_elements)(u32,int32_t,u32,const void *) DS_IO_SOFT;
static void (*menu_real_arrays)(u32,int32_t,int32_t) DS_IO_SOFT;
static void (*menu_real_image)(u32,int32_t,int32_t,int32_t,int32_t,int32_t,u32,u32,const void *) DS_IO_SOFT;
static void (*menu_real_subimage)(u32,int32_t,int32_t,int32_t,int32_t,int32_t,u32,u32,const void *) DS_IO_SOFT;
static void (*menu_real_clear)(u32) DS_IO_SOFT;
static void (*menu_real_finish)(void) DS_IO_SOFT;
static void (*menu_real_read)(int32_t,int32_t,int32_t,int32_t,u32,u32,void *) DS_IO_SOFT;
static u32 menu_profile_enabled;
static u32 menu_profile_page_saves,menu_profile_page_loads;
static u64 menu_profile_queue0,menu_profile_vblank0;
static LoaderIO menu_profile_io0;
static LoaderIO menu_profile_io(void){
    LoaderIO sum={0};LightLock_Lock(&loader_io_lock);
    for(u32 i=0;i<17;++i){sum.bytes+=loader_io[i].bytes;sum.positive_reads+=loader_io[i].positive_reads;sum.completed+=loader_io[i].completed;}
    LightLock_Unlock(&loader_io_lock);return sum;
}
static void menu_profile_record(u32 op,u64 start,u32 caller){
    if(!menu_profile_enabled)return;
    u64 ticks=svcGetSystemTick()-start;MenuOperation *m=&menu_ops[op];++m->calls;m->ticks+=ticks;
    if(ticks>m->maximum){m->maximum=ticks;m->caller=caller>=(u32)image && caller-(u32)image<info.image_size?caller-(u32)image:0;}
}
static void DS_IO_SOFT menu_profile_elements(u32 mode,int32_t count,u32 type,const void *indices){
    u64 t=svcGetSystemTick();menu_real_elements(mode,count,type,indices);menu_profile_record(0,t,(u32)__builtin_return_address(0));
}
static void DS_IO_SOFT menu_profile_arrays(u32 mode,int32_t first,int32_t count){
    u64 t=svcGetSystemTick();menu_real_arrays(mode,first,count);menu_profile_record(1,t,(u32)__builtin_return_address(0));
}
static void DS_IO_SOFT menu_profile_image(u32 target,int32_t level,int32_t internal,int32_t w,int32_t h,int32_t border,u32 format,u32 type,const void *data){
    u64 t=svcGetSystemTick();menu_real_image(target,level,internal,w,h,border,format,type,data);menu_profile_record(2,t,(u32)__builtin_return_address(0));
}
static void DS_IO_SOFT menu_profile_subimage(u32 target,int32_t level,int32_t x,int32_t y,int32_t w,int32_t h,u32 format,u32 type,const void *data){
    u64 t=svcGetSystemTick();menu_real_subimage(target,level,x,y,w,h,format,type,data);menu_profile_record(3,t,(u32)__builtin_return_address(0));
}
static void DS_IO_SOFT menu_profile_clear(u32 mask){u64 t=svcGetSystemTick();menu_real_clear(mask);menu_profile_record(4,t,(u32)__builtin_return_address(0));}
static void DS_IO_SOFT menu_profile_finish(void){u64 t=svcGetSystemTick();menu_real_finish();menu_profile_record(5,t,(u32)__builtin_return_address(0));}
static void DS_IO_SOFT menu_profile_read(int32_t x,int32_t y,int32_t w,int32_t h,u32 format,u32 type,void *pixels){
    u64 t=svcGetSystemTick();menu_real_read(x,y,w,h,format,type,pixels);menu_profile_record(6,t,(u32)__builtin_return_address(0));
}
extern int __real_ds34_begin_draw(DS13Context *);
int __wrap_ds34_begin_draw(DS13Context *c){u64 t=svcGetSystemTick();int r=__real_ds34_begin_draw(c);menu_profile_record(7,t,(u32)__builtin_return_address(0));return r;}
extern void __real_ds34_end_draw(DS13Context *);
void __wrap_ds34_end_draw(DS13Context *c){u64 t=svcGetSystemTick();__real_ds34_end_draw(c);menu_profile_record(8,t,(u32)__builtin_return_address(0));}
extern int __real_ds15_resident(DS15State *,DS15Object *,u32);
int __wrap_ds15_resident(DS15State *s,DS15Object *o,u32 level){u64 t=svcGetSystemTick();int r=__real_ds15_resident(s,o,level);menu_profile_record(9,t,(u32)__builtin_return_address(0));return r;}
extern u32 __real_ds_crc32(const u8 *,u32);
u32 __wrap_ds_crc32(const u8 *data,u32 bytes){
    u64 t=svcGetSystemTick();u32 r=__real_ds_crc32(data,bytes);
    if(menu_profile_enabled)menu_ops[10].bytes+=bytes;
    menu_profile_record(10,t,(u32)__builtin_return_address(0));return r;
}
u32 menu_page_crc32(const u8 *data,u32 bytes){
    u64 t=svcGetSystemTick();u32 r=menu_page_crc_exact(data,bytes);
    if(menu_profile_enabled)menu_ops[11].bytes+=bytes;
    menu_profile_record(11,t,(u32)__builtin_return_address(0));return r;
}
static void menu_profile_bindings(DSBinding *b,u32 count){
    for(u32 i=0;i<count;++i){
        if(!strcmp(b[i].name,"glDrawElements")){menu_real_elements=(void *)b[i].address;b[i].address=(u32)menu_profile_elements;}
        if(!strcmp(b[i].name,"glDrawArrays")){menu_real_arrays=(void *)b[i].address;b[i].address=(u32)menu_profile_arrays;}
        if(!strcmp(b[i].name,"glTexImage2D")){menu_real_image=(void *)b[i].address;b[i].address=(u32)menu_profile_image;}
        if(!strcmp(b[i].name,"glTexSubImage2D")){menu_real_subimage=(void *)b[i].address;b[i].address=(u32)menu_profile_subimage;}
        if(!strcmp(b[i].name,"glClear")){menu_real_clear=(void *)b[i].address;b[i].address=(u32)menu_profile_clear;}
        if(!strcmp(b[i].name,"glFinish")){menu_real_finish=(void *)b[i].address;b[i].address=(u32)menu_profile_finish;}
        if(!strcmp(b[i].name,"glReadPixels")){menu_real_read=(void *)b[i].address;b[i].address=(u32)menu_profile_read;}
    }
}
static void menu_profile_begin(void){
    memset(menu_ops,0,sizeof(menu_ops));menu_profile_enabled=1;
    menu_profile_page_saves=graphics.texture.page_saves;menu_profile_page_loads=graphics.texture.page_loads;
    menu_profile_queue0=gpu_wait_ticks;menu_profile_vblank0=vblank_wait_ticks;menu_profile_io0=menu_profile_io();
}
static void menu_profile_end(u64 ticks){
    menu_profile_enabled=0;
    if(ticks>SYSCLOCK_ARM11/20 || current_frame%120==0){
        LoaderIO resources=menu_profile_io();
        report("CALLBACKJSON {\"frame\":%lu,\"ms\":%.3f,\"ops\":[",(unsigned long)current_frame,(double)ticks*1000/SYSCLOCK_ARM11);
        for(u32 i=0;i<12;++i)report("%s{\"id\":%lu,\"calls\":%lu,\"ms\":%.3f,\"max_ms\":%.3f,\"caller\":%lu,\"bytes\":%llu}",i?",":"",(unsigned long)i,(unsigned long)menu_ops[i].calls,(double)menu_ops[i].ticks*1000/SYSCLOCK_ARM11,(double)menu_ops[i].maximum*1000/SYSCLOCK_ARM11,(unsigned long)menu_ops[i].caller,(unsigned long long)menu_ops[i].bytes);
        report("],\"page_saves\":%lu,\"page_loads\":%lu,\"resident_bytes\":%lu,\"resource_bytes\":%lu,\"resource_reads\":%lu,\"IO_completions\":%lu,\"gpu_queue_wait_ms\":%.3f,\"vblank_wait_ms\":%.3f}\n",(unsigned long)(graphics.texture.page_saves-menu_profile_page_saves),(unsigned long)(graphics.texture.page_loads-menu_profile_page_loads),(unsigned long)graphics.texture.resident,(unsigned long)(resources.bytes-menu_profile_io0.bytes),(unsigned long)(resources.positive_reads-menu_profile_io0.positive_reads),(unsigned long)(resources.completed-menu_profile_io0.completed),(double)(gpu_wait_ticks-menu_profile_queue0)*1000/SYSCLOCK_ARM11,(double)(vblank_wait_ticks-menu_profile_vblank0)*1000/SYSCLOCK_ARM11);
    }
}
