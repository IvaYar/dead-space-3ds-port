#include "ds13_gles.h"
#include "ds_runtime.h"
#include <string.h>
#define BAD_ENUM 0x500u
#define BAD_VALUE 0x501u
#define BAD_OPERATION 0x502u
#define NO_MEMORY 0x505u
static DS14State *state(void){DS13Context *c=ds13_active_context();return c?&c->vertex:NULL;}
static unsigned unit(void){return ds13_active_context()->client_active_texture-0x84c0;}
static int slot(uint32_t name,unsigned u){
    switch(name){case 0x8074:return 0;case 0x8075:return 1;case 0x8076:return 2;case 0x8078:return 3+(int)u;default:return -1;}
}
static DS14Buffer *find(DS14State *s,uint32_t name){
    if(name)for(unsigned i=0;i<DS14_BUFFERS;++i)if(s->buffers[i].used && s->buffers[i].name==name)return &s->buffers[i];
    return NULL;
}
static DS14Buffer *empty(DS14State *s){for(unsigned i=0;i<DS14_BUFFERS;++i)if(!s->buffers[i].used)return &s->buffers[i];return NULL;}
static uint32_t *binding(DS14State *s,uint32_t target){
    if(target==0x8892)return &s->array_buffer;
    if(target==0x8893)return &s->element_buffer;
    ds13_error(BAD_ENUM);return NULL;
}
void ds14_init(DS14State *s){
    memset(s,0,sizeof(*s));s->limit=2*1024*1024;
    for(unsigned i=0;i<DS14_ARRAYS;++i){s->arrays[i].size=i==1?3:4;s->arrays[i].type=0x1406;}
}
void ds14_close(DS14State *s){for(unsigned i=0;i<DS14_BUFFERS;++i)if(s->buffers[i].data)ds_rt_free(s->buffers[i].data);memset(s,0,sizeof(*s));}
int ds14_enabled(DS14State *s,uint32_t name,uint32_t u){int i=slot(name,u);return i<0?-1:(int)s->arrays[i].enabled;}
static void set_client(uint32_t name,int enabled){
    DS14State *s=state();if(!s)return;int i=slot(name,unit());
    if(i<0){ds13_error(BAD_ENUM);return;}s->arrays[i].enabled=(uint32_t)enabled;
}
static void DS13_SOFT enable_client(uint32_t name){set_client(name,1);}
static void DS13_SOFT disable_client(uint32_t name){set_client(name,0);}
static unsigned scalar_bytes(uint32_t type){switch(type){case 0x1400:case 0x1401:return 1;case 0x1402:return 2;case 0x1406:case 0x140c:return 4;default:return 0;}}
static void pointer(unsigned i,int32_t count,uint32_t type,int32_t stride,const void *p){
    DS14State *s=state();if(!s)return;
    if(stride<0 || count<2 || count>4 || (i==1 && count!=3) || (i==2 && count!=4)){ds13_error(BAD_VALUE);return;}
    int allowed=i==2?(type==0x1401 || type==0x1406 || type==0x140c):(type==0x1400 || type==0x1402 || type==0x1406 || type==0x140c);
    if(!allowed){ds13_error(BAD_ENUM);return;}
    DS14Array next=s->arrays[i];next.size=(uint32_t)count;next.type=type;next.stride=(uint32_t)stride;next.pointer=(uintptr_t)p;next.buffer=s->array_buffer;s->arrays[i]=next;
}
static void DS13_SOFT vertex_pointer(int32_t n,uint32_t t,int32_t stride,const void *p){pointer(0,n,t,stride,p);}
static void DS13_SOFT normal_pointer(uint32_t t,int32_t stride,const void *p){pointer(1,3,t,stride,p);}
static void DS13_SOFT color_pointer(int32_t n,uint32_t t,int32_t stride,const void *p){pointer(2,n,t,stride,p);}
static void DS13_SOFT tex_pointer(int32_t n,uint32_t t,int32_t stride,const void *p){if(state())pointer(3+unit(),n,t,stride,p);}
static void DS13_SOFT get_pointer(uint32_t name,void **out){
    DS14State *s=state();if(!s)return;if(!out){ds13_error(BAD_VALUE);return;}
    int i=name==0x808e?0:name==0x808f?1:name==0x8090?2:name==0x8092?3+(int)unit():-1;
    if(i<0){ds13_error(BAD_ENUM);return;}*out=(void *)s->arrays[i].pointer;
}
static void DS13_SOFT gen_buffers(int32_t n,uint32_t *names){
    DS14State *s=state();if(!s)return;if(n<0 || (n && !names)){ds13_error(BAD_VALUE);return;}
    if(!n)return;
    unsigned available=0;for(unsigned i=0;i<DS14_BUFFERS;++i)available+=!s->buffers[i].used;
    if((uint32_t)n>available || (uint64_t)s->next_name+(uint32_t)n+DS14_BUFFERS>UINT32_MAX){ds13_error(NO_MEMORY);return;}
    for(int32_t i=0;i<n;++i){
        do{++s->next_name;}while(find(s,s->next_name));
        DS14Buffer *b=empty(s);*b=(DS14Buffer){s->next_name,1,0,0,0x88e4,NULL};names[i]=b->name;
    }
}
static void DS13_SOFT bind_buffer(uint32_t target,uint32_t name){
    DS14State *s=state();if(!s)return;uint32_t *selected=binding(s,target);if(!selected)return;
    DS14Buffer *b=find(s,name);
    if(name && !b){b=empty(s);if(!b){ds13_error(NO_MEMORY);return;}*b=(DS14Buffer){name,1,0,0,0x88e4,NULL};}
    if(b)b->created=1;
    *selected=name;
}
static uint8_t DS13_SOFT is_buffer(uint32_t name){DS14State *s=state();DS14Buffer *b=s?find(s,name):NULL;return b && b->created;}
static void DS13_SOFT delete_buffers(int32_t n,const uint32_t *names){
    DS14State *s=state();if(!s)return;if(n<0 || (n && !names)){ds13_error(BAD_VALUE);return;}
    for(int32_t i=0;i<n;++i){
        DS14Buffer *b=find(s,names[i]);if(!b)continue;
        if(s->array_buffer==b->name)s->array_buffer=0;
        if(s->element_buffer==b->name)s->element_buffer=0;
        for(unsigned a=0;a<DS14_ARRAYS;++a)if(s->arrays[a].buffer==b->name)s->arrays[a].buffer=0;
        if(b->data)ds_rt_free(b->data);
        s->bytes-=b->size;memset(b,0,sizeof(*b));
    }
}
static DS14Buffer *bound(uint32_t target){DS14State *s=state();if(!s)return NULL;uint32_t *name=binding(s,target);if(!name)return NULL;DS14Buffer *b=find(s,*name);if(!b)ds13_error(BAD_OPERATION);return b;}
static void DS13_SOFT buffer_data(uint32_t target,int32_t size,const void *data,uint32_t usage){
    DS14State *s=state();if(!s)return;DS14Buffer *b=bound(target);if(!b)return;
    if(size<0){ds13_error(BAD_VALUE);return;}
    if(usage!=0x88e4 && usage!=0x88e8){ds13_error(BAD_ENUM);return;}
    if((uint64_t)s->bytes-b->size+(uint32_t)size>s->limit){ds13_error(NO_MEMORY);return;}
    uint8_t *next=size?ds_rt_calloc(1,(uint32_t)size):NULL;
    if(size && !next){ds13_error(NO_MEMORY);return;}
    if(size && data)memcpy(next,data,(uint32_t)size);
    if(b->data)ds_rt_free(b->data);
    s->bytes=s->bytes-b->size+(uint32_t)size;b->data=next;b->size=(uint32_t)size;b->usage=usage;
}
static void DS13_SOFT buffer_sub_data(uint32_t target,int32_t offset,int32_t size,const void *data){
    DS14Buffer *b=bound(target);if(!b)return;
    if(offset<0 || size<0 || (uint32_t)offset>b->size || (uint32_t)size>b->size-(uint32_t)offset || (size && !data)){ds13_error(BAD_VALUE);return;}
    if(size)memcpy(b->data+(uint32_t)offset,data,(uint32_t)size);
}
static void DS13_SOFT get_buffer_parameter(uint32_t target,uint32_t name,int32_t *out){
    DS14Buffer *b=bound(target);if(!b)return;if(!out){ds13_error(BAD_VALUE);return;}
    if(name==0x8764)*out=(int32_t)b->size;
    else if(name==0x8765)*out=(int32_t)b->usage;
    else ds13_error(BAD_ENUM);
}
int ds14_query(DS14State *s,uint32_t name,int32_t *out,uint32_t u){
    if(name==0x8894){*out=(int32_t)s->array_buffer;return 1;}
    if(name==0x8895){*out=(int32_t)s->element_buffer;return 1;}
    int enabled=ds14_enabled(s,name,u);if(enabled>=0){*out=enabled;return 1;}
    int i=-1,field=0;
    switch(name){
        case 0x807a:i=0;field=0;break;case 0x807b:i=0;field=1;break;case 0x807c:i=0;field=2;break;
        case 0x807e:i=1;field=1;break;case 0x807f:i=1;field=2;break;
        case 0x8081:i=2;field=0;break;case 0x8082:i=2;field=1;break;case 0x8083:i=2;field=2;break;
        case 0x8088:i=3+(int)u;field=0;break;case 0x8089:i=3+(int)u;field=1;break;case 0x808a:i=3+(int)u;field=2;break;
        case 0x8896:i=0;field=3;break;case 0x8897:i=1;field=3;break;case 0x8898:i=2;field=3;break;case 0x889a:i=3+(int)u;field=3;break;
        default:return 0;
    }
    DS14Array *a=&s->arrays[i];*out=(int32_t)(field==0?a->size:field==1?a->type:field==2?a->stride:a->buffer);return 1;
}
int ds14_client_range(DS14State *s,const void *base,uint32_t size){
    if(!s || !base || !size || (uint64_t)(uintptr_t)base+size>UINT32_MAX+1ull)return -1;
    for(unsigned i=0;i<DS14_RANGES;++i)if(s->ranges[i].base==(uintptr_t)base){s->ranges[i].size=size;return 0;}
    for(unsigned i=0;i<DS14_RANGES;++i)if(!s->ranges[i].base){s->ranges[i]=(DS14Range){(uintptr_t)base,size};return 0;}
    return -1;
}
int ds14_client_remove(DS14State *s,const void *base){
    if(!s || !base)return -1;
    for(unsigned i=0;i<DS14_RANGES;++i)if(s->ranges[i].base==(uintptr_t)base){s->ranges[i]=(DS14Range){0,0};return 0;}
    return -1;
}
int ds14_read_array(DS14State *s,uint32_t i,uint32_t index,void *out,uint32_t capacity){
    if(!s || i>=DS14_ARRAYS || !out)return -1;
    DS14Array *a=&s->arrays[i];uint32_t size=a->size*scalar_bytes(a->type);if(!size || capacity<size)return -1;
    uint64_t offset=(uint64_t)index*(a->stride?a->stride:size)+a->pointer;
    const uint8_t *source=NULL;
    if(a->buffer){DS14Buffer *b=find(s,a->buffer);if(!b || offset>b->size || size>b->size-offset)return -1;source=b->data+(uint32_t)offset;}
    else for(unsigned r=0;r<DS14_RANGES;++r){
        DS14Range *range=&s->ranges[r];if(range->base && offset>=range->base && offset-range->base<=range->size && size<=range->size-(offset-range->base)){source=(const uint8_t *)(uintptr_t)offset;break;}
    }
    if(!source)return -1;
    memcpy(out,source,size);return (int)size;
}
#define B(name,fn) {name,(uint32_t)(uintptr_t)fn}
static const DSBinding bindings[]={B("glEnableClientState",enable_client),B("glDisableClientState",disable_client),B("glVertexPointer",vertex_pointer),
    B("glNormalPointer",normal_pointer),B("glColorPointer",color_pointer),B("glTexCoordPointer",tex_pointer),B("glGetPointerv",get_pointer),
    B("glGenBuffers",gen_buffers),B("glBindBuffer",bind_buffer),B("glIsBuffer",is_buffer),B("glDeleteBuffers",delete_buffers),
    B("glBufferData",buffer_data),B("glBufferSubData",buffer_sub_data),B("glGetBufferParameteriv",get_buffer_parameter)};
_Static_assert(sizeof(bindings)/sizeof(bindings[0])==DS14_BINDINGS,"GL array binding count");
uint32_t ds14_bindings(DSBinding *out,uint32_t capacity){uint32_t n=sizeof(bindings)/sizeof(bindings[0]);if(!out || capacity<n)return 0;memcpy(out,bindings,sizeof(bindings));return n;}
