#ifndef DS31_COMBINE_H
#define DS31_COMBINE_H
#include "ds_elf.h"
struct DS13Context;
typedef struct {uint32_t rgb,alpha,src_rgb[3],src_alpha[3],op_rgb[3],op_alpha[3];float rgb_scale,alpha_scale;} DS31Unit;
typedef struct {DS31Unit unit[2];} DS31Combine;
int ds31_attach(struct DS13Context *);
void ds31_close(struct DS13Context *);
int ds31_set(struct DS13Context *,uint32_t name,float value);
int ds31_get(struct DS13Context *,uint32_t name,float *value,int *is_enum);
int ds31_scale(uint32_t name);
void ds31_apply(const DS31Unit *,const float primary[4],const float previous[4],const float texture[4],const float constant[4],float out[4]);
#endif
