/* Serialized GLES OES framebuffer objects. Attachments own their stores;
 * deleting a name never invalidates another framebuffer's retained object. */
#include "ds13_gles.h"
#include "ds_runtime.h"
#include <string.h>
#include <math.h>
enum { FB=0x8d40,RB=0x8d41,TEX=0xde1,COLOR=0x8ce0,DEPTH=0x8d00,STENCIL=0x8d20,
    COMPLETE=0x8cd5,ATTACHMENT=0x8cd6,MISSING=0x8cd7,DIMENSIONS=0x8cd9,UNSUPPORTED=0x8cdd,
    RGBA4=0x8056,RGB5A1=0x8057,RGB565=0x8d62,D16=0x81a5,S8=0x8d48 };
typedef struct {uint32_t name,live,refs,format,width,height,bytes;void *pixels;} Renderbuffer;
typedef struct {uint32_t type,name;DS15Object *texture;Renderbuffer *renderbuffer;} Attachment;
typedef struct {uint32_t name,used,live;Attachment attachments[3];} Framebuffer;
struct DS26State {Framebuffer frames[DS26_OBJECTS];Renderbuffer renders[DS26_OBJECTS];uint32_t next_frame,next_render,render_binding,bytes,changes;};
void ds26_trace(const char *,uint32_t,uint32_t,uint32_t,uint32_t) __attribute__((weak));
static void trace(const char *op,uint32_t a,uint32_t b,uint32_t c,uint32_t d){if(ds26_trace)ds26_trace(op,a,b,c,d);}
static DS13Context *ctx(void){return ds13_active_context();}
static DS26State *state(DS13Context *c){
    if(!c->fbo){c->fbo=ds_rt_calloc(1,sizeof(*c->fbo));if(!c->fbo)ds13_error(0x505);}return c->fbo;
}
static Framebuffer *frame(DS13Context *c,uint32_t name){if(c->fbo && name)for(unsigned i=0;i<DS26_OBJECTS;++i)if(c->fbo->frames[i].used && c->fbo->frames[i].name==name)return &c->fbo->frames[i];return NULL;}
static Renderbuffer *render(DS13Context *c,uint32_t name){if(c->fbo && name)for(unsigned i=0;i<DS26_OBJECTS;++i)if(c->fbo->renders[i].refs && c->fbo->renders[i].name==name && c->fbo->renders[i].live<2)return &c->fbo->renders[i];return NULL;}
static void drop(DS13Context *c,Attachment *a){
    if(a->type==TEX)ds15_release(&c->texture,a->texture);
    if(a->type==RB && !--a->renderbuffer->refs){Renderbuffer *r=a->renderbuffer;c->fbo->bytes-=r->bytes;ds_rt_free(r->pixels);memset(r,0,sizeof(*r));}
    memset(a,0,sizeof(*a));
}
void ds26_close(DS13Context *c){
    if(!c->fbo)return;
    for(unsigned i=0;i<DS26_OBJECTS;++i)for(unsigned j=0;j<3;++j)drop(c,&c->fbo->frames[i].attachments[j]);
    for(unsigned i=0;i<DS26_OBJECTS;++i)if(c->fbo->renders[i].refs)ds_rt_free(c->fbo->renders[i].pixels);
    ds_rt_free(c->fbo);c->fbo=NULL;c->framebuffer_binding=0;
}
static int slot(uint32_t attachment){return attachment==COLOR?0:attachment==DEPTH?1:attachment==STENCIL?2:-1;}
static int description(Attachment *a,uint32_t *w,uint32_t *h,uint32_t *format,void **pixels){
    if(a->type==TEX){DS15Level *l=&a->texture->levels[0];if(!l->defined)return 0;*w=l->width;*h=l->height;*format=l->format;*pixels=l->rgba;}
    else if(a->type==RB){Renderbuffer *r=a->renderbuffer;*w=r->width;*h=r->height;*format=r->format;*pixels=r->pixels;}
    else return 0;
    return *w && *h && (*pixels || (a->type==TEX && a->texture->levels[0].backing));
}
static uint32_t status(DS13Context *c){
    if(!c->framebuffer_binding)return COMPLETE;
    Framebuffer *f=frame(c,c->framebuffer_binding);if(!f)return MISSING;
    uint32_t width=0,height=0;unsigned count=0;
    for(unsigned i=0;i<3;++i)if(f->attachments[i].type){
        uint32_t w,h,format;void *p;if(!description(&f->attachments[i],&w,&h,&format,&p))return ATTACHMENT;
        int legal=i==0?(format==0x1907 || format==0x1908 || format==RGBA4 || format==RGB5A1 || format==RGB565):i==1?format==D16:format==S8;
        if(!legal)return ATTACHMENT;
        if(count && (w!=width || h!=height))return DIMENSIONS;
        width=w;height=h;++count;
    }return count?COMPLETE:MISSING;
}
int ds26_surface(DS13Context *c,DS26Surface *out){
    memset(out,0,sizeof(*out));
    if(!c->framebuffer_binding){*out=(DS26Surface){c->width,c->height,c->layout,0,c->pixels,NULL,NULL};return 0;}
    if(status(c)!=COMPLETE){ds13_error(0x506);return -1;}
    Framebuffer *f=frame(c,c->framebuffer_binding);out->layout=3;
    for(unsigned i=0;i<3;++i)if(f->attachments[i].type){
        if(f->attachments[i].type==TEX && ds15_resident(&c->texture,f->attachments[i].texture,0))return -1;
        uint32_t format;void *pixels;description(&f->attachments[i],&out->width,&out->height,&format,&pixels);
        if(!i){out->pixels=pixels;out->format=format;}else if(i==1)out->depth=pixels;else out->stencil=pixels;
    }return 0;
}
static void bits(uint32_t format,int32_t out[6]){
    memset(out,0,24);
    if(format==0x1907 || format==0x1908){out[0]=out[1]=out[2]=8;out[3]=format==0x1908?8:0;}
    if(format==RGBA4)out[0]=out[1]=out[2]=out[3]=4;
    if(format==RGB5A1){out[0]=out[1]=out[2]=5;out[3]=1;}
    if(format==RGB565){out[0]=out[2]=5;out[1]=6;}
    if(format==D16)out[4]=16;
    if(format==S8)out[5]=8;
}
int ds26_integer(DS13Context *c,uint32_t name,int32_t *out){
    if(name==0x8b9a || name==0x8b9b){*out=name==0x8b9a?0x1401:0x1908;return 1;}
    if(name==0x84e8){*out=1024;return 1;}
    if(name==0x8ca7){*out=c->fbo?(int32_t)c->fbo->render_binding:0;return 1;}
    if(c->framebuffer_binding && name>=0xd52 && name<=0xd57){
        Framebuffer *f=frame(c,c->framebuffer_binding);int32_t values[6]={0};
        if(f){unsigned i=name==0xd56?1:name==0xd57?2:0;uint32_t w,h,format;void *p;if(description(&f->attachments[i],&w,&h,&format,&p))bits(format,values);}
        *out=values[name-0xd52];return 1;
    }return 0;
}
static void DS13_SOFT gen_frames(int32_t n,uint32_t *names){
    DS13Context *c=ctx();if(!c)return;if(n<0 || (n && !names)){ds13_error(0x501);return;}if(!n)return;
    DS26State *s=state(c);if(!s)return;unsigned available=0;for(unsigned i=0;i<DS26_OBJECTS;++i)available+=!s->frames[i].used;
    if((uint32_t)n>available){ds13_error(0x505);return;}
    for(int32_t k=0;k<n;++k){while(!++s->next_frame || frame(c,s->next_frame)){}for(unsigned i=0;i<DS26_OBJECTS;++i)if(!s->frames[i].used){s->frames[i]=(Framebuffer){s->next_frame,1,0,{{0}}};names[k]=s->next_frame;break;}}
}
static void DS13_SOFT bind_frame(uint32_t target,uint32_t name){
    DS13Context *c=ctx();if(!c)return;if(target!=FB){ds13_error(0x500);return;}
    if(name){DS26State *s=state(c);if(!s)return;Framebuffer *f=frame(c,name);
        if(!f)for(unsigned i=0;i<DS26_OBJECTS;++i)if(!s->frames[i].used){f=&s->frames[i];*f=(Framebuffer){name,1,0,{{0}}};break;}
        if(!f){ds13_error(0x505);return;}f->live=1;
    }
    c->framebuffer_binding=name;if(c->fbo)++c->fbo->changes;
    trace("bind",name,status(c),0,0);
}
static uint8_t DS13_SOFT is_frame(uint32_t name){DS13Context *c=ctx();Framebuffer *f=c?frame(c,name):NULL;return f && f->live;}
static void DS13_SOFT delete_frames(int32_t n,const uint32_t *names){
    DS13Context *c=ctx();if(!c)return;if(n<0 || (n && !names)){ds13_error(0x501);return;}
    for(int32_t k=0;k<n;++k){Framebuffer *f=frame(c,names[k]);if(!f)continue;if(c->framebuffer_binding==f->name)c->framebuffer_binding=0;
        for(unsigned i=0;i<3;++i)drop(c,&f->attachments[i]);
        memset(f,0,sizeof(*f));}
}
static uint32_t DS13_SOFT check(uint32_t target){if(!ctx())return 0;if(target!=FB){ds13_error(0x500);return 0;}return status(ctx());}
static void DS13_SOFT gen_renders(int32_t n,uint32_t *names){
    DS13Context *c=ctx();if(!c)return;if(n<0 || (n && !names)){ds13_error(0x501);return;}if(!n)return;
    DS26State *s=state(c);if(!s)return;unsigned available=0;for(unsigned i=0;i<DS26_OBJECTS;++i)available+=!s->renders[i].refs;
    if((uint32_t)n>available){ds13_error(0x505);return;}
    for(int32_t k=0;k<n;++k){while(!++s->next_render || render(c,s->next_render)){}for(unsigned i=0;i<DS26_OBJECTS;++i)if(!s->renders[i].refs){s->renders[i]=(Renderbuffer){.name=s->next_render,.refs=1};names[k]=s->next_render;break;}}
}
static void DS13_SOFT bind_render(uint32_t target,uint32_t name){
    DS13Context *c=ctx();if(!c)return;if(target!=RB){ds13_error(0x500);return;}
    DS26State *s=state(c);if(!s)return;
    if(name){Renderbuffer *r=render(c,name);if(!r)for(unsigned i=0;i<DS26_OBJECTS;++i)if(!s->renders[i].refs){r=&s->renders[i];*r=(Renderbuffer){.name=name,.refs=1};break;}
        if(!r){ds13_error(0x505);return;}r->live=1;}
    s->render_binding=name;
}
static uint8_t DS13_SOFT is_render(uint32_t name){DS13Context *c=ctx();Renderbuffer *r=c?render(c,name):NULL;return r && r->live==1;}
static void DS13_SOFT delete_renders(int32_t n,const uint32_t *names){
    DS13Context *c=ctx();if(!c)return;if(n<0 || (n && !names)){ds13_error(0x501);return;}
    for(int32_t k=0;k<n;++k){Renderbuffer *r=render(c,names[k]);if(!r)continue;
        Framebuffer *f=frame(c,c->framebuffer_binding);if(f)for(unsigned i=0;i<3;++i)if(f->attachments[i].renderbuffer==r)drop(c,&f->attachments[i]);
        if(c->fbo->render_binding==r->name)c->fbo->render_binding=0;
        r->live=2;Attachment a={RB,0,NULL,r};drop(c,&a);
    }
}
static Renderbuffer *bound_render(uint32_t target){
    DS13Context *c=ctx();if(!c)return NULL;if(target!=RB){ds13_error(0x500);return NULL;}
    Renderbuffer *r=render(c,c->fbo?c->fbo->render_binding:0);if(!r){ds13_error(0x502);return NULL;}return r;
}
static void DS13_SOFT storage(uint32_t target,uint32_t format,int32_t w,int32_t h){
    Renderbuffer *r=bound_render(target);if(!r)return;
    if(w<0 || h<0 || w>1024 || h>1024){ds13_error(0x501);return;}
    if(format!=RGBA4 && format!=RGB5A1 && format!=RGB565 && format!=D16 && format!=S8){ds13_error(0x500);return;}
    uint32_t bytes=(uint32_t)w*(uint32_t)h*(format==D16?2:format==S8?1:4);DS26State *s=ctx()->fbo;
    if(s->bytes-r->bytes+bytes>4*1024*1024){ds13_error(0x505);return;}
    void *p=bytes?ds_rt_calloc(1,bytes):NULL;if(bytes && !p){ds13_error(0x505);return;}
    s->bytes=s->bytes-r->bytes+bytes;ds_rt_free(r->pixels);r->pixels=p;r->bytes=bytes;r->format=format;r->width=w;r->height=h;
    trace("storage",w,h,format,bytes);
}
static void DS13_SOFT render_parameter(uint32_t target,uint32_t name,int32_t *out){
    Renderbuffer *r=bound_render(target);if(!r)return;if(!out){ds13_error(0x501);return;}
    int32_t value,values[6];bits(r->format,values);
    if(name==0x8d42)value=r->width;else if(name==0x8d43)value=r->height;else if(name==0x8d44)value=r->format;
    else if(name>=0x8d50 && name<=0x8d55)value=values[name-0x8d50];else{ds13_error(0x500);return;}
    *out=value;
}
static Attachment *bound_attachment(uint32_t target,uint32_t attachment){
    DS13Context *c=ctx();if(!c)return NULL;if(target!=FB || slot(attachment)<0){ds13_error(0x500);return NULL;}
    Framebuffer *f=frame(c,c->framebuffer_binding);if(!f){ds13_error(0x502);return NULL;}return &f->attachments[slot(attachment)];
}
static void DS13_SOFT attach_texture(uint32_t target,uint32_t attachment,uint32_t textarget,uint32_t name,int32_t level){
    Attachment *a=bound_attachment(target,attachment);if(!a)return;
    if(textarget!=TEX){ds13_error(0x500);return;}if(level){ds13_error(0x501);return;}
    DS15Object *o=name?ds15_retain(&ctx()->texture,name):NULL;if(name && !o){ds13_error(0x502);return;}
    drop(ctx(),a);if(name)*a=(Attachment){TEX,name,o,NULL};
    trace("texture",name,attachment,status(ctx()),0);
}
static void DS13_SOFT attach_render(uint32_t target,uint32_t attachment,uint32_t rendertarget,uint32_t name){
    Attachment *a=bound_attachment(target,attachment);if(!a)return;if(rendertarget!=RB){ds13_error(0x500);return;}
    Renderbuffer *r=name?render(ctx(),name):NULL;if(name && (!r || r->live!=1)){ds13_error(0x502);return;}
    if(r)++r->refs;
    drop(ctx(),a);if(r)*a=(Attachment){RB,name,NULL,r};
    trace("renderbuffer",name,attachment,status(ctx()),0);
}
static void DS13_SOFT attachment_parameter(uint32_t target,uint32_t attachment,uint32_t name,int32_t *out){
    Attachment *a=bound_attachment(target,attachment);if(!a)return;if(!out){ds13_error(0x501);return;}
    int32_t value;if(name==0x8cd0)value=a->type==TEX?0x1702:(int32_t)a->type;
    else if(name==0x8cd1){if(!a->type){ds13_error(0x500);return;}value=a->name;}
    else if(name==0x8cd2 || name==0x8cd3){if(a->type!=TEX){ds13_error(0x500);return;}value=0;}
    else{ds13_error(0x500);return;}*out=value;
}
void ds26_texture_deleted(DS13Context *c,DS15Object *object){Framebuffer *f=frame(c,c->framebuffer_binding);if(f)for(unsigned i=0;i<3;++i)if(f->attachments[i].texture==object)drop(c,&f->attachments[i]);}
int ds26_attached(DS13Context *c,DS15Object *object){Framebuffer *f=frame(c,c->framebuffer_binding);if(f)for(unsigned i=0;i<3;++i)if(f->attachments[i].texture==object)return 1;return 0;}
void ds26_quantize(const DS26Surface *target,float rgba[4]){
    uint32_t format=target->format;
    if(format==0x1907)rgba[3]=1;
    if(format!=RGBA4 && format!=RGB5A1 && format!=RGB565)return;
    int32_t channels[6];bits(format,channels);
    for(unsigned i=0;i<4;++i){unsigned scale=(1u<<channels[i])-1;rgba[i]=scale?roundf(fmaxf(0,fminf(1,rgba[i]))*scale)/scale:1;}
}
static int compare(uint32_t function,uint32_t a,uint32_t b){switch(function){case 0x200:return 0;case 0x201:return a<b;case 0x202:return a==b;case 0x203:return a<=b;case 0x204:return a>b;case 0x205:return a!=b;case 0x206:return a>=b;default:return 1;}}
static void stencil_op(DS16State *s,uint8_t *p,uint32_t op){
    unsigned v=*p;switch(op){case 0:v=0;break;case 0x1e01:v=s->stencil_ref;break;case 0x1e02:if(v<255)++v;break;case 0x1e03:if(v)--v;break;case 0x150a:v=~v;break;default:break;}
    *p=(uint8_t)((*p&~s->stencil_write_mask)|(v&s->stencil_write_mask));
}
int ds26_fragment(DS13Context *c,DS26Surface *target,uint32_t x,uint32_t y,float depth){
    DS16State *s=&c->pipeline;uint32_t i=y*target->width+x;uint8_t *stencil=target->stencil?target->stencil+i:NULL;
    if(stencil && s->stencil && !compare(s->stencil_func,s->stencil_ref&s->stencil_value_mask,*stencil&s->stencil_value_mask)){stencil_op(s,stencil,s->stencil_fail);return 0;}
    uint32_t z=(uint32_t)lrintf(fmaxf(0,fminf(1,depth))*65535);
    int pass=!target->depth || !s->depth || compare(s->depth_func,z,target->depth[i]);
    if(stencil && s->stencil)stencil_op(s,stencil,pass?s->stencil_zpass:s->stencil_zfail);
    if(pass && target->depth && s->depth && s->depth_mask)target->depth[i]=(uint16_t)z;
    return pass;
}
void ds26_stats(DS13Context *c,uint32_t out[4]){memset(out,0,16);if(c->fbo){for(unsigned i=0;i<DS26_OBJECTS;++i){out[0]+=c->fbo->frames[i].used;out[1]+=c->fbo->renders[i].refs!=0;}out[2]=c->fbo->bytes;out[3]=c->fbo->changes;}}
static void DS13_SOFT read_pixels(int32_t x,int32_t y,int32_t w,int32_t h,uint32_t format,uint32_t type,void *pixels){
    DS13Context *c=ctx();if(!c)return;
    if(w<0 || h<0){ds13_error(0x501);return;}
    uint32_t bytes=type==0x1401?(format==0x1908?4:format==0x1907?3:0):
        ((type==0x8363 && format==0x1907) || ((type==0x8033 || type==0x8034) && format==0x1908))?2:0;
    if(!bytes){ds13_error(0x500);return;}
    DS26Surface surface;if(ds26_surface(c,&surface))return;
    uint64_t row=(uint64_t)(uint32_t)w*bytes,pitch=(row+c->texture.pack-1)&~(uint64_t)(c->texture.pack-1);
    uint64_t size=h?(uint64_t)(uint32_t)(h-1)*pitch+row:0;
    if((w && h && !pixels) || size>UINT32_MAX || (uint64_t)(uintptr_t)pixels+size>UINT32_MAX+1ull){ds13_error(0x501);return;}
    if(!surface.pixels){ds13_error(0x502);return;}
    if(!w || !h)return;
    trace("read",w,h,format,type);
    for(int32_t j=0;j<h;++j)for(int32_t i=0;i<w;++i){
        int64_t sx=(int64_t)x+i,sy=(int64_t)y+j;uint8_t rgba[4]={0,0,0,0};
        if(sx>=0 && sy>=0 && sx<surface.width && sy<surface.height){
            uint32_t index=(uint32_t)(surface.layout==0 || surface.layout==3?sy*surface.width+sx:sx*surface.height+sy);
            const uint8_t *p=surface.pixels+index*(surface.layout==3?4:surface.layout==2?2:3);
            if(surface.layout==2){unsigned v=p[0]|(unsigned)p[1]<<8;rgba[0]=(uint8_t)((((v>>11)&31)*255+15)/31);rgba[1]=(uint8_t)((((v>>5)&63)*255+31)/63);rgba[2]=(uint8_t)(((v&31)*255+15)/31);rgba[3]=255;}
            else if(surface.layout==3)memcpy(rgba,p,4);
            else{for(unsigned k=0;k<3;++k)rgba[k]=p[surface.layout==0?k:2-k];rgba[3]=255;}
        }
        uint8_t *p=(uint8_t *)pixels+(uint32_t)((uint64_t)(uint32_t)j*pitch)+(uint32_t)i*bytes;
        if(type==0x1401)memcpy(p,rgba,bytes);
        else{uint16_t value=type==0x8363?(uint16_t)((rgba[0]>>3)<<11|(rgba[1]>>2)<<5|(rgba[2]>>3)):
            type==0x8033?(uint16_t)((rgba[0]>>4)<<12|(rgba[1]>>4)<<8|(rgba[2]>>4)<<4|(rgba[3]>>4)):
            (uint16_t)((rgba[0]>>3)<<11|(rgba[1]>>3)<<6|(rgba[2]>>3)<<1|(rgba[3]>>7));memcpy(p,&value,2);}
    }
}
#define B(name,fn) {name,(uint32_t)(uintptr_t)fn}
uint32_t ds26_bindings(DSBinding *out,uint32_t capacity){
    const DSBinding bindings[]={B("glGenFramebuffersOES",gen_frames),B("glBindFramebufferOES",bind_frame),B("glIsFramebufferOES",is_frame),B("glDeleteFramebuffersOES",delete_frames),
        B("glCheckFramebufferStatusOES",check),B("glFramebufferTexture2DOES",attach_texture),B("glFramebufferRenderbufferOES",attach_render),B("glGetFramebufferAttachmentParameterivOES",attachment_parameter),
        B("glGenRenderbuffersOES",gen_renders),B("glBindRenderbufferOES",bind_render),B("glIsRenderbufferOES",is_render),B("glDeleteRenderbuffersOES",delete_renders),B("glRenderbufferStorageOES",storage),B("glGetRenderbufferParameterivOES",render_parameter),B("glReadPixels",read_pixels)};
    if(!out || capacity<DS26_BINDINGS)return 0;
    memcpy(out,bindings,sizeof(bindings));return DS26_BINDINGS;
}
