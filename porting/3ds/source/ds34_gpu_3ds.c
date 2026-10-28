/* Optional emulator GPU backend. CPU validation/clipping/lighting remain in
 * DS22. Unsupported states stop explicitly; CPU FBO rendering is retained. */
#include <3ds.h>
#include <citro3d.h>
#include "ds13_gles.h"
#include "ds34_gpu.h"
#include "ds34_shader.h"
#include <math.h>
#include <string.h>
#include <stdio.h>
#define STREAM 8190u
#define CACHE 32u
#define BUDGET (4u*1024*1024)
typedef struct {DS15Object *object;C3D_Tex tex;void *staging;uint32_t used,bytes,stamp,wrap_s,wrap_t;} Entry;
static struct {
    DS13Context *ctx;C3D_RenderTarget *target;DVLB_s *dvlb;shaderProgram_s program;
    C3D_Mtx projection;int projection_loc,scale_loc,frame;
    DS34Vertex *stream;uint32_t used,start,draws,triangles,uploads,bytes,stamp,staging_bytes;
    Entry entries[CACHE];DS15Object *protected[2];
} g;
static int fail(const char *name,uint32_t value){ds13_unsupported(name,value);return -1;}
int ds34_active(DS13Context *c){return g.ctx==c;}
static void release_staging(void){
    for(unsigned i=0;i<CACHE;++i)if(g.entries[i].staging){linearFree(g.entries[i].staging);g.entries[i].staging=NULL;}
    g.staging_bytes=0;
}
/* Split only queues commands. End + blocking Begin actually retires GPU reads.
 * Detach output so an internal barrier does not present a partial game frame. */
