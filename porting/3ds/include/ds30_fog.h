#ifndef DS30_FOG_H
#define DS30_FOG_H
#include "ds_elf.h"
#define DS30_BINDINGS 4
struct DS13Context;
typedef struct {uint32_t mode;float density,start,end,color[4];} DS30Fog;
int ds30_attach(struct DS13Context *);
void ds30_close(struct DS13Context *);
int ds30_real(struct DS13Context *,uint32_t,float out[16],int *normalized);
int ds30_integer(struct DS13Context *,uint32_t,int32_t *out);
float ds30_factor(const DS30Fog *,float eye_z);
void ds30_apply(const DS30Fog *,float factor,float rgba[4]);
uint32_t ds30_bindings(DSBinding *,uint32_t);
#endif
