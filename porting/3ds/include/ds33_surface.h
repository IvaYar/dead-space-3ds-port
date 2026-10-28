#ifndef DS33_SURFACE_H
#define DS33_SURFACE_H
#include "ds_elf.h"
struct DS13Context;
typedef struct {uint16_t *depth;uint8_t *stencil;void *allocation;uint32_t bytes;} DS33Default;
int ds33_attach(struct DS13Context *,uint32_t depth_bits,uint32_t stencil_bits);
void ds33_close(struct DS13Context *);
int ds33_integer(struct DS13Context *,uint32_t,int32_t *);
#endif
