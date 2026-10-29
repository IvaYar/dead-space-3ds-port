/* Native New3DS GPU fixture. Synthetic data, no donor loading or RX backend. */
#include <3ds.h>
#include <citro3d.h>
#include "ds13_gles.h"
#include "ds34_gpu.h"
#include "ds_runtime.h"
#include "gpu_hardware_diag.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#define ROOT GPU_HARDWARE_ROOT
#ifndef GPU_TEST_VERSION
#error GPU_TEST_VERSION must be supplied by the hardware fixture builder
#endif
u32 __stacksize__=256*1024;
static DS13Context ctx;
static DSBinding bindings[128];static uint32_t count,presents,cases_completed;
static FILE *journal;static int failed,cancelled;
static DS34Audit audit;
static void console_flush(void){
    u16 w,h;void *pixels=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,&w,&h);
    GSPGPU_FlushDataCache(pixels,(u32)w*h*2);
}
static const float quad[]={-1,-1,0,1,-1,0,-1,1,0,1,1,0};
static const float uv[]={0,0,1,0,0,1,1,1};
static const uint8_t rgba[]={255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255};
static uint8_t large_rgba[256*256*4];
static float rollover[8196*3];
typedef void (*One)(uint32_t) DS13_SOFT;
typedef void (*Two)(uint32_t,uint32_t) DS13_SOFT;
typedef void (*Names)(int32_t,uint32_t*) DS13_SOFT;
typedef void (*Delete)(int32_t,const uint32_t*) DS13_SOFT;
typedef void (*Color)(float,float,float,float) DS13_SOFT;
typedef void (*Pointer)(int32_t,uint32_t,int32_t,const void*) DS13_SOFT;
typedef void (*Draw)(uint32_t,int32_t,int32_t) DS13_SOFT;
typedef void (*Box)(int32_t,int32_t,int32_t,int32_t) DS13_SOFT;
typedef void (*Parameter)(uint32_t,uint32_t,int32_t) DS13_SOFT;
typedef void (*Image)(uint32_t,int32_t,int32_t,int32_t,int32_t,int32_t,uint32_t,uint32_t,const void*) DS13_SOFT;
static void *fn(const char *name){for(uint32_t i=0;i<count;++i)if(!strcmp(name,bindings[i].name))return (void*)bindings[i].address;return NULL;}
static void observed(const char *name,uint32_t value){failed=1;printf("FAIL %s %08lx\n",name,(unsigned long)value);if(journal){fprintf(journal,"FAIL %s %08lx\n",name,(unsigned long)value);fflush(journal);}}
static uint32_t crc(const void *data,uint32_t n){const uint8_t *p=data;uint32_t c=~0u;while(n--){c^=*p++;for(unsigned i=0;i<8;++i)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;}
static int present(void){
    ds34_diagnostic_mark("PRESENT BEGIN");
    if(failed || ctx.error || ds34_present(&ctx))return -1;
    ++presents;
    /* DMA completion and CPU cache visibility are separate requirements. */
    ds34_diagnostic_mark("READBACK INVALIDATE BEGIN");
    Result rc=GSPGPU_InvalidateDataCache(ctx.pixels,192000);
    if(R_FAILED(rc)){observed("readback cache invalidate",(uint32_t)rc);return -1;}
    ds34_diagnostic_mark("READBACK INVALIDATE OK");
    ds34_diagnostic_mark("INTEGRITY AUDIT BEGIN");
    if(ds34_sequence_audit(&audit)){observed("GPU lifetime/integrity audit",presents);return -1;}
    ds34_diagnostic_mark("INTEGRITY AUDIT OK");
    ds34_diagnostic_mark("PRESENT OK");
    return 0;
}
static int near(unsigned x,unsigned y,int r,int g,int b){
    uint32_t off=(x*240+239-y)*2,v=ctx.pixels[off]|ctx.pixels[off+1]<<8;
    int actual[]={((v>>11)&31)*255/31,((v>>5)&63)*255/63,(v&31)*255/31},expected[]={r,g,b};
    for(unsigned i=0;i<3;++i)if(actual[i]-expected[i]>8 || expected[i]-actual[i]>8){
        if(journal)fprintf(journal,"pixel %u,%u got %d,%d,%d expected %d,%d,%d\n",x,y,actual[0],actual[1],actual[2],r,g,b);
        observed("pixel mismatch",x<<16|y);return -1;
    }return 0;
}
static int capture(unsigned id){
    ds34_diagnostic_mark("PIXEL CHECKS OK; CAPTURE BEGIN");
    char path[128];snprintf(path,sizeof(path),ROOT"case-%u.raw",id);FILE *f=fopen(path,"wb");if(!f)return -1;
    int bad=fwrite(ctx.pixels,1,192000,f)!=192000;if(fclose(f))bad=1;if(bad)return -1;
    snprintf(path,sizeof(path),ROOT"case-%u.json",id);f=fopen(path,"w");if(!f)return -1;
    fprintf(f,"{\"case\":%u,\"width\":400,\"height\":240,\"layout\":2,\"bytes\":192000,\"crc32\":\"%08lx\",\"presents\":%lu}\n",id,(unsigned long)crc(ctx.pixels,192000),(unsigned long)presents);
    if(fclose(f))return -1;
    ++cases_completed;ds34_diagnostic_mark("CAPTURE OK");
    printf("Case %u PASS\n",id);if(journal){fprintf(journal,"CASE %u PASS presents=%lu\n",id,(unsigned long)presents);fflush(journal);}return 0;
}
static void texture(uint32_t *name,unsigned dim,const uint8_t *pixels){
    ((Names)fn("glGenTextures"))(1,name);((Two)fn("glBindTexture"))(0xde1,*name);
    ((Parameter)fn("glTexParameteri"))(0xde1,0x2801,0x2600);((Parameter)fn("glTexParameteri"))(0xde1,0x2800,0x2600);
    ((Parameter)fn("glTexParameteri"))(0xde1,0x2802,0x812f);((Parameter)fn("glTexParameteri"))(0xde1,0x2803,0x812f);
    ((Image)fn("glTexImage2D"))(0xde1,0,0x1908,dim,dim,0,0x1908,0x1401,pixels);
    ((Pointer)fn("glTexCoordPointer"))(2,0x1406,0,uv);((One)fn("glEnableClientState"))(0x8078);
}
static void draw(void){ds34_diagnostic_mark("GLES DRAW BEGIN");((Draw)fn("glDrawArrays"))(5,0,4);ds34_diagnostic_mark("GLES DRAW RETURNED");}
static void clear(float r,float g,float b){ds34_diagnostic_mark("GLES CLEAR BEGIN");((Color)fn("glClearColor"))(r,g,b,1);((One)fn("glClear"))(0x4100);ds34_diagnostic_mark("GLES CLEAR RETURNED");}
static int bands(void){return near(200,30,255,255,255) || near(200,90,0,0,255) || near(200,150,0,255,0) || near(200,210,255,0,0);}
static int tests(void){
    u16 w,h;void *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);
    ds_runtime_init(8*1024*1024);
    if(ds13_init(&ctx,pixels,400,240,192000,DS13_RGB565_CTR) || ds13_current(&ctx))return -1;
    ds13_observer(&ctx,observed,NULL);count=ds13_bindings(bindings,128);
    if(count!=99 || ds22_client_range(&ctx,quad,sizeof(quad)) || ds22_client_range(&ctx,uv,sizeof(uv)) || ds22_client_range(&ctx,rollover,sizeof(rollover)))return -1;
    if(journal){fputs("ATTACH BEGIN: GPU white texture transfer\n",journal);fflush(journal);}
    if(ds34_attach(&ctx))return -1;
    if(journal){fputs("ATTACH OK: white texture transfer verified\n",journal);fflush(journal);}
    ds34_diagnostic_mark("VERTEX SETUP BEGIN");
    ((Pointer)fn("glVertexPointer"))(3,0x1406,0,quad);((One)fn("glEnableClientState"))(0x8074);
    ds34_diagnostic_mark("VERTEX SETUP OK");
    clear(16/255.f,32/255.f,48/255.f);if(failed || ctx.error)return -1;
    ((Color)fn("glColor4f"))(0,1,0,1);
    ((Box)fn("glScissor"))(100,40,200,160);((One)fn("glEnable"))(0xc11);draw();
    if(present() || near(200,120,0,255,0) || near(50,120,16,32,48) || capture(0))return -1;
    ((One)fn("glDisable"))(0xc11);((Color)fn("glColor4f"))(1,1,1,1);
    for(unsigned y=0;y<256;++y)for(unsigned x=0;x<256;++x)memcpy(large_rgba+(y*256+x)*4,rgba+(y/64)*4,4);
    uint32_t large=0;texture(&large,256,large_rgba);((One)fn("glEnable"))(0xde1);draw();
    if(present() || bands() || capture(1))return -1;
    ((One)fn("glDisable"))(0xde1);
    ((One)fn("glActiveTexture"))(0x84c1);((One)fn("glClientActiveTexture"))(0x84c1);
    uint32_t second=0;texture(&second,2,rgba);((One)fn("glEnable"))(0xde1);draw();
    if(present() || near(80,40,0,0,255) || near(320,40,255,255,255) || near(80,200,255,0,0) || near(320,200,0,255,0) || capture(2))return -1;
    draw();((One)fn("glDisable"))(0xde1);((Delete)fn("glDeleteTextures"))(1,&second);
    ((Color)fn("glColor4f"))(1,0,0,1);draw();
    if(present() || near(100,120,255,0,0) || near(300,120,255,0,0) || capture(3))return -1;
    ((One)fn("glDisableClientState"))(0x8078);
    ((One)fn("glActiveTexture"))(0x84c0);((One)fn("glClientActiveTexture"))(0x84c0);((One)fn("glDisableClientState"))(0x8078);
    const float left[]={-1,-1,0,0,-1,0,-1,1,0,-1,1,0,0,-1,0,0,1,0};
    const float right[]={0,-1,0,1,-1,0,0,1,0,0,1,0,1,-1,0,1,1,0};
    const float tiny[]={.99f,.99f,0,1,.99f,0,.99f,1,0};
    memcpy(rollover,left,sizeof(left));for(unsigned i=6;i<8190;i+=3)memcpy(rollover+i*3,tiny,sizeof(tiny));memcpy(rollover+8190*3,right,sizeof(right));
    clear(0,0,0);((Color)fn("glColor4f"))(0,1,0,1);((Pointer)fn("glVertexPointer"))(3,0x1406,0,rollover);
    ((Draw)fn("glDrawArrays"))(4,0,8196);
    if(present() || near(100,120,0,255,0) || near(300,120,0,255,0) || audit.peak_vertices!=8190 || !audit.drains || capture(4))return -1;
    ((Pointer)fn("glVertexPointer"))(3,0x1406,0,quad);draw();clear(0,0,1);
    ((Box)fn("glScissor"))(200,0,200,240);((One)fn("glEnable"))(0xc11);((Color)fn("glColor4f"))(1,0,0,1);draw();
    if(present() || near(100,120,0,0,255) || near(300,120,255,0,0) || capture(5))return -1;
    ((One)fn("glDisable"))(0xc11);
    for(unsigned frame=0;frame<16;++frame){
        if(!aptMainLoop()){cancelled=1;return -1;}
        hidScanInput();if(hidKeysDown()&KEY_START){cancelled=1;return -1;}
        clear(0,0,0);((Box)fn("glViewport"))(20+frame*20,40,40,160);((Color)fn("glColor4f"))(frame&1?0:1,frame&1?1:0,0,1);draw();
        if(present() || near(40+frame*20,120,frame&1?0:255,frame&1?255:0,0) || near(5,120,0,0,0))return -1;
    }
    if(capture(6))return -1;
    ((Box)fn("glViewport"))(0,0,400,240);((Color)fn("glColor4f"))(1,1,1,1);
    ((Two)fn("glBindTexture"))(0xde1,large);((Pointer)fn("glTexCoordPointer"))(2,0x1406,0,uv);((One)fn("glEnableClientState"))(0x8078);((One)fn("glEnable"))(0xde1);draw();
    if(present() || bands() || capture(7))return -1;
    uint32_t cpu[4];ds22_stats(&ctx,cpu);
    return failed || ctx.error || cpu[2] || cpu[3] || audit.pending_staging || audit.upload_checks!=2?-1:0;
}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);
    bool new3ds=false;Result model=APT_CheckNew3DS(&new3ds);s64 info=0;int emulator=svcGetSystemInfo(&info,0x20000,0)==0;
    printf("DS34 GPU TEST v" GPU_TEST_VERSION "\nSynthetic data only. No game.\n");
    if(R_FAILED(model) || !new3ds){printf("Requires New Nintendo 3DS.\nSTART to exit.\n");goto wait;}
    gfxSetScreenFormat(GFX_TOP,GSP_RGB565_OES);gfxSwapBuffers();gspWaitForVBlank();
    if((mkdir("sdmc:/3ds",0777) && errno!=EEXIST) || (mkdir(ROOT,0777) && errno!=EEXIST)){printf("SD directory unavailable\n");goto wait;}
    if(remove(ROOT"result.json") && errno!=ENOENT){printf("Cannot clear previous result\n");goto wait;}
    journal=fopen(ROOT"gpu-test.log","w");if(!journal){printf("SD log unavailable\n");goto wait;}
    fprintf(journal,"DS34 native GPU fixture v" GPU_TEST_VERSION " environment=%s\n",emulator?"emulator":"native");fflush(journal);
    gpu_diag_init(journal,emulator);
    FILE *ready=fopen(ROOT"ready.txt","w");if(ready){fputs("Press A to begin\n",ready);fclose(ready);}
    printf("New3DS detected.\nA: begin bounded GPU test\nSTART: exit\n");
    while(aptMainLoop()){
        hidScanInput();u32 keys=hidKeysDown();if(keys&KEY_START)goto finish;
        if(keys&KEY_A){
            int ok=tests()==0;if(cancelled)goto finish;
            uint32_t gpu[4]={0},cpu[4]={0};ds34_stats(gpu);ds22_stats(&ctx,cpu);
            ds34_diagnostic_mark("RESULT WRITE BEGIN");
            FILE *f=fopen(ROOT"result.json","w");if(f){fprintf(f,"{\"version\":\"" GPU_TEST_VERSION "\",\"passed\":%s,\"environment\":\"%s\",\"game_called\":false,\"cases\":8,\"cases_completed\":%lu,\"wait_timeout\":%s,\"timeout_phase\":\"%s\",\"presents\":%lu,\"gpu_draws\":%lu,\"gpu_triangles\":%lu,\"uploads\":%lu,\"cpu_fragments\":%lu,\"cpu_samples\":%lu,\"gl_error\":%lu,\"peak_vertices\":%lu,\"drains\":%lu,\"upload_checks\":%lu,\"upload_mismatches\":%lu,\"vertex_mismatches\":%lu,\"texture_mismatches\":%lu}\n",ok?"true":"false",emulator?"emulator":"native",(unsigned long)cases_completed,gpu_diag_timed_out()?"true":"false",gpu_diag_timeout_phase(),(unsigned long)presents,(unsigned long)gpu[0],(unsigned long)gpu[1],(unsigned long)gpu[2],(unsigned long)cpu[2],(unsigned long)cpu[3],(unsigned long)ctx.error,(unsigned long)audit.peak_vertices,(unsigned long)audit.drains,(unsigned long)audit.upload_checks,(unsigned long)audit.upload_mismatches,(unsigned long)audit.vertex_mismatches,(unsigned long)audit.texture_mismatches);if(fclose(f))ok=0;}else ok=0;
            ds34_diagnostic_mark("RESULT WRITE RETURNED");
            printf(ok?"GPU TEST PASSED\n":"GPU TEST FAILED - inspect log\n");fprintf(journal,"GPU TEST %s\n",ok?"PASSED":"FAILED");fflush(journal);break;
        }
        console_flush();gspWaitForVBlank();
    }
