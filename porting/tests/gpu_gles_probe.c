/* Exercise the same GLES bindings/CPU vertex validation as the donor, with
 * actual PICA fragments. No original game code is called by this fixture. */
#include <3ds.h>
#include "ds13_gles.h"
#include "ds34_gpu.h"
#include "ds_runtime.h"
#include <stdio.h>
#include <string.h>
#ifdef DS_GPU_ENGINE_MEMORY
u32 __ctru_heap_size=40*1024*1024;
u32 __ctru_linear_heap_size=132*1024*1024;
#endif
static DS13Context ctx;
static DSBinding bindings[128];static uint32_t count;
static const float quad[]={-1,-1,0,1,-1,0,-1,1,0,1,1,0};
static const float uv[]={0,0,1,0,0,1,1,1};
static const uint8_t rgba[]={255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255};
static const uint8_t alpha[]={128,128,128,128};
/* 256 KiB: each 64-row band occupies a separate old scratch upload. */
static uint8_t large_rgba[256*256*4];
static float rollover[8196*3];
static const float left_tri[]={-1,-1,0,0,-1,0,-1,1,0,-1,1,0,0,-1,0,0,1,0};
static const float right_tri[]={0,-1,0,1,-1,0,0,1,0,0,1,0,1,-1,0,1,1,0};
static void *fn(const char *name){for(uint32_t i=0;i<count;++i)if(!strcmp(name,bindings[i].name))return (void*)bindings[i].address;return NULL;}
typedef void (*One)(uint32_t) DS13_SOFT;
typedef void (*Color)(float,float,float,float) DS13_SOFT;
typedef void (*Pointer)(int32_t,uint32_t,int32_t,const void*) DS13_SOFT;
typedef void (*Draw)(uint32_t,int32_t,int32_t) DS13_SOFT;
typedef void (*Two)(uint32_t,uint32_t) DS13_SOFT;
typedef void (*Names)(int32_t,uint32_t*) DS13_SOFT;
typedef void (*Parameter)(uint32_t,uint32_t,int32_t) DS13_SOFT;
typedef void (*Image)(uint32_t,int32_t,int32_t,int32_t,int32_t,int32_t,uint32_t,uint32_t,const void*) DS13_SOFT;
typedef void (*Box)(int32_t,int32_t,int32_t,int32_t) DS13_SOFT;
typedef uint32_t (*Error)(void) DS13_SOFT;
static void observed(const char *name,uint32_t value){FILE *f=fopen("sdmc:/3ds/deadspace/gpu-gles-error.txt","w");if(f){fprintf(f,"%s %08lx\n",name,(unsigned long)value);fclose(f);}}
static int capture(unsigned id){char path[128];snprintf(path,sizeof(path),"sdmc:/3ds/deadspace/gpu-gles-%u.raw",id);FILE *f=fopen(path,"wb");if(!f)return -1;int bad=fwrite(ctx.pixels,1,192000,f)!=192000;if(fclose(f))bad=1;return bad?-1:0;}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);s64 emulator;
    if(svcGetSystemInfo(&emulator,0x20000,0)!=0)goto wait;
    gfxSetScreenFormat(GFX_TOP,GSP_RGB565_OES);gfxSwapBuffers();gspWaitForVBlank();
#ifdef DS_GPU_ENGINE_MEMORY
    /* Match the real engine's large donor arena before allocating GPU buffers. */
    if(!linearMemAlign(128*1024*1024,4096))goto wait;
