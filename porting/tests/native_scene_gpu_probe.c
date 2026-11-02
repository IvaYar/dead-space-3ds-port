/* Synthetic CPU/PICA comparison only; this fixture is never the game scene. */
#include <3ds.h>
#include "ds13_gles.h"
#include "ds34_gpu.h"
#include "ds_runtime.h"
#include <stdio.h>
#include <string.h>
static DS13Context cpu,gpu;
static uint8_t pixels[288000],texels[16]={128,200,32,64,128,200,32,64,128,200,32,64,128,200,32,64};
static uint8_t snapshot[288000];
static const float quad[]={-1,-1,0,1,-1,1,-1,1,0,1,1,1},uv[]={0,0,1,0,0,1,1,1};
static DSBinding b[192];static unsigned n;
int ds_scene_defer_resident(void){return 1;}
void scene_texture_event(unsigned k,DS15Object *o,unsigned b,unsigned c,unsigned r,unsigned f){(void)k;(void)o;(void)b;(void)c;(void)r;(void)f;}
typedef void (*One)(u32) DS13_SOFT;
typedef void (*Two)(u32,u32) DS13_SOFT;
typedef void (*Ptr)(int,u32,int,const void *) DS13_SOFT;
typedef void (*Color)(float,float,float,float) DS13_SOFT;
typedef void (*Fog)(u32,float) DS13_SOFT;
typedef void (*Fogv)(u32,const float *) DS13_SOFT;
typedef void (*Draw)(u32,int,int) DS13_SOFT;
typedef void (*Image)(u32,int,int,int,int,int,u32,u32,const void *) DS13_SOFT;
typedef void (*SubImage)(u32,int,int,int,int,int,u32,u32,const void *) DS13_SOFT;
typedef void (*Param)(u32,u32,int) DS13_SOFT;
typedef void (*Matrix)(const float *) DS13_SOFT;
typedef u32 (*GetError)(void) DS13_SOFT;
static void *fn(const char *name){for(unsigned i=0;i<n;++i)if(!strcmp(b[i].name,name))return (void *)b[i].address;return NULL;}
static int setup(DS13Context *c,void *data){
    if(ds13_init(c,data,400,240,288000,DS13_BGR8_CTR)||ds13_current(c)||ds30_attach(c)||ds31_attach(c))return -1;
    if(ds22_client_range(c,quad,sizeof(quad))||ds22_client_range(c,uv,sizeof(uv)))return -1;
    ((Ptr)fn("glVertexPointer"))(3,0x1406,0,quad);((One)fn("glEnableClientState"))(0x8074);
    ((Ptr)fn("glTexCoordPointer"))(2,0x1406,0,uv);((One)fn("glEnableClientState"))(0x8078);
    ((Color)fn("glColor4f"))(1,.4f,.2f,.6f);
    const float k[]={.1f,.2f,.9f,1};((Fogv)fn("glFogfv"))(0xb66,k);
    ((Fog)fn("glFogf"))(0xb65,0x2601);((Fog)fn("glFogf"))(0xb63,0);((Fog)fn("glFogf"))(0xb64,1);
    ((Two)fn("glBindTexture"))(0xde1,1);((Image)fn("glTexImage2D"))(0xde1,0,0x1908,2,2,0,0x1908,0x1401,texels);
    ((Param)fn("glTexParameteri"))(0xde1,0x2801,0x2600);((Param)fn("glTexParameteri"))(0xde1,0x2800,0x2600);
    ((Param)fn("glTexParameteri"))(0xde1,0x2802,0x812f);((Param)fn("glTexParameteri"))(0xde1,0x2803,0x812f);
    return 0;
}
int main(void){
    gfxInitDefault();s64 emu;if(svcGetSystemInfo(&emu,0x20000,0))goto wait;
    ds_runtime_init(8*1024*1024);n=ds13_bindings(b,192);n+=ds30_bindings(b+n,192-n);
#ifdef DS_SCENE_STORE_TEST
    DSBinding fbo_bindings[32];unsigned fbo_count=ds26_bindings(fbo_bindings,32);
    for(unsigned i=0;i<fbo_count;++i){unsigned j=0;while(j<n && strcmp(b[j].name,fbo_bindings[i].name))++j;b[j]=fbo_bindings[i];if(j==n)++n;}
#endif
    if(setup(&cpu,pixels))goto wait;
    u16 w,h;
    if(setup(&gpu,gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h))||ds34_attach(&gpu))goto wait;
    const float hidden[]={3,3,0,5,3,0,3,5,0,5,5,0};
    const float projected[]={0,0,0,.5f,2,0,0,2,0,.5f,0,.5f,2,2,0,2};
    const float projected_constant[]={0,0,0,2,2,0,0,2,0,2,0,2,2,2,0,2};
    const float constant_q[]={1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,2};
    const uint8_t pattern[]={255,32,64,255,32,240,64,255,32,64,255,255,240,240,64,255};
    u32 hidden_uploads[2]={0},hidden_triangles[2]={0};
    for(unsigned test=0;test<15;++test)for(unsigned hw=0;hw<2;++hw){
        DS13Context *c=hw?&gpu:&cpu;if(ds13_current(c))goto wait;
        ((Color)fn("glClearColor"))(.15f,.25f,.35f,1);((One)fn("glClear"))(0x4000);
        ((One)fn(test==0?"glDisable":"glEnable"))(0xb60);
        ((One)fn(test<2?"glDisable":"glEnable"))(0xde1);
        ((One)fn(test==3?"glEnable":"glDisable"))(0xbe2);((Two)fn("glBlendFunc"))(0x302,0x303);
        if(test==6 || test==7){
            uint8_t changed[16]={16,64,240,128,16,64,240,128,16,64,240,128,16,64,240,128};
            if(test==6)((SubImage)fn("glTexSubImage2D"))(0xde1,0,0,0,2,2,0x1908,0x1401,changed);
            else ((Image)fn("glTexImage2D"))(0xde1,0,0x1908,2,2,0,0x1908,0x1401,texels);
        }
        if(test>=4 && test<=5){
            ((Param)fn("glTexEnvi"))(0x2300,0x2200,0x8570);
            ((Param)fn("glTexEnvi"))(0x2300,0x8571,test==4?0x2100:0x8575);
        }else ((Param)fn("glTexEnvi"))(0x2300,0x2200,0x2100);
        if(test==8 || test==9){
            ((Two)fn("glBindTexture"))(0xde1,test+2);
            ((Image)fn("glTexImage2D"))(0xde1,0,0x1908,2,2,0,0x1908,0x1401,texels);
            ((Param)fn("glTexParameteri"))(0xde1,0x2801,0x2600);((Param)fn("glTexParameteri"))(0xde1,0x2800,0x2600);
            ((Param)fn("glTexParameteri"))(0xde1,0x2802,0x812f);((Param)fn("glTexParameteri"))(0xde1,0x2803,0x812f);
        }
        ((One)fn(test==8?"glEnable":"glDisable"))(0xb44);
        ((One)fn("glCullFace"))(0x408);
        if(test==9){if(ds22_client_range(c,hidden,sizeof(hidden)))goto wait;((Ptr)fn("glVertexPointer"))(3,0x1406,0,hidden);}
        if(test==10)((Ptr)fn("glVertexPointer"))(3,0x1406,0,quad);
        if(test>=11){
            ((One)fn("glDisable"))(0xb60);((Color)fn("glColor4f"))(1,1,1,1);
            ((Image)fn("glTexImage2D"))(0xde1,0,0x1908,2,2,0,0x1908,0x1401,pattern);
            ((Param)fn("glTexParameteri"))(0xde1,0x2801,0x2601);((Param)fn("glTexParameteri"))(0xde1,0x2800,0x2601);
            const float *tc=test==11?projected_constant:projected;
            if(ds22_client_range(c,tc,sizeof(projected)))goto wait;
            ((Ptr)fn("glTexCoordPointer"))(4,0x1406,0,tc);
            if(test>=13){
                ((One)fn("glActiveTexture"))(0x84c1);((One)fn("glEnable"))(0xde1);((Two)fn("glBindTexture"))(0xde1,11);
                if(test==14){
                    ((One)fn("glClientActiveTexture"))(0x84c1);((One)fn("glEnableClientState"))(0x8078);((Ptr)fn("glTexCoordPointer"))(2,0x1406,0,uv);
                    ((One)fn("glClientActiveTexture"))(0x84c0);((One)fn("glMatrixMode"))(0x1702);((Matrix)fn("glLoadMatrixf"))(constant_q);((One)fn("glMatrixMode"))(0x1700);
                }
                ((One)fn("glActiveTexture"))(0x84c0);
            }
        }
        u32 before[4],after[4];ds34_stats(before);
        ((Draw)fn("glDrawArrays"))(5,0,4);
        ds34_stats(after);
        if(hw && (test==8 || test==9)){hidden_uploads[test-8]=after[2]-before[2];hidden_triangles[test-8]=after[1]-before[1];}
        if(c->error || (hw&&ds34_present(c)))goto wait;
        if(hw){gspWaitForVBlank();GSPGPU_InvalidateDataCache(c->pixels,288000);}
        memcpy(snapshot,c->pixels,288000);
        char name[128];snprintf(name,sizeof(name),"sdmc:/3ds/deadspace/scene-%s-%u.raw",hw?"gpu":"cpu",test);
        FILE *f=fopen(name,"wb");if(!f)goto wait;size_t wrote=fwrite(snapshot,1,288000,f);if(fclose(f)||wrote!=288000)goto wait;
    }
    {FILE *f=fopen("sdmc:/3ds/deadspace/scene-visible-stats.json","w");if(!f)goto wait;fprintf(f,"{\"culled_uploads\":%lu,\"clipped_uploads\":%lu,\"culled_triangles\":%lu,\"clipped_triangles\":%lu}\n",(unsigned long)hidden_uploads[0],(unsigned long)hidden_uploads[1],(unsigned long)hidden_triangles[0],(unsigned long)hidden_triangles[1]);if(fclose(f))goto wait;}
    /* Unit 1 with varying q has no exact native implementation yet. */
    if(ds13_current(&gpu))goto wait;
    ((One)fn("glActiveTexture"))(0x84c1);((One)fn("glMatrixMode"))(0x1702);((GetError)fn("glGetError"))();
    typedef void (*Void)(void) DS13_SOFT;((Void)fn("glLoadIdentity"))();
    ((One)fn("glClientActiveTexture"))(0x84c1);((Ptr)fn("glTexCoordPointer"))(4,0x1406,0,projected);((One)fn("glActiveTexture"))(0x84c0);
    ((Draw)fn("glDrawArrays"))(5,0,4);u32 refused=((GetError)fn("glGetError"))();
    {FILE *f=fopen("sdmc:/3ds/deadspace/scene-projective-refusal.json","w");if(!f)goto wait;fprintf(f,"{\"varying_unit1_error\":%lu}\n",(unsigned long)refused);if(fclose(f))goto wait;}
