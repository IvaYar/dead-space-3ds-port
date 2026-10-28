/* Emulator-only PICA foundation. No donor, JNI bridge or CPU rasterizer linked.
 * Citro3D initialization follows devkitPro's public simple_tri example. */
#include <3ds.h>
#include <citro3d.h>
#include <stdio.h>
#include <string.h>
#include "gpu_probe_shader.h"
#define ROOT "sdmc:/3ds/deadspace/"
typedef struct {float x,y,z,r,g,b;} Vertex;
static const Vertex vertices[]={
    {200,200,.5,1,0,0},{100,40,.5,0,1,0},{300,40,.5,0,0,1}
};
static uint32_t crc32(const void *data,uint32_t n){
    const uint8_t *p=data;uint32_t c=~0u;
    while(n--){c^=*p++;for(unsigned i=0;i<8;++i)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;
}
int main(void){
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);
    s64 emulator=0;
    if(svcGetSystemInfo(&emulator,0x20000,0)!=0){printf("REFUSED: emulator-only GPU probe\n");goto wait;}
    if(!C3D_Init(C3D_DEFAULT_CMDBUF_SIZE)){printf("GPU init failed\n");goto wait;}
    C3D_RenderTarget *target=C3D_RenderTargetCreate(240,400,GPU_RB_RGBA8,GPU_RB_DEPTH16);
    if(!target){printf("GPU target failed\n");goto wait;}
    const u32 transfer=GX_TRANSFER_FLIP_VERT(0)|GX_TRANSFER_OUT_TILED(0)|GX_TRANSFER_RAW_COPY(0)|
        GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGBA8)|GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB8)|GX_TRANSFER_SCALING(GX_TRANSFER_SCALE_NO);
    C3D_RenderTargetSetOutput(target,GFX_TOP,GFX_LEFT,transfer);
    DVLB_s *dvlb=DVLB_ParseFile((u32*)gpu_probe_shader,sizeof(gpu_probe_shader));
    if(!dvlb){printf("GPU shader failed\n");goto wait;}
    shaderProgram_s program;shaderProgramInit(&program);shaderProgramSetVsh(&program,&dvlb->DVLE[0]);C3D_BindProgram(&program);
    int location=shaderInstanceGetUniformLocation(program.vertexShader,"projection");
    if(location<0){printf("GPU uniform failed\n");goto wait;}
    C3D_AttrInfo *attributes=C3D_GetAttrInfo();AttrInfo_Init(attributes);
    AttrInfo_AddLoader(attributes,0,GPU_FLOAT,3);AttrInfo_AddLoader(attributes,1,GPU_FLOAT,3);
    void *vbo=linearAlloc(sizeof(vertices));if(!vbo){printf("GPU VBO failed\n");goto wait;}
    memcpy(vbo,vertices,sizeof(vertices));GSPGPU_FlushDataCache(vbo,sizeof(vertices));
    C3D_BufInfo *buffers=C3D_GetBufInfo();BufInfo_Init(buffers);BufInfo_Add(buffers,vbo,sizeof(Vertex),2,0x10);
    C3D_TexEnv *env=C3D_GetTexEnv(0);C3D_TexEnvInit(env);C3D_TexEnvSrc(env,C3D_Both,GPU_PRIMARY_COLOR,0,0);C3D_TexEnvFunc(env,C3D_Both,GPU_REPLACE);
    C3D_CullFace(GPU_CULL_NONE);C3D_DepthTest(false,GPU_ALWAYS,GPU_WRITE_COLOR);
    C3D_Mtx projection;Mtx_OrthoTilt(&projection,0,400,0,240,0,1,true);
    u64 start=svcGetSystemTick();unsigned rendered=0;
    for(unsigned i=0;i<16;++i){
        if(!C3D_FrameBegin(C3D_FRAME_SYNCDRAW))break;
        C3D_RenderTargetClear(target,C3D_CLEAR_ALL,0x102030ff,0);C3D_FrameDrawOn(target);
        C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER,location,&projection);C3D_DrawArrays(GPU_TRIANGLES,0,3);C3D_FrameEnd(0);++rendered;
    }
    C3D_FrameSync();
    // Both output buffers now hold the same static draw. Wait for pending
    // commands/transfers before reading one borrowed display buffer.
    if(!C3D_FrameBegin(C3D_FRAME_SYNCDRAW)){printf("GPU final sync failed\n");goto wait;}
    u16 width,height;u8 *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&width,&height);
    u32 bytes=(u32)width*height*3;FILE *f=fopen(ROOT"gpu-probe.raw","wb");
    if(!f || fwrite(pixels,1,bytes,f)!=bytes){if(f)fclose(f);printf("GPU capture failed\n");goto wait;}
    fclose(f);u32 checksum=crc32(pixels,bytes);
    f=fopen(ROOT"gpu-probe.json","w");if(!f){printf("GPU metadata failed\n");goto wait;}
    fprintf(f,"{\"backend\":\"PICA200 through Citro3D\",\"game_called\":false,\"cpu_rasterizer_linked\":false,\"frames\":%u,\"width\":400,\"height\":240,\"layout\":1,\"bytes\":%lu,\"crc32\":\"%08lx\",\"ticks\":%llu}\n",rendered,(unsigned long)bytes,(unsigned long)checksum,(unsigned long long)(svcGetSystemTick()-start));fclose(f);
    printf("GPU PROBE PASSED\n16 PICA frames; no game called\n");
wait:
    for(;;)svcSleepThread(1000000000LL);
}