#endif
    u16 w,h;void *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);
    ds_runtime_init(8*1024*1024);
    if(ds13_init(&ctx,pixels,400,240,192000,DS13_RGB565_CTR) || ds13_current(&ctx))goto wait;
    ds13_observer(&ctx,observed,NULL);count=ds13_bindings(bindings,128);
    if(count!=99 || ds22_client_range(&ctx,quad,sizeof(quad)) || ds22_client_range(&ctx,uv,sizeof(uv)) || ds34_attach(&ctx))goto wait;
    ((Pointer)fn("glVertexPointer"))(3,0x1406,0,quad);((One)fn("glEnableClientState"))(0x8074);
    uint32_t texture=0;
    for(unsigned y=0;y<256;++y)for(unsigned x=0;x<256;++x)
        memcpy(large_rgba+(y*256+x)*4,rgba+(y/64)*4,4);
    for(unsigned test=0;test<5;++test){
        /* engine_azahar starts with consoleInit(TOP), which disables buffering. */
        if(test==4)gfxSetDoubleBuffering(GFX_TOP,false);
        ((One)fn("glDisable"))(0xc11);((One)fn("glDisable"))(0xbe2);((One)fn("glDisable"))(0xde1);
        if(test){
            if(!texture){((Names)fn("glGenTextures"))(1,&texture);((Two)fn("glBindTexture"))(0xde1,texture);}
            ((Parameter)fn("glTexParameteri"))(0xde1,0x2801,0x2600);((Parameter)fn("glTexParameteri"))(0xde1,0x2800,0x2600);
            ((Parameter)fn("glTexParameteri"))(0xde1,0x2802,0x812f);((Parameter)fn("glTexParameteri"))(0xde1,0x2803,0x812f);
            ((Two)fn("glPixelStorei"))(0xcf5,1);
            ((Image)fn("glTexImage2D"))(0xde1,0,test==2?0x1906:0x1908,test>=3?256:2,test>=3?256:2,0,test==2?0x1906:0x1908,0x1401,test>=3?large_rgba:test==1?rgba:alpha);
            ((Pointer)fn("glTexCoordPointer"))(2,0x1406,0,uv);((One)fn("glEnableClientState"))(0x8078);
        }
        for(unsigned frame=0;frame<3;++frame){
            ((One)fn("glDisable"))(0xc11);((One)fn("glDisable"))(0xbe2);((One)fn("glDisable"))(0xde1);
            ((Color)fn("glClearColor"))(test==2?0:16/255.f,test==2?0:32/255.f,test==2?1:48/255.f,1);((One)fn("glClear"))(0x4100);
            ((Color)fn("glColor4f"))(test==0?0:1,test==0?1:0,test==1?1:0,1);
            if(test==1 || test>=3)((Color)fn("glColor4f"))(1,1,1,1);
            if(test==0){((Box)fn("glScissor"))(100,40,200,160);((One)fn("glEnable"))(0xc11);}
            else ((One)fn("glEnable"))(0xde1);
            if(test==2){((One)fn("glEnable"))(0xbe2);((Two)fn("glBlendFunc"))(0x302,0x303);}
            ((Draw)fn("glDrawArrays"))(5,0,4);if(((Error)fn("glGetError"))() || ds34_present(&ctx))goto wait;
        }
        if(capture(test))goto wait;
    }
    /* A single GLES draw crosses STREAM=8190: the first left quad must survive
     * reuse of its six vertices by the final right quad. Tiny filler triangles
     * keep the pixel workload small while using the real client-array path. */
    gfxSetDoubleBuffering(GFX_TOP,true);
    memcpy(rollover,left_tri,sizeof(left_tri));
    for(unsigned i=6;i<8190;i+=3){
        const float tiny[]={.99f,.99f,0,1,.99f,0,.99f,1,0};
        memcpy(rollover+i*3,tiny,sizeof(tiny));
    }
    memcpy(rollover+8190*3,right_tri,sizeof(right_tri));
    if(ds22_client_range(&ctx,rollover,sizeof(rollover)))goto wait;
    ((One)fn("glDisable"))(0xde1);((One)fn("glDisable"))(0xbe2);((One)fn("glDisable"))(0xc11);
    ((One)fn("glDisableClientState"))(0x8078);
    ((Color)fn("glClearColor"))(0,0,0,1);((One)fn("glClear"))(0x4100);
    ((Pointer)fn("glVertexPointer"))(3,0x1406,0,rollover);((Color)fn("glColor4f"))(0,1,0,1);
    ((Draw)fn("glDrawArrays"))(4,0,8196);
    if(((Error)fn("glGetError"))() || ds34_present(&ctx) || capture(5))goto wait;
    /* Clear must follow an already queued draw, then precede the next draw. */
    ((Pointer)fn("glVertexPointer"))(3,0x1406,0,quad);
    ((Draw)fn("glDrawArrays"))(5,0,4);
    ((Color)fn("glClearColor"))(0,0,1,1);((One)fn("glClear"))(0x4000);
    ((Box)fn("glScissor"))(200,0,200,240);((One)fn("glEnable"))(0xc11);
    ((Color)fn("glColor4f"))(1,0,0,1);((Draw)fn("glDrawArrays"))(5,0,4);
    if(((Error)fn("glGetError"))() || ds34_present(&ctx) || capture(6))goto wait;
    uint32_t gpu[4],cpu[4];ds34_stats(gpu);ds22_stats(&ctx,cpu);FILE *f=fopen("sdmc:/3ds/deadspace/gpu-gles-result.json","w");
    if(f){fprintf(f,"{\"passed\":true,\"gpu_draws\":%lu,\"gpu_triangles\":%lu,\"gpu_uploads\":%lu,\"gpu_bytes\":%lu,\"cpu_fragments\":%lu,\"cpu_samples\":%lu}\n",(unsigned long)gpu[0],(unsigned long)gpu[1],(unsigned long)gpu[2],(unsigned long)gpu[3],(unsigned long)cpu[2],(unsigned long)cpu[3]);fclose(f);}
    printf("GPU GLES PROBE COMPLETED\n");
wait:for(;;)svcSleepThread(1000000000LL);
}
