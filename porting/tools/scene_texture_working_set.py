"""Bounded render-thread GPU cache events, emitted after original callbacks."""
from build_native_loading import replace


def instrument(gpu):
    gpu=replace(gpu, 'static void drop(Entry *e){', '''void scene_texture_event(unsigned,DS15Object *,unsigned,unsigned,unsigned,unsigned);
static unsigned scene_texture_reason;
static void drop(Entry *e){''')
    gpu=replace(gpu, 'C3D_TexDelete(&e->tex);g.bytes-=e->bytes;',
        'scene_texture_event(3,e->object,e->bytes,g.bytes,scene_texture_reason,e->tex.fmt);C3D_TexDelete(&e->tex);g.bytes-=e->bytes;')
    gpu=replace(gpu, 'for(unsigned i=0;i<CACHE;++i)if(g.entries[i].used && g.entries[i].object==o)drop(&g.entries[i]);',
        'scene_texture_reason=1;for(unsigned i=0;i<CACHE;++i)if(g.entries[i].used && g.entries[i].object==o)drop(&g.entries[i]);scene_texture_reason=0;')
    gpu=replace(gpu, 'e->stamp=++g.stamp;return e;',
        'scene_texture_event(1,o,e->bytes,g.bytes,0,e->tex.fmt);e->stamp=++g.stamp;return e;')
    gpu=replace(gpu, 'if(defined && ds15_resident(&g.ctx->texture,o,0))return NULL;',
        'scene_texture_event(2,o,pw*ph*4,g.bytes,0,0);if(defined && ds15_resident(&g.ctx->texture,o,0))return NULL;')
    gpu=replace(gpu, 'g.bytes+=bytes;++g.uploads;return entry;',
        'g.bytes+=bytes;++g.uploads;scene_texture_event(4,o,bytes,g.bytes,0,entry->tex.fmt);return entry;')
    gpu=replace(gpu, 'void *p=g.stream+g.start;unsigned n=g.used-g.start;',
        'for(unsigned u=0;u<2;++u)if(g.ctx->texture.enabled[u])scene_texture_event(5,g.ctx->draw->sampler[u],(g.used-g.start)/3,g.bytes,u,0);\n    void *p=g.stream+g.start;unsigned n=g.used-g.start;')
    gpu=replace(gpu,'uint32_t mode=c->draw->env_mode[u],format=o?o->levels[0].format:0x1908;',
        'uint32_t mode=c->draw->env_mode[u],format=o?o->levels[0].format:0x1908;\n        scene_texture_event(6,o,mode,g.bytes,u,format);')
    return gpu


def visible_textures(gpu):
    gpu=replace(gpu, 'int ds34_begin_draw(DS13Context *c){',
        'static int scene_draw_pending;\nint ds_scene_defer_resident(void) __attribute__((weak));\nstatic int scene_materialize_draw(DS13Context *c){')
    public='''/* The CPU has already validated vertex ranges and sampler state.
 * Only materialize GPU resources once clipping/culling produces a triangle.
 * State is immutable during this synchronous DS22 draw. Retirement remains
 * exclusively in the original blocking sync_gpu/drop paths. */
int ds34_begin_draw(DS13Context *c){
    scene_draw_pending=0;
    if(!ds34_active(c) || c->framebuffer_binding)return 0;
    if(c->pipeline.stencil || c->pipeline.offset_fill)return fail("GPU fog/stencil/offset not implemented",c->fog?0xb60:c->pipeline.stencil?0xb90:0x8037);
    for(unsigned u=0;u<2;++u)if(c->texture.enabled[u]){
        uint32_t mode=c->draw->env_mode[u];
        if(mode!=0x8570 && mode!=0x2100 && mode!=0x1e01 && mode!=0x104)return fail("GPU texture environment not implemented",mode);
    }
    if(ds_scene_defer_resident && ds_scene_defer_resident()){scene_draw_pending=1;return 1;}
    return scene_materialize_draw(c);
}
'''
    gpu=replace(gpu, 'void ds34_end_draw(DS13Context *c){', public+'\nvoid ds34_end_draw(DS13Context *c){\n    if(scene_draw_pending){scene_draw_pending=0;return;}')
    gpu=replace(gpu, 'if(g.used+3>STREAM)',
        'if(scene_draw_pending){scene_draw_pending=0;if(scene_materialize_draw(c)<0)return -1;}\n    if(g.used+3>STREAM)')
    return gpu


def projective_texture0(gpu):
    gpu=replace(gpu,'C3D_Tex inactive,fog_ramp;','C3D_Tex inactive,fog_ramp,bound[2];')
    gpu=replace(gpu, 'C3D_TexBind(u,&e->tex);',
        '''g.bound[u]=e->tex;
        if(u==0)g.bound[u].param=(g.bound[u].param & ~GPU_TEXTURE_MODE(7)) | GPU_TEXTURE_MODE(GPU_TEX_PROJECTION);
        C3D_TexBind(u,&g.bound[u]);''')
    gpu=replace(gpu, 'for(unsigned u=0;u<2;++u)if(c->texture.enabled[u])for(unsigned i=0;i<3;++i)if(v[i].tex[u][3]!=1)return fail("GPU projective coordinates unsupported",u);',
        '''void scene_projective_trace(unsigned,const DS34Vertex *) __attribute__((weak));
    DS34Vertex fixed[3];const DS34Vertex *vertices=v;
    for(unsigned u=0;u<2;++u)if(c->texture.enabled[u])for(unsigned i=0;i<3;++i){
        float q=v[i].tex[u][3];
        if(!isfinite(q) || q<=0 || (u && q!=v[0].tex[u][3])){
            if(scene_projective_trace)scene_projective_trace(u,v);
            return fail("GPU projective coordinates unsupported",u);
        }
    }
    /* A constant q commutes with perspective interpolation exactly. Unit 1
     * has no hardware projective sampler; varying q remains fail-closed. */
    if(c->texture.enabled[1] && v[0].tex[1][3]!=1){
        memcpy(fixed,v,sizeof(fixed));vertices=fixed;
        for(unsigned i=0;i<3;++i){float q=fixed[i].tex[1][3];fixed[i].tex[1][0]/=q;fixed[i].tex[1][1]/=q;fixed[i].tex[1][3]=1;}
    }''')
    gpu=replace(gpu,'memcpy(g.stream+g.used,v,3*sizeof(*v));','memcpy(g.stream+g.used,vertices,3*sizeof(*v));')
    return gpu
