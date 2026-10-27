/* Test adapters for internal safe attribute staging; not GL exports. */
#include "ds13_gles.h"
int ds14_test_range(uint32_t base,uint32_t size){DS13Context *c=ds13_active_context();return c?ds14_client_range(&c->vertex,(void *)base,size):-1;}
int ds14_test_unrange(uint32_t base){DS13Context *c=ds13_active_context();return c?ds14_client_remove(&c->vertex,(void *)base):-1;}
int ds14_test_read(uint32_t slot,uint32_t index,uint32_t out,uint32_t size){DS13Context *c=ds13_active_context();return c?ds14_read_array(&c->vertex,slot,index,(void *)out,size):-1;}
void ds14_test_stats(uint32_t *out){
    DS13Context *c=ds13_active_context();unsigned n=0;for(unsigned i=0;i<DS14_BUFFERS;++i)n+=c->vertex.buffers[i].used;
    out[0]=n;out[1]=c->vertex.bytes;out[2]=c->vertex.array_buffer;out[3]=c->vertex.element_buffer;
}
