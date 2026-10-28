/* GLES1.1 section 2.12: eight lights, one front/back material, infinite viewer.
 * Only an explicitly attached context gains lighting entry points and draws. */
#include "ds13_gles.h"
#include "ds_runtime.h"
#include <limits.h>
#include <math.h>
#include <string.h>
static float clamp(float v){return v<0?0:v>1?1:v;}
static DS13Context *context(void){DS13Context *c=ds13_active_context();return c&&c->lighting_state?c:NULL;}
int ds32_attach(DS13Context *c){
    if(!c || c!=ds13_active_context() || c->lighting_state)return -1;
    DS32Lighting *s=ds_rt_calloc(1,sizeof(*s));if(!s)return -1;
    for(unsigned i=0;i<4;++i){s->ambient[i]=s->scene[i]=i==3?1:.2f;s->diffuse[i]=i==3?1:.8f;s->specular[i]=s->emission[i]=i==3?1:0;}
    s->normal[2]=1;
    for(unsigned l=0;l<8;++l){DS32Light *v=&s->light[l];v->ambient[3]=v->diffuse[3]=v->specular[3]=1;
        if(!l)for(unsigned i=0;i<3;++i)v->diffuse[i]=v->specular[i]=1;
        v->position[2]=1;v->direction[2]=-1;v->cutoff=180;v->attenuation[0]=1;}
    c->lighting_state=s;
    if(c->pipeline.color_material){float white[4]={1,1,1,1};ds32_track(c,c->draw?c->draw->color:white);}return 0;
}
void ds32_close(DS13Context *c){ds_rt_free(c->lighting_state);c->lighting_state=NULL;}
void ds32_track(DS13Context *c,const float color[4]){
    if(c->lighting_state && c->pipeline.color_material){memcpy(c->lighting_state->ambient,color,16);memcpy(c->lighting_state->diffuse,color,16);}
}
static int finite(const float *p,unsigned n){if(!p)return 0;for(unsigned i=0;i<n;++i)if(!isfinite(p[i]))return 0;return 1;}
static float *material(DS32Lighting *s,uint32_t name,unsigned *n){*n=4;switch(name){
    case 0x1200:return s->ambient;case 0x1201:return s->diffuse;case 0x1202:return s->specular;case 0x1600:return s->emission;
    case 0x1601:*n=1;return &s->shininess;case 0x1602:return s->ambient;default:*n=0;return NULL;}}
static float *light(DS32Light *s,uint32_t name,unsigned *n){*n=4;switch(name){
    case 0x1200:return s->ambient;case 0x1201:return s->diffuse;case 0x1202:return s->specular;case 0x1203:return s->position;
    case 0x1204:*n=3;return s->direction;case 0x1205:*n=1;return &s->exponent;case 0x1206:*n=1;return &s->cutoff;
    case 0x1207:case 0x1208:case 0x1209:*n=1;return &s->attenuation[name-0x1207];default:*n=0;return NULL;}}
