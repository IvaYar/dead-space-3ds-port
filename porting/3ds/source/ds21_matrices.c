#include "ds13_gles.h"
#include "ds_runtime.h"
#include <math.h>
#include <string.h>
static void identity(float m[16]){memset(m,0,64);for(unsigned i=0;i<4;++i)m[i*5]=1;}
static unsigned slot(DS13Context *c,uint32_t mode,uint32_t unit){(void)c;return mode==0x1700?0:mode==0x1701?1:2+unit;}
static DS21State *storage(DS13Context *c){
    if(!c->matrix){DS21State *s=ds_rt_calloc(1,sizeof(*s));if(!s){ds13_error(0x505);return NULL;}for(unsigned i=0;i<4;++i)identity(s->stack[i][0]);c->matrix=s;}return c->matrix;
}
static float *selected(DS13Context *c){DS21State *s=storage(c);unsigned i=slot(c,c->matrix_mode,c->active_texture-0x84c0);return s?s->stack[i][s->top[i]]:NULL;}
static void matrix(DS13Context *c,unsigned i,float out[16]){if(c->matrix)memcpy(out,c->matrix->stack[i][c->matrix->top[i]],64);else identity(out);}
static void multiply(float out[16],const float a[16],const float b[16]){
    float result[16];for(unsigned col=0;col<4;++col)for(unsigned row=0;row<4;++row){double v=0;for(unsigned k=0;k<4;++k)v+=(double)a[k*4+row]*b[col*4+k];result[col*4+row]=(float)v;}memcpy(out,result,64);
}
static int finite_matrix(const float m[16]){if(!m)return 0;for(unsigned i=0;i<16;++i)if(!isfinite(m[i]))return 0;return 1;}
static void DS13_SOFT load_identity(void){DS13Context *c=ds13_active_context();if(!c)return;float *m=selected(c);if(m)identity(m);}
static void DS13_SOFT load_matrix(const float *in){DS13Context *c=ds13_active_context();if(!c)return;if(!finite_matrix(in)){ds13_error(0x501);return;}float *m=selected(c);if(m)memcpy(m,in,64);}
static void DS13_SOFT mult_matrix(const float *in){DS13Context *c=ds13_active_context();if(!c)return;if(!finite_matrix(in)){ds13_error(0x501);return;}float *m=selected(c);if(m)multiply(m,m,in);}
static void DS13_SOFT load_matrix_x(const int32_t *in){if(!in){ds13_error(0x501);return;}float m[16];for(unsigned i=0;i<16;++i)m[i]=in[i]/65536.0f;load_matrix(m);}
static void DS13_SOFT mult_matrix_x(const int32_t *in){if(!in){ds13_error(0x501);return;}float m[16];for(unsigned i=0;i<16;++i)m[i]=in[i]/65536.0f;mult_matrix(m);}
static void DS13_SOFT push(void){
    DS13Context *c=ds13_active_context();if(!c)return;DS21State *s=storage(c);if(!s)return;
    unsigned i=slot(c,c->matrix_mode,c->active_texture-0x84c0),limit=i?2:16;
    if(s->top[i]+1==limit){ds13_error(0x503);return;}memcpy(s->stack[i][s->top[i]+1],s->stack[i][s->top[i]],64);++s->top[i];
}
static void DS13_SOFT pop(void){DS13Context *c=ds13_active_context();if(!c)return;unsigned i=slot(c,c->matrix_mode,c->active_texture-0x84c0);if(!c->matrix || !c->matrix->top[i]){ds13_error(0x504);return;}--c->matrix->top[i];}
static void DS13_SOFT translate(float x,float y,float z){float m[16];identity(m);m[12]=x;m[13]=y;m[14]=z;mult_matrix(m);}
static void DS13_SOFT scale(float x,float y,float z){float m[16];identity(m);m[0]=x;m[5]=y;m[10]=z;mult_matrix(m);}
static void DS13_SOFT rotate(float angle,float x,float y,float z){
    if(!isfinite(angle)||!isfinite(x)||!isfinite(y)||!isfinite(z)){ds13_error(0x501);return;}
    double length=sqrt((double)x*x+(double)y*y+(double)z*z);if(!length)return;
    x=(float)(x/length);y=(float)(y/length);z=(float)(z/length);double a=angle*0.01745329251994329577,c=cos(a),s=sin(a),t=1-c;
    float m[16];identity(m);
    m[0]=(float)(x*x*t+c);m[4]=(float)(x*y*t-z*s);m[8]=(float)(x*z*t+y*s);
    m[1]=(float)(y*x*t+z*s);m[5]=(float)(y*y*t+c);m[9]=(float)(y*z*t-x*s);
    m[2]=(float)(z*x*t-y*s);m[6]=(float)(z*y*t+x*s);m[10]=(float)(z*z*t+c);mult_matrix(m);
}
static void DS13_SOFT ortho(float l,float r,float b,float t,float n,float f){
    if(!isfinite(l)||!isfinite(r)||!isfinite(b)||!isfinite(t)||!isfinite(n)||!isfinite(f)||l==r||b==t||n==f){ds13_error(0x501);return;}
    float m[16];identity(m);m[0]=2/(r-l);m[5]=2/(t-b);m[10]=-2/(f-n);m[12]=-(r+l)/(r-l);m[13]=-(t+b)/(t-b);m[14]=-(f+n)/(f-n);mult_matrix(m);
}
static void DS13_SOFT frustum(float l,float r,float b,float t,float n,float f){
    if(!isfinite(l)||!isfinite(r)||!isfinite(b)||!isfinite(t)||!isfinite(n)||!isfinite(f)||l==r||b==t||n==f||n<=0||f<=0){ds13_error(0x501);return;}
    float m[16]={0};m[0]=2*n/(r-l);m[5]=2*n/(t-b);m[8]=(r+l)/(r-l);m[9]=(t+b)/(t-b);m[10]=-(f+n)/(f-n);m[11]=-1;m[14]=-2*f*n/(f-n);mult_matrix(m);
}
static void DS13_SOFT translate_x(int32_t x,int32_t y,int32_t z){translate(x/65536.0f,y/65536.0f,z/65536.0f);}
static void DS13_SOFT scale_x(int32_t x,int32_t y,int32_t z){scale(x/65536.0f,y/65536.0f,z/65536.0f);}
static void DS13_SOFT rotate_x(int32_t a,int32_t x,int32_t y,int32_t z){rotate(a/65536.0f,x/65536.0f,y/65536.0f,z/65536.0f);}
static void DS13_SOFT ortho_x(int32_t l,int32_t r,int32_t b,int32_t t,int32_t n,int32_t f){ortho(l/65536.0f,r/65536.0f,b/65536.0f,t/65536.0f,n/65536.0f,f/65536.0f);}
static void DS13_SOFT frustum_x(int32_t l,int32_t r,int32_t b,int32_t t,int32_t n,int32_t f){frustum(l/65536.0f,r/65536.0f,b/65536.0f,t/65536.0f,n/65536.0f,f/65536.0f);}
void ds21_close(DS13Context *c){ds_rt_free(c->matrix);c->matrix=NULL;}
int ds21_real(DS13Context *c,uint32_t name,float out[16]){
    unsigned i;if(name==0xba6)i=0;else if(name==0xba7)i=1;else if(name==0xba8)i=2+c->active_texture-0x84c0;else return 0;matrix(c,i,out);return 16;
}
int ds21_integer(DS13Context *c,uint32_t name,int32_t *out){
    unsigned i;if(name==0xba3)i=0;else if(name==0xba4)i=1;else if(name==0xba5)i=2+c->active_texture-0x84c0;
    else if(name==0xd36){*out=16;return 1;}else if(name==0xd38||name==0xd39){*out=2;return 1;}else return 0;
    *out=1+(int32_t)(c->matrix?c->matrix->top[i]:0);return 1;
}
void ds21_transform(DS13Context *c,uint32_t mode,uint32_t unit,const float in[4],float out[4]){
    float m[16],v[4];matrix(c,slot(c,mode,unit),m);for(unsigned i=0;i<4;++i){v[i]=0;for(unsigned j=0;j<4;++j)v[i]+=m[j*4+i]*in[j];}memcpy(out,v,16);
}
#define B(name,fn) {name,(uint32_t)(uintptr_t)fn}
uint32_t ds21_bindings(DSBinding *out,uint32_t capacity){
    const DSBinding b[]={B("glLoadIdentity",load_identity),B("glLoadMatrixf",load_matrix),B("glLoadMatrixx",load_matrix_x),B("glMultMatrixf",mult_matrix),B("glMultMatrixx",mult_matrix_x),B("glPushMatrix",push),B("glPopMatrix",pop),B("glTranslatef",translate),B("glTranslatex",translate_x),B("glScalef",scale),B("glScalex",scale_x),B("glRotatef",rotate),B("glRotatex",rotate_x),B("glOrthof",ortho),B("glOrthox",ortho_x),B("glFrustumf",frustum),B("glFrustumx",frustum_x)};
    if(capacity<DS21_BINDINGS)return 0;
    memcpy(out,b,sizeof(b));return DS21_BINDINGS;
}
