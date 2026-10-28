#include "ds13_gles.h"
#include "ds_runtime.h"
#include "ds34_gpu.h"
#include <math.h>
#include <string.h>
#define BAD_ENUM 0x500u
#define BAD_VALUE 0x501u
#define BAD_OPERATION 0x502u
#define NO_MEMORY 0x505u
#define TEXTURE_2D 0xde1u
/* Optional audit hook, also used for real budget/allocator refusals. */
void ds15_upload_trace(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,int) __attribute__((weak));
static void upload_trace(uint32_t w,uint32_t h,uint32_t format,uint32_t required,uint32_t limit,int result){
    if(ds15_upload_trace)ds15_upload_trace(w,h,format,required,limit,result);
}
static DS15State *state(void){DS13Context *c=ds13_active_context();return c?&c->texture:NULL;}
static unsigned unit(void){return ds13_active_context()->active_texture-0x84c0;}
static void object_init(DS15Object *o){memset(o,0,sizeof(*o));o->references=1;o->min_filter=0x2702;o->mag_filter=0x2601;o->wrap_s=o->wrap_t=0x2901;}
void ds15_init(DS15State *s){memset(s,0,sizeof(*s));object_init(&s->default_object);s->pack=s->unpack=4;s->limit=2*1024*1024;s->name_limit=32;}
int ds15_limits(DS15State *s,uint32_t names,uint32_t bytes){
    if(!names || names>DS15_TEXTURES || !bytes || bytes<s->bytes)return -1;
    for(unsigned i=names;i<DS15_TEXTURES;++i)if(s->textures[i].used)return -1;
    s->name_limit=names;s->limit=bytes;return 0;
}
int ds15_backing(DS15State *s,const DS15Backing *ops,uint32_t bytes){
    if(s->bytes || s->objects || !ops || !ops->save || !ops->load || !ops->drop || !bytes)return -1;
    s->backing_ops=ops;s->resident_limit=bytes;return 0;
}
static DS15Texture *find(DS15State *s,uint32_t name){
    if(name)for(unsigned i=0;i<DS15_TEXTURES;++i)if(s->textures[i].used && s->textures[i].name==name)return &s->textures[i];
    return NULL;
}
static DS15Texture *empty(DS15State *s){for(unsigned i=0;i<s->name_limit;++i)if(!s->textures[i].used)return &s->textures[i];return NULL;}
static DS15Object *object(DS15State *,uint32_t);
static int spill(DS15State *s,DS15Level *l){
    uint32_t bytes=l->width*l->height*4;
    if(s->backing_ops->save(&l->backing,l->rgba,bytes)){++s->page_failures;return -1;}
    ds_rt_free(l->rgba);l->rgba=NULL;s->resident-=bytes;++s->page_saves;return 0;
}
static int pinned(DS15State *s,DS15Object *o){
    for(unsigned u=0;u<2;++u)if(s->enabled[u] && object(s,s->binding[u])==o)return 1;
    DS13Context *c=ds13_active_context();return c && &c->texture==s && ds26_attached(c,o);
}
static int room(DS15State *s,uint32_t bytes,DS15Level *protect){
    if(!s->backing_ops)return 0;
    if(bytes>s->resident_limit)return -1;
    while((uint64_t)s->resident+bytes>s->resident_limit){
        DS15Level *victim=NULL;
        for(DS15Object *o=&s->default_object;o;o=o==&s->default_object?s->objects:o->next)if(!pinned(s,o))for(unsigned j=0;j<DS15_LEVELS;++j){
            DS15Level *l=&o->levels[j];if(l->rgba && l!=protect && (!victim || l->stamp<victim->stamp))victim=l;
        }
        /* Image replacement may stage its old pixels on SD first. The old
         * store remains logically valid if the subsequent allocation fails. */
        if(!victim && protect && protect->rgba)victim=protect;
        if(!victim || spill(s,victim))return -1;
    }return 0;
}
int ds15_resident(DS15State *s,DS15Object *o,uint32_t level){
    if(!o || level>=DS15_LEVELS)return -1;
    DS15Level *l=&o->levels[level];
    if(!l->defined)return -1;
    if(!l->rgba && l->backing){uint32_t bytes=l->width*l->height*4;
        if(room(s,bytes,l)){ds13_error(NO_MEMORY);return -1;}
        uint8_t *p=ds_rt_malloc(bytes);if(!p){ds13_error(NO_MEMORY);return -1;}
        if(s->backing_ops->load(l->backing,p,bytes)){ds_rt_free(p);++s->page_failures;ds13_error(BAD_OPERATION);return -1;}
        l->rgba=p;s->resident+=bytes;++s->page_loads;
    }l->stamp=++s->stamp;return 0;
}
static void level_clear(DS15State *s,DS15Level *l){
    uint32_t bytes=l->width*l->height*4;
    if(l->rgba){ds_rt_free(l->rgba);s->resident-=bytes;}
    if(l->backing && s->backing_ops)s->backing_ops->drop(l->backing);
    s->bytes-=bytes;memset(l,0,sizeof(*l));
}
static void object_clear(DS15State *s,DS15Object *o){
    if(ds34_texture_dirty)ds34_texture_dirty(s,o);
    for(unsigned i=0;i<DS15_LEVELS;++i)level_clear(s,&o->levels[i]);
}
void ds15_close(DS15State *s){
    object_clear(s,&s->default_object);
    while(s->objects){DS15Object *o=s->objects;s->objects=o->next;object_clear(s,o);ds_rt_free(o);}
    memset(s,0,sizeof(*s));
}
static DS15Object *object(DS15State *s,uint32_t name){if(!name)return &s->default_object;DS15Texture *t=find(s,name);return t?t->object:NULL;}
DS15Object *ds15_retain(DS15State *s,uint32_t name){DS15Object *o=name?object(s,name):NULL;if(o)++o->references;return o;}
void ds15_release(DS15State *s,DS15Object *o){if(o && !--o->references){
    if(o->previous)o->previous->next=o->next;else s->objects=o->next;
    if(o->next)o->next->previous=o->previous;
    object_clear(s,o);ds_rt_free(o);}}
