/* Bounded CPU triangles, with opt-in FBO, fog and texture combiners.
 * Optional per-vertex lighting; unsupported mipmap sampling stops explicitly. */
#include "ds13_gles.h"
#include "ds_runtime.h"
#include "ds34_gpu.h"
int ds_scene_defer_resident(void) __attribute__((weak));
#include <math.h>
#include <string.h>
#include "p2_profile.h"
#if DS_OPT_COPY
#define memcpy(d,s,n) __builtin_memcpy(d,s,n)
#endif
static inline void p8_track(DS13Context *c,const float color[4]){
#if DS_P8_TRACK
    if(!c->lighting_state || !c->pipeline.color_material)return;
#endif
    ds32_track(c,color);
}
typedef struct {float p[4],color[4],back_color[4],tex[2][4],fog_factor;} Vertex;
/* Direct-mapped, per-draw scratch. Array storage and GL state are immutable
 * during a serialized draw; no cache survives a subsequent API call. */
typedef struct {uint32_t index;Vertex vertex;float primary[4];} VertexCache;
#define VERTEX_CACHE 64
#define P5_CACHE 8192u
static VertexCache p5_cache[P5_CACHE];static unsigned p5_cache_busy;
static float p8_screen[P5_CACHE][3]; /* CPU-only, default target, privately owned draw. */
static uint16_t p6_touched[P5_CACHE];static unsigned p6_touch_count,p6_initialized;
static void p6_cache_begin(void){if(!p6_initialized){for(unsigned i=0;i<P5_CACHE;++i)p5_cache[i].index=UINT32_MAX;p6_initialized=1;}}
static void p6_cache_end(void){for(unsigned i=0;i<p6_touch_count;++i)p5_cache[p6_touched[i]].index=UINT32_MAX;p6_touch_count=0;p5_cache_busy=0;}

void ds22_vertex_trace(DS13Context *,uint32_t,const float *,const float *,const float *,float) __attribute__((weak));
void ds22_pixel_trace(DS13Context *,unsigned,unsigned,const float *,const float *,const float *) __attribute__((weak));
static float clamp(float x){return x<0?0:x>1?1:x;}
static DS22State *state(DS13Context *c){
    if(!c->draw){DS22State *s=ds_rt_calloc(1,sizeof(*s));if(!s){ds13_error(0x505);return NULL;}for(unsigned i=0;i<4;++i)s->color[i]=1;s->env_mode[0]=s->env_mode[1]=0x2100;c->draw=s;}return c->draw;
}
int ds22_prepare(DS13Context *c){return state(c)?0:-1;}
void ds22_close(DS13Context *c){ds31_close(c);ds_rt_free(c->draw);c->draw=NULL;}
void ds22_stats(DS13Context *c,uint32_t out[4]){memset(out,0,16);if(c->draw){out[0]=c->draw->calls;out[1]=c->draw->triangles;out[2]=c->draw->fragments;out[3]=c->draw->samples;}}
void ds22_observer(DS13Context *c,DS22Observe fn){DS22State *s=state(c);if(s)s->observe=fn;}
int ds22_client_range(DS13Context *c,const void *p,uint32_t n){return ds14_client_range(&c->vertex,p,n);}
int ds22_real(DS13Context *c,uint32_t name,float out[16]){if(name!=0xb00)return 0;for(unsigned i=0;i<4;++i)out[i]=c->draw?c->draw->color[i]:1;return 4;}
static void DS13_SOFT color(float r,float g,float b,float a){
    DS13Context *c=ds13_active_context();if(!c)return;if(isnan(r)||isnan(g)||isnan(b)||isnan(a)){ds13_error(0x501);return;}
    if(c->lighting_state && (!isfinite(r)||!isfinite(g)||!isfinite(b)||!isfinite(a))){ds13_error(0x501);return;}
    DS22State *s=state(c);if(s){float color[4]={r,g,b,a};for(unsigned i=0;i<4;++i)s->color[i]=c->lighting_state?color[i]:clamp(color[i]);ds32_track(c,s->color);}
}
static void DS13_SOFT color_x(int32_t r,int32_t g,int32_t b,int32_t a){color(r/65536.0f,g/65536.0f,b/65536.0f,a/65536.0f);}
static void DS13_SOFT color_b(uint8_t r,uint8_t g,uint8_t b,uint8_t a){color(r/255.0f,g/255.0f,b/255.0f,a/255.0f);}
static void env(uint32_t target,uint32_t name,const float *v){
    DS13Context *c=ds13_active_context();if(!c)return;if(target!=0x2300 || !v){ds13_error(v?0x500:0x501);return;}
    DS22State *s=state(c);if(!s)return;unsigned u=c->active_texture-0x84c0;
    if(ds31_set(c,name,v[0]))return;
    if(name==0x2201){for(unsigned i=0;i<4;++i)if(isnan(v[i])){ds13_error(0x501);return;}for(unsigned i=0;i<4;++i)s->env_color[u][i]=clamp(v[i]);return;}
    if(name!=0x2200){ds13_unsupported("texture combiner state unsupported",name);return;}
    if(!isfinite(v[0]) || v[0]<0 || v[0]>65535){ds13_error(0x500);return;}
    uint32_t mode=(uint32_t)v[0];if(v[0]!=(float)mode || (mode!=0x2100 && mode!=0x1e01 && mode!=0x2101 && mode!=0xbe2 && mode!=0x104)){
        ds13_unsupported("texture environment mode unsupported",mode);return;
    }s->env_mode[u]=mode;
}
static void DS13_SOFT env_f(uint32_t t,uint32_t n,float v){if(n==0x2201){ds13_error(0x500);return;}env(t,n,&v);}
static void DS13_SOFT env_i(uint32_t t,uint32_t n,int32_t v){env_f(t,n,(float)v);}
static void DS13_SOFT env_x(uint32_t t,uint32_t n,int32_t v){env_f(t,n,ds31_scale(n)?v/65536.0f:(float)v);}
static void DS13_SOFT env_fv(uint32_t t,uint32_t n,const float *v){env(t,n,v);}
static void env_vector(uint32_t t,uint32_t n,const int32_t *v,int fixed){if(!v){ds13_error(0x501);return;}float f[4];unsigned count=n==0x2201?4:1;for(unsigned i=0;i<count;++i)f[i]=n==0x2201?(fixed?v[i]/65536.0f:(float)((double)v[i]/2147483647.0)):(fixed&&ds31_scale(n)?v[i]/65536.0f:(float)v[i]);env(t,n,f);}
static void DS13_SOFT env_xv(uint32_t t,uint32_t n,const int32_t *v){env_vector(t,n,v,1);}
static void DS13_SOFT env_iv(uint32_t t,uint32_t n,const int32_t *v){env_vector(t,n,v,0);}
static void get_env(uint32_t t,uint32_t n,void *out,unsigned kind){
    DS13Context *c=ds13_active_context();if(!c)return;if(!out){ds13_error(0x501);return;}
    if(t!=0x2300){ds13_error(0x500);return;}
    if(n!=0x2200 && n!=0x2201){float value;int is_enum;
        if(!ds31_get(c,n,&value,&is_enum)){ds13_error(0x500);return;}
        if(!kind)((float *)out)[0]=value;else ((int32_t *)out)[0]=(int32_t)(kind==1&&!is_enum?value*65536:value);return;
    }
    unsigned u=c->active_texture-0x84c0,count=n==0x2201?4:1;
    for(unsigned i=0;i<count;++i){float v=n==0x2200?(float)(c->draw?c->draw->env_mode[u]:0x2100):(c->draw?c->draw->env_color[u][i]:0);
        if(!kind)((float *)out)[i]=v;else if(kind==1)((int32_t *)out)[i]=n==0x2200?(int32_t)v:(int32_t)(v*65536);else ((int32_t *)out)[i]=n==0x2200?(int32_t)v:v>=1?INT32_MAX:(int32_t)((double)v*INT32_MAX);
    }
}
static void DS13_SOFT get_env_f(uint32_t t,uint32_t n,float *v){get_env(t,n,v,0);}
static void DS13_SOFT get_env_x(uint32_t t,uint32_t n,int32_t *v){get_env(t,n,v,1);}
static void DS13_SOFT get_env_i(uint32_t t,uint32_t n,int32_t *v){get_env(t,n,v,2);}
static int readable(DS14State *s,uintptr_t p,uint32_t n){
    if((uint64_t)p+n>UINT32_MAX+1ull)return 0;
    for(unsigned i=0;i<DS14_RANGES;++i){DS14Range *r=&s->ranges[i];if(r->base && p>=r->base && p-r->base<=r->size && n<=r->size-(p-r->base))return 1;}return 0;
}
static int index_at(DS13Context *c,const void *indices,uint32_t type,uint32_t i,uint32_t *out){
    uint32_t bytes=type==0x1401?1:type==0x1403?2:0;if(!bytes)return -1;
    uint64_t offset=(uint64_t)(uintptr_t)indices+(uint64_t)i*bytes;const uint8_t *p=NULL;
    if(c->vertex.element_buffer){for(unsigned b=0;b<DS14_BUFFERS;++b){DS14Buffer *v=&c->vertex.buffers[b];if(v->used && v->name==c->vertex.element_buffer && offset<=v->size && bytes<=v->size-offset){p=v->data+(uint32_t)offset;break;}}}
    else if(offset<=UINT32_MAX && readable(&c->vertex,(uintptr_t)offset,bytes))p=(const uint8_t *)(uintptr_t)offset;
    if(!p)return -1;
    *out=p[0]|(bytes==2?(uint32_t)p[1]<<8:0);return 0;
}
/* Per-draw optional proof for the complete index span. Never retain pointers
 * across draws. Failure to prove the whole span uses the original per-index
 * checks, including fragmented registered ranges and malformed buffers. */
