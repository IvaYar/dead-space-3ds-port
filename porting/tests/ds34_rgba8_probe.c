/* Synthetic DS34 RGBA8 -> RGB8 native control. No game or native RX backend. */
#include <3ds.h>
#include <citro3d.h>
#include "ds13_gles.h"
#include "ds34_gpu.h"
#include "ds_runtime.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#define ROOT "sdmc:/3ds/ds34-rgba8-v0.1.0/"
#define BYTES (400u*240u*3u)
#define FRAMES 9u
#define RECORDS 64u
#define COMMANDS 32u
u32 __stacksize__=256*1024;
static DS13Context ctx;
static DSBinding bindings[128];
static uint32_t binding_count,completed_frames,failed,retired_runs,bad_retirement;
static FILE *journal;
static uint64_t epoch;
static DS34Audit audit;
static uint32_t queue_address,record_count,printed;
typedef struct {uint32_t kind,total,submitted,completed,words[COMMANDS][8],commit;} Record;
static Record records[RECORDS];
extern void __real_gxCmdQueueRun(gxCmdQueue_s *q);
extern void __real_gxCmdQueueClear(gxCmdQueue_s *q);

/* No stdio, allocation, waits, callback replacement or queue-field writes here.
 * SDK Clear can also be called by onQueueFinish for safe transfers. */
static void record_queue(unsigned kind,gxCmdQueue_s *q){
    __atomic_store_n(&queue_address,(uint32_t)(uintptr_t)q,__ATOMIC_RELEASE);
    uint32_t n=__atomic_fetch_add(&record_count,1,__ATOMIC_RELAXED);
    if(n>=RECORDS)return;
    Record *r=&records[n];volatile gxCmdQueue_s *v=q;
    r->kind=kind;r->total=v->numEntries;r->submitted=v->curEntry;r->completed=v->lastEntry;
    if(q->entries && r->total<=COMMANDS && r->total<=v->maxEntries)
        for(unsigned i=0;i<r->total;++i)for(unsigned j=0;j<8;++j)r->words[i][j]=q->entries[i].data[j];
    else if(r->total)r->kind=2;
    if(kind==1 && r->total){
        __atomic_fetch_add(&retired_runs,1,__ATOMIC_RELAXED);
        if(r->submitted!=r->total || r->completed!=r->total)__atomic_store_n(&bad_retirement,1,__ATOMIC_RELEASE);
    }
    __atomic_store_n(&r->commit,n+1,__ATOMIC_RELEASE);
}
void __wrap_gxCmdQueueRun(gxCmdQueue_s *q){record_queue(0,q);__real_gxCmdQueueRun(q);}
void __wrap_gxCmdQueueClear(gxCmdQueue_s *q){record_queue(1,q);__real_gxCmdQueueClear(q);}

