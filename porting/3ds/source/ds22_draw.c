/* Bounded CPU triangles, with opt-in FBO, fog and texture combiners.
 * Lighting and unsupported mipmap sampling still stop explicitly. */
#include "ds13_gles.h"
#include "ds_runtime.h"
#include <math.h>
#include <string.h>
typedef struct {float p[4],color[4],tex[2][4],fog_factor;} Vertex;
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
    DS22State *s=state(c);if(s){s->color[0]=clamp(r);s->color[1]=clamp(g);s->color[2]=clamp(b);s->color[3]=clamp(a);}
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
static int attribute(DS13Context *c,unsigned slot,uint32_t index,float out[4]){
    uint8_t packed[16];DS14Array *a=&c->vertex.arrays[slot];if(ds14_read_array(&c->vertex,slot,index,packed,sizeof(packed))<0)return -1;
    for(unsigned i=0;i<a->size;++i){float v;switch(a->type){
        case 0x1400:v=(int8_t)packed[i];break;case 0x1401:v=packed[i]/255.0f;break;
        case 0x1402:{int16_t x;memcpy(&x,packed+i*2,2);v=x;break;}
        case 0x1406:memcpy(&v,packed+i*4,4);break;
        case 0x140c:{int32_t x;memcpy(&x,packed+i*4,4);v=x/65536.0f;break;}
        default:return -1;
    }if(!isfinite(v))return -1;out[i]=v;}return 0;
}
static int vertex(DS13Context *c,uint32_t index,Vertex *v){
    float p[4]={0,0,0,1},eye[4];if(attribute(c,0,index,p))return -1;ds21_transform(c,0x1700,0,p,eye);ds21_transform(c,0x1701,0,eye,v->p);
    if(c->fog && !isfinite(eye[2]))return -1;
    v->fog_factor=c->fog?ds30_factor(c->fog_state,eye[2]):1;
    DS22State *s=c->draw;memcpy(v->color,s->color,16);
    if(c->vertex.arrays[2].enabled && attribute(c,2,index,v->color))return -1;
    for(unsigned u=0;u<2;++u){float t[4]={0,0,0,1};if(c->vertex.arrays[3+u].enabled && attribute(c,3+u,index,t))return -1;ds21_transform(c,0x1702,u,t,v->tex[u]);}
    for(unsigned i=0;i<4;++i){if(!isfinite(v->p[i]) || !isfinite(v->color[i]))return -1;v->color[i]=clamp(v->color[i]);for(unsigned u=0;u<2;++u)if(!isfinite(v->tex[u][i]))return -1;}
    return 0;
}
static DS15Object *texture(DS13Context *c,unsigned u){uint32_t name=c->texture.binding[u];if(!name)return &c->texture.default_object;for(unsigned i=0;i<DS15_TEXTURES;++i)if(c->texture.textures[i].used && c->texture.textures[i].name==name)return c->texture.textures[i].object;return NULL;}
static unsigned coord(int x,unsigned size,uint32_t wrap){if(wrap==0x812f)return x<0?0:(unsigned)x>=size?size-1:(unsigned)x;int i=x%(int)size;return (unsigned)(i<0?i+(int)size:i);}
static void texel(const DS15Level *l,DS15Object *o,int x,int y,float out[4]){const uint8_t *p=l->rgba+(coord(y,l->height,o->wrap_t)*l->width+coord(x,l->width,o->wrap_s))*4;for(unsigned i=0;i<4;++i)out[i]=p[i]/255.0f;}
static void sample(DS13Context *c,unsigned u,float x,float y,float out[4]){
    DS15Object *o=texture(c,u);const DS15Level *l=o?&o->levels[0]:NULL;++c->draw->samples;
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
        DS15Object *o=texture(c,u);uint32_t format=o?o->levels[0].format:0x1908;
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
    if(!ds16_alpha_pass(&c->pipeline,src[3]))return;
    DS26Surface *t=&c->draw->target;
    if((t->depth || t->stencil) && !ds26_fragment(c,t,x,y,depth))return;
    if(!t->pixels)return;
    uint32_t offset=pixel_offset(t,x,y);uint8_t *p=t->pixels+offset;float dst[4]={0,0,0,1},out[4];
    if(t->layout==DS13_RGB565_CTR){uint32_t v=p[0]|(uint32_t)p[1]<<8;dst[0]=((v>>11)&31)/31.0f;dst[1]=((v>>5)&63)/63.0f;dst[2]=(v&31)/31.0f;}
    else for(unsigned i=0;i<(t->layout==3?4u:3u);++i)dst[i]=p[t->layout==DS13_RGB8_ROWS || t->layout==3?i:2-i]/255.0f;
    ds16_blend(&c->pipeline,c->blend,src,dst,out);
    for(unsigned i=0;i<4;++i)if(!c->color_mask[i])out[i]=dst[i];
    if(t->layout==3)ds26_quantize(t,out);
    if(t->layout==DS13_RGB565_CTR){uint32_t v=(uint32_t)lrintf(clamp(out[0])*31)<<11|(uint32_t)lrintf(clamp(out[1])*63)<<5|(uint32_t)lrintf(clamp(out[2])*31);p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
    else for(unsigned i=0;i<(t->layout==3?4u:3u);++i)p[t->layout==DS13_RGB8_ROWS || t->layout==3?i:2-i]=(uint8_t)lrintf(clamp(out[i])*255);
    ++c->draw->fragments;++c->pixels_written;
}
static float edge(const float a[2],const float b[2],float x,float y){return (b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]);}
static int inclusive(const float a[2],const float b[2]){return b[1]>a[1] || (b[1]==a[1] && b[0]<a[0]);}
static void raster(DS13Context *c,Vertex a,Vertex b,Vertex d){
    Vertex v[3]={a,b,d};float p[3][2],inv[3];for(unsigned i=0;i<3;++i){if(v[i].p[3]<=0)return;inv[i]=1/v[i].p[3];p[i][0]=c->viewport[0]+(v[i].p[0]*inv[i]+1)*c->viewport[2]*.5f;p[i][1]=c->viewport[1]+(v[i].p[1]*inv[i]+1)*c->viewport[3]*.5f;}
    float area=edge(p[0],p[1],p[2][0],p[2][1]);if(!isfinite(area)||area==0 || ds16_culled(&c->pipeline,area))return;
    if(area<0){Vertex tmp=v[1];v[1]=v[2];v[2]=tmp;for(unsigned j=0;j<2;++j){float f=p[1][j];p[1][j]=p[2][j];p[2][j]=f;}float f=inv[1];inv[1]=inv[2];inv[2]=f;area=-area;}
    DS26Surface *target=&c->draw->target;
    float minx=fmaxf(0,fminf((float)target->width,fminf(p[0][0],fminf(p[1][0],p[2][0])))),maxx=fmaxf(0,fminf((float)target->width,fmaxf(p[0][0],fmaxf(p[1][0],p[2][0]))));
    float miny=fmaxf(0,fminf((float)target->height,fminf(p[0][1],fminf(p[1][1],p[2][1])))),maxy=fmaxf(0,fminf((float)target->height,fmaxf(p[0][1],fmaxf(p[1][1],p[2][1]))));
    float z[3];for(unsigned i=0;i<3;++i)z[i]=c->pipeline.depth_range[0]+(v[i].p[2]*inv[i]+1)*.5f*(c->pipeline.depth_range[1]-c->pipeline.depth_range[0]);
    float offset=0;if(c->pipeline.offset_fill){
        float dx=((z[1]-z[0])*(p[2][1]-p[0][1])-(z[2]-z[0])*(p[1][1]-p[0][1]))/area;
        float dy=((p[1][0]-p[0][0])*(z[2]-z[0])-(p[2][0]-p[0][0])*(z[1]-z[0]))/area;
        offset=fmaxf(fabsf(dx),fabsf(dy))*c->pipeline.offset_factor+c->pipeline.offset_units/65535.0f;
    }
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
static float plane(Vertex *v,unsigned p){return v->p[3]+(p&1?-v->p[p/2]:v->p[p/2]);}
static void triangle(DS13Context *c,Vertex a,Vertex b,Vertex d){
    Vertex poly[12]={a,b,d},tmp[12];unsigned n=3;
    if(c->pipeline.shade==0x1d00){memcpy(poly[0].color,d.color,16);memcpy(poly[1].color,d.color,16);}
    for(unsigned p=0;p<6 && n;++p){unsigned count=0;for(unsigned i=0;i<n;++i){Vertex *x=&poly[i],*y=&poly[(i+1)%n];float dx=plane(x,p),dy=plane(y,p);
        if(dx>=0)tmp[count++]=*x;
        if((dx>=0)!=(dy>=0)){float t=dx/(dx-dy);Vertex *r=&tmp[count++];r->fog_factor=x->fog_factor+(y->fog_factor-x->fog_factor)*t;for(unsigned j=0;j<4;++j){r->p[j]=x->p[j]+(y->p[j]-x->p[j])*t;r->color[j]=x->color[j]+(y->color[j]-x->color[j])*t;for(unsigned u=0;u<2;++u)r->tex[u][j]=x->tex[u][j]+(y->tex[u][j]-x->tex[u][j])*t;}}
    }n=count;memcpy(poly,tmp,n*sizeof(Vertex));}
    for(unsigned i=1;i+1<n;++i)raster(c,poly[0],poly[i],poly[i+1]);
}
static void draw(uint32_t mode,int32_t first,int32_t count,uint32_t type,const void *indices,int indexed,uint32_t caller){
    DS13Context *c=ds13_active_context();if(!c)return;
    if(first<0||count<0||count>65535){ds13_error(0x501);return;}if(mode<4||mode>6){ds13_unsupported("primitive mode unsupported",mode);return;}
    if(indexed && type!=0x1401 && type!=0x1403){ds13_error(0x500);return;}if(!count || !c->vertex.arrays[0].enabled)return;
    if((c->fog && !c->fog_state) || c->pipeline.lighting){ds13_unsupported("lit/fog draw unsupported",c->fog?0xb60:0xb50);return;}
    DS22State *s=state(c);if(!s)return;
    if(ds26_surface(c,&s->target))return;
    for(unsigned u=0;u<2;++u)if(c->texture.enabled[u]){DS15Object *o=texture(c,u);
        if(o && o->levels[0].defined && ds15_resident(&c->texture,o,0))return;
        if(c->framebuffer_binding && s->target.pixels && o && o->levels[0].rgba==s->target.pixels){ds13_unsupported("framebuffer texture feedback unsupported",c->texture.binding[u]);return;}}
    for(unsigned u=0;u<2;++u)if(c->texture.enabled[u]){DS15Object *o=texture(c,u);if(o && (o->min_filter>=0x2700 || o->min_filter!=o->mag_filter)){ds13_unsupported("mipmap or distinct min/mag sampling unsupported",o->min_filter);return;}}
    /* Validate all referenced attributes before changing any target pixel. */
    for(int32_t i=0;i<count;++i){uint32_t index=(uint32_t)first+(uint32_t)i;Vertex v;if((indexed && index_at(c,indices,type,(uint32_t)i,&index)) || vertex(c,index,&v)){ds13_unsupported("unreadable draw arrays",i);return;}}
    Vertex v[3];for(int32_t i=0;i<count;++i){uint32_t index=(uint32_t)first+(uint32_t)i;if(indexed)index_at(c,indices,type,(uint32_t)i,&index);Vertex next;vertex(c,index,&next);
        if(mode==4){v[i%3]=next;if(i%3==2)triangle(c,v[0],v[1],v[2]);}
        else if(i<2)v[i]=next;
        else{if(mode==5 && (i&1))triangle(c,v[1],v[0],next);else triangle(c,v[0],v[1],next);if(mode==5)v[0]=v[1];v[1]=next;}
    }++s->calls;if(s->observe)s->observe(c,caller);
}
static void DS13_SOFT draw_arrays(uint32_t mode,int32_t first,int32_t count){draw(mode,first,count,0,NULL,0,(uint32_t)__builtin_return_address(0));}
static void DS13_SOFT draw_elements(uint32_t mode,int32_t count,uint32_t type,const void *indices){draw(mode,0,count,type,indices,1,(uint32_t)__builtin_return_address(0));}
#define B(name,fn) {name,(uint32_t)(uintptr_t)fn}
uint32_t ds22_bindings(DSBinding *out,uint32_t capacity){
    const DSBinding b[]={B("glColor4f",color),B("glColor4x",color_x),B("glColor4ub",color_b),B("glTexEnvf",env_f),B("glTexEnvx",env_x),B("glTexEnvi",env_i),B("glTexEnvfv",env_fv),B("glTexEnvxv",env_xv),B("glTexEnviv",env_iv),B("glGetTexEnvfv",get_env_f),B("glGetTexEnvxv",get_env_x),B("glGetTexEnviv",get_env_i),B("glDrawArrays",draw_arrays),B("glDrawElements",draw_elements)};
    if(capacity<DS22_BINDINGS)return 0;
    memcpy(out,b,sizeof(b));return DS22_BINDINGS;
}