static __attribute__((noinline)) const uint8_t *p4_index_span(DS13Context *c,const void *indices,uint32_t type,uint32_t count){
    uint32_t bytes=type==0x1401?1:type==0x1403?2:0;
    if(!bytes || !count || count>65535)return NULL;
    uint64_t offset=(uint64_t)(uintptr_t)indices,n=(uint64_t)count*bytes;
    if(c->vertex.element_buffer){
        for(unsigned b=0;b<DS14_BUFFERS;++b){DS14Buffer *v=&c->vertex.buffers[b];
            if(v->used && v->name==c->vertex.element_buffer){
                if(offset<=v->size && n<=v->size-offset)return v->data+(uint32_t)offset;
                /* Duplicate/malformed names may resolve differently per index.
                 * Stop at the first match; preserve all old checks via fallback. */
                return NULL;
            }
        }
    }else if(offset<=UINT32_MAX && readable(&c->vertex,(uintptr_t)offset,(uint32_t)n))return (const uint8_t *)(uintptr_t)offset;
    return NULL;
}
static inline int p4_index_at(DS13Context *c,const void *indices,uint32_t type,uint32_t i,const uint8_t *span,uint32_t *out){
    if(!span)return index_at(c,indices,type,i,out);
    if(type==0x1401)*out=span[i];
    else{const uint8_t *p=span+(size_t)i*2;*out=p[0]|(uint32_t)p[1]<<8;}
    return 0;
}

/* Per-draw descriptor scratch. Rebuilt before every pre-validation pass.
 * Referenced storage and GL array state are already immutable for serialized
 * DS22 draws (the same invariant used by VertexCache). Bounds still checked
 * on every read; fragmented/outside views retain the original resolver. */
typedef struct {const uint8_t *base;uint32_t available,stride,size;} HQArrayView;
static HQArrayView hq_views[DS14_ARRAYS];
static DS14State *hq_view_owner;
static __attribute__((noinline,noclone)) void hq_array_begin(DS14State *s){
    memset(hq_views,0,sizeof(hq_views));hq_view_owner=s;
    for(unsigned i=0;i<DS14_ARRAYS;++i){
        DS14Array *a=&s->arrays[i];unsigned scalar=a->type==0x1400 || a->type==0x1401?1:a->type==0x1402?2:a->type==0x1406 || a->type==0x140c?4:0;
        if(!scalar || !a->size || a->size>4)continue;
        HQArrayView *v=&hq_views[i];v->size=scalar*a->size;v->stride=a->stride?a->stride:v->size;
        if(a->buffer){
            for(unsigned j=0;j<DS14_BUFFERS;++j){DS14Buffer *b=&s->buffers[j];if(!b->used || b->name!=a->buffer)continue;
                if(a->pointer<=b->size && b->data && (uint64_t)(uintptr_t)b->data+b->size<=UINT32_MAX+1ull){v->base=b->data+a->pointer;v->available=b->size-a->pointer;}
                break;
            }
        }else for(unsigned j=0;j<DS14_RANGES;++j){DS14Range *r=&s->ranges[j];
            if(r->base && a->pointer>=r->base && a->pointer-r->base<=r->size && (uint64_t)r->base+r->size<=UINT32_MAX+1ull){v->base=(const uint8_t*)a->pointer;v->available=r->size-(a->pointer-r->base);break;}
        }
    }
}
static __attribute__((noinline,noclone)) int hq_array_read(DS14State *s,uint32_t slot,uint32_t index,void *out,uint32_t capacity){
    if(s==hq_view_owner && slot<DS14_ARRAYS && out){
        HQArrayView *v=&hq_views[slot];uint64_t off=(uint64_t)index*v->stride;
        if(v->base && v->size && capacity>=v->size && off<=v->available && v->size<=v->available-off){
            const uint8_t *p=v->base+(uint32_t)off;
            switch(v->size){case 4:__builtin_memcpy(out,p,4);break;case 8:__builtin_memcpy(out,p,8);break;case 12:__builtin_memcpy(out,p,12);break;case 16:__builtin_memcpy(out,p,16);break;default:memcpy(out,p,v->size);break;}
            return (int)v->size;
        }
    }
    return ds14_read_array(s,slot,index,out,capacity);
}