static DS15Object *bound(uint32_t target){DS15State *s=state();if(!s)return NULL;if(target!=TEXTURE_2D){ds13_error(BAD_ENUM);return NULL;}return object(s,s->binding[unit()]);}
static void DS13_SOFT gen_textures(int32_t n,uint32_t *names){
    DS15State *s=state();if(!s)return;if(n<0 || (n && !names)){ds13_error(BAD_VALUE);return;}
    unsigned available=0;for(unsigned i=0;i<s->name_limit;++i)available+=!s->textures[i].used;
    if((uint32_t)n>available){ds13_error(NO_MEMORY);return;}
    for(int32_t i=0;i<n;++i){do{++s->next_name;}while(!s->next_name || find(s,s->next_name));DS15Texture *t=empty(s);*t=(DS15Texture){s->next_name,1,NULL};names[i]=t->name;}
}
static void DS13_SOFT bind_texture(uint32_t target,uint32_t name){
    DS15State *s=state();if(!s)return;if(target!=TEXTURE_2D){ds13_error(BAD_ENUM);return;}
    if(name){
        DS15Texture *t=find(s,name);if(!t)t=empty(s);if(!t){ds13_error(NO_MEMORY);return;}
        if(!t->object){DS15Object *o=ds_rt_malloc(sizeof(*o));if(!o){ds13_error(NO_MEMORY);return;}object_init(o);o->next=s->objects;if(s->objects)s->objects->previous=o;s->objects=o;*t=(DS15Texture){name,1,o};}
    }
    s->binding[unit()]=name;
}
static uint8_t DS13_SOFT is_texture(uint32_t name){DS15State *s=state();DS15Texture *t=s?find(s,name):NULL;return t && t->object;}
static void DS13_SOFT delete_textures(int32_t n,const uint32_t *names){
    DS15State *s=state();if(!s)return;if(n<0 || (n && !names)){ds13_error(BAD_VALUE);return;}
    for(int32_t i=0;i<n;++i){DS15Texture *t=find(s,names[i]);if(!t)continue;
        for(unsigned u=0;u<2;++u)if(s->binding[u]==t->name)s->binding[u]=0;
        if(t->object){ds26_texture_deleted(ds13_active_context(),t->object);ds15_release(s,t->object);}memset(t,0,sizeof(*t));
    }
}
static void DS13_SOFT pixel_store(uint32_t name,int32_t value){
    DS15State *s=state();if(!s)return;if(name!=0xd05 && name!=0xcf5){ds13_error(BAD_ENUM);return;}
    if(value!=1 && value!=2 && value!=4 && value!=8){ds13_error(BAD_VALUE);return;}
    if(name==0xd05)s->pack=(uint32_t)value;else s->unpack=(uint32_t)value;
}
static uint32_t *parameter(DS15Object *o,uint32_t name){switch(name){case 0x2801:return &o->min_filter;case 0x2800:return &o->mag_filter;case 0x2802:return &o->wrap_s;case 0x2803:return &o->wrap_t;default:return NULL;}}
static void DS13_SOFT tex_parameter_i(uint32_t target,uint32_t name,int32_t value){
    DS15Object *o=bound(target);if(!o)return;
    if(name==0x8191){ /* Automatic mipmap generation is deliberately not advertised. */
        if(value!=0 && value!=1)ds13_error(BAD_VALUE);
        else if(value)ds13_unsupported("GL_GENERATE_MIPMAP unsupported",name);
        return;
    }
    uint32_t *p=parameter(o,name);if(!p){ds13_error(BAD_ENUM);return;}
    int allowed=name==0x2801?(value==0x2600 || value==0x2601 || (value>=0x2700 && value<=0x2703)):
        name==0x2800?(value==0x2600 || value==0x2601):(value==0x2901 || value==0x812f);
    if(!allowed){ds13_error(BAD_ENUM);return;}*p=(uint32_t)value;
}
static void DS13_SOFT tex_parameter_f(uint32_t target,uint32_t name,float value){
    if(!isfinite(value) || value<0 || value>65535 || floorf(value)!=value){ds13_error(BAD_ENUM);return;}tex_parameter_i(target,name,(int32_t)value);
}
/* Fixed-point enum parameters are passed as unscaled enum integers. */
static void DS13_SOFT tex_parameter_iv(uint32_t target,uint32_t name,const int32_t *p){if(!p){ds13_error(BAD_VALUE);return;}tex_parameter_i(target,name,*p);}
static void DS13_SOFT tex_parameter_fv(uint32_t target,uint32_t name,const float *p){if(!p){ds13_error(BAD_VALUE);return;}tex_parameter_f(target,name,*p);}
static int get_parameter(uint32_t target,uint32_t name,uint32_t *value){DS15Object *o=bound(target);if(!o)return 0;if(name==0x8191){*value=0;return 1;}uint32_t *p=parameter(o,name);if(!p){ds13_error(BAD_ENUM);return 0;}*value=*p;return 1;}
static void DS13_SOFT get_parameter_i(uint32_t target,uint32_t name,int32_t *out){uint32_t v;if(!out){ds13_error(BAD_VALUE);return;}if(get_parameter(target,name,&v))*out=(int32_t)v;}
static void DS13_SOFT get_parameter_f(uint32_t target,uint32_t name,float *out){uint32_t v;if(!out){ds13_error(BAD_VALUE);return;}if(get_parameter(target,name,&v))*out=(float)v;}
static unsigned pixel_bytes(uint32_t format,uint32_t type){
    unsigned components=format==0x1906 || format==0x1909?1:format==0x190a?2:format==0x1907?3:format==0x1908?4:0;
    if(!components || (type!=0x1401 && type!=0x8363 && type!=0x8033 && type!=0x8034)){ds13_error(BAD_ENUM);return 0;}
    if(type==0x1401)return components;
    if((type==0x8363 && format!=0x1907) || ((type==0x8033 || type==0x8034) && format!=0x1908)){ds13_error(BAD_OPERATION);return 0;}
    return 2;
}
static void decode(const uint8_t *p,uint32_t format,uint32_t type,uint8_t *out){
    out[0]=out[1]=out[2]=0;out[3]=255;
    if(type==0x1401){switch(format){
        case 0x1906:out[3]=p[0];break;
        case 0x1909:out[0]=out[1]=out[2]=p[0];break;
        case 0x190a:out[0]=out[1]=out[2]=p[0];out[3]=p[1];break;
        case 0x1907:memcpy(out,p,3);break;
        default:memcpy(out,p,4);break;
    }return;}
    uint32_t v=p[0]|(uint32_t)p[1]<<8;
    if(type==0x8363){out[0]=(uint8_t)(((v>>11)*255+15)/31);out[1]=(uint8_t)((((v>>5)&63)*255+31)/63);out[2]=(uint8_t)(((v&31)*255+15)/31);}
    else if(type==0x8033){for(unsigned i=0;i<4;++i)out[i]=(uint8_t)(((v>>(12-4*i))&15)*17);}
    else{out[0]=(uint8_t)(((v>>11)*255+15)/31);out[1]=(uint8_t)((((v>>6)&31)*255+15)/31);out[2]=(uint8_t)((((v>>1)&31)*255+15)/31);out[3]=(v&1)?255:0;}
}
static int source_range(const void *p,uint32_t w,uint32_t h,uint32_t bpp,uint32_t alignment,uint32_t *pitch){
    *pitch=(w*bpp+alignment-1)&~(alignment-1);
    uint64_t size=h?(uint64_t)(h-1)*(*pitch)+(uint64_t)w*bpp:0;
    if(p && (uint64_t)(uintptr_t)p+size>UINT32_MAX+1ull){ds13_error(BAD_VALUE);return 0;}return 1;
}
static void copy_image(uint8_t *out,uint32_t out_width,uint32_t x,uint32_t y,uint32_t w,uint32_t h,uint32_t format,uint32_t type,const uint8_t *p,uint32_t pitch,uint32_t bpp){
    for(uint32_t row=0;row<h;++row)for(uint32_t col=0;col<w;++col)decode(p+row*pitch+col*bpp,format,type,out+((y+row)*out_width+x+col)*4);
}
static int level_valid(int32_t level){if(level<0 || level>=DS15_LEVELS){ds13_error(BAD_VALUE);return 0;}return 1;}
static void DS13_SOFT tex_image(uint32_t target,int32_t level,int32_t internal,int32_t w,int32_t h,int32_t border,uint32_t format,uint32_t type,const void *pixels){
    DS15Object *o=bound(target);if(!o || !level_valid(level))return;
    if(w<0 || h<0 || w>(DS15_MAX_SIZE>>level) || h>(DS15_MAX_SIZE>>level) || (w && (w&(w-1))) || (h && (h&(h-1))) || border ||
       (internal!=0x1906 && internal!=0x1907 && internal!=0x1908 && internal!=0x1909 && internal!=0x190a)){ds13_error(BAD_VALUE);return;}
    if((uint32_t)internal!=format){ds13_error(BAD_OPERATION);return;}
    uint32_t bpp=pixel_bytes(format,type),pitch;if(!bpp || !source_range(pixels,(uint32_t)w,(uint32_t)h,bpp,state()->unpack,&pitch))return;
    DS15State *s=state();DS15Level *old=&o->levels[level];uint32_t bytes=(uint32_t)w*(uint32_t)h*4,old_bytes=old->width*old->height*4;
    if((uint64_t)s->bytes-old_bytes+bytes>s->limit){upload_trace(w,h,format,s->bytes-old_bytes+bytes,s->limit,1);ds13_error(NO_MEMORY);return;}
    if(room(s,bytes,old)){upload_trace(w,h,format,s->bytes-old_bytes+bytes,s->limit,2);ds13_error(NO_MEMORY);return;}
    uint8_t *data=bytes?ds_rt_calloc(1,bytes):NULL;if(bytes && !data){upload_trace(w,h,format,s->bytes-old_bytes+bytes,s->limit,2);ds13_error(NO_MEMORY);return;}
    if(bytes && pixels)copy_image(data,(uint32_t)w,0,0,(uint32_t)w,(uint32_t)h,format,type,pixels,pitch,bpp);
    level_clear(s,old);
    *old=(DS15Level){.defined=1,.width=(uint32_t)w,.height=(uint32_t)h,.format=format,.rgba=data,.stamp=++s->stamp};s->bytes+=bytes;s->resident+=bytes;++s->uploads;
    upload_trace(w,h,format,s->bytes,s->limit,0);
    if(ds34_texture_dirty)ds34_texture_dirty(s,o);
}
static void DS13_SOFT tex_sub_image(uint32_t target,int32_t level,int32_t x,int32_t y,int32_t w,int32_t h,uint32_t format,uint32_t type,const void *pixels){
    DS15Object *o=bound(target);if(!o || !level_valid(level))return;DS15Level *l=&o->levels[level];
    if(!l->defined || format!=l->format){ds13_error(BAD_OPERATION);return;}
    if(x<0 || y<0 || w<0 || h<0 || (uint32_t)x>l->width || (uint32_t)y>l->height || (uint32_t)w>l->width-(uint32_t)x || (uint32_t)h>l->height-(uint32_t)y || (w && h && !pixels)){ds13_error(BAD_VALUE);return;}
    uint32_t bpp=pixel_bytes(format,type),pitch;if(!bpp || !source_range(pixels,(uint32_t)w,(uint32_t)h,bpp,state()->unpack,&pitch))return;
    if(ds15_resident(state(),o,(uint32_t)level))return;
    if(w && h)copy_image(l->rgba,l->width,(uint32_t)x,(uint32_t)y,(uint32_t)w,(uint32_t)h,format,type,pixels,pitch,bpp);
    ++state()->patches;
    if(ds34_texture_dirty)ds34_texture_dirty(state(),o);
}
int ds15_query(DS15State *s,uint32_t name,int32_t *out,uint32_t u){switch(name){
    case 0x8069:*out=(int32_t)s->binding[u];break;case 0xde1:*out=(int32_t)s->enabled[u];break;
    case 0xd33:*out=DS15_MAX_SIZE;break;case 0xd05:*out=(int32_t)s->pack;break;case 0xcf5:*out=(int32_t)s->unpack;break;
    default:return 0;
}return 1;}
const DS15Level *ds15_level(DS15State *s,uint32_t name,uint32_t level){
    if(!s || level>=DS15_LEVELS)return NULL;
    DS15Object *o=object(s,name);if(!o || ds15_resident(s,o,level))return NULL;return &o->levels[level];
}
int ds15_read_texel(DS15State *s,uint32_t name,uint32_t level,uint32_t x,uint32_t y,uint8_t out[4]){
    const DS15Level *l=ds15_level(s,name,level);if(!l || !out || x>=l->width || y>=l->height)return -1;
    memcpy(out,l->rgba+(y*l->width+x)*4,4);return 0;
}
void ds15_stats(DS15State *s,uint32_t out[4]){unsigned n=0;for(unsigned i=0;i<DS15_TEXTURES;++i)n+=s->textures[i].used;out[0]=n;out[1]=s->bytes;out[2]=s->uploads;out[3]=s->patches;}
#define B(name,fn) {name,(uint32_t)(uintptr_t)fn}
static const DSBinding bindings[]={B("glGenTextures",gen_textures),B("glBindTexture",bind_texture),B("glIsTexture",is_texture),B("glDeleteTextures",delete_textures),
    B("glPixelStorei",pixel_store),B("glTexParameteri",tex_parameter_i),B("glTexParameterx",tex_parameter_i),B("glTexParameterf",tex_parameter_f),
    B("glTexParameteriv",tex_parameter_iv),B("glTexParameterxv",tex_parameter_iv),B("glTexParameterfv",tex_parameter_fv),
    B("glGetTexParameteriv",get_parameter_i),B("glGetTexParameterxv",get_parameter_i),B("glGetTexParameterfv",get_parameter_f),
    B("glTexImage2D",tex_image),B("glTexSubImage2D",tex_sub_image)};
_Static_assert(sizeof(bindings)/sizeof(bindings[0])==DS15_BINDINGS,"GL texture binding count");
uint32_t ds15_bindings(DSBinding *out,uint32_t capacity){uint32_t n=DS15_BINDINGS;if(!out || capacity<n)return 0;memcpy(out,bindings,sizeof(bindings));return n;}
