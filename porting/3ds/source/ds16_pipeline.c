#include "ds13_gles.h"
#include <limits.h>
#include <math.h>
#include <string.h>
#define BAD_ENUM 0x500u
#define BAD_VALUE 0x501u
static DS16State *state(void){DS13Context *c=ds13_active_context();return c?&c->pipeline:NULL;}
static float clamp(float v){return v<0?0:v>1?1:v;}
void ds16_init(DS16State *s){
    memset(s,0,sizeof(*s));s->cull_mode=0x405;s->front_face=0x901;s->depth_func=0x201;s->depth_mask=1;
    s->alpha_func=s->stencil_func=0x207;s->blend_src=1;s->shade=0x1d01;
    s->stencil_value_mask=s->stencil_write_mask=UINT32_MAX;s->stencil_fail=s->stencil_zfail=s->stencil_zpass=0x1e00;s->depth_range[1]=1;
}
int ds16_capability(DS16State *s,uint32_t name,int set){
    uint32_t *p=NULL;
    switch(name){case 0xb44:p=&s->cull;break;case 0xb71:p=&s->depth;break;case 0xbc0:p=&s->alpha;break;case 0xb90:p=&s->stencil;break;
        case 0x8037:p=&s->offset_fill;break;case 0xb50:p=&s->lighting;break;case 0xb57:p=&s->color_material;break;case 0xba1:p=&s->normalize;break;case 0x803a:p=&s->rescale;break;
        default:if(name>=0x4000 && name<=0x4007)p=&s->lights[name-0x4000];break;
    }
    if(!p)return -1;
    if(set>=0)*p=set!=0;
    return (int)*p;
}
static int compare(uint32_t func,float a,float b){switch(func){
    case 0x200:return 0;case 0x201:return a<b;case 0x202:return a==b;case 0x203:return a<=b;
    case 0x204:return a>b;case 0x205:return a!=b;case 0x206:return a>=b;case 0x207:return 1;default:return 0;
}}
int ds16_culled(const DS16State *s,float area){
    if(!isfinite(area))return -1;
    if(!s->cull)return 0;
    int front=s->front_face==0x901?area>0:area<0;
    return s->cull_mode==0x408 || (s->cull_mode==0x404?front:!front);
}
int ds16_alpha_pass(const DS16State *s,float alpha){return !s->alpha || compare(s->alpha_func,clamp(alpha),s->alpha_ref);}
int ds16_depth_pass(const DS16State *s,float source,float destination){return !s->depth || compare(s->depth_func,source,destination);}
static float factor(uint32_t f,unsigned i,const float *s,const float *d){switch(f){
    case 0:return 0;case 1:return 1;case 0x300:return s[i];case 0x301:return 1-s[i];case 0x302:return s[3];case 0x303:return 1-s[3];
    case 0x304:return d[3];case 0x305:return 1-d[3];case 0x306:return d[i];case 0x307:return 1-d[i];case 0x308:return i==3?1:fminf(s[3],1-d[3]);default:return 0;
}}
void ds16_blend(const DS16State *s,int enabled,const float source[4],const float destination[4],float out[4]){
    float src[4],dst[4],result[4];for(unsigned i=0;i<4;++i){src[i]=clamp(source[i]);dst[i]=clamp(destination[i]);}
    for(unsigned i=0;i<4;++i)result[i]=enabled?clamp(src[i]*factor(s->blend_src,i,src,dst)+dst[i]*factor(s->blend_dst,i,src,dst)):src[i];
    memcpy(out,result,sizeof(result)); /* Source/destination may alias output. */
}
static int comparison(uint32_t f){return f>=0x200 && f<=0x207;}
static void DS13_SOFT cull_face(uint32_t mode){DS16State *s=state();if(!s)return;if(mode!=0x404 && mode!=0x405 && mode!=0x408){ds13_error(BAD_ENUM);return;}s->cull_mode=mode;}
static void DS13_SOFT front_face(uint32_t mode){DS16State *s=state();if(!s)return;if(mode!=0x900 && mode!=0x901){ds13_error(BAD_ENUM);return;}s->front_face=mode;}
static void DS13_SOFT depth_func(uint32_t f){DS16State *s=state();if(!s)return;if(!comparison(f)){ds13_error(BAD_ENUM);return;}s->depth_func=f;}
static void DS13_SOFT depth_mask(uint8_t mask){DS16State *s=state();if(s)s->depth_mask=mask!=0;}
static void DS13_SOFT depth_range(float near,float far){DS16State *s=state();if(!s)return;if(isnan(near)||isnan(far)){ds13_error(BAD_VALUE);return;}s->depth_range[0]=clamp(near);s->depth_range[1]=clamp(far);}
static void DS13_SOFT depth_range_x(int32_t near,int32_t far){depth_range(near/65536.0f,far/65536.0f);}
static void DS13_SOFT alpha_func(uint32_t f,float ref){DS16State *s=state();if(!s)return;if(!comparison(f)){ds13_error(BAD_ENUM);return;}if(isnan(ref)){ds13_error(BAD_VALUE);return;}s->alpha_func=f;s->alpha_ref=clamp(ref);}
static void DS13_SOFT alpha_func_x(uint32_t f,int32_t ref){alpha_func(f,ref/65536.0f);}
static void DS13_SOFT blend_func(uint32_t src,uint32_t dst){
    DS16State *s=state();if(!s)return;
    int source=src<=1 || (src>=0x302 && src<=0x308),destination=dst<=1 || (dst>=0x300 && dst<=0x305);
    if(!source || !destination){ds13_error(BAD_ENUM);return;}s->blend_src=src;s->blend_dst=dst;
}
static void DS13_SOFT shade_model(uint32_t mode){DS16State *s=state();if(!s)return;if(mode!=0x1d00 && mode!=0x1d01){ds13_error(BAD_ENUM);return;}s->shade=mode;}
static void DS13_SOFT polygon_offset(float f,float u){DS16State *s=state();if(!s)return;if(!isfinite(f)||!isfinite(u)){ds13_error(BAD_VALUE);return;}s->offset_factor=f;s->offset_units=u;}
static void DS13_SOFT polygon_offset_x(int32_t f,int32_t u){polygon_offset(f/65536.0f,u/65536.0f);}
static void DS13_SOFT stencil_func(uint32_t f,int32_t ref,uint32_t mask){DS16State *s=state();if(!s)return;if(!comparison(f)){ds13_error(BAD_ENUM);return;}(void)ref;s->stencil_func=f;s->stencil_ref=0; /* Current surface has zero stencil bits. */ s->stencil_value_mask=mask;}
static void DS13_SOFT stencil_mask(uint32_t mask){DS16State *s=state();if(s)s->stencil_write_mask=mask;}
static int stencil_action(uint32_t op){return op==0 || op==0x1e00 || op==0x1e01 || op==0x1e02 || op==0x1e03 || op==0x150a;}
static void DS13_SOFT stencil_op(uint32_t fail,uint32_t zfail,uint32_t zpass){DS16State *s=state();if(!s)return;if(!stencil_action(fail)||!stencil_action(zfail)||!stencil_action(zpass)){ds13_error(BAD_ENUM);return;}s->stencil_fail=fail;s->stencil_zfail=zfail;s->stencil_zpass=zpass;}
int ds16_query(DS16State *s,uint32_t name,int32_t *out){
    int enabled=ds16_capability(s,name,-1);if(enabled>=0){*out=enabled;return 1;}
    uint32_t v;
    switch(name){case 0xb45:v=s->cull_mode;break;case 0xb46:v=s->front_face;break;case 0xb74:v=s->depth_func;break;case 0xb72:v=s->depth_mask;break;
        case 0xbc1:v=s->alpha_func;break;case 0xbe1:v=s->blend_src;break;case 0xbe0:v=s->blend_dst;break;case 0xb54:v=s->shade;break;
        case 0xb92:v=s->stencil_func;break;case 0xb97:v=s->stencil_ref;break;case 0xb93:v=s->stencil_value_mask;break;case 0xb98:v=s->stencil_write_mask;break;
        case 0xb94:v=s->stencil_fail;break;case 0xb95:v=s->stencil_zfail;break;case 0xb96:v=s->stencil_zpass;break;default:return 0;
    }*out=(int32_t)v;return 1;
}
int ds16_enum(uint32_t name){switch(name){
    case 0xb45:case 0xb46:case 0xb74:case 0xbc1:case 0xbe1:case 0xbe0:case 0xb54:case 0xb92:case 0xb94:case 0xb95:case 0xb96:
    case 0x84e0:case 0x84e1:case 0xba0:case 0x807b:case 0x807e:case 0x8082:case 0x8089:return 1;default:return 0;
}}
static int unsigned_query(uint32_t name){return name==0xb93 || name==0xb98 || name==0x8069 || name==0x8894 || name==0x8895 || (name>=0x8896 && name<=0x889a) || name==0x8ca6;}
static void get_values(uint32_t name,void *out,unsigned kind){
    DS13Context *c=ds13_active_context();if(!c)return;if(!out){ds13_error(BAD_VALUE);return;}
    float real[16];int normalized=0;int n=ds13_real_values(name,real,&normalized);
    if(n){++c->queries;for(int i=0;i<n;++i){
        if(kind==0)((float *)out)[i]=real[i];
        else if(kind==2)((uint8_t *)out)[i]=real[i]!=0;
        else{double v=(double)real[i]*65536;((int32_t *)out)[i]=v>=INT32_MAX?INT32_MAX:v<=INT32_MIN?INT32_MIN:(int32_t)v;}
    }return;}
    int32_t integer[16];n=ds13_integer_values(name,integer);if(!n)return;
    for(int i=0;i<n;++i){
        double v=unsigned_query(name)?(double)(uint32_t)integer[i]:(double)integer[i];
        if(kind==0)((float *)out)[i]=(float)v;
        else if(kind==2)((uint8_t *)out)[i]=integer[i]!=0;
        else if(ds16_enum(name))((int32_t *)out)[i]=integer[i];
        else{v*=65536;((int32_t *)out)[i]=v>=INT32_MAX?INT32_MAX:v<=INT32_MIN?INT32_MIN:(int32_t)v;}
    }
}
static void DS13_SOFT get_float(uint32_t name,float *out){get_values(name,out,0);}
static void DS13_SOFT get_fixed(uint32_t name,int32_t *out){get_values(name,out,1);}
static void DS13_SOFT get_boolean(uint32_t name,uint8_t *out){get_values(name,out,2);}
#define B(name,fn) {name,(uint32_t)(uintptr_t)fn}
static const DSBinding bindings[]={B("glCullFace",cull_face),B("glFrontFace",front_face),B("glDepthFunc",depth_func),B("glDepthMask",depth_mask),
    B("glDepthRangef",depth_range),B("glDepthRangex",depth_range_x),B("glAlphaFunc",alpha_func),B("glAlphaFuncx",alpha_func_x),B("glBlendFunc",blend_func),B("glShadeModel",shade_model),
    B("glPolygonOffset",polygon_offset),B("glPolygonOffsetx",polygon_offset_x),B("glStencilFunc",stencil_func),B("glStencilMask",stencil_mask),B("glStencilOp",stencil_op),
    B("glGetFloatv",get_float),B("glGetFixedv",get_fixed),B("glGetBooleanv",get_boolean)};
_Static_assert(sizeof(bindings)/sizeof(bindings[0])==DS16_BINDINGS,"GL pipeline binding count");
uint32_t ds16_bindings(DSBinding *out,uint32_t capacity){if(!out || capacity<DS16_BINDINGS)return 0;memcpy(out,bindings,sizeof(bindings));return DS16_BINDINGS;}