static int attribute(DS13Context *c,unsigned slot,uint32_t index,float out[4]){
#if DS_P8_INTEGER
    DS14Array *integer=&c->vertex.arrays[slot];
    if(integer->type==0x1402 || integer->type==0x140c || integer->type==0x1401){
        uint8_t raw[16];if(hq_array_read(&c->vertex,slot,index,raw,16)<0)return -1;
        /* Integer-derived results are finite by construction. Bounds and the
         * original conversion expressions remain; no float input is trusted. */
        for(unsigned i=0;i<integer->size;++i){
            if(integer->type==0x1402){int16_t x;__builtin_memcpy(&x,raw+i*2,2);out[i]=slot==1?(2.0f*x+1)/65535:x;}
            else if(integer->type==0x140c){int32_t x;__builtin_memcpy(&x,raw+i*4,4);out[i]=x/65536.0f;}
            else out[i]=raw[i]/255.0f;
        }
        return 0;
    }
#endif
#if DS_OPT_ATTRIBUTE
    /* The existing resolver still proves the complete element before copying.
     * FLOAT arrays need neither a packed temporary nor a per-component type
     * switch. Default absent components and non-finite rejection are retained. */
    DS14Array *fast=&c->vertex.arrays[slot];
    if(fast->type==0x1406){
        if(hq_array_read(&c->vertex,slot,index,out,16)<0)return -1;
        for(unsigned i=0;i<fast->size;++i)if(!isfinite(out[i]))return -1;
        return 0;
    }
#endif
    uint8_t packed[16];DS14Array *a=&c->vertex.arrays[slot];if(hq_array_read(&c->vertex,slot,index,packed,sizeof(packed))<0)return -1;
    for(unsigned i=0;i<a->size;++i){float v;switch(a->type){
        case 0x1400:v=slot==1?(2.0f*(int8_t)packed[i]+1)/255:(int8_t)packed[i];break;case 0x1401:v=packed[i]/255.0f;break;
        case 0x1402:{int16_t x;__builtin_memcpy(&x,packed+i*2,2);v=slot==1?(2.0f*x+1)/65535:x;break;}
        case 0x1406:__builtin_memcpy(&v,packed+i*4,4);break;
        case 0x140c:{int32_t x;__builtin_memcpy(&x,packed+i*4,4);v=x/65536.0f;break;}
        default:return -1;
    }if(!isfinite(v))return -1;out[i]=v;}return 0;
}
#if DS_OPT_IDENTITY
static unsigned hq_identity[4];
#if DS_P8_MATRIXVIEWS
static const float *p8_matrix_view[4];
#endif
static void hq_matrix_begin(DS13Context *c){
    for(unsigned k=0;k<4;++k){
        hq_identity[k]=1;
#if DS_P8_MATRIXVIEWS
        p8_matrix_view[k]=c->matrix?c->matrix->stack[k][c->matrix->top[k]]:NULL;
#endif
        if(c->matrix){const float *m=c->matrix->stack[k][c->matrix->top[k]];
            for(unsigned i=0;i<16;++i)if(m[i]!=(i%5==0?1.0f:0.0f)){hq_identity[k]=0;break;}}
    }
}
static void hq_transform(DS13Context *c,unsigned k,const float in[4],float out[4]){
    if(hq_identity[k] && isfinite(in[0]) && isfinite(in[1]) && isfinite(in[2]) && isfinite(in[3])){
        /* The old sum begins at +0 and includes zero products. Finite input
         * +0 preserves its result, including normalization of negative zero.
         * Read all components first to retain in/out alias semantics. */
        float x=in[0]+0.0f,y=in[1]+0.0f,z=in[2]+0.0f,w=in[3]+0.0f;
        out[0]=x;out[1]=y;out[2]=z;out[3]=w;return;
    }
#if DS_P8_MATRIXVIEWS
    const float *m=p8_matrix_view[k];
    if(m){
        float x0=in[0],x1=in[1],x2=in[2],x3=in[3],a=0,b=0,d=0,e=0;
#define P8COL(j,x) a+=m[(j)*4]*(x);b+=m[(j)*4+1]*(x);d+=m[(j)*4+2]*(x);e+=m[(j)*4+3]*(x)
        P8COL(0,x0);P8COL(1,x1);P8COL(2,x2);P8COL(3,x3);
#undef P8COL
        out[0]=a;out[1]=b;out[2]=d;out[3]=e;return;
    }
#endif
    ds21_transform(c,k==0?0x1700:k==1?0x1701:0x1702,k>1?k-2:0,in,out);
}
#else
static void hq_matrix_begin(DS13Context *c){(void)c;}
static void hq_transform(DS13Context *c,unsigned k,const float in[4],float out[4]){ds21_transform(c,k==0?0x1700:k==1?0x1701:0x1702,k>1?k-2:0,in,out);}
#endif
#if DS_P8_CONST_TEX
static float p8_default_tex[2][4];
static void p8_tex_begin(DS13Context *c){
    const float zero[4]={0,0,0,1};
    for(unsigned u=0;u<2;++u)if(!c->vertex.arrays[3+u].enabled)hq_transform(c,2+u,zero,p8_default_tex[u]);
}
#else
static void p8_tex_begin(DS13Context *c){(void)c;}
#endif
static int vertex(DS13Context *c,uint32_t index,Vertex *v,float primary[4],int trace){
    int sample=p2_sample();uint64_t start=sample?p2_clock():0,t=start;
    float p[4]={0,0,0,1},eye[4];if(attribute(c,0,index,p))return -1;
    if(sample){p2_add(3,t);t=p2_clock();}
    hq_transform(c,0,p,eye);hq_transform(c,1,eye,v->p);
    if(sample)p2_add(4,t);
    if(c->fog && !isfinite(eye[2]))return -1;
    v->fog_factor=c->fog?ds30_factor(c->fog_state,eye[2]):1;
    DS22State *s=c->draw;memcpy(v->color,s->color,16);
    t=sample?p2_clock():0;
    if(c->vertex.arrays[2].enabled && attribute(c,2,index,v->color))return -1;
    if(sample)p2_add(3,t);
    memcpy(primary,v->color,16);
    if(c->pipeline.lighting){float normal[4]={c->lighting_state->normal[0],c->lighting_state->normal[1],c->lighting_state->normal[2],0};
        if(c->vertex.arrays[1].enabled && attribute(c,1,index,normal))return -1;
        t=sample?p2_clock():0;
        if(ds32_vertex(c,eye,normal,v->color,v->color,v->back_color))return -1;
        if(sample)p2_add(5,t);
    }else{p8_track(c,v->color);memcpy(v->back_color,v->color,16);}
    for(unsigned u=0;u<2;++u){float tex[4]={0,0,0,1};t=sample?p2_clock():0;
        if(c->vertex.arrays[3+u].enabled && attribute(c,3+u,index,tex))return -1;
        if(sample){p2_add(3,t);t=p2_clock();}
#if DS_P8_CONST_TEX
        if(!c->vertex.arrays[3+u].enabled)__builtin_memcpy(v->tex[u],p8_default_tex[u],16);
        else
#endif
        hq_transform(c,2+u,tex,v->tex[u]);
        if(sample)p2_add(4,t);}
    for(unsigned i=0;i<4;++i){if(!isfinite(v->p[i]) || !isfinite(v->color[i]))return -1;v->color[i]=clamp(v->color[i]);for(unsigned u=0;u<2;++u)if(!isfinite(v->tex[u][i]))return -1;}
    if(sample){p2_add(2,start);p2_count(2);}
    if(trace && ds22_vertex_trace)ds22_vertex_trace(c,index,eye,v->p,v->color,v->fog_factor);
    return 0;
}
static int cached_vertex(DS13Context *c,VertexCache *cache,uint32_t mask,uint32_t index,Vertex *out,int trace){
    VertexCache *entry=&cache[index&mask];
    if(entry->index!=index){
        if(cache==p5_cache && entry->index==UINT32_MAX)p6_touched[p6_touch_count++]=(uint16_t)(index&mask);
        p2_count(0);if(vertex(c,index,&entry->vertex,entry->primary,trace))return -1;
        entry->index=index;
    }else{
        /* Even a reused vertex updates the tracked current material. The
         * source color, not its lit/clamped result, is the tracked value. */
        p2_count(1);p8_track(c,entry->primary);
    }
    if(out){*out=entry->vertex;}return 0;
}
static DS15Object *texture(DS13Context *c,unsigned u){uint32_t name=c->texture.binding[u];if(!name)return &c->texture.default_object;for(unsigned i=0;i<DS15_TEXTURES;++i)if(c->texture.textures[i].used && c->texture.textures[i].name==name)return c->texture.textures[i].object;return NULL;}
static unsigned coord(int x,unsigned size,uint32_t wrap){if(wrap==0x812f)return x<0?0:(unsigned)x>=size?size-1:(unsigned)x;if(!(size&(size-1)))return (unsigned)x&(size-1);int i=x%(int)size;return (unsigned)(i<0?i+(int)size:i);}
static void texel(const DS15Level *l,DS15Object *o,int x,int y,float out[4]){const uint8_t *p=l->rgba+(coord(y,l->height,o->wrap_t)*l->width+coord(x,l->width,o->wrap_s))*4;for(unsigned i=0;i<4;++i)out[i]=p[i]/255.0f;}
static void sample(DS13Context *c,unsigned u,float x,float y,float out[4]){
    DS15Object *o=c->draw->sampler[u];const DS15Level *l=o?&o->levels[0]:NULL;++c->draw->samples;
    if(!l || !l->defined || !l->width || !l->height || !isfinite(x) || !isfinite(y)){out[0]=out[1]=out[2]=0;out[3]=1;return;}
    /* Reduce large repeated coordinates before conversion to bounded integers. */
    x=o->wrap_s==0x2901?x-floorf(x):clamp(x);y=o->wrap_t==0x2901?y-floorf(y):clamp(y);
    if(o->mag_filter==0x2600){texel(l,o,(int)floorf(x*l->width),(int)floorf(y*l->height),out);return;}
    x=x*l->width-.5f;y=y*l->height-.5f;int ix=(int)floorf(x),iy=(int)floorf(y);float a=x-ix,b=y-iy,t[4][4];
    texel(l,o,ix,iy,t[0]);texel(l,o,ix+1,iy,t[1]);texel(l,o,ix,iy+1,t[2]);texel(l,o,ix+1,iy+1,t[3]);
    for(unsigned i=0;i<4;++i)out[i]=(t[0][i]*(1-a)+t[1][i]*a)*(1-b)+(t[2][i]*(1-a)+t[3][i]*a)*b;
}
static void shade(DS13Context *c,const float primary[4],const float tex[2][4],float out[4]){
    memcpy(out,primary,16);for(unsigned u=0;u<2;++u)if(c->texture.enabled[u]){float t[4];sample(c,u,tex[u][0]/tex[u][3],tex[u][1]/tex[u][3],t);uint32_t mode=c->draw->env_mode[u];
        DS15Object *o=c->draw->sampler[u];uint32_t format=o?o->levels[0].format:0x1908;
        if(mode==0x8570 && c->draw->combine){ds31_apply(&c->draw->combine->unit[u],primary,out,t,c->draw->env_color[u],out);continue;}
        for(unsigned i=0;i<4;++i){/* ALPHA preserves RGB in ES 1.1 tables 3.15/3.16. */
            if(format==0x1906 && i<3)continue;
            if(mode==0x1e01){if((i<3 && format!=0x1906) || (i==3 && format!=0x1907 && format!=0x1909))out[i]=t[i];}else if(mode==0x2101){if(i<3)out[i]=out[i]*(1-t[3])+t[i]*t[3];}
            else if(mode==0xbe2)out[i]=i==3?out[i]*t[i]:out[i]*(1-t[i])+c->draw->env_color[u][i]*t[i];
            else if(mode==0x104)out[i]=i==3?out[i]*t[i]:clamp(out[i]+t[i]);else out[i]*=t[i];}
    }
}
static uint32_t pixel_offset(DS26Surface *t,unsigned x,unsigned y){return (t->layout==DS13_RGB8_ROWS || t->layout==3?y*t->width+x:x*t->height+y)*(t->layout==3?4:t->layout==DS13_RGB565_CTR?2:3);}
static void fragment(DS13Context *c,unsigned x,unsigned y,const float src[4],float depth){
    if(c->pipeline.alpha && !ds16_alpha_pass(&c->pipeline,src[3]))return;
    DS26Surface *t=&c->draw->target;
    if(((t->depth && c->pipeline.depth) || (t->stencil && c->pipeline.stencil)) && !ds26_fragment(c,t,x,y,depth))return;
    if(!t->pixels)return;
    int trace_pixel=ds22_pixel_trace && x==t->width/2 && y==t->height/2;
    uint32_t offset=pixel_offset(t,x,y);uint8_t *p=t->pixels+offset;float dst[4]={0,0,0,1},out[4];
    if(trace_pixel || c->blend || !c->color_mask[0] || !c->color_mask[1] || !c->color_mask[2] || (t->layout==3 && !c->color_mask[3])){
        if(t->layout==DS13_RGB565_CTR){uint32_t v=p[0]|(uint32_t)p[1]<<8;dst[0]=((v>>11)&31)/31.0f;dst[1]=((v>>5)&63)/63.0f;dst[2]=(v&31)/31.0f;}
        else for(unsigned i=0;i<(t->layout==3?4u:3u);++i)dst[i]=p[t->layout==DS13_RGB8_ROWS || t->layout==3?i:2-i]/255.0f;
    }
    if(c->blend)ds16_blend(&c->pipeline,1,src,dst,out);else for(unsigned i=0;i<4;++i)out[i]=clamp(src[i]);
    if(trace_pixel)ds22_pixel_trace(c,x,y,src,dst,out);
    for(unsigned i=0;i<4;++i)if(!c->color_mask[i])out[i]=dst[i];
    if(t->layout==3)ds26_quantize(t,out);
    if(t->layout==DS13_RGB565_CTR){uint32_t v=(uint32_t)lrintf(clamp(out[0])*31)<<11|(uint32_t)lrintf(clamp(out[1])*63)<<5|(uint32_t)lrintf(clamp(out[2])*31);p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
    else for(unsigned i=0;i<(t->layout==3?4u:3u);++i)p[t->layout==DS13_RGB8_ROWS || t->layout==3?i:2-i]=(uint8_t)lrintf(clamp(out[i])*255);
    ++c->draw->fragments;++c->pixels_written;
}
static float edge(const float a[2],const float b[2],float x,float y){return (b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]);}
static int inclusive(const float a[2],const float b[2]){return b[1]>a[1] || (b[1]==a[1] && b[0]<a[0]);}
static void raster_legacy(DS13Context *c,const Vertex *a,const Vertex *b,const Vertex *d){
    Vertex v[3]={*a,*b,*d};float p[3][2],inv[3];for(unsigned i=0;i<3;++i){if(v[i].p[3]<=0)return;inv[i]=1/v[i].p[3];p[i][0]=c->viewport[0]+(v[i].p[0]*inv[i]+1)*c->viewport[2]*.5f;p[i][1]=c->viewport[1]+(v[i].p[1]*inv[i]+1)*c->viewport[3]*.5f;}
    float area=edge(p[0],p[1],p[2][0],p[2][1]);if(!isfinite(area)||area==0 || ds16_culled(&c->pipeline,area))return;
    if(c->pipeline.lighting && c->lighting_state->two_side && (c->pipeline.front_face==0x901?area<0:area>0))
        for(unsigned i=0;i<3;++i)memcpy(v[i].color,v[i].back_color,16);
    if(area<0){Vertex tmp=v[1];v[1]=v[2];v[2]=tmp;for(unsigned j=0;j<2;++j){float f=p[1][j];p[1][j]=p[2][j];p[2][j]=f;}float f=inv[1];inv[1]=inv[2];inv[2]=f;area=-area;}
    DS26Surface *target=&c->draw->target;
    float z[3];for(unsigned i=0;i<3;++i)z[i]=c->pipeline.depth_range[0]+(v[i].p[2]*inv[i]+1)*.5f*(c->pipeline.depth_range[1]-c->pipeline.depth_range[0]);
    float offset=0;if(c->pipeline.offset_fill){
        float dx=((z[1]-z[0])*(p[2][1]-p[0][1])-(z[2]-z[0])*(p[1][1]-p[0][1]))/area;
        float dy=((p[1][0]-p[0][0])*(z[2]-z[0])-(p[2][0]-p[0][0])*(z[1]-z[0]))/area;
        offset=fmaxf(fabsf(dx),fabsf(dy))*c->pipeline.offset_factor+c->pipeline.offset_units/65535.0f;
    }
    if(ds34_active && ds34_active(c) && !c->framebuffer_binding){
        DS34Vertex packed[3];for(unsigned i=0;i<3;++i){
            packed[i].p[0]=p[i][0]*v[i].p[3];packed[i].p[1]=p[i][1]*v[i].p[3];packed[i].p[2]=(z[i]+offset)*v[i].p[3];packed[i].p[3]=v[i].p[3];
            memcpy(packed[i].color,v[i].color,16);memcpy(packed[i].tex,v[i].tex,32);
            packed[i].tex[0][2]=(v[i].fog_factor*7+.5f)/8;packed[i].tex[1][2]=.5f;
        }
        if(ds34_triangle(c,packed)>0)++c->draw->triangles;
        return;
    }
    float minx=fmaxf(0,fminf((float)target->width,fminf(p[0][0],fminf(p[1][0],p[2][0])))),maxx=fmaxf(0,fminf((float)target->width,fmaxf(p[0][0],fmaxf(p[1][0],p[2][0]))));
    float miny=fmaxf(0,fminf((float)target->height,fminf(p[0][1],fminf(p[1][1],p[2][1])))),maxy=fmaxf(0,fminf((float)target->height,fmaxf(p[0][1],fmaxf(p[1][1],p[2][1]))));
    int x0=(int)ceilf(minx-.5f),x1=(int)floorf(maxx-.5f),y0=(int)ceilf(miny-.5f),y1=(int)floorf(maxy-.5f);
    for(int y=y0;y<=y1;++y)for(int x=x0;x<=x1;++x){if(c->scissor_test && (x<c->scissor[0] || y<c->scissor[1] || (int64_t)x>=(int64_t)c->scissor[0]+c->scissor[2] || (int64_t)y>=(int64_t)c->scissor[1]+c->scissor[3]))continue;
        float w[3]={edge(p[1],p[2],x+.5f,y+.5f),edge(p[2],p[0],x+.5f,y+.5f),edge(p[0],p[1],x+.5f,y+.5f)};
        if(w[0]<0||w[1]<0||w[2]<0 || (!w[0]&&!inclusive(p[1],p[2])) || (!w[1]&&!inclusive(p[2],p[0])) || (!w[2]&&!inclusive(p[0],p[1])))continue;
        float depth=offset;for(unsigned i=0;i<3;++i)depth+=z[i]*w[i]/area;
        float q=0;for(unsigned i=0;i<3;++i){w[i]=w[i]/area*inv[i];q+=w[i];}if(!q)continue;for(unsigned i=0;i<3;++i)w[i]/=q;
        float color[4]={0},tex[2][4]={{0}},shaded[4];for(unsigned i=0;i<3;++i)for(unsigned j=0;j<4;++j){color[j]+=v[i].color[j]*w[i];for(unsigned u=0;u<2;++u)tex[u][j]+=v[i].tex[u][j]*w[i];}
        if((c->texture.enabled[0]&&!tex[0][3]) || (c->texture.enabled[1]&&!tex[1][3]))continue;
        shade(c,color,tex,shaded);
        if(c->fog){float f=0;for(unsigned i=0;i<3;++i)f+=v[i].fog_factor*w[i];ds30_apply(c->fog_state,f,shaded);}
        fragment(c,(unsigned)x,(unsigned)y,shaded,depth);
    }++c->draw->triangles;
}
/* P6: immutable vertex references through the GPU packing branch. Arithmetic
 * order/clip/flat/back colors preserved; CPU target retains legacy raster. */
