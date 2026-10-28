#ifndef DS26_FRAMEBUFFER_H
#define DS26_FRAMEBUFFER_H
#include "ds15_textures.h"
#define DS26_BINDINGS 15
#define DS26_OBJECTS 8
struct DS13Context;
typedef struct DS26State DS26State;
typedef struct {
    uint32_t width,height,layout,format;
    uint8_t *pixels,*stencil;
    uint16_t *depth;
} DS26Surface;
uint32_t ds26_bindings(DSBinding *,uint32_t);
void ds26_close(struct DS13Context *);
int ds26_surface(struct DS13Context *,DS26Surface *); /* Incomplete -> GL error, no pixels touched. */
int ds26_integer(struct DS13Context *,uint32_t,int32_t *);
void ds26_texture_deleted(struct DS13Context *,DS15Object *);
int ds26_attached(struct DS13Context *,DS15Object *);
int ds26_fragment(struct DS13Context *,DS26Surface *,uint32_t,uint32_t,float);
void ds26_quantize(const DS26Surface *,float rgba[4]);
void ds26_stats(struct DS13Context *,uint32_t out[4]); /* FBOs, RBOs, RBO bytes, target changes */
#endif
