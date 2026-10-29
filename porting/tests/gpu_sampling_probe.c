/* Identical real GLES draws through DS22 and DS34. Synthetic data only. */
#include <3ds.h>
#include "ds13_gles.h"
#include "ds34_gpu.h"
#include "ds_runtime.h"
#include <stdio.h>
#include <string.h>
static DS13Context cpu,gpu;
static uint8_t cpu_pixels[192000],pattern[32*32*4],atlas[256*256*4];
static const float quad[]={-1,-1,0,1,-1,0,-1,1,0,1,1,0};
static float uv[8];
static DSBinding bindings[128];static uint32_t count;
typedef void (*One)(uint32_t) DS13_SOFT;
typedef void (*Two)(uint32_t,uint32_t) DS13_SOFT;
typedef void (*Names)(int32_t,uint32_t*) DS13_SOFT;
typedef void (*Parameter)(uint32_t,uint32_t,int32_t) DS13_SOFT;
typedef void (*Color)(float,float,float,float) DS13_SOFT;
typedef void (*Pointer)(int32_t,uint32_t,int32_t,const void*) DS13_SOFT;
typedef void (*Draw)(uint32_t,int32_t,int32_t) DS13_SOFT;
typedef void (*Box)(int32_t,int32_t,int32_t,int32_t) DS13_SOFT;
typedef void (*Image)(uint32_t,int32_t,int32_t,int32_t,int32_t,int32_t,uint32_t,uint32_t,const void*) DS13_SOFT;
typedef uint32_t (*Error)(void) DS13_SOFT;
static void *fn(const char *name){for(uint32_t i=0;i<count;++i)if(!strcmp(name,bindings[i].name))return (void*)bindings[i].address;return NULL;}
static void observed(const char *name,uint32_t value){FILE *f=fopen("sdmc:/3ds/deadspace/sampling-error.txt","w");if(f){fprintf(f,"%s %08lx\n",name,(unsigned long)value);fclose(f);}}
static int capture(DS13Context *c,unsigned test,int hardware){
    char path[128];snprintf(path,sizeof(path),"sdmc:/3ds/deadspace/sampling-%s-%u.raw",hardware?"gpu":"cpu",test);
    FILE *f=fopen(path,"wb");if(!f)return -1;int bad=fwrite(c->pixels,1,192000,f)!=192000;if(fclose(f))bad=1;return bad?-1:0;
}
static int setup(DS13Context *c,void *pixels){
    if(ds13_init(c,pixels,400,240,192000,DS13_RGB565_CTR) || ds13_current(c))return -1;
    ds13_observer(c,observed,NULL);
    if(ds22_client_range(c,quad,sizeof(quad)) || ds22_client_range(c,uv,sizeof(uv)))return -1;
    ((Pointer)fn("glVertexPointer"))(3,0x1406,0,quad);((One)fn("glEnableClientState"))(0x8074);
    ((Pointer)fn("glTexCoordPointer"))(2,0x1406,0,uv);((One)fn("glEnableClientState"))(0x8078);
    ((One)fn("glEnable"))(0xde1);((Color)fn("glColor4f"))(1,1,1,1);
    return 0;
}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);s64 emulator;
    if(svcGetSystemInfo(&emulator,0x20000,0)!=0)goto wait;
    gfxSetScreenFormat(GFX_TOP,GSP_RGB565_OES);gfxSwapBuffers();gspWaitForVBlank();
    ds_runtime_init(8*1024*1024);count=ds13_bindings(bindings,128);if(count!=99)goto wait;
    /* Left: one-texel horizontal lines. Right: one-texel checkerboard. */
    for(unsigned y=0;y<32;++y)for(unsigned x=0;x<32;++x){
        unsigned v=((x<16?y:x+y)&1)?255:0;uint8_t *p=pattern+(y*32+x)*4;
        p[0]=p[1]=p[2]=v;p[3]=255;
    }
    /* Alpha atlas patch, away from texture edges, with text-sized strokes. */
    for(unsigned y=0;y<16;++y)for(unsigned x=0;x<16;++x){
        uint8_t *p=atlas+((50+y)*256+80+x)*4;p[0]=p[1]=p[2]=255;
        p[3]=((x<8?y:x+y)&1)?255:0;
    }
    if(setup(&cpu,cpu_pixels))goto wait;
    u16 w,h;if(setup(&gpu,gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h)) || ds34_attach(&gpu))goto wait;
    /* Asymmetric untextured color control: format, orientation and stride.
     * Logical lower row red/green, upper row blue/white, 50x40 per block. */
    for(int hardware=0;hardware<2;++hardware){
        DS13Context *c=hardware?&gpu:&cpu;if(ds13_current(c))goto wait;
        ((Color)fn("glClearColor"))(0,0,0,1);((One)fn("glClear"))(0x4100);
        ((One)fn("glDisable"))(0xde1);
        for(unsigned k=0;k<4;++k){
            ((Box)fn("glViewport"))(20+(k&1)*50,20+(k>>1)*40,50,40);
            ((Color)fn("glColor4f"))(k==0 || k==3,k==1 || k==3,k>=2,1);
            ((Draw)fn("glDrawArrays"))(5,0,4);
        }
        if(((Error)fn("glGetError"))() || (hardware && ds34_present(c)) || capture(c,8,hardware))goto wait;
        ((One)fn("glEnable"))(0xde1);((Color)fn("glColor4f"))(1,1,1,1);
    }
    for(unsigned test=0;test<8;++test){
        unsigned kind=test/2,dim=kind==3?256:32,side=kind==0?160:32;
        float lo=kind==3?80/256.f:0,ly=kind==3?50/256.f:0;
        float span=kind==3?16/256.f:1;
        /* Include exact texel boundaries and fractional atlas offsets. */
        float dx=kind==1?.25f/dim:kind==2?.5f/dim:kind==3?.25f/dim:0;
        float dy=kind==1?.375f/dim:kind==2?.5f/dim:kind==3?.375f/dim:0;
        float coords[]={lo+dx,ly+dy,lo+span+dx,ly+dy,lo+dx,ly+span+dy,lo+span+dx,ly+span+dy};memcpy(uv,coords,sizeof(uv));
        for(int hardware=0;hardware<2;++hardware){
            DS13Context *c=hardware?&gpu:&cpu;if(ds13_current(c))goto wait;
            ((Color)fn("glClearColor"))(0,0,0,1);((One)fn("glClear"))(0x4100);
            ((Box)fn("glViewport"))(20,20,side,side);
            uint32_t name=c->texture.binding[0];if(!name){((Names)fn("glGenTextures"))(1,&name);((Two)fn("glBindTexture"))(0xde1,name);}
            ((Parameter)fn("glTexParameteri"))(0xde1,0x2801,test&1?0x2601:0x2600);((Parameter)fn("glTexParameteri"))(0xde1,0x2800,test&1?0x2601:0x2600);
            ((Parameter)fn("glTexParameteri"))(0xde1,0x2802,0x812f);((Parameter)fn("glTexParameteri"))(0xde1,0x2803,0x812f);
            ((Image)fn("glTexImage2D"))(0xde1,0,0x1908,dim,dim,0,0x1908,0x1401,kind==3?atlas:pattern);
            if(kind==3){((One)fn("glEnable"))(0xbe2);((Two)fn("glBlendFunc"))(0x302,0x303);}
            else ((One)fn("glDisable"))(0xbe2);
            ((Draw)fn("glDrawArrays"))(5,0,4);
            if(((Error)fn("glGetError"))() || (hardware && ds34_present(c)) || capture(c,test,hardware))goto wait;
        }
    }
    uint32_t gs[4],cs[4],cpu_stats[4];ds34_stats(gs);ds22_stats(&gpu,cs);ds22_stats(&cpu,cpu_stats);
    FILE *f=fopen("sdmc:/3ds/deadspace/sampling-result.json","w");if(f){fprintf(f,"{\"completed\":true,\"gpu_draws\":%lu,\"gpu_cpu_fragments\":%lu,\"cpu_fragments\":%lu}\n",(unsigned long)gs[0],(unsigned long)cs[2],(unsigned long)cpu_stats[2]);fclose(f);}
wait:for(;;)svcSleepThread(1000000000LL);
}