static void raster_gpu(DS13Context *c,const Vertex *a,const Vertex *b,const Vertex *d){
    const Vertex *v[3]={a,b,d};float p[3][2],inv[3];for(unsigned i=0;i<3;++i){if(v[i]->p[3]<=0)return;inv[i]=1/v[i]->p[3];p[i][0]=c->viewport[0]+(v[i]->p[0]*inv[i]+1)*c->viewport[2]*.5f;p[i][1]=c->viewport[1]+(v[i]->p[1]*inv[i]+1)*c->viewport[3]*.5f;}
    float area=edge(p[0],p[1],p[2][0],p[2][1]);if(!isfinite(area)||area==0 || ds16_culled(&c->pipeline,area))return;
    int back=c->pipeline.lighting && c->lighting_state->two_side && (c->pipeline.front_face==0x901?area<0:area>0);
    if(area<0){const Vertex *tmp=v[1];v[1]=v[2];v[2]=tmp;for(unsigned j=0;j<2;++j){float f=p[1][j];p[1][j]=p[2][j];p[2][j]=f;}float f=inv[1];inv[1]=inv[2];inv[2]=f;area=-area;}
    float z[3];for(unsigned i=0;i<3;++i)z[i]=c->pipeline.depth_range[0]+(v[i]->p[2]*inv[i]+1)*.5f*(c->pipeline.depth_range[1]-c->pipeline.depth_range[0]);
    float offset=0;if(c->pipeline.offset_fill){
        float dx=((z[1]-z[0])*(p[2][1]-p[0][1])-(z[2]-z[0])*(p[1][1]-p[0][1]))/area;
        float dy=((p[1][0]-p[0][0])*(z[2]-z[0])-(p[2][0]-p[0][0])*(z[1]-z[0]))/area;
        offset=fmaxf(fabsf(dx),fabsf(dy))*c->pipeline.offset_factor+c->pipeline.offset_units/65535.0f;
    }
    DS34Vertex packed[3];for(unsigned i=0;i<3;++i){
        packed[i].p[0]=p[i][0]*v[i]->p[3];packed[i].p[1]=p[i][1]*v[i]->p[3];packed[i].p[2]=(z[i]+offset)*v[i]->p[3];packed[i].p[3]=v[i]->p[3];
        memcpy(packed[i].color,back?v[i]->back_color:v[i]->color,16);memcpy(packed[i].tex,v[i]->tex,32);
        packed[i].tex[0][2]=(v[i]->fog_factor*7+.5f)/8;packed[i].tex[1][2]=.5f;
    }
    if(ds34_triangle(c,packed)>0)++c->draw->triangles;
}
static void raster(DS13Context *c,const Vertex *a,const Vertex *b,const Vertex *d){
    if(ds34_active && ds34_active(c) && !c->framebuffer_binding)raster_gpu(c,a,b,d);
    else raster_legacy(c,a,b,d);
}

