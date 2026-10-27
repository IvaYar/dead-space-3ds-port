#ifndef DS21_MATRICES_H
#define DS21_MATRICES_H
#include "ds_elf.h"
#define DS21_BINDINGS 17
typedef struct {float stack[4][16][16];uint32_t top[4];} DS21State;
struct DS13Context;
void ds21_close(struct DS13Context *);
int ds21_real(struct DS13Context *,uint32_t,float out[16]);
int ds21_integer(struct DS13Context *,uint32_t,int32_t *);
void ds21_transform(struct DS13Context *,uint32_t mode,uint32_t unit,const float in[4],float out[4]);
uint32_t ds21_bindings(DSBinding *,uint32_t);
#endif
