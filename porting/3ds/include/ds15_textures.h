#ifndef DS15_TEXTURES_H
#define DS15_TEXTURES_H
#include "ds_elf.h"
#define DS15_TEXTURES 32
#define DS15_LEVELS 11
#define DS15_MAX_SIZE 1024
#define DS15_BINDINGS 16
/* Canonical CPU RGBA8 stores. These are not PICA200 texture allocations. */
typedef struct {uint32_t defined,width,height,format;uint8_t *rgba;} DS15Level;
typedef struct {
    uint32_t min_filter,mag_filter,wrap_s,wrap_t;
    DS15Level levels[DS15_LEVELS];
} DS15Object;
typedef struct {uint32_t name,used;DS15Object *object;} DS15Texture;
typedef struct {
    DS15Texture textures[DS15_TEXTURES];
    DS15Object default_object;
    uint32_t binding[2],enabled[2],next_name,pack,unpack,bytes,limit,uploads,patches;
} DS15State;
void ds15_init(DS15State *);
void ds15_close(DS15State *);
int ds15_query(DS15State *,uint32_t name,int32_t *out,uint32_t unit);
/* Internal renderer staging, one canonical texel; no GL readback extension. */
int ds15_read_texel(DS15State *,uint32_t name,uint32_t level,uint32_t x,uint32_t y,uint8_t out[4]);
/* Borrowed immutable view; invalidated by image replacement/delete/close. */
const DS15Level *ds15_level(DS15State *,uint32_t name,uint32_t level);
void ds15_stats(DS15State *,uint32_t out[4]); /* names, bytes, uploads, patches */
uint32_t ds15_bindings(DSBinding *,uint32_t);
#endif
