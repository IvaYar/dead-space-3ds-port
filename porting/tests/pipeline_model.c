#include "ds13_gles.h"
#include <string.h>
static float bits(uint32_t v){float f;memcpy(&f,&v,4);return f;}
uint32_t ds16_test_error(void){DS13Context *c=ds13_active_context();return c?c->error:0x502;}
int ds16_test_cull(uint32_t area){DS13Context *c=ds13_active_context();return c?ds16_culled(&c->pipeline,bits(area)):-1;}
int ds16_test_alpha(uint32_t alpha){DS13Context *c=ds13_active_context();return c?ds16_alpha_pass(&c->pipeline,bits(alpha)):-1;}
int ds16_test_depth(uint32_t a,uint32_t b){DS13Context *c=ds13_active_context();return c?ds16_depth_pass(&c->pipeline,bits(a),bits(b)):-1;}
void ds16_test_blend(const float *src,const float *dst,float *out){DS13Context *c=ds13_active_context();if(c)ds16_blend(&c->pipeline,c->blend,src,dst,out);}