static float plane(const Vertex *v,unsigned p){return v->p[3]+(p&1?-v->p[p/2]:v->p[p/2]);}
static void triangle(DS13Context *c,const Vertex *a,const Vertex *b,const Vertex *d){
    /* Same six homogeneous planes. Entirely visible triangles require no
     * polygon interpolation/copying; common outside plane rejects exactly. */
    unsigned ac=0,bc=0,dc=0;
    for(unsigned p=0;p<6;++p){
        if(plane(a,p)<0)ac|=1u<<p;
        if(plane(b,p)<0)bc|=1u<<p;
        if(plane(d,p)<0)dc|=1u<<p;
    }
    p2_count(3);if(ac&bc&dc){p2_count(4);return;}
    if(!(ac|bc|dc)){p2_count(5);
        if(c->pipeline.shade==0x1d00){Vertex x=*a,y=*b;memcpy(x.color,d->color,16);memcpy(y.color,d->color,16);memcpy(x.back_color,d->back_color,16);memcpy(y.back_color,d->back_color,16);raster(c,&x,&y,d);}else raster(c,a,b,d);return;
    }
    p2_count(6);Vertex poly[12]={*a,*b,*d},tmp[12];unsigned n=3;
    if(c->pipeline.shade==0x1d00){memcpy(poly[0].color,d->color,16);memcpy(poly[1].color,d->color,16);memcpy(poly[0].back_color,d->back_color,16);memcpy(poly[1].back_color,d->back_color,16);}
    for(unsigned p=0;p<6 && n;++p){unsigned count=0;for(unsigned i=0;i<n;++i){Vertex *x=&poly[i],*y=&poly[(i+1)%n];float dx=plane(x,p),dy=plane(y,p);
        if(dx>=0)tmp[count++]=*x;
        if((dx>=0)!=(dy>=0)){float t=dx/(dx-dy);Vertex *r=&tmp[count++];r->fog_factor=x->fog_factor+(y->fog_factor-x->fog_factor)*t;for(unsigned j=0;j<4;++j){r->p[j]=x->p[j]+(y->p[j]-x->p[j])*t;r->color[j]=x->color[j]+(y->color[j]-x->color[j])*t;r->back_color[j]=x->back_color[j]+(y->back_color[j]-x->back_color[j])*t;for(unsigned u=0;u<2;++u)r->tex[u][j]=x->tex[u][j]+(y->tex[u][j]-x->tex[u][j])*t;}}
    }n=count;memcpy(poly,tmp,n*sizeof(Vertex));}
    for(unsigned i=1;i+1<n;++i)raster(c,&poly[0],&poly[i],&poly[i+1]);
}
/* Phase8: six exact clip-plane predicates once per live cached vertex.
 * Only after complete prevalidation proved all original indices <8192, tag
 * the high bits of the privately owned cache identity. There are no further
 * cache lookups in this branch. Nested draws use local64; cleanup invalidates
 * every touched slot. Vertex ABI, buffers and fallback remain unchanged. */
