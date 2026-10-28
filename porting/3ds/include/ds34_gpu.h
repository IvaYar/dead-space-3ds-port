#ifndef DS34_GPU_H
#define DS34_GPU_H
#include "ds15_textures.h"
struct DS13Context;
typedef struct {float p[4],color[4],tex[2][4];} DS34Vertex;
int ds34_attach(struct DS13Context *);
int ds34_present(struct DS13Context *);
void ds34_stats(uint32_t out[4]);
int ds34_active(struct DS13Context *) __attribute__((weak));
int ds34_begin_draw(struct DS13Context *) __attribute__((weak));
int ds34_triangle(struct DS13Context *,const DS34Vertex v[3]) __attribute__((weak));
void ds34_end_draw(struct DS13Context *) __attribute__((weak));
int ds34_clear(struct DS13Context *,uint32_t) __attribute__((weak));
int ds34_integer(struct DS13Context *,uint32_t,int32_t *) __attribute__((weak));
void ds34_texture_dirty(DS15State *,DS15Object *) __attribute__((weak));
void ds34_fbo_dirty(struct DS13Context *);
#endif