/* Persist only on the application's main thread, outside SDK/IRQ callbacks. */
static void dump_records(void){
    uint32_t end=__atomic_load_n(&record_count,__ATOMIC_ACQUIRE);
    if(end>RECORDS){failed=1;end=RECORDS;}
    while(printed<end){
        Record *r=&records[printed];
        if(__atomic_load_n(&r->commit,__ATOMIC_ACQUIRE)!=printed+1)break;
        char path[128];snprintf(path,sizeof(path),ROOT"queue-%02lu.json",(unsigned long)printed);
        FILE *f=fopen(path,"w");if(!f){failed=1;return;}
        fprintf(f,"{\"index\":%lu,\"phase\":\"%s\",\"total\":%lu,\"submitted\":%lu,\"completed\":%lu,\"entries\":[",
            (unsigned long)printed,r->kind==0?"before-run":r->kind==1?"before-clear":"invalid",
            (unsigned long)r->total,(unsigned long)r->submitted,(unsigned long)r->completed);
        for(unsigned i=0;i<r->total && i<COMMANDS;++i){
            fprintf(f,"%s[",i?",":"");for(unsigned j=0;j<8;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)r->words[i][j]);fputc(']',f);
        }
        fputs("]}\n",f);if(fclose(f))failed=1;
        if(journal)fprintf(journal,"QUEUE %lu %s total=%lu submitted=%lu completed=%lu\n",(unsigned long)printed,
            r->kind==0?"RUN":"CLEAR",(unsigned long)r->total,(unsigned long)r->submitted,(unsigned long)r->completed);
        ++printed;
    }
}
void ds34_diagnostic_mark(const char *phase){
    dump_records();if(journal){fprintf(journal,"PHASE ms=%llu frame=%lu vb=%lu,%lu %s\n",
        (unsigned long long)(osGetTime()-epoch),(unsigned long)completed_frames,
        (unsigned long)C3D_FrameCounter(0),(unsigned long)C3D_FrameCounter(1),phase);fflush(journal);}
}
int ds34_diagnostic_begin(uint32_t flags){
    ds34_diagnostic_mark("SDK FRAME BEGIN");
    int ok=C3D_FrameBegin(flags); /* Preserve real SYNCDRAW, including SDK waits. */
    ds34_diagnostic_mark(ok?"SDK FRAME BEGIN OK":"SDK FRAME BEGIN FAILED");return ok;
}
void ds34_diagnostic_end(void){ds34_diagnostic_mark("SDK FRAME END BEGIN");C3D_FrameEnd(0);ds34_diagnostic_mark("SDK FRAME END OK");}
int ds34_diagnostic_sync(void){ds34_diagnostic_mark("SDK SYNC BEGIN");C3D_FrameSync();ds34_diagnostic_mark("SDK SYNC OK");return 0;}
static void flush_bottom(void){
    u16 w,h;void *p=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,&w,&h);
    unsigned bpp=gfxGetScreenFormat(GFX_BOTTOM)==GSP_RGB565_OES?2:3;
    GSPGPU_FlushDataCache(p,(uint32_t)w*h*bpp);
}
static void observed(const char *name,uint32_t arg){
    failed=1;if(journal){fprintf(journal,"FAIL %s %08lx\n",name,(unsigned long)arg);fflush(journal);}
}
typedef void (*One)(uint32_t) DS13_SOFT;
typedef void (*Color)(float,float,float,float) DS13_SOFT;
typedef void (*Pointer)(int32_t,uint32_t,int32_t,const void*) DS13_SOFT;
typedef void (*Box)(int32_t,int32_t,int32_t,int32_t) DS13_SOFT;
typedef void (*Draw)(uint32_t,int32_t,int32_t) DS13_SOFT;
static void *fn(const char *name){for(unsigned i=0;i<binding_count;++i)if(!strcmp(bindings[i].name,name))return (void*)bindings[i].address;return NULL;}
static uint32_t crc(const void *data,unsigned size){const uint8_t *p=data;uint32_t c=~0u;while(size--){c^=*p++;for(unsigned i=0;i<8;++i)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;}
static const float quad[]={-1,-1,0,1,-1,0,-1,1,0,1,1,0};
static void pattern(unsigned frame,unsigned *x,uint8_t rgb[3]){
    unsigned step=frame<7?frame:6;*x=40+32*step;
    rgb[0]=rgb[1]=rgb[2]=step?0:255;if(step)rgb[(step-1)%3]=255;
}
static int check_and_capture(unsigned frame){
    if(ctx.layout!=DS13_BGR8_CTR || ctx.capacity!=BYTES)return -1;
    ds34_diagnostic_mark("READBACK INVALIDATE BEGIN");
    if(R_FAILED(GSPGPU_InvalidateDataCache(ctx.pixels,BYTES)))return -1;
    ds34_diagnostic_mark("READBACK INVALIDATE OK");
    unsigned left;uint8_t foreground[3];pattern(frame,&left,foreground);
    /* Compare every pixel, using the actual BGR column layout, logical y up. */
    for(unsigned x=0;x<400;++x)for(unsigned y=0;y<240;++y){
        const uint8_t bg[]={104,176,216};
        const uint8_t *want=x>=left && x<left+64 && y>=40 && y<120?foreground:bg;
        const uint8_t *got=ctx.pixels+(x*240+y)*3;
        if(got[0]!=want[2] || got[1]!=want[1] || got[2]!=want[0]){observed("BGR8 pixel mismatch",x<<16|y);return -1;}
    }
    if(ds34_sequence_audit(&audit))return -1;
    char path[128];snprintf(path,sizeof(path),ROOT"frame-%02u.raw",frame);FILE *f=fopen(path,"wb");if(!f)return -1;
    int bad=fwrite(ctx.pixels,1,BYTES,f)!=BYTES;if(fclose(f))bad=1;if(bad)return -1;
    snprintf(path,sizeof(path),ROOT"frame-%02u.json",frame);f=fopen(path,"w");if(!f)return -1;
    fprintf(f,"{\"frame\":%u,\"width\":400,\"height\":240,\"layout\":1,\"bytes\":%u,\"crc32\":\"%08lx\",\"left\":%u,\"foreground_RGB\":[%u,%u,%u]}\n",
        frame,BYTES,(unsigned long)crc(ctx.pixels,BYTES),left,foreground[0],foreground[1],foreground[2]);
    if(fclose(f))return -1;
    ++completed_frames;ds34_diagnostic_mark("FRAME PIXELS AND CAPTURE PASS");return 0;
}
static int tests(void){
    u16 w,h;void *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);
    if(gfxGetScreenFormat(GFX_TOP)!=GSP_BGR8_OES || w!=240 || h!=400)return -1;
    ds_runtime_init(8*1024*1024);
    if(ds13_init(&ctx,pixels,400,240,BYTES,DS13_BGR8_CTR) || ds13_current(&ctx))return -1;
    ds13_observer(&ctx,observed,NULL);binding_count=ds13_bindings(bindings,128);
    if(binding_count!=99 || ds22_client_range(&ctx,quad,sizeof(quad)))return -1;
    ds34_diagnostic_mark("ATTACH BEGIN");if(ds34_attach(&ctx))return -1;ds34_diagnostic_mark("ATTACH OK");
    ((Pointer)fn("glVertexPointer"))(3,0x1406,0,quad);((One)fn("glEnableClientState"))(0x8074);
    for(unsigned frame=0;frame<FRAMES;++frame){
        if(!aptMainLoop())return -1;
        ((One)fn("glDisable"))(0xc11);
        ((Color)fn("glClearColor"))(104/255.f,176/255.f,216/255.f,1);
        ((One)fn("glClear"))(0x4100);
        unsigned left;uint8_t color[3];pattern(frame,&left,color);
        ((Box)fn("glScissor"))(left,40,64,80);((One)fn("glEnable"))(0xc11);
        ((Color)fn("glColor4f"))(color[0]/255.f,color[1]/255.f,color[2]/255.f,1);
        ((Draw)fn("glDrawArrays"))(5,0,4);
        ds34_diagnostic_mark("PRESENT BEGIN");if(failed || ctx.error || ds34_present(&ctx))return -1;
        ds34_diagnostic_mark("PRESENT OK");
        if(check_and_capture(frame))return -1;
        if(!frame){printf("First DS34 frame PASS\n");flush_bottom();}
    }
    uint32_t gpu[4],cpu[4];ds34_stats(gpu);ds22_stats(&ctx,cpu);
    return failed || ctx.error || gpu[0]!=FRAMES || gpu[1]!=FRAMES*2 || cpu[2] || cpu[3] ||
        audit.presents!=FRAMES || bad_retirement || retired_runs<FRAMES?-1:0;
}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);epoch=osGetTime();
    bool new3ds=false;Result model=APT_CheckNew3DS(&new3ds);s64 info=0;int emulator=svcGetSystemInfo(&info,0x20000,0)==0;
    printf("DS34 RGBA8 -> RGB8 v0.1.0\nSynthetic draw/present only\n");
    if(R_FAILED(model) || !new3ds){printf("Requires New Nintendo 3DS\n");goto wait;}
    if((mkdir("sdmc:/3ds",0777) && errno!=EEXIST) || (mkdir(ROOT,0777) && errno!=EEXIST))goto wait;
    const char *old[]={"result.json","exit.txt","ready.txt"};
    for(unsigned i=0;i<3;++i){char path[128];snprintf(path,sizeof(path),ROOT"%s",old[i]);if(remove(path) && errno!=ENOENT)goto wait;}
    for(unsigned i=0;i<FRAMES;++i)for(unsigned ext=0;ext<2;++ext){
        char path[128];snprintf(path,sizeof(path),ROOT"frame-%02u.%s",i,ext?"json":"raw");if(remove(path) && errno!=ENOENT)goto wait;
    }
    for(unsigned i=0;i<RECORDS;++i){char path[128];snprintf(path,sizeof(path),ROOT"queue-%02u.json",i);if(remove(path) && errno!=ENOENT)goto wait;}
    journal=fopen(ROOT"gpu-test.log","w");if(!journal)goto wait;
    fprintf(journal,"DS34 RGBA8 RGB8 v0.1.0 environment=%s bytes=%u layout=1 flags=00001000\n",emulator?"emulator":"native",BYTES);fflush(journal);
    FILE *ready=fopen(ROOT"ready.txt","w");if(!ready)goto wait;fputs("A begins one test\n",ready);if(fclose(ready))goto wait;
    printf("A: run nine frames once\nSTART: exit\nMay hang inside SDK waits.\n");
    while(aptMainLoop()){
        hidScanInput();u32 keys=hidKeysDown();if(keys&KEY_START)goto finish;
        if(keys&KEY_A){
            int ok=tests()==0;uint32_t gpu[4],cpu[4];ds34_stats(gpu);ds22_stats(&ctx,cpu);
            ds34_diagnostic_mark("RESULT WRITE BEGIN");FILE *f=fopen(ROOT"result.json","w");
            if(f){fprintf(f,"{\"version\":\"0.1.0\",\"passed\":%s,\"environment\":\"%s\",\"game_called\":false,\"frames\":%lu,\"bytes\":%u,\"layout\":1,\"gpu_draws\":%lu,\"gpu_triangles\":%lu,\"cpu_fragments\":%lu,\"cpu_samples\":%lu,\"gl_error\":%lu,\"retired_runs\":%lu,\"bad_retirement\":%lu,\"vertex_mismatches\":%lu,\"texture_mismatches\":%lu}\n",
                ok?"true":"false",emulator?"emulator":"native",(unsigned long)completed_frames,BYTES,(unsigned long)gpu[0],(unsigned long)gpu[1],
                (unsigned long)cpu[2],(unsigned long)cpu[3],(unsigned long)ctx.error,(unsigned long)retired_runs,(unsigned long)bad_retirement,
                (unsigned long)audit.vertex_mismatches,(unsigned long)audit.texture_mismatches);if(fclose(f))ok=0;}else ok=0;
            ds34_diagnostic_mark(ok?"TEST PASS":"TEST FAIL");printf(ok?"DS34 TEST PASS: 9 frames\n":"DS34 TEST FAIL: keep SD logs\n");break;
        }
        flush_bottom();gspWaitForVBlank();
    }
wait:
    while(aptMainLoop()){hidScanInput();if(hidKeysDown()&KEY_START)break;flush_bottom();svcSleepThread(16666667);}
finish:;
    gxCmdQueue_s *q=(void*)(uintptr_t)__atomic_load_n(&queue_address,__ATOMIC_ACQUIRE);
    if(q && !gxCmdQueueWait(q,0)){printf("GPU busy. Memory retained.\nSTART: recheck; keep logs.\n");goto wait;}
    ds34_diagnostic_mark("EXIT BEGIN");if(q)C3D_Fini();
    ds34_diagnostic_mark("EXIT GPU DRAINED");
    if(journal){FILE *f=fopen(ROOT"exit.txt","w");if(f){fputs("GPU drained; returning to HOME\n",f);fclose(f);}fclose(journal);}
    gfxExit();return 0;
}