#ifdef DS_SCENE_STORE_TEST
    extern void ds_scene_test_evict(void);extern int scene_store_probe(void);
    ((One)fn("glActiveTexture"))(0x84c1);((One)fn("glDisable"))(0xde1);
    ((One)fn("glActiveTexture"))(0x84c0);((One)fn("glClientActiveTexture"))(0x84c0);((Ptr)fn("glTexCoordPointer"))(4,0x1406,0,projected_constant);
    for(unsigned pass=0;pass<2;++pass){
        if(pass)ds_scene_test_evict();
        ((One)fn("glClear"))(0x4000);((Draw)fn("glDrawArrays"))(5,0,4);
        if(gpu.error || ds34_present(&gpu))goto wait;
        gspWaitForVBlank();GSPGPU_InvalidateDataCache(gpu.pixels,288000);memcpy(snapshot,gpu.pixels,288000);
        char name[128];snprintf(name,sizeof(name),"sdmc:/3ds/deadspace/store-reload-%u.raw",pass);FILE *f=fopen(name,"wb");if(!f)goto wait;
        if(fwrite(snapshot,1,288000,f)!=288000 || fclose(f))goto wait;
        DS34Audit audit;if(ds34_sequence_audit(&audit))goto wait;
    }
    /* A CPU FBO write must invalidate both the GPU entry and its disk image. */
    typedef void (*Gen)(int,u32 *) DS13_SOFT;
    typedef void (*Attach)(u32,u32,u32,u32,int) DS13_SOFT;
    for(unsigned hw=0;hw<2;++hw){
        DS13Context *c=hw?&gpu:&cpu;if(ds13_current(c))goto wait;
        ((One)fn("glActiveTexture"))(0x84c1);((One)fn("glDisable"))(0xde1);((One)fn("glActiveTexture"))(0x84c0);
        ((One)fn("glClientActiveTexture"))(0x84c0);((Ptr)fn("glTexCoordPointer"))(4,0x1406,0,projected_constant);
        ((Two)fn("glBindTexture"))(0xde1,11);
        u32 fbo=0;((Gen)fn("glGenFramebuffersOES"))(1,&fbo);((Two)fn("glBindFramebufferOES"))(0x8d40,fbo);
        ((Attach)fn("glFramebufferTexture2DOES"))(0x8d40,0x8ce0,0xde1,11,0);
        ((Color)fn("glClearColor"))(.2f,.4f,.6f,1);((One)fn("glClear"))(0x4000);
        ((Two)fn("glBindFramebufferOES"))(0x8d40,0);((One)fn("glEnable"))(0xde1);
        ((Color)fn("glClearColor"))(.15f,.25f,.35f,1);((One)fn("glClear"))(0x4000);
        if(hw)ds_scene_test_evict();
        ((Draw)fn("glDrawArrays"))(5,0,4);if(c->error || (hw && ds34_present(c)))goto wait;
        if(hw){gspWaitForVBlank();GSPGPU_InvalidateDataCache(c->pixels,288000);}
        memcpy(snapshot,c->pixels,288000);char name[128];snprintf(name,sizeof(name),"sdmc:/3ds/deadspace/scene-%s-15.raw",hw?"gpu":"cpu");
        FILE *f=fopen(name,"wb");if(!f)goto wait;if(fwrite(snapshot,1,288000,f)!=288000 || fclose(f))goto wait;
    }
    if(scene_store_probe())goto wait;
#endif
    {FILE *f=fopen("sdmc:/3ds/deadspace/scene-fixture-done.txt","w");if(f){fputs("CPU/PICA comparisons complete\n",f);fclose(f);}}
wait:for(;;)svcSleepThread(1000000000LL);
}
