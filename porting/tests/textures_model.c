#include "ds13_gles.h"
int ds15_test_limits(uint32_t names,uint32_t bytes){DS13Context *c=ds13_active_context();return c?ds15_limits(&c->texture,names,bytes):-1;}
uint32_t ds15_test_object_size(void){return sizeof(DS15Object);}
int ds15_test_backing(const DS15Backing *ops,uint32_t bytes){DS13Context *c=ds13_active_context();return c?ds15_backing(&c->texture,ops,bytes):-1;}
void ds15_test_pages(uint32_t out[6]){DS13Context *c=ds13_active_context();if(c){DS15State *s=&c->texture;out[0]=s->resident;out[1]=s->resident_limit;out[2]=s->page_saves;out[3]=s->page_loads;out[4]=s->page_failures;out[5]=s->bytes;}}
int ds15_test_read(uint32_t name,uint32_t level,uint32_t x,uint32_t y,uint8_t *out){DS13Context *c=ds13_active_context();return c?ds15_read_texel(&c->texture,name,level,x,y,out):-1;}
void ds15_test_stats(uint32_t *out){DS13Context *c=ds13_active_context();if(c)ds15_stats(&c->texture,out);}
int ds15_test_image(uint32_t name,uint32_t level,uint32_t out[4]){DS13Context *c=ds13_active_context();const DS15Level *l=c?ds15_level(&c->texture,name,level):0;if(!l)return -1;out[0]=l->width;out[1]=l->height;out[2]=l->format;out[3]=(uint32_t)l->rgba;return 0;}
