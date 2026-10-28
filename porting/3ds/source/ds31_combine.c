/* ES1.1 section 3.7.12: two independent texture combiners. */
#include "ds13_gles.h"
#include "ds_runtime.h"
#include <math.h>
#include <string.h>
int ds31_attach(DS13Context *c){
    if(!c || c!=ds13_active_context() || ds22_prepare(c) || c->draw->combine)return -1;
    DS31Combine *s=ds_rt_calloc(1,sizeof(*s));if(!s)return -1;
    for(unsigned u=0;u<2;++u){DS31Unit *v=&s->unit[u];v->rgb=v->alpha=0x2100;v->rgb_scale=v->alpha_scale=1;
        for(unsigned i=0;i<3;++i){v->src_rgb[i]=v->src_alpha[i]=i==0?0x1702:i==1?0x8578:0x8576;v->op_rgb[i]=i==2?0x302:0x300;v->op_alpha[i]=0x302;}}
    c->draw->combine=s;return 0;
}
void ds31_close(DS13Context *c){if(c->draw){ds_rt_free(c->draw->combine);c->draw->combine=NULL;}}
int ds31_scale(uint32_t name){return name==0x8573 || name==0xd1c;}
static uint32_t *parameter(DS31Unit *u,uint32_t name,unsigned *kind){
    *kind=0;if(name==0x8571){*kind=1;return &u->rgb;}if(name==0x8572){*kind=2;return &u->alpha;}
    if(name>=0x8580 && name<=0x8582)return &u->src_rgb[name-0x8580];
    if(name>=0x8588 && name<=0x858a)return &u->src_alpha[name-0x8588];
    if(name>=0x8590 && name<=0x8592){*kind=3;return &u->op_rgb[name-0x8590];}
    if(name>=0x8598 && name<=0x859a){*kind=4;return &u->op_alpha[name-0x8598];}return NULL;
}
static int function(uint32_t value){return value==0x1e01 || value==0x2100 || value==0x104 || value==0x8574 || value==0x8575 || value==0x84e7;}
int ds31_set(DS13Context *c,uint32_t name,float value){
    if(!c->draw || !c->draw->combine)return 0;
    unsigned unit=c->active_texture-0x84c0;DS31Unit *u=&c->draw->combine->unit[unit];
    if(name==0x2200){if(value!=0x8570)return 0;c->draw->env_mode[unit]=0x8570;return 1;}
    if(ds31_scale(name)){
        if(value!=1 && value!=2 && value!=4){ds13_error(0x501);return 1;}
        if(name==0x8573)u->rgb_scale=value;else u->alpha_scale=value;return 1;
    }
    unsigned kind;uint32_t *p=parameter(u,name,&kind);if(!p)return 0;
    if(!isfinite(value) || value<0 || value>65535 || value!=(float)(uint32_t)value){ds13_error(0x500);return 1;}
    uint32_t v=(uint32_t)value;int valid=kind==1?(function(v)||v==0x86ae||v==0x86af):kind==2?function(v):kind==3?(v>=0x300&&v<=0x303):kind==4?(v==0x302||v==0x303):(v==0x1702||v==0x8576||v==0x8577||v==0x8578);
    if(!valid)ds13_error(0x500);else *p=v;
    return 1;
}
int ds31_get(DS13Context *c,uint32_t name,float *value,int *is_enum){
    if(!c->draw || !c->draw->combine)return 0;
    DS31Unit *u=&c->draw->combine->unit[c->active_texture-0x84c0];
    if(ds31_scale(name)){*value=name==0x8573?u->rgb_scale:u->alpha_scale;*is_enum=0;return 1;}
    unsigned kind;uint32_t *p=parameter(u,name,&kind);if(!p)return 0;*value=(float)*p;*is_enum=1;return 1;
}
static const float *source(uint32_t s,const float *primary,const float *previous,const float *texture,const float *constant){return s==0x1702?texture:s==0x8576?constant:s==0x8577?primary:previous;}
static float op(uint32_t operation,const float *s,unsigned component){float v=s[operation==0x302||operation==0x303?3:component];return operation==0x301||operation==0x303?1-v:v;}
static float calculate(uint32_t mode,float x,float y,float z){switch(mode){case 0x1e01:return x;case 0x2100:return x*y;case 0x104:return x+y;case 0x8574:return x+y-.5f;case 0x8575:return x*z+y*(1-z);default:return x-y;}}
static float clamp(float v){return v<0?0:v>1?1:v;}
void ds31_apply(const DS31Unit *u,const float primary[4],const float previous[4],const float texture[4],const float constant[4],float out[4]){
    float rgb[3][3],alpha[3],result[4];
    for(unsigned arg=0;arg<3;++arg){const float *s=source(u->src_rgb[arg],primary,previous,texture,constant);
        for(unsigned i=0;i<3;++i)rgb[arg][i]=op(u->op_rgb[arg],s,i);
        s=source(u->src_alpha[arg],primary,previous,texture,constant);alpha[arg]=op(u->op_alpha[arg],s,3);}
    float dot=0;if(u->rgb==0x86ae || u->rgb==0x86af)for(unsigned i=0;i<3;++i)dot+=4*(rgb[0][i]-.5f)*(rgb[1][i]-.5f);
    for(unsigned i=0;i<3;++i)result[i]=clamp((u->rgb==0x86ae||u->rgb==0x86af?dot:calculate(u->rgb,rgb[0][i],rgb[1][i],rgb[2][i]))*u->rgb_scale);
    result[3]=clamp((u->rgb==0x86af?dot:calculate(u->alpha,alpha[0],alpha[1],alpha[2]))*u->alpha_scale);memcpy(out,result,sizeof(result));
}