static int sync_gpu(void){
    if(g.frame){
        u32 flags=g.target->transferFlags;
        C3D_RenderTargetDetachOutput(g.target);C3D_FrameEnd(0);g.frame=0;
        if(!C3D_FrameBegin(0))return fail("GPU queue drain unavailable",0);
        g.frame=1;release_staging();g.used=g.start=0;
        C3D_RenderTargetSetOutput(g.target,GFX_TOP,GFX_LEFT,flags);C3D_FrameDrawOn(g.target);
    }
    return 0;
}
static int frame(void){
    if(!g.frame){if(!C3D_FrameBegin(C3D_FRAME_SYNCDRAW))return fail("GPU frame unavailable",0);g.frame=1;release_staging();g.used=g.start=0;}
    C3D_FrameDrawOn(g.target);return 0;
}
static uint32_t byte(float v){return (uint32_t)lrintf(fmaxf(0,fminf(1,v))*255);}
static GPU_TESTFUNC test(uint32_t f,int reverse){
    static const GPU_TESTFUNC normal[]={GPU_NEVER,GPU_LESS,GPU_EQUAL,GPU_LEQUAL,GPU_GREATER,GPU_NOTEQUAL,GPU_GEQUAL,GPU_ALWAYS};
    static const GPU_TESTFUNC inverted[]={GPU_NEVER,GPU_GREATER,GPU_EQUAL,GPU_GEQUAL,GPU_LESS,GPU_NOTEQUAL,GPU_LEQUAL,GPU_ALWAYS};
    return (reverse?inverted:normal)[f-0x200];
}
static GPU_BLENDFACTOR blend(uint32_t f,int alpha){
    switch(f){case 0:return GPU_ZERO;case 1:return GPU_ONE;
        case 0x300:return alpha?GPU_SRC_ALPHA:GPU_SRC_COLOR;case 0x301:return alpha?GPU_ONE_MINUS_SRC_ALPHA:GPU_ONE_MINUS_SRC_COLOR;
        case 0x302:return GPU_SRC_ALPHA;case 0x303:return GPU_ONE_MINUS_SRC_ALPHA;case 0x304:return GPU_DST_ALPHA;case 0x305:return GPU_ONE_MINUS_DST_ALPHA;
        case 0x306:return alpha?GPU_DST_ALPHA:GPU_DST_COLOR;case 0x307:return alpha?GPU_ONE_MINUS_DST_ALPHA:GPU_ONE_MINUS_DST_COLOR;
        default:return alpha?GPU_ONE:GPU_SRC_ALPHA_SATURATE;}
}
static unsigned pot(unsigned n){unsigned v=8;while(v<n)v*=2;return v;}
static void drop(Entry *e){if(e->used){if(sync_gpu())return;C3D_TexDelete(&e->tex);g.bytes-=e->bytes;memset(e,0,sizeof(*e));}}
void ds34_texture_dirty(DS15State *s,DS15Object *o){
    if(!g.ctx || s!=&g.ctx->texture)return;
    for(unsigned i=0;i<CACHE;++i)if(g.entries[i].used && g.entries[i].object==o)drop(&g.entries[i]);
}
static Entry *texture(DS15Object *o){
    DS15Level *l=o?&o->levels[0]:NULL;int defined=l && l->defined;
    unsigned w=defined?l->width:1,h=defined?l->height:1,pw=pot(w),ph=pot(h);
    uint32_t ws=o?o->wrap_s:0x812f,wt=o?o->wrap_t:0x812f;
    if((pw!=w && ws==0x2901 && (w&(w-1))) || (ph!=h && wt==0x2901 && (h&(h-1)))){fail("GPU NPOT repeat unsupported",w);return NULL;}
    for(unsigned i=0;i<CACHE;++i){Entry *e=&g.entries[i];if(e->used && e->object==o){
        if((pw!=w || ph!=h) && (e->wrap_s!=ws || e->wrap_t!=wt)){drop(e);break;}
        e->stamp=++g.stamp;return e;}}
    unsigned bytes=pw*ph*4;if(bytes>BUDGET){fail("GPU texture budget",bytes);return NULL;}
    Entry *entry=NULL;
    for(;;){
        for(unsigned i=0;i<CACHE;++i)if(!g.entries[i].used){entry=&g.entries[i];break;}
        if(entry && g.bytes+bytes<=BUDGET)break;
        Entry *victim=NULL;for(unsigned i=0;i<CACHE;++i){Entry *e=&g.entries[i];if(e->used && e->object!=g.protected[0] && e->object!=g.protected[1] && (!victim || e->stamp<victim->stamp))victim=e;}
        if(!victim){fail("GPU pinned texture budget",bytes);return NULL;}drop(victim);
    }
    if(g.staging_bytes+bytes>BUDGET && sync_gpu())return NULL;
    uint8_t *staging=linearAlloc(bytes);
    if(!staging){if(sync_gpu())return NULL;staging=linearAlloc(bytes);}
    if(!staging){fail("GPU staging allocation",bytes);return NULL;}
    if(!C3D_TexInitVRAM(&entry->tex,pw,ph,GPU_RGBA8)){linearFree(staging);fail("GPU VRAM allocation",bytes);return NULL;}
    // One immutable Morton image per upload, retained until blocking FrameBegin.
        for(unsigned j=0;j<bytes/4;++j){unsigned index=j,tile=index/64,m=index&63;
            unsigned x=(tile%(pw/8))*8+((m&1)|((m>>1)&2)|((m>>2)&4));
            unsigned y=(tile/(pw/8))*8+(((m>>1)&1)|((m>>2)&2)|((m>>3)&4));y=ph-1-y;
            unsigned sx=ws==0x2901?x%w:x>=w?w-1:x,sy=wt==0x2901?y%h:y>=h?h-1:y;
            const uint8_t black[4]={0,0,0,255};const uint8_t *p=defined?l->rgba+(sy*w+sx)*4:black;
            staging[j*4]=p[3];staging[j*4+1]=p[2];staging[j*4+2]=p[1];staging[j*4+3]=p[0];
        }
    GSPGPU_FlushDataCache(staging,bytes);C3D_SyncTextureCopy((u32*)staging,0,(u32*)entry->tex.data,0,bytes,8);
    entry->staging=staging;g.staging_bytes+=bytes;
#ifdef DS34_TRACE
    {unsigned nz=0;for(unsigned i=0;defined && i<w*h*4;++i)nz+=l->rgba[i]!=0;FILE *f=fopen("sdmc:/3ds/deadspace/gpu-texture-trace.txt","a");if(f){fprintf(f,"upload=%lu logical=%u,%u physical=%u,%u format=%lx nz=%u enabled=%lu,%lu\n",(unsigned long)g.uploads,w,h,pw,ph,(unsigned long)(defined?l->format:0),nz,(unsigned long)g.ctx->texture.enabled[0],(unsigned long)g.ctx->texture.enabled[1]);fclose(f);}}
#endif
    entry->object=o;entry->used=1;entry->bytes=bytes;entry->stamp=++g.stamp;entry->wrap_s=ws;entry->wrap_t=wt;g.bytes+=bytes;++g.uploads;return entry;
}
int ds34_attach(DS13Context *c){
    if(g.ctx || !c || c->width!=400 || c->height!=240 || c->layout!=DS13_RGB565_CTR)return -1;
    if(!C3D_Init(C3D_DEFAULT_CMDBUF_SIZE))return -1;
    g.target=C3D_RenderTargetCreate(240,400,GPU_RB_RGB8,GPU_RB_DEPTH24_STENCIL8);
    g.stream=linearAlloc(STREAM*sizeof(DS34Vertex));
    g.dvlb=DVLB_ParseFile((u32*)ds34_shader,sizeof(ds34_shader));
    if(!g.target || !g.stream || !g.dvlb)return -1;
    shaderProgramInit(&g.program);shaderProgramSetVsh(&g.program,&g.dvlb->DVLE[0]);C3D_BindProgram(&g.program);
    g.projection_loc=shaderInstanceGetUniformLocation(g.program.vertexShader,"projection");g.scale_loc=shaderInstanceGetUniformLocation(g.program.vertexShader,"texture_scale");
    if(g.projection_loc<0 || g.scale_loc<0)return -1;
    Mtx_OrthoTilt(&g.projection,0,400,0,240,0,1,true);
    C3D_AttrInfo *a=C3D_GetAttrInfo();AttrInfo_Init(a);for(unsigned i=0;i<4;++i)AttrInfo_AddLoader(a,i,GPU_FLOAT,4);
    u32 flags=GX_TRANSFER_FLIP_VERT(0)|GX_TRANSFER_OUT_TILED(0)|GX_TRANSFER_RAW_COPY(0)|GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGB8)|GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB565)|GX_TRANSFER_SCALING(GX_TRANSFER_SCALE_NO);
    C3D_RenderTargetSetOutput(g.target,GFX_TOP,GFX_LEFT,flags);C3D_CullFace(GPU_CULL_NONE);g.ctx=c;return 0;
}
int ds34_begin_draw(DS13Context *c){
    if(!ds34_active(c) || c->framebuffer_binding)return 0;
    if(c->fog || c->pipeline.stencil || c->pipeline.offset_fill)return fail("GPU fog/stencil/offset not implemented",c->fog?0xb60:c->pipeline.stencil?0xb90:0x8037);
    if(frame())return -1;
    C3D_BindProgram(&g.program);C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER,g.projection_loc,&g.projection);
    g.protected[0]=c->texture.enabled[0]?c->draw->sampler[0]:NULL;g.protected[1]=c->texture.enabled[1]?c->draw->sampler[1]:NULL;
    float scale[4]={1,1,1,1};
    for(unsigned i=0;i<6;++i)C3D_TexEnvInit(C3D_GetTexEnv(i));
    C3D_TexEnvSrc(C3D_GetTexEnv(0),C3D_Both,GPU_PRIMARY_COLOR,0,0);
    for(unsigned u=0;u<2;++u){
        if(!c->texture.enabled[u]){C3D_TexBind(u,NULL);continue;}
        DS15Object *o=c->draw->sampler[u];Entry *e=texture(o);if(!e)return -1;
        C3D_TexSetFilter(&e->tex,o && o->mag_filter==0x2601?GPU_LINEAR:GPU_NEAREST,o && o->min_filter==0x2601?GPU_LINEAR:GPU_NEAREST);
        C3D_TexSetWrap(&e->tex,o && o->wrap_s==0x2901?GPU_REPEAT:GPU_CLAMP_TO_EDGE,o && o->wrap_t==0x2901?GPU_REPEAT:GPU_CLAMP_TO_EDGE);C3D_TexBind(u,&e->tex);
        if(o && o->levels[0].defined){scale[u*2]=(float)o->levels[0].width/e->tex.width;scale[u*2+1]=(float)o->levels[0].height/e->tex.height;}
        uint32_t mode=c->draw->env_mode[u],format=o?o->levels[0].format:0x1908;
        C3D_TexEnv *env=C3D_GetTexEnv(u);GPU_TEVSRC previous=u?GPU_PREVIOUS:GPU_PRIMARY_COLOR,tex=u?GPU_TEXTURE1:GPU_TEXTURE0;
        if(mode!=0x2100 && mode!=0x1e01 && mode!=0x104)return fail("GPU texture environment not implemented",mode);
        C3D_TexEnvSrc(env,C3D_Both,mode==0x1e01?tex:previous,tex,0);
        C3D_TexEnvFunc(env,C3D_RGB,mode==0x1e01?GPU_REPLACE:mode==0x104?GPU_ADD:GPU_MODULATE);
        C3D_TexEnvFunc(env,C3D_Alpha,mode==0x1e01?GPU_REPLACE:GPU_MODULATE);
        if(format==0x1906){C3D_TexEnvSrc(env,C3D_RGB,previous,0,0);C3D_TexEnvFunc(env,C3D_RGB,GPU_REPLACE);}
        if(format==0x1907 || format==0x1909){C3D_TexEnvSrc(env,C3D_Alpha,previous,0,0);C3D_TexEnvFunc(env,C3D_Alpha,GPU_REPLACE);}
    }
    C3D_FVUnifSet(GPU_VERTEX_SHADER,g.scale_loc,scale[0],scale[1],scale[2],scale[3]);
    unsigned mask=0;for(unsigned i=0;i<3;++i)if(c->color_mask[i])mask|=1u<<i;if(c->pipeline.depth_mask && c->pipeline.depth)mask|=GPU_WRITE_DEPTH;
    C3D_DepthTest(c->pipeline.depth,test(c->pipeline.depth_func,1),(GPU_WRITEMASK)mask);
    C3D_StencilTest(false,GPU_ALWAYS,0,255,255);C3D_AlphaTest(c->pipeline.alpha,test(c->pipeline.alpha_func,0),byte(c->pipeline.alpha_ref));
    C3D_AlphaBlend(GPU_BLEND_ADD,GPU_BLEND_ADD,c->blend?blend(c->pipeline.blend_src,0):GPU_ONE,c->blend?blend(c->pipeline.blend_dst,0):GPU_ZERO,
        c->blend?blend(c->pipeline.blend_src,1):GPU_ONE,c->blend?blend(c->pipeline.blend_dst,1):GPU_ZERO);
    if(c->scissor_test){int x=c->scissor[1],y=400-c->scissor[0]-c->scissor[2],w=c->scissor[3],h=c->scissor[2];
        int x1=x+w,y1=y+h;if(x<0)x=0;if(y<0)y=0;if(x1>240)x1=240;if(y1>400)y1=400;if(x1<x)x1=x;if(y1<y)y1=y;
        C3D_SetScissor(GPU_SCISSOR_NORMAL,x,y,x1,y1);
    }else C3D_SetScissor(GPU_SCISSOR_DISABLE,0,0,0,0);
    g.start=g.used;return 1;
}
void ds34_end_draw(DS13Context *c){
    if(!ds34_active(c) || c->framebuffer_binding || g.used==g.start)return;
#ifdef DS34_TRACE
    if(g.draws<8 || g.draws%120==0){FILE *f=fopen("sdmc:/3ds/deadspace/gpu-draw-trace.txt","a");if(f){
        DS34Vertex *v=g.stream+g.start;fprintf(f,"draw=%lu blend=%lu factors=%lx,%lx depth=%lu/%lx alpha=%lu/%lx/%g mask=%u%u%u env=%lx,%lx tex=%lu,%lu vertex=%g,%g,%g,%g color=%g,%g,%g,%g uv=%g,%g\n",(unsigned long)g.draws,(unsigned long)c->blend,(unsigned long)c->pipeline.blend_src,(unsigned long)c->pipeline.blend_dst,(unsigned long)c->pipeline.depth,(unsigned long)c->pipeline.depth_func,(unsigned long)c->pipeline.alpha,(unsigned long)c->pipeline.alpha_func,(double)c->pipeline.alpha_ref,c->color_mask[0],c->color_mask[1],c->color_mask[2],(unsigned long)c->draw->env_mode[0],(unsigned long)c->draw->env_mode[1],(unsigned long)c->texture.binding[0],(unsigned long)c->texture.binding[1],(double)v->p[0],(double)v->p[1],(double)v->p[2],(double)v->p[3],(double)v->color[0],(double)v->color[1],(double)v->color[2],(double)v->color[3],(double)v->tex[0][0],(double)v->tex[0][1]);fclose(f);}}
#endif
    void *p=g.stream+g.start;unsigned n=g.used-g.start;GSPGPU_FlushDataCache(p,n*sizeof(DS34Vertex));
    C3D_BufInfo *b=C3D_GetBufInfo();BufInfo_Init(b);
    /* Attribute offsets are only 28 bits. The default VRAM base (0x18000000)
     * overflows once New3DS linear allocations reach physical 0x28000000. */
    b->base_paddr=osConvertVirtToPhys(g.stream);
    if(BufInfo_Add(b,p,sizeof(DS34Vertex),4,0x3210)<0){fail("GPU vertex buffer address",b->base_paddr);return;}
    C3D_DrawArrays(GPU_TRIANGLES,0,n);++g.draws;g.start=g.used;
}
int ds34_triangle(DS13Context *c,const DS34Vertex v[3]){
    for(unsigned u=0;u<2;++u)if(c->texture.enabled[u])for(unsigned i=0;i<3;++i)if(v[i].tex[u][3]!=1)return fail("GPU projective coordinates unsupported",u);
    if(g.used+3>STREAM){ds34_end_draw(c);if(sync_gpu())return -1;}
    memcpy(g.stream+g.used,v,3*sizeof(*v));g.used+=3;++g.triangles;return 1;
}
int ds34_clear(DS13Context *c,uint32_t mask){
    if(!ds34_active(c) || c->framebuffer_binding)return 0;
    if(c->scissor_test || !c->color_mask[0] || !c->color_mask[1] || !c->color_mask[2] || ((mask&0x100) && !c->pipeline.depth_mask) || c->clear_stencil || c->pipeline.stencil_write_mask!=UINT32_MAX){fail("GPU masked clear unsupported",mask);return 1;}
    if(frame())return 1;
    C3D_ClearBits bits=0;if(mask&0x4000)bits|=C3D_CLEAR_COLOR;if(mask&(0x100|0x400))bits|=C3D_CLEAR_DEPTH;
    uint32_t color=byte(c->clear_color[0])<<16|byte(c->clear_color[1])<<8|byte(c->clear_color[2]);
    /* MemoryFill is queued immediately; submit earlier PICA draws first. */
    if(bits){C3D_FrameSplit(0);C3D_RenderTargetClear(g.target,bits,color,(uint32_t)lrintf((1-c->clear_depth)*16777215));}return 1;
}
int ds34_integer(DS13Context *c,uint32_t name,int32_t *out){if(!ds34_active(c) || c->framebuffer_binding)return 0;if(name==0xd56){*out=24;return 1;}if(name==0xd57){*out=8;return 1;}return 0;}
int ds34_present(DS13Context *c){
    if(!ds34_active(c) || frame())return -1;
    u16 w,h;void *pixels=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&w,&h);
    C3D_FrameEnd(0);g.frame=0;C3D_FrameSync();
    if(frame())return -1;
    c->pixels=pixels;c->capacity=(uint32_t)w*h*2;return 0;
}
void ds34_stats(uint32_t out[4]){out[0]=g.draws;out[1]=g.triangles;out[2]=g.uploads;out[3]=g.bytes;}