wait:;
    int first_timeout_loop=gpu_diag_timed_out();
    for(;;){
        if(first_timeout_loop)ds34_diagnostic_mark("POST TIMEOUT APT BEGIN");
        if(!aptMainLoop())break;
        if(first_timeout_loop)ds34_diagnostic_mark("POST TIMEOUT APT OK");
        if(first_timeout_loop)ds34_diagnostic_mark("POST TIMEOUT HID BEGIN");
        hidScanInput();u32 keys=hidKeysDown();
        if(first_timeout_loop)ds34_diagnostic_mark("POST TIMEOUT HID OK");
        if(keys&KEY_START){ds34_diagnostic_mark("START RECEIVED");goto finish;}
        if(first_timeout_loop)ds34_diagnostic_mark("POST TIMEOUT CONSOLE FLUSH BEGIN");
        console_flush();
        if(first_timeout_loop)ds34_diagnostic_mark("POST TIMEOUT CONSOLE FLUSH OK");
        first_timeout_loop=0;
        if(gpu_diag_timed_out())svcSleepThread(16666667);else gspWaitForVBlank();
    }
finish:if(!gpu_diag_can_exit()){
        printf("GPU still busy. Memory retained.\nSTART: recheck. Keep log.\n");goto wait;
    }
    if(journal){fputs("EXIT BEGIN\n",journal);fflush(journal);}
    /* Fini waits for the GX queue and unregisters VBlank/APT callbacks. */
    C3D_Fini();if(journal){fputs("EXIT GPU DRAINED\n",journal);fclose(journal);}gfxExit();return 0;
}