static void p8_raster_cached(DS13Context *c,const Vertex *a,const Vertex *b,const Vertex *d){
    const Vertex *v[3]={a,b,d};float p[3][2],z[3];for(unsigned i=0;i<3;++i){
        if(v[i]->p[3]<=0)return;
        const VertexCache *e=(const void *)((const unsigned char *)v[i]-__builtin_offsetof(VertexCache,vertex));
        const float *screen=p8_screen[e->index&(P5_CACHE-1)];
        p[i][0]=screen[0];p[i][1]=screen[1];z[i]=screen[2];
    }
    float area=edge(p[0],p[1],p[2][0],p[2][1]);if(!isfinite(area)||area==0 || ds16_culled(&c->pipeline,area))return;
    int back=c->pipeline.lighting && c->lighting_state->two_side && (c->pipeline.front_face==0x901?area<0:area>0);
    if(area<0){const Vertex *tmp=v[1];v[1]=v[2];v[2]=tmp;for(unsigned j=0;j<2;++j){float f=p[1][j];p[1][j]=p[2][j];p[2][j]=f;}float f=z[1];z[1]=z[2];z[2]=f;area=-area;}
    float offset=0;if(c->pipeline.offset_fill){
        float dx=((z[1]-z[0])*(p[2][1]-p[0][1])-(z[2]-z[0])*(p[1][1]-p[0][1]))/area;
        float dy=((p[1][0]-p[0][0])*(z[2]-z[0])-(p[2][0]-p[0][0])*(z[1]-z[0]))/area;
        offset=fmaxf(fabsf(dx),fabsf(dy))*c->pipeline.offset_factor+c->pipeline.offset_units/65535.0f;
    }
    DS34Vertex packed[3];for(unsigned i=0;i<3;++i){
#if DS_OPT_PACK
        if(!c->pipeline.lighting && !c->pipeline.offset_fill)memcpy(packed[i].p,v[i]->back_color,16);
        else
#endif
        {packed[i].p[0]=p[i][0]*v[i]->p[3];packed[i].p[1]=p[i][1]*v[i]->p[3];packed[i].p[2]=(z[i]+offset)*v[i]->p[3];packed[i].p[3]=v[i]->p[3];}
        const Vertex *col=c->pipeline.shade==0x1d00?d:v[i];memcpy(packed[i].color,back?col->back_color:col->color,16);memcpy(packed[i].tex,v[i]->tex,32);
        packed[i].tex[0][2]=(v[i]->fog_factor*7+.5f)/8;packed[i].tex[1][2]=.5f;
    }
    if(ds34_triangle(c,packed)>0)++c->draw->triangles;
}
static void p8_triangle(DS13Context *c,const Vertex *a,const Vertex *b,const Vertex *d,unsigned ac,unsigned bc,unsigned dc){
    if(ac&bc&dc){p2_count(3);p2_count(4);return;}
    if(!(ac|bc|dc)){
        p2_count(3);p2_count(5);
        if(ds34_active && ds34_active(c) && !c->framebuffer_binding){p8_raster_cached(c,a,b,d);return;}
        if(c->pipeline.shade==0x1d00){Vertex x=*a,y=*b;memcpy(x.color,d->color,16);memcpy(y.color,d->color,16);memcpy(x.back_color,d->back_color,16);memcpy(y.back_color,d->back_color,16);raster(c,&x,&y,d);}else raster(c,a,b,d);
        return;
    }
    triangle(c,a,b,d); /* exact old six-plane interpolation for crossings */
}
static void draw_internal(uint32_t mode,int32_t first,int32_t count,uint32_t type,const void *indices,int indexed,uint32_t caller){
    DS13Context *c=ds13_active_context();if(!c)return;
    if(first<0||count<0||count>65535){ds13_error(0x501);return;}if(mode<4||mode>6){ds13_unsupported("primitive mode unsupported",mode);return;}
    if(indexed && type!=0x1401 && type!=0x1403){ds13_error(0x500);return;}if(!count || !c->vertex.arrays[0].enabled)return;
    if((c->fog && !c->fog_state) || (c->pipeline.lighting && !c->lighting_state)){ds13_unsupported("lit/fog draw unsupported",c->fog?0xb60:0xb50);return;}
    if(c->pipeline.lighting && ds32_prepare(c)){ds13_unsupported("singular lighting modelview unsupported",0x1700);return;}
    DS22State *s=state(c);if(!s)return;
    for(unsigned u=0;u<2;++u)s->sampler[u]=c->texture.enabled[u]?texture(c,u):NULL;
    if(ds26_surface(c,&s->target))return;
    for(unsigned u=0;u<2;++u)if(c->texture.enabled[u]){DS15Object *o=s->sampler[u];
        if(o && o->levels[0].defined && !(ds_scene_defer_resident && ds_scene_defer_resident() && ds34_active && ds34_active(c) && !c->framebuffer_binding) && ds15_resident(&c->texture,o,0))return;
        if(c->framebuffer_binding && s->target.pixels && o && o->levels[0].rgba==s->target.pixels){ds13_unsupported("framebuffer texture feedback unsupported",c->texture.binding[u]);return;}}
    for(unsigned u=0;u<2;++u)if(c->texture.enabled[u]){DS15Object *o=s->sampler[u];if(o && (o->min_filter>=0x2700 || o->min_filter!=o->mag_filter)){ds13_unsupported("mipmap or distinct min/mag sampling unsupported",o->min_filter);return;}}
    const uint8_t *index_span=indexed?p4_index_span(c,indices,type,(uint32_t)count):NULL;
    hq_array_begin(&c->vertex);
    hq_matrix_begin(c);
    p8_tex_begin(c);
    /* Validate all referenced attributes before changing any target pixel. */
    VertexCache local[VERTEX_CACHE];int wide=!p5_cache_busy;VertexCache *cache=wide?p5_cache:local;unsigned capacity=wide?P5_CACHE:VERTEX_CACHE;if(wide){p5_cache_busy=1;p6_cache_begin();}else for(unsigned i=0;i<capacity;++i)cache[i].index=UINT32_MAX;
    uint64_t p2_t=p2_clock();
    uint32_t index_bits=0;
    for(int32_t i=0;i<count;++i){uint32_t index=(uint32_t)first+(uint32_t)i;if((indexed && p4_index_at(c,indices,type,(uint32_t)i,index_span,&index)) || cached_vertex(c,cache,capacity-1,index,NULL,i==0)){ds13_unsupported("unreadable draw arrays",i);if(wide)p6_cache_end();return;}index_bits|=index;}
    p2_add(0,p2_t);
    int gpu=ds34_begin_draw?ds34_begin_draw(c):0;if(gpu<0){if(wide)p6_cache_end();return;}
    p2_t=p2_clock();
    /* All indices fit the direct map: prevalidation left every vertex live,
     * without slot collisions. Preserve per-reference material tracking and
     * counters, borrow immutable vertices only until this draw ends. */
    if(wide && index_bits<P5_CACHE){
        for(unsigned j=0;j<p6_touch_count;++j){
            VertexCache *e=&cache[p6_touched[j]];unsigned code=0;
            for(unsigned p=0;p<6;++p)if(plane(&e->vertex,p)<0)code|=1u<<p;
            e->index|=code<<16;
            if(!code && !c->framebuffer_binding && e->vertex.p[3]>0){
                const Vertex *v=&e->vertex;float inv=1/v->p[3];
                float *screen=p8_screen[p6_touched[j]];
                screen[0]=c->viewport[0]+(v->p[0]*inv+1)*c->viewport[2]*.5f;
                screen[1]=c->viewport[1]+(v->p[1]*inv+1)*c->viewport[3]*.5f;
                screen[2]=c->pipeline.depth_range[0]+(v->p[2]*inv+1)*.5f*(c->pipeline.depth_range[1]-c->pipeline.depth_range[0]);
#if DS_OPT_PACK
                /* Unlit vertices never consume back-face lighting colors.
                 * Borrow those four private floats until draw cleanup; keep
                 * clip-space positions intact for crossings and CPU fallback.
                 * No arena growth and exactly the old multiply/add order. */
                if(gpu>0 && !c->pipeline.lighting && !c->pipeline.offset_fill){
                    e->vertex.back_color[0]=screen[0]*v->p[3];
                    e->vertex.back_color[1]=screen[1]*v->p[3];
                    e->vertex.back_color[2]=(screen[2]+0.0f)*v->p[3];
                    e->vertex.back_color[3]=v->p[3];
                }
#endif
            }
        }
        const Vertex *v[3];unsigned codes[3];
        for(int32_t i=0;i<count;++i){uint32_t index=(uint32_t)first+(uint32_t)i;
            if(indexed)p4_index_at(c,indices,type,(uint32_t)i,index_span,&index);
            VertexCache *e=&cache[index];p2_count(1);p8_track(c,e->primary);
            const Vertex *next=&e->vertex;unsigned code=e->index>>16;
            if(mode==4){unsigned k=i%3;v[k]=next;codes[k]=code;if(k==2)p8_triangle(c,v[0],v[1],v[2],codes[0],codes[1],codes[2]);}
            else if(i<2){v[i]=next;codes[i]=code;}
            else{if(mode==5 && (i&1))p8_triangle(c,v[1],v[0],next,codes[1],codes[0],code);else p8_triangle(c,v[0],v[1],next,codes[0],codes[1],code);if(mode==5){v[0]=v[1];codes[0]=codes[1];}v[1]=next;codes[1]=code;}
        }
    }else{Vertex v[3];for(int32_t i=0;i<count;++i){uint32_t index=(uint32_t)first+(uint32_t)i;if(indexed)p4_index_at(c,indices,type,(uint32_t)i,index_span,&index);Vertex next;cached_vertex(c,cache,capacity-1,index,&next,0);
        if(mode==4){v[i%3]=next;if(i%3==2)triangle(c,&v[0],&v[1],&v[2]);}
        else if(i<2)v[i]=next;
        else{if(mode==5 && (i&1))triangle(c,&v[1],&v[0],&next);else triangle(c,&v[0],&v[1],&next);if(mode==5)v[0]=v[1];v[1]=next;}
    }}p2_add(1,p2_t);if(gpu)ds34_end_draw(c);else if(c->framebuffer_binding)ds34_fbo_dirty(c);
    if(wide)p6_cache_end();
    ++s->calls;if(s->observe)s->observe(c,caller);
}
static void draw(uint32_t mode,int32_t first,int32_t count,uint32_t type,const void *indices,int indexed,uint32_t caller){
    DS13Context *c=ds13_active_context();uint32_t before=c && c->draw?c->draw->triangles:0;uint64_t start=p2_clock();
    extern void p7_view_note(DS13Context *,uint32_t,uint32_t);
    if(c)p7_view_note(c,caller,count>0?(uint32_t)count:0);
    draw_internal(mode,first,count,type,indices,indexed,caller);
    if(c && c->draw){extern void p5_note(DS13Context *,uint32_t,uint32_t,uint32_t,uint64_t);p5_note(c,mode,count>0?(uint32_t)count:0,c->draw->triangles-before,p2_clock()-start);}
}
static void DS13_SOFT draw_arrays(uint32_t mode,int32_t first,int32_t count){draw(mode,first,count,0,NULL,0,(uint32_t)__builtin_return_address(0));}
static void DS13_SOFT draw_elements(uint32_t mode,int32_t count,uint32_t type,const void *indices){draw(mode,0,count,type,indices,1,(uint32_t)__builtin_return_address(0));}
#define B(name,fn) {name,(uint32_t)(uintptr_t)fn}
uint32_t ds22_bindings(DSBinding *out,uint32_t capacity){
    const DSBinding b[]={B("glColor4f",color),B("glColor4x",color_x),B("glColor4ub",color_b),B("glTexEnvf",env_f),B("glTexEnvx",env_x),B("glTexEnvi",env_i),B("glTexEnvfv",env_fv),B("glTexEnvxv",env_xv),B("glTexEnviv",env_iv),B("glGetTexEnvfv",get_env_f),B("glGetTexEnvxv",get_env_x),B("glGetTexEnviv",get_env_i),B("glDrawArrays",draw_arrays),B("glDrawElements",draw_elements)};
    if(capacity<DS22_BINDINGS)return 0;
    memcpy(out,b,sizeof(b));return DS22_BINDINGS;
}