static void set_material(uint32_t face,uint32_t name,const float *v,int vector){
    DS13Context *c=context();if(!c)return;unsigned n;float *p=material(c->lighting_state,name,&n);
    if(face!=0x408 || !n || (!vector&&n!=1)){ds13_error(0x500);return;}
    if(!finite(v,n) || (name==0x1601&&(v[0]<0||v[0]>128))){ds13_error(0x501);return;}
    memcpy(p,v,n*4);if(name==0x1602)memcpy(c->lighting_state->diffuse,v,16);
    float white[4]={1,1,1,1};ds32_track(c,c->draw?c->draw->color:white);++c->lighting_state->setters;
}
static void set_light(uint32_t id,uint32_t name,const float *v,int vector){
    DS13Context *c=context();if(!c)return;if(id<0x4000 || id>0x4007){ds13_error(0x500);return;}
    unsigned n;float *p=light(&c->lighting_state->light[id-0x4000],name,&n);
    if(!n || (!vector&&n!=1)){ds13_error(0x500);return;}
    if(!finite(v,n) || (name==0x1205&&(v[0]<0||v[0]>128)) || (name==0x1206&&v[0]!=180&&(v[0]<0||v[0]>90)) || (name>=0x1207&&name<=0x1209&&v[0]<0)){ds13_error(0x501);return;}
    float transformed[4];
    if(name==0x1203 || name==0x1204){float in[4]={v[0],v[1],v[2],name==0x1203?v[3]:0};ds21_transform(c,0x1700,0,in,transformed);
        if(!finite(transformed,n)){ds13_error(0x501);return;}v=transformed;}
    memcpy(p,v,n*4);++c->lighting_state->setters;
}
static void set_model(uint32_t name,const float *v,int vector){
    DS13Context *c=context();if(!c)return;unsigned n=name==0xb53?4:name==0xb52?1:0;
    if(!n || (!vector&&n!=1)){ds13_error(0x500);return;}if(!finite(v,n)){ds13_error(0x501);return;}
    if(name==0xb53)memcpy(c->lighting_state->scene,v,16);else c->lighting_state->two_side=v[0]!=0;++c->lighting_state->setters;
}
static void DS13_SOFT normal_f(float x,float y,float z){DS13Context *c=context();if(!c)return;float n[3]={x,y,z};if(!finite(n,3)){ds13_error(0x501);return;}memcpy(c->lighting_state->normal,n,12);}
static void DS13_SOFT normal_x(int32_t x,int32_t y,int32_t z){normal_f(x/65536.0f,y/65536.0f,z/65536.0f);}
static void DS13_SOFT material_f(uint32_t f,uint32_t n,float v){set_material(f,n,&v,0);}
static void DS13_SOFT material_x(uint32_t f,uint32_t n,int32_t v){material_f(f,n,v/65536.0f);}
static void DS13_SOFT material_fv(uint32_t f,uint32_t n,const float *v){set_material(f,n,v,1);}
static void DS13_SOFT material_xv(uint32_t f,uint32_t n,const int32_t *v){DS13Context *c=context();if(!c)return;unsigned count;material(c->lighting_state,n,&count);if(!v){ds13_error(0x501);return;}float p[4];for(unsigned i=0;i<count;++i)p[i]=v[i]/65536.0f;set_material(f,n,p,1);}
static void DS13_SOFT light_f(uint32_t l,uint32_t n,float v){set_light(l,n,&v,0);}
static void DS13_SOFT light_x(uint32_t l,uint32_t n,int32_t v){light_f(l,n,v/65536.0f);}
static void DS13_SOFT light_fv(uint32_t l,uint32_t n,const float *v){set_light(l,n,v,1);}
static void DS13_SOFT light_xv(uint32_t l,uint32_t n,const int32_t *v){DS13Context *c=context();if(!c)return;unsigned count;DS32Light temp;light(&temp,n,&count);if(!v){ds13_error(0x501);return;}float p[4];for(unsigned i=0;i<count;++i)p[i]=v[i]/65536.0f;set_light(l,n,p,1);}
static void DS13_SOFT model_f(uint32_t n,float v){set_model(n,&v,0);}
static void DS13_SOFT model_x(uint32_t n,int32_t v){model_f(n,v/65536.0f);}
static void DS13_SOFT model_fv(uint32_t n,const float *v){set_model(n,v,1);}
static void DS13_SOFT model_xv(uint32_t n,const int32_t *v){if(!v){ds13_error(0x501);return;}float p[4];unsigned count=n==0xb53?4:1;for(unsigned i=0;i<count;++i)p[i]=v[i]/65536.0f;set_model(n,p,1);}
static void query(uint32_t id,uint32_t name,void *out,int fixed,int is_light){
    DS13Context *c=context();if(!c)return;unsigned n;float *p;
    if(is_light){if(id<0x4000||id>0x4007){ds13_error(0x500);return;}p=light(&c->lighting_state->light[id-0x4000],name,&n);}
    else{if((id!=0x404&&id!=0x405)||name==0x1602){ds13_error(0x500);return;}p=material(c->lighting_state,name,&n);}
    if(!n){ds13_error(0x500);return;}if(!out){ds13_error(0x501);return;}
    if(!fixed){memcpy(out,p,n*4);return;}
    for(unsigned i=0;i<n;++i){double v=(double)p[i]*65536;((int32_t *)out)[i]=v>=INT32_MAX?INT32_MAX:v<=INT32_MIN?INT32_MIN:(int32_t)v;}
}
static void DS13_SOFT get_light_f(uint32_t l,uint32_t n,float *v){query(l,n,v,0,1);}
static void DS13_SOFT get_light_x(uint32_t l,uint32_t n,int32_t *v){query(l,n,v,1,1);}
static void DS13_SOFT get_material_f(uint32_t l,uint32_t n,float *v){query(l,n,v,0,0);}
static void DS13_SOFT get_material_x(uint32_t l,uint32_t n,int32_t *v){query(l,n,v,1,0);}
int ds32_real(DS13Context *c,uint32_t name,float out[16],int *normalized){
    if(!c->lighting_state)return 0;
    if(name==0xb53){memcpy(out,c->lighting_state->scene,16);*normalized=1;return 4;}
    if(name==0xb02){memcpy(out,c->lighting_state->normal,12);*normalized=1;return 3;}return 0;
}
int ds32_integer(DS13Context *c,uint32_t name,int32_t *out){if(!c->lighting_state)return 0;if(name==0xb52){*out=c->lighting_state->two_side;return 1;}if(name==0xd31){*out=8;return 1;}return 0;}
int ds32_prepare(DS13Context *c){
    float m[16];ds21_real(c,0xba6,m);double a[4][8];
    for(unsigned r=0;r<4;++r)for(unsigned k=0;k<8;++k)a[r][k]=k<4?m[k*4+r]:(k-4==r);
    for(unsigned col=0;col<4;++col){unsigned pivot=col;for(unsigned r=col+1;r<4;++r)if(fabs(a[r][col])>fabs(a[pivot][col]))pivot=r;
        if(!isfinite(a[pivot][col]) || a[pivot][col]==0)return -1;
        if(pivot!=col)for(unsigned k=0;k<8;++k){double t=a[col][k];a[col][k]=a[pivot][k];a[pivot][k]=t;}
        double d=a[col][col];for(unsigned k=0;k<8;++k)a[col][k]/=d;
        for(unsigned r=0;r<4;++r)if(r!=col){double f=a[r][col];for(unsigned k=0;k<8;++k)a[r][k]-=f*a[col][k];}
    }
    DS32Lighting *s=c->lighting_state;for(unsigned r=0;r<3;++r)for(unsigned k=0;k<3;++k){s->normal_matrix[r*3+k]=(float)a[k][r+4];if(!isfinite(s->normal_matrix[r*3+k]))return -1;}
    double length=sqrt(a[2][4]*a[2][4]+a[2][5]*a[2][5]+a[2][6]*a[2][6]);s->rescale=length>0?(float)(1/length):1;return isfinite(s->rescale)?0:-1;
}
static float length3(const float *v){return (float)sqrt((double)v[0]*v[0]+(double)v[1]*v[1]+(double)v[2]*v[2]);}
static float dot(const float *a,const float *b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
static int unit(float *v){float length=length3(v);if(!length || !isfinite(length)){v[0]=v[1]=v[2]=0;return 0;}for(unsigned i=0;i<3;++i)v[i]/=length;return 1;}
static void illuminate(DS13Context *c,const float eye[4],const float normal[3],float out[4]){
    DS32Lighting *s=c->lighting_state;float rgb[3];for(unsigned k=0;k<3;++k)rgb[k]=s->emission[k]+s->ambient[k]*s->scene[k];
    for(unsigned l=0;l<8;++l)if(c->pipeline.lights[l]){DS32Light *v=&s->light[l];float direction[3];
        for(unsigned k=0;k<3;++k)direction[k]=v->position[3]?v->position[k]/v->position[3]-eye[k]/eye[3]:v->position[k];
        float distance=length3(direction);unit(direction);float attenuation=1;
        if(v->position[3]){double d=v->attenuation[0]+(double)v->attenuation[1]*distance+(double)v->attenuation[2]*distance*distance;attenuation=d>0?(float)(1/d):1;}
        if(v->cutoff!=180){float spot[3]={v->direction[0],v->direction[1],v->direction[2]};unit(spot);float cosine=-dot(direction,spot);
            attenuation*=cosine<cosf(v->cutoff*.01745329251994329577f)?0:powf(fmaxf(cosine,0),v->exponent);}
        float diffuse=fmaxf(dot(normal,direction),0),half[3]={direction[0],direction[1],direction[2]+1};int h=unit(half);
        float specular=diffuse>0&&h?powf(fmaxf(dot(normal,half),0),s->shininess):0;
        for(unsigned k=0;k<3;++k)rgb[k]+=attenuation*(s->ambient[k]*v->ambient[k]+diffuse*s->diffuse[k]*v->diffuse[k]+specular*s->specular[k]*v->specular[k]);
    }
    for(unsigned k=0;k<3;++k)out[k]=clamp(rgb[k]);
    out[3]=clamp(s->diffuse[3]);
}
int ds32_vertex(DS13Context *c,const float eye[4],const float normal[3],const float primary[4],float front[4],float back[4]){
    DS32Lighting *s=c->lighting_state;if(!finite(eye,4)||!eye[3])return -1;ds32_track(c,primary);float n[3];
    for(unsigned r=0;r<3;++r){n[r]=0;for(unsigned k=0;k<3;++k)n[r]+=s->normal_matrix[r*3+k]*normal[k];if(c->pipeline.rescale)n[r]*=s->rescale;}
    if(!finite(n,3))return -1;
    if(c->pipeline.normalize)unit(n);
    illuminate(c,eye,n,front);if(s->two_side){for(unsigned k=0;k<3;++k)n[k]=-n[k];illuminate(c,eye,n,back);}else memcpy(back,front,16);++s->vertices;return 0;
}
#define B(n,f) {n,(uint32_t)f}
uint32_t ds32_bindings(DSBinding *out,uint32_t capacity){
    const DSBinding b[]={B("glLightf",light_f),B("glLightx",light_x),B("glLightfv",light_fv),B("glLightxv",light_xv),
        B("glLightModelf",model_f),B("glLightModelx",model_x),B("glLightModelfv",model_fv),B("glLightModelxv",model_xv),
        B("glMaterialf",material_f),B("glMaterialx",material_x),B("glMaterialfv",material_fv),B("glMaterialxv",material_xv),
        B("glGetLightfv",get_light_f),B("glGetLightxv",get_light_x),B("glGetMaterialfv",get_material_f),B("glGetMaterialxv",get_material_x),B("glNormal3f",normal_f),B("glNormal3x",normal_x)};
    if(!out || capacity<DS32_BINDINGS)return 0;
    memcpy(out,b,sizeof(b));return DS32_BINDINGS;
}
