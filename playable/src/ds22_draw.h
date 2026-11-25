#ifndef DS22_DRAW_H
#define DS22_DRAW_H
#include "ds_elf.h"
#include "ds26_framebuffer.h"
#include "ds31_combine.h"
#define DS22_BINDINGS 14
struct DS13Context;
typedef void (*DS22Observe)(struct DS13Context *,uint32_t);
typedef struct {
    float color[4],env_color[2][4];uint32_t env_mode[2];
    uint32_t calls,triangles,fragments,samples;DS22Observe observe;
    DS26Surface target;
    DS31Combine *combine;
    /* Borrowed only while a serialized draw executes; refreshed every draw. */
    DS15Object *sampler[2];
} DS22State;
void ds22_close(struct DS13Context *);
int ds22_prepare(struct DS13Context *);
int ds22_real(struct DS13Context *,uint32_t,float out[16]);
int ds22_client_range(struct DS13Context *,const void *,uint32_t);
void ds22_observer(struct DS13Context *,DS22Observe);
void ds22_stats(struct DS13Context *,uint32_t out[4]);
uint32_t ds22_bindings(DSBinding *,uint32_t);
#endif
