/* Independent Citro3D control: direct SDK API, no game/GLES/DS34 sources. */
#include <3ds.h>
#include <citro3d.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include "control_shader.h"

#define ROOT "sdmc:/3ds/citro3d-control-v0.1.0/"
#define WAIT_MS 2000u
#define SUBMITS 64u
u32 __stacksize__=256*1024;
static FILE *journal;
static int stage=-1,initialized,frame_open,emulator,timed_out,completed;
static const char *failure="none";
static gxCmdQueue_s *queue;
static C3D_RenderTarget *target;
static DVLB_s *shader;
static shaderProgram_s program;
static void *vbo;
static int projection_location;
static C3D_Mtx projection;
static const float vertices[][3]={{200,200,.5f},{100,40,.5f},{300,40,.5f}};
typedef struct {u32 words[8],result,ready;} Submission;
static Submission submissions[SUBMITS];
static u32 submitted,printed;
extern void __real_gxCmdQueueRun(gxCmdQueue_s *q);
extern Result __real_gspSubmitGxCommand(const u32 words[8]);
extern u32 __ctru_linear_heap,__ctru_linear_heap_size;

static void mark(const char *name){
    if(journal){fprintf(journal,"PHASE stage=%d ms=%llu vb=%lu,%lu %s\n",stage,
        (unsigned long long)osGetTime(),(unsigned long)C3D_FrameCounter(0),
        (unsigned long)C3D_FrameCounter(1),name);fflush(journal);}
}
static void snapshot(const char *name){
    if(!journal)return;
    volatile gxCmdQueue_s *q=queue;
    fprintf(journal,"QUEUE %s stage=%d total=%u submitted=%u completed=%u\n",name,stage,
        q?q->numEntries:0,q?q->curEntry:0,q?q->lastEntry:0);
    u32 end=__atomic_load_n(&submitted,__ATOMIC_ACQUIRE);
    while(printed<end && printed<SUBMITS){
        Submission *s=&submissions[printed];if(!__atomic_load_n(&s->ready,__ATOMIC_ACQUIRE))break;
        fprintf(journal,"SUBMIT %lu result=%08lx",(unsigned long)printed,(unsigned long)s->result);
        for(unsigned i=0;i<8;++i)fprintf(journal," %08lx",(unsigned long)s->words[i]);
        fputc('\n',journal);++printed;
    }
    fflush(journal);
}
Result __wrap_gspSubmitGxCommand(const u32 words[8]){
    /* This can run on the GSP thread with the SDK lock held: no I/O here. */
    u32 n=__atomic_fetch_add(&submitted,1,__ATOMIC_RELAXED);
    if(n<SUBMITS)memcpy(submissions[n].words,words,32);
    Result rc=__real_gspSubmitGxCommand(words);
    if(n<SUBMITS){submissions[n].result=(u32)rc;__atomic_store_n(&submissions[n].ready,1,__ATOMIC_RELEASE);}
    return rc;
}
void __wrap_gxCmdQueueRun(gxCmdQueue_s *q){
    queue=q;snapshot("RUN BEGIN");
    if(journal && stage>=0 && q->entries && q->numEntries<=32){
        char name[128];snprintf(name,sizeof(name),ROOT"stage-%d-queue.json",stage);
        FILE *f=fopen(name,"w");
        if(f){fprintf(f,"{\"stage\":%d,\"entries\":[",stage);
            for(unsigned i=0;i<q->numEntries;++i){const gxCmdEntry_s *e=&q->entries[i];
                fprintf(f,"%s{\"index\":%u,\"type\":%u,\"words\":[",i?",":"",i,e->type);
                for(unsigned w=0;w<8;++w)fprintf(f,"%s%lu",w?",":"",(unsigned long)e->data[w]);
                fputs("]}",f);
                if(e->type==1){uintptr_t a=e->args[0];u32 n=e->args[1];
                    if(a>=__ctru_linear_heap && n && n<=C3D_DEFAULT_CMDBUF_SIZE && !(a&7) && !(n&3) &&
                       a-__ctru_linear_heap<=__ctru_linear_heap_size && n<=__ctru_linear_heap_size-(a-__ctru_linear_heap)){
                        snprintf(name,sizeof(name),ROOT"stage-%d-%u.pica",stage,i);FILE *b=fopen(name,"wb");
                        if(b){size_t saved=fwrite((void*)a,1,n,b);int closed=fclose(b);
                            fprintf(journal,"PICA stage=%d entry=%u bytes=%lu captured=%d\n",stage,i,(unsigned long)n,saved==n && !closed);}
                    }
                }
            }fputs("]}\n",f);fclose(f);
        }
    }
    __real_gxCmdQueueRun(q);snapshot("RUN RETURNED");
}
static int fail(const char *reason){failure=reason;mark(reason);snapshot("FAILURE");return -1;}
static int begin_frame(int retire){
    if(frame_open)return 0;
    mark("VBLANK WAIT BEGIN");u32 a=C3D_FrameCounter(0),b=C3D_FrameCounter(1);u64 deadline=osGetTime()+WAIT_MS;
    while(C3D_FrameCounter(0)==a || C3D_FrameCounter(1)==b){
        if(osGetTime()>=deadline){timed_out=1;return fail("VBLANK TIMEOUT");}svcSleepThread(1000000);
    }
    mark("VBLANK WAIT OK");mark("GX WAIT BEGIN");deadline=osGetTime()+WAIT_MS;unsigned previous=65535;
    for(;;){
        if(queue && queue->lastEntry!=previous){previous=queue->lastEntry;snapshot("PROGRESS");}
        int injected=0;
#ifdef CONTROL_FAULT_TEST
        injected=emulator && retire && stage==0;
#endif
        (void)retire;
        if(!injected && C3D_FrameBegin(C3D_FRAME_NONBLOCK)){frame_open=1;mark("GX WAIT OK");return 0;}
        if(osGetTime()>=deadline){timed_out=1;return fail("GX QUEUE TIMEOUT");}svcSleepThread(1000000);
    }
}
static int save(const char *name,const void *data,size_t size){
    char path[128];snprintf(path,sizeof(path),ROOT"%s",name);FILE *f=fopen(path,"wb");if(!f)return -1;
    size_t n=fwrite(data,1,size,f);int bad=fclose(f);return n==size && !bad?0:-1;
}
static u32 pixel(const u8 *p,unsigned x,unsigned y){u32 offset=(x*240+239-y)*2;return p[offset]|p[offset+1]<<8;}
static int near(u32 v,int r,int g,int b){
    int delta[3]={((v>>11)&31)*255/31-r,((v>>5)&63)*255/63-g,(v&31)*255/31-b};
    for(unsigned i=0;i<3;++i)if(delta[i]<-8 || delta[i]>8)return 0;
    return 1;
}
static int scene(void){
    mark("SCENE INIT BEGIN");shader=DVLB_ParseFile((u32*)control_shader,sizeof(control_shader));if(!shader)return fail("SHADER PARSE FAILED");
    shaderProgramInit(&program);if(shaderProgramSetVsh(&program,&shader->DVLE[0]))return fail("SHADER SETUP FAILED");
    C3D_BindProgram(&program);projection_location=shaderInstanceGetUniformLocation(program.vertexShader,"projection");
    if(projection_location<0)return fail("PROJECTION UNIFORM MISSING");
    C3D_AttrInfo *attributes=C3D_GetAttrInfo();AttrInfo_Init(attributes);
    AttrInfo_AddLoader(attributes,0,GPU_FLOAT,3);AttrInfo_AddFixed(attributes,1);C3D_FixedAttribSet(1,1,1,1,1);
    Mtx_OrthoTilt(&projection,0,400,0,240,0,1,true);
    vbo=linearAlloc(sizeof(vertices));if(!vbo)return fail("VBO ALLOCATION FAILED");memcpy(vbo,vertices,sizeof(vertices));
    C3D_BufInfo *buffers=C3D_GetBufInfo();BufInfo_Init(buffers);
    if(BufInfo_Add(buffers,vbo,sizeof(vertices[0]),1,0)<0)return fail("VBO ADDRESS FAILED");
    fprintf(journal,"VBO virtual=%08lx physical=%08lx base=%08lx bytes=%u stride=%u\n",
        (unsigned long)(uintptr_t)vbo,(unsigned long)osConvertVirtToPhys(vbo),(unsigned long)buffers->base_paddr,
        (unsigned)sizeof(vertices),(unsigned)sizeof(vertices[0]));
    if(save("triangle-vertices.bin",vbo,sizeof(vertices)))return fail("VBO CAPTURE FAILED");
    C3D_TexEnv *env=C3D_GetTexEnv(0);C3D_TexEnvInit(env);C3D_TexEnvSrc(env,C3D_Both,GPU_PRIMARY_COLOR,0,0);C3D_TexEnvFunc(env,C3D_Both,GPU_REPLACE);
    mark("SCENE INIT OK");return 0;
}
static int render(void){
    if(begin_frame(0))return -1;
    u16 w,h;u8 *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);if((u32)w*h*2!=192000)return fail("FRAMEBUFFER SIZE FAILED");
    mark("CLEAR BEGIN");C3D_RenderTargetClear(target,C3D_CLEAR_ALL,0x102030,0);mark("CLEAR QUEUED");
    C3D_FrameDrawOn(target);
    if(stage==1){C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER,projection_location,&projection);C3D_DrawArrays(GPU_TRIANGLES,0,3);mark("TRIANGLE QUEUED");}
    mark("FRAME END BEGIN");C3D_FrameEnd(0);frame_open=0;mark("FRAME END RETURNED");
    if(begin_frame(1))return -1; /* Equivalent to the next SDK frame begin: GPU is now retired. */
    mark("READBACK INVALIDATE BEGIN");Result rc=GSPGPU_InvalidateDataCache(pixels,192000);
    if(R_FAILED(rc))return fail("READBACK INVALIDATE FAILED");
    mark("READBACK INVALIDATE OK");
    if(!near(pixel(pixels,20,20),16,32,48) || !near(pixel(pixels,200,120),stage?255:16,stage?255:32,stage?255:48))return fail("PIXEL CHECK FAILED");
    if(stage && memcmp(vbo,vertices,sizeof(vertices)))return fail("VBO CONTENT CHANGED");
    if(save(stage?"triangle.raw":"clear.raw",pixels,192000))return fail("PIXEL CAPTURE FAILED");
    ++completed;printf("%s PASS\n",stage?"TRIANGLE":"CLEAR");mark("STAGE PASS");return 0;
}
static int run(void){
    mark("C3D INIT BEGIN");if(!C3D_Init(C3D_DEFAULT_CMDBUF_SIZE))return fail("C3D INIT FAILED");initialized=1;mark("C3D INIT OK");
    target=C3D_RenderTargetCreate(240,400,GPU_RB_RGB8,GPU_RB_DEPTH24_STENCIL8);if(!target)return fail("TARGET ALLOCATION FAILED");
    u32 flags=GX_TRANSFER_FLIP_VERT(0)|GX_TRANSFER_OUT_TILED(0)|GX_TRANSFER_RAW_COPY(0)|GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGB8)|GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB565)|GX_TRANSFER_SCALING(GX_TRANSFER_SCALE_NO);
    C3D_RenderTargetSetOutput(target,GFX_TOP,GFX_LEFT,flags);
    fprintf(journal,"TARGET color=%08lx depth=%08lx format=RGB8/D24S8 dimensions=240x400 transfer=%08lx\n",
        (unsigned long)(uintptr_t)target->frameBuf.colorBuf,(unsigned long)(uintptr_t)target->frameBuf.depthBuf,(unsigned long)flags);fflush(journal);
    stage=0;if(render())return -1; /* No shader, texture, VBO or draw before this pass. */
    stage=1;if(scene() || render())return -1;return 0;
}
static void flush_console(void){u16 w,h;void *p=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,&w,&h);GSPGPU_FlushDataCache(p,(u32)w*h*2);}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);bool newer=false;s64 info=0;emulator=svcGetSystemInfo(&info,0x20000,0)==0;
    printf("CITRO3D CONTROL v0.1.0\nNo DS34. No game.\n");
    if(R_FAILED(APT_CheckNew3DS(&newer)) || !newer){printf("New3DS required\n");goto wait;}
