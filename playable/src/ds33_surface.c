/* Owned depth/stencil for the borrowed default color surface. Color swaps do
 * not reallocate or alias FBO attachments; app clear/write masks still apply. */
#include "ds13_gles.h"
#include "ds_runtime.h"
#include <string.h>
int ds33_attach(DS13Context *c,uint32_t depth,uint32_t stencil){
    if(!c || c!=ds13_active_context() || c->default_storage || (depth!=0&&depth!=16) || (stencil!=0&&stencil!=8) || (!depth&&!stencil))return -1;
    uint32_t count=c->width*c->height,bytes=count*((depth?2:0)+(stencil?1:0));
    DS33Default *s=ds_rt_calloc(1,sizeof(*s));if(!s)return -1;
    s->allocation=ds_rt_calloc(1,bytes);if(!s->allocation){ds_rt_free(s);return -1;}s->bytes=bytes;
    if(depth){s->depth=s->allocation;for(uint32_t i=0;i<count;++i)s->depth[i]=65535;}
    if(stencil)s->stencil=(uint8_t *)s->allocation+(depth?count*2:0);
    c->default_storage=s;return 0;
}
void ds33_close(DS13Context *c){if(c->default_storage){ds_rt_free(c->default_storage->allocation);ds_rt_free(c->default_storage);c->default_storage=NULL;}}
int ds33_integer(DS13Context *c,uint32_t name,int32_t *out){
    if(!c->default_storage || c->framebuffer_binding)return 0;
    if(name==0xd56){*out=c->default_storage->depth?16:0;return 1;}if(name==0xd57){*out=c->default_storage->stencil?8:0;return 1;}return 0;
}
