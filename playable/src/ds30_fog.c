/* ES 1.1 section 3.8: |eye-space z|, per-vertex fog factor interpolated
 * perspective-correctly by the rasterizer. Fog changes post-texture RGB only. */
#include "ds13_gles.h"
#include "ds30_fog.h"
#include "ds_runtime.h"
#include <math.h>
#include <string.h>
static float clamp(float v){return v<0?0:v>1?1:v;}
int ds30_attach(DS13Context *c){
    if(!c || c!=ds13_active_context() || c->fog_state)return -1;
    DS30Fog *s=ds_rt_calloc(1,sizeof(*s));if(!s)return -1;
    s->mode=0x800;s->density=s->end=1;c->fog_state=s;return 0;
}
void ds30_close(DS13Context *c){ds_rt_free(c->fog_state);c->fog_state=NULL;}
static DS30Fog *active(void){DS13Context *c=ds13_active_context();return c?c->fog_state:NULL;}
static int size(uint32_t name){return name==0xb66?4:(name>=0xb62 && name<=0xb65)?1:0;}
static void set(uint32_t name,const float *v,int vector){
    DS30Fog *s=active();if(!s)return;int n=size(name);
    if(!n || (!vector && n!=1)){ds13_error(0x500);return;}
    if(!v){ds13_error(0x501);return;}
    for(int i=0;i<n;++i)if(!isfinite(v[i])){ds13_error(0x501);return;}
    if(name==0xb65){if(v[0]!=0x800 && v[0]!=0x801 && v[0]!=0x2601){ds13_error(0x500);return;}s->mode=(uint32_t)v[0];}
    else if(name==0xb62){if(v[0]<0){ds13_error(0x501);return;}s->density=v[0];}
    else if(name==0xb63)s->start=v[0];else if(name==0xb64)s->end=v[0];
    else for(unsigned i=0;i<4;++i)s->color[i]=clamp(v[i]);
}
static void DS13_SOFT fog_f(uint32_t name,float v){set(name,&v,0);}
static void DS13_SOFT fog_x(uint32_t name,int32_t v){float f=name==0xb65?(float)v:v/65536.0f;set(name,&f,0);}
static void DS13_SOFT fog_fv(uint32_t name,const float *v){set(name,v,1);}
static void DS13_SOFT fog_xv(uint32_t name,const int32_t *v){
    if(!size(name)){ds13_error(0x500);return;}if(!v){ds13_error(0x501);return;}
    float f[4];for(int i=0;i<size(name);++i)f[i]=name==0xb65?(float)v[i]:v[i]/65536.0f;set(name,f,1);
}
int ds30_real(DS13Context *c,uint32_t name,float out[16],int *normalized){
    DS30Fog *s=c->fog_state;if(!s)return 0;
    switch(name){case 0xb62:*out=s->density;return 1;case 0xb63:*out=s->start;return 1;case 0xb64:*out=s->end;return 1;
        case 0xb66:memcpy(out,s->color,16);*normalized=1;return 4;default:return 0;}
}
int ds30_integer(DS13Context *c,uint32_t name,int32_t *out){if(!c->fog_state || name!=0xb65)return 0;*out=(int32_t)c->fog_state->mode;return 1;}
float ds30_factor(const DS30Fog *s,float eye_z){
    float z=fabsf(eye_z),f;
    if(s->mode==0x2601)f=s->end==s->start?(z<=s->start?1:0):(s->end-z)/(s->end-s->start);
    else{float d=s->density*z;f=expf(s->mode==0x801?-(d*d):-d);}
    return clamp(f);
}
void ds30_apply(const DS30Fog *s,float factor,float rgba[4]){float f=clamp(factor);for(unsigned i=0;i<3;++i)rgba[i]=rgba[i]*f+s->color[i]*(1-f);}
uint32_t ds30_bindings(DSBinding *out,uint32_t capacity){
    const DSBinding b[]={{"glFogf",(uint32_t)fog_f},{"glFogx",(uint32_t)fog_x},{"glFogfv",(uint32_t)fog_fv},{"glFogxv",(uint32_t)fog_xv}};
    if(!out || capacity<DS30_BINDINGS)return 0;
    memcpy(out,b,sizeof(b));return DS30_BINDINGS;
}