#ifdef CONTROL_FAULT_TEST
    if(!emulator){printf("Emulator-only fault build\n");goto wait;}
#endif
    gfxSetScreenFormat(GFX_TOP,GSP_RGB565_OES);gfxSwapBuffers();gspWaitForVBlank();
    if((mkdir("sdmc:/3ds",0777) && errno!=EEXIST) || (mkdir(ROOT,0777) && errno!=EEXIST))goto wait;
    if(remove(ROOT"result.json") && errno!=ENOENT)goto wait;
    journal=fopen(ROOT"control.log","w");if(!journal)goto wait;
    fprintf(journal,"CITRO3D CONTROL v0.1.0 environment=%s\n",emulator?"emulator":"native");fflush(journal);
    if(save("ready.txt","Press A\n",8))goto wait;
    printf("A: clear, then triangle\nSTART: checked exit\n");
    while(aptMainLoop()){
        hidScanInput();u32 keys=hidKeysDown();if(keys&KEY_START)goto finish;
        if(keys&KEY_A){int ok=run()==0;FILE *f=fopen(ROOT"result.json","w");
            if(f){fprintf(f,"{\"version\":\"0.1.0\",\"environment\":\"%s\",\"passed\":%s,\"stages_completed\":%d,\"stage\":%d,\"timeout\":%s,\"failure\":\"%s\",\"ds34_linked\":false,\"game_called\":false}\n",emulator?"emulator":"native",ok?"true":"false",completed,stage,timed_out?"true":"false",failure);fclose(f);}
            printf("CONTROL %s\n",ok?"PASSED":"FAILED");mark("RESULT SAVED");break;}
        flush_console();gspWaitForVBlank();
    }
wait:while(aptMainLoop()){hidScanInput();if(hidKeysDown()&KEY_START)goto finish;flush_console();svcSleepThread(16666667);}
finish:
    if(initialized && !frame_open){mark("EXIT PRECHECK");snapshot("EXIT PRECHECK");
        if(!C3D_FrameBegin(C3D_FRAME_NONBLOCK)){printf("GPU busy; memory retained\nSTART: recheck\n");mark("EXIT DEFERRED");goto wait;}frame_open=1;}
    mark("EXIT BEGIN");if(initialized)C3D_Fini();
    if(vbo)linearFree(vbo);
    if(shader){shaderProgramFree(&program);DVLB_Free(shader);}
    mark("EXIT GPU DRAINED");if(journal)fclose(journal);gfxExit();return 0;
}
