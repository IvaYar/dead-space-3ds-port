#ifndef DS16_PIPELINE_H
#define DS16_PIPELINE_H
#include "ds_elf.h"
#define DS16_BINDINGS 18
/* Pipeline state/arithmetic used by the unlit CPU rasterizer. The default
 * borrowed surface has no depth or stencil attachment. */
typedef struct {
    uint32_t cull,depth,alpha,stencil,offset_fill,lighting,color_material,normalize,rescale;
    uint32_t lights[8];
    uint32_t cull_mode,front_face,depth_func,depth_mask,alpha_func,blend_src,blend_dst,shade;
    uint32_t stencil_func,stencil_ref,stencil_value_mask,stencil_write_mask,stencil_fail,stencil_zfail,stencil_zpass;
    float alpha_ref,depth_range[2],offset_factor,offset_units;
} DS16State;
void ds16_init(DS16State *);
int ds16_capability(DS16State *,uint32_t name,int set); /* -1 unknown; set=-1 queries */
int ds16_query(DS16State *,uint32_t name,int32_t *out);
int ds16_enum(uint32_t name);
int ds16_culled(const DS16State *,float signed_window_area);
int ds16_alpha_pass(const DS16State *,float alpha);
int ds16_depth_pass(const DS16State *,float source,float destination);
void ds16_blend(const DS16State *,int enabled,const float source[4],const float destination[4],float out[4]);
uint32_t ds16_bindings(DSBinding *,uint32_t);
#endif
