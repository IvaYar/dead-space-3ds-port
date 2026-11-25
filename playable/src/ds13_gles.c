#include "ds13_gles.h"
#include "ds34_gpu.h"
#include <limits.h>
#include <math.h>
#include <string.h>
#define MAGIC 0x44533133u
#define INVALID_ENUM 0x500u
#define INVALID_VALUE 0x501u
#define INVALID_OPERATION 0x502u
static DS13Context *current;
_Static_assert(sizeof(DS13Context)<4096,"CPU harness GLES context page");
static int valid(const DS13Context *c){return c && c->magic==MAGIC;}
static void error(DS13Context *c,uint32_t value){if(c && !c->error)c->error=value;}
static void unsupported(DS13Context *c,const char *op,uint32_t arg){error(c,INVALID_ENUM);if(c->observe)c->observe(op,arg);}
int ds13_init(DS13Context *c,void *pixels,uint32_t w,uint32_t h,uint32_t capacity,uint32_t layout){
    uint32_t bytes=layout==DS13_RGB565_CTR?2:3;
    if(!c || valid(c) || c==current || !pixels || !w || !h || w>1024 || h>1024 || (uint64_t)w*h*bytes>capacity || layout>DS13_RGB565_CTR)return -1;
    DS13Context next={0};next.magic=MAGIC;next.width=w;next.height=h;next.capacity=capacity;next.layout=layout;next.pixels=pixels;
    next.viewport[2]=next.scissor[2]=(int32_t)w;next.viewport[3]=next.scissor[3]=(int32_t)h;
    next.dither=1;next.active_texture=next.client_active_texture=0x84c0;next.matrix_mode=0x1700;
    ds14_init(&next.vertex);ds15_init(&next.texture);ds16_init(&next.pipeline);next.clear_depth=1;memset(next.color_mask,1,4);*c=next;return 0;
}
int ds13_current(DS13Context *c){if(c && !valid(c))return -1;current=c;return 0;}
int ds13_target(DS13Context *c,void *pixels,uint32_t capacity){
    if(!valid(c) || !pixels || (uint64_t)c->width*c->height*(c->layout==DS13_RGB565_CTR?2:3)>capacity)return -1;
    c->pixels=pixels;c->capacity=capacity;return 0;
}
void ds13_close(DS13Context *c){if(current==c)current=NULL;if(valid(c)){ds26_close(c);ds14_close(&c->vertex);ds15_close(&c->texture);ds21_close(c);ds22_close(c);ds30_close(c);ds32_close(c);ds33_close(c);}if(c)memset(c,0,sizeof(*c));}
DS13Context *ds13_active_context(void){return current;}
void ds13_error(uint32_t value){error(current,value);}
void ds13_unsupported(const char *op,uint32_t value){if(current)unsupported(current,op,value);}
uint32_t ds13_context_size(void){return sizeof(DS13Context);}
void ds13_observer(DS13Context *c,DS13Observe observe,DS13Sync sync){if(valid(c)){c->observe=observe;c->sync=sync;}}
void ds13_stats(DS13Context *c,uint32_t out[4]){out[0]=c->queries;out[1]=c->clears;out[2]=c->pixels_written;out[3]=c->flushes;}
static uint32_t DS13_SOFT get_error(void){if(!current)return INVALID_OPERATION;uint32_t e=current->error;current->error=0;return e;}
int ds13_real_values(uint32_t name,float out[16],int *normalized){
    DS13Context *c=current;if(!c)return 0;*normalized=0;
    switch(name){
        case 0xc22:memcpy(out,c->clear_color,16);*normalized=1;return 4;
        case 0xb73:*out=c->clear_depth;*normalized=1;return 1;
        case 0xb70:memcpy(out,c->pipeline.depth_range,8);*normalized=1;return 2;
        case 0xbc2:*out=c->pipeline.alpha_ref;return 1;
        case 0x8038:*out=c->pipeline.offset_factor;return 1;
        case 0x2a00:*out=c->pipeline.offset_units;return 1;
        default:{int n=ds32_real(c,name,out,normalized);if(n)return n;n=ds30_real(c,name,out,normalized);if(n)return n;n=ds21_real(c,name,out);if(n)return n;n=ds22_real(c,name,out);if(n)*normalized=1;return n;}
    }
}
int ds13_integer_values(uint32_t name,int32_t out[4]){
    DS13Context *c=current;if(!c)return 0;++c->queries;
    float real[16];int normalized=0;int count=ds13_real_values(name,real,&normalized);
    if(count){for(int i=0;i<count;++i){double v=round(normalized?(double)real[i]*INT32_MAX:(double)real[i]);out[i]=v>=INT32_MAX?INT32_MAX:v<=INT32_MIN?INT32_MIN:(int32_t)v;}return count;}
    if(ds34_integer && ds34_integer(c,name,out))return 1;
    if(ds26_integer(c,name,out))return 1;
    if(ds30_integer(c,name,out))return 1;
    if(ds32_integer(c,name,out))return 1;
    switch(name){
        case 0xba2:memcpy(out,c->viewport,16);break;
        case 0xc10:memcpy(out,c->scissor,16);break;
        case 0xd3a:out[0]=1024;out[1]=1024;break; /* Supported state range. */
        case 0xc23:for(unsigned i=0;i<4;++i)out[i]=c->color_mask[i];break;
        case 0xc11:*out=(int32_t)c->scissor_test;break;
        case 0xbd0:*out=(int32_t)c->dither;break;
        case 0x84e0:*out=(int32_t)c->active_texture;break;
        case 0x84e1:*out=(int32_t)c->client_active_texture;break;
        case 0xba0:*out=(int32_t)c->matrix_mode;break;
        case 0x8ca6:*out=(int32_t)c->framebuffer_binding;break; /* Actual borrowed default surface. */
        case 0xbe2:*out=(int32_t)c->blend;break;
        case 0xb60:*out=(int32_t)c->fog;break;
        case 0xb97:{int32_t bits=0;ds26_integer(c,0xd57,&bits);*out=bits?(int32_t)c->pipeline.stencil_ref:0;break;}
        case 0xd52:case 0xd54:*out=c->layout==DS13_RGB565_CTR?5:8;break;
        case 0xd53:*out=c->layout==DS13_RGB565_CTR?6:8;break;
        case 0xd55:case 0xd56:case 0xd57:*out=0;break; /* No alpha/depth/stencil attachments. */
        default:if(!ds14_query(&c->vertex,name,out,c->client_active_texture-0x84c0) && !ds15_query(&c->texture,name,out,c->active_texture-0x84c0) && !ds16_query(&c->pipeline,name,out) && !ds21_integer(c,name,out)){unsupported(c,"glGetIntegerv unsupported state",name);return 0;}break;
    }
    return name==0xba2 || name==0xc10 || name==0xc23?4:name==0xd3a?2:1;
}
static void DS13_SOFT get_integer(uint32_t name,int32_t *out){
    if(!current)return;
    if(!out){error(current,INVALID_VALUE);return;}
    int32_t values[16];int count=ds13_integer_values(name,values);if(count)memcpy(out,values,(uint32_t)count*4);
}
static void DS13_SOFT viewport(int32_t x,int32_t y,int32_t w,int32_t h){
    DS13Context *c=current;if(!c)return;if(w<0 || h<0){error(c,INVALID_VALUE);return;}
    c->viewport[0]=x;c->viewport[1]=y;c->viewport[2]=w>1024?1024:w;c->viewport[3]=h>1024?1024:h;
}
static void DS13_SOFT scissor(int32_t x,int32_t y,int32_t w,int32_t h){
    DS13Context *c=current;if(!c)return;if(w<0 || h<0){error(c,INVALID_VALUE);return;}
    c->scissor[0]=x;c->scissor[1]=y;c->scissor[2]=w;c->scissor[3]=h;
}
static void capability(uint32_t name,int on){
    DS13Context *c=current;if(!c)return;
    if(name==0xc11)c->scissor_test=(uint32_t)on;
    else if(name==0xbd0)c->dither=(uint32_t)on;
    else if(name==0xbe2)c->blend=(uint32_t)on;
    else if(name==0xb60)c->fog=(uint32_t)on;
    else if(name==0xde1)c->texture.enabled[c->active_texture-0x84c0]=(uint32_t)on;
    else if(ds16_capability(&c->pipeline,name,on)<0)unsupported(c,"GL capability unsupported",name);
    if(name==0xb57 && on){float white[4]={1,1,1,1};ds32_track(c,c->draw?c->draw->color:white);}
}
static void DS13_SOFT enable(uint32_t name){capability(name,1);}
static void DS13_SOFT disable(uint32_t name){capability(name,0);}
static void texture_selector(uint32_t unit,int client){
    if(!current)return;
    if(unit<0x84c0 || unit>0x84c1){error(current,INVALID_ENUM);return;}
    if(client)current->client_active_texture=unit;else current->active_texture=unit;
}
static void DS13_SOFT active_texture(uint32_t unit){texture_selector(unit,0);}
static void DS13_SOFT client_active_texture(uint32_t unit){texture_selector(unit,1);}
static uint8_t DS13_SOFT is_enabled(uint32_t name){
    DS13Context *c=current;if(!c)return 0;
    if(name==0xc11)return (uint8_t)c->scissor_test;
    if(name==0xbd0)return (uint8_t)c->dither;
    if(name==0xbe2)return (uint8_t)c->blend;
    if(name==0xb60)return (uint8_t)c->fog;
    if(name==0xde1)return (uint8_t)c->texture.enabled[c->active_texture-0x84c0];
    int pipeline_enabled=ds16_capability(&c->pipeline,name,-1);if(pipeline_enabled>=0)return (uint8_t)pipeline_enabled;
    int enabled=ds14_enabled(&c->vertex,name,c->client_active_texture-0x84c0);
    if(enabled>=0)return (uint8_t)enabled;
    unsupported(c,"glIsEnabled unsupported",name);return 0;
}
static void DS13_SOFT matrix_mode(uint32_t mode){
    if(!current)return;
    if(mode!=0x1700 && mode!=0x1701 && mode!=0x1702){error(current,INVALID_ENUM);return;}
    current->matrix_mode=mode;
}
static float clamp(float value){return value<0?0:value>1?1:value;}
static void DS13_SOFT clear_color(float r,float g,float b,float a){
    DS13Context *c=current;if(!c)return;
    if(isnan(r)||isnan(g)||isnan(b)||isnan(a)){error(c,INVALID_VALUE);return;}
    c->clear_color[0]=clamp(r);c->clear_color[1]=clamp(g);c->clear_color[2]=clamp(b);c->clear_color[3]=clamp(a);
}
static void DS13_SOFT clear_color_x(int32_t r,int32_t g,int32_t b,int32_t a){clear_color(r/65536.0f,g/65536.0f,b/65536.0f,a/65536.0f);}
static void DS13_SOFT color_mask(uint8_t r,uint8_t g,uint8_t b,uint8_t a){
    if(current){current->color_mask[0]=r!=0;current->color_mask[1]=g!=0;current->color_mask[2]=b!=0;current->color_mask[3]=a!=0;}
}
static void DS13_SOFT clear_depth(float value){if(current){if(isnan(value))error(current,INVALID_VALUE);else current->clear_depth=clamp(value);}}
static void DS13_SOFT clear_depth_x(int32_t value){clear_depth(value/65536.0f);}
static void DS13_SOFT clear_stencil(int32_t value){if(current)current->clear_stencil=value;}
static void DS13_SOFT clear(uint32_t mask){
    DS13Context *c=current;if(!c)return;
    if(mask&~(0x4000u|0x100u|0x400u)){error(c,INVALID_VALUE);return;}
    DS26Surface target;if(ds26_surface(c,&target))return;
    ++c->clears;
    if(ds34_clear && ds34_clear(c,mask))return;
    int64_t x0=0,y0=0,x1=target.width,y1=target.height;
    if(c->scissor_test){
        x0=c->scissor[0];y0=c->scissor[1];x1=x0+(int64_t)c->scissor[2];y1=y0+(int64_t)c->scissor[3];
        if(x0<0)x0=0;
        if(y0<0)y0=0;
        if(x1>target.width)x1=target.width;
        if(y1>target.height)y1=target.height;
    }
    uint8_t rgb[3];for(unsigned i=0;i<3;++i)rgb[i]=(uint8_t)(c->clear_color[i]*255.0f+0.5f);
    for(int64_t y=y0;y<y1;++y)for(int64_t x=x0;x<x1;++x){
        uint32_t index=(uint32_t)(y*target.width+x);
        if((mask&0x100) && target.depth && c->pipeline.depth_mask)target.depth[index]=(uint16_t)(c->clear_depth*65535+.5f);
        if((mask&0x400) && target.stencil)target.stencil[index]=(uint8_t)((target.stencil[index]&~c->pipeline.stencil_write_mask)|((uint32_t)c->clear_stencil&c->pipeline.stencil_write_mask));
        if(!(mask&0x4000) || !target.pixels || (!c->color_mask[0] && !c->color_mask[1] && !c->color_mask[2] && (target.layout!=3 || !c->color_mask[3])))continue;
        if(target.layout==3){
            float rgba[4];memcpy(rgba,c->clear_color,16);ds26_quantize(&target,rgba);
            for(unsigned i=0;i<4;++i)if(c->color_mask[i])target.pixels[index*4+i]=(uint8_t)(rgba[i]*255+.5f);
            ++c->pixels_written;continue;
        }
        if(c->layout==DS13_RGB565_CTR){
            uint32_t offset=(uint32_t)(x*c->height+y)*2;
            uint32_t old=c->pixels[offset]|(uint32_t)c->pixels[offset+1]<<8;
            uint32_t value=(uint32_t)(c->clear_color[0]*31.0f+0.5f)<<11 | (uint32_t)(c->clear_color[1]*63.0f+0.5f)<<5 | (uint32_t)(c->clear_color[2]*31.0f+0.5f);
            uint32_t bits=(c->color_mask[0]?0xf800:0)|(c->color_mask[1]?0x07e0:0)|(c->color_mask[2]?0x001f:0);
            value=(old&~bits)|(value&bits);c->pixels[offset]=(uint8_t)value;c->pixels[offset+1]=(uint8_t)(value>>8);++c->pixels_written;continue;
        }
        uint32_t offset=(uint32_t)(c->layout==DS13_RGB8_ROWS?(y*c->width+x)*3:(x*c->height+y)*3);
        for(unsigned channel=0;channel<3;++channel)if(c->color_mask[channel])c->pixels[offset+(c->layout==DS13_RGB8_ROWS?channel:2-channel)]=rgb[channel];
        ++c->pixels_written;
    }
    if((mask&0x4000) && c->framebuffer_binding)ds34_fbo_dirty(c);
}
static void DS13_SOFT flush(void){
    if(!current)return;
    if(current->sync && current->sync(current->pixels,current->width*current->height*(current->layout==DS13_RGB565_CTR?2:3))){
        error(current,INVALID_OPERATION);if(current->observe)current->observe("surface cache flush failed",0);return;
    }
    ++current->flushes; /* Rendering is synchronous: no queued commands. */
}
static void DS13_SOFT bind_default_framebuffer(uint32_t target,uint32_t name){
    if(!current)return;
    if(target!=0x8d40){error(current,INVALID_ENUM);return;}
    if(name){unsupported(current,"non-default framebuffer unsupported",name);return;}
    current->framebuffer_binding=0;
}
#define B(name,fn) {name,(uint32_t)(uintptr_t)fn}
static const DSBinding bindings[]={B("glGetError",get_error),B("glGetIntegerv",get_integer),B("glViewport",viewport),B("glScissor",scissor),
    B("glEnable",enable),B("glDisable",disable),B("glIsEnabled",is_enabled),B("glClearColor",clear_color),B("glClearColorx",clear_color_x),
    B("glColorMask",color_mask),B("glClearDepthf",clear_depth),B("glClearDepthx",clear_depth_x),B("glClearStencil",clear_stencil),
    B("glClear",clear),B("glFlush",flush),B("glFinish",flush),B("glActiveTexture",active_texture),B("glClientActiveTexture",client_active_texture),B("glMatrixMode",matrix_mode)};
uint32_t ds13_bindings(DSBinding *out,uint32_t capacity){
    uint32_t count=sizeof(bindings)/sizeof(bindings[0]);
    if(!out || capacity<DS13_BINDINGS)return 0;
    memcpy(out,bindings,sizeof(bindings));count+=ds14_bindings(out+count,capacity-count);count+=ds15_bindings(out+count,capacity-count);count+=ds16_bindings(out+count,capacity-count);
    out[count++]=(DSBinding)B("glBindFramebufferOES",bind_default_framebuffer);count+=ds21_bindings(out+count,capacity-count);return count+ds22_bindings(out+count,capacity-count);
}
