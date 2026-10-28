#ifndef DS15_TEXTURES_H
#define DS15_TEXTURES_H
#include "ds_elf.h"
#define DS15_TEXTURES 128
#define DS15_LEVELS 11
#define DS15_MAX_SIZE 1024
#define DS15_BINDINGS 16
/* Canonical CPU RGBA8 stores. These are not PICA200 texture allocations. */
typedef struct {uint32_t defined,width,height,format;uint8_t *rgba;uint32_t backing,stamp;} DS15Level;
typedef struct {
    int (*save)(uint32_t *token,const void *pixels,uint32_t bytes);
    int (*load)(uint32_t token,void *pixels,uint32_t bytes);
    void (*drop)(uint32_t token);
} DS15Backing;
typedef struct DS15Object {
    uint32_t references;
    struct DS15Object *next,*previous;
    uint32_t min_filter,mag_filter,wrap_s,wrap_t;
    DS15Level levels[DS15_LEVELS];
} DS15Object;
typedef struct {uint32_t name,used;DS15Object *object;} DS15Texture;
typedef struct {
    DS15Texture textures[DS15_TEXTURES];
    DS15Object default_object;
    uint32_t binding[2],enabled[2],next_name,pack,unpack,bytes,limit,uploads,patches,name_limit;
    DS15Object *objects;
    const DS15Backing *backing_ops;
    uint32_t resident,resident_limit,stamp,page_saves,page_loads,page_failures;
} DS15State;
void ds15_init(DS15State *);
void ds15_close(DS15State *);
int ds15_limits(DS15State *,uint32_t names,uint32_t bytes);
int ds15_backing(DS15State *,const DS15Backing *,uint32_t resident_limit);
int ds15_resident(DS15State *,DS15Object *,uint32_t level);
int ds15_query(DS15State *,uint32_t name,int32_t *out,uint32_t unit);
/* Internal renderer staging, one canonical texel; no GL readback extension. */
int ds15_read_texel(DS15State *,uint32_t name,uint32_t level,uint32_t x,uint32_t y,uint8_t out[4]);
/* Borrowed immutable view; invalidated by image replacement/delete/close. */
const DS15Level *ds15_level(DS15State *,uint32_t name,uint32_t level);
DS15Object *ds15_retain(DS15State *,uint32_t name);
void ds15_release(DS15State *,DS15Object *);
void ds15_stats(DS15State *,uint32_t out[4]); /* names, bytes, uploads, patches */
uint32_t ds15_bindings(DSBinding *,uint32_t);
#endif
