#ifndef DS13_GLES_H
#define DS13_GLES_H
#include "ds_elf.h"
#include "ds14_arrays.h"
#include "ds15_textures.h"
#include "ds16_pipeline.h"
#include "ds21_matrices.h"
#include "ds22_draw.h"
#include "ds26_framebuffer.h"
#include "ds30_fog.h"
#include "ds32_lighting.h"
#include "ds33_surface.h"
#define DS13_BINDINGS (19+DS14_BINDINGS+DS15_BINDINGS+DS16_BINDINGS+1+DS21_BINDINGS+DS22_BINDINGS)
#define DS13_SOFT __attribute__((pcs("aapcs")))
/* Diagnostic GLES state, clear and bounded unlit CPU triangle rendering.
 * One serialized caller; borrowed pixels, logical origin at bottom left. */
enum {DS13_RGB8_ROWS=0,DS13_BGR8_CTR=1,DS13_RGB565_CTR=2};
typedef void (*DS13Observe)(const char *operation,uint32_t argument);
typedef int (*DS13Sync)(void *pixels,uint32_t size);
typedef struct DS13Context {
    uint32_t magic,width,height,capacity,layout,error,scissor_test,dither;
    uint32_t active_texture,client_active_texture;
    uint32_t matrix_mode,framebuffer_binding,blend,fog;
    DS14State vertex;
    DS15State texture;
    DS16State pipeline;
    DS21State *matrix;
    DS22State *draw;
    DS26State *fbo;
    DS30Fog *fog_state;
    DS32Lighting *lighting_state;
    DS33Default *default_storage;
    uint8_t *pixels;
    int32_t viewport[4],scissor[4];
    float clear_color[4],clear_depth;
    int32_t clear_stencil;
    uint8_t color_mask[4];
    uint32_t queries,clears,pixels_written,flushes;
    DS13Observe observe;
    DS13Sync sync;
} DS13Context;
int ds13_init(DS13Context *,void *pixels,uint32_t width,uint32_t height,uint32_t capacity,uint32_t layout);
int ds13_current(DS13Context *); /* NULL releases the current context. */
int ds13_target(DS13Context *,void *pixels,uint32_t capacity);
void ds13_close(DS13Context *);
uint32_t ds13_context_size(void);
uint32_t ds13_bindings(DSBinding *,uint32_t capacity);
void ds13_observer(DS13Context *,DS13Observe,DS13Sync);
void ds13_stats(DS13Context *,uint32_t out[4]);
/* Internal shared state for GL modules; caller serializes entry points. */
DS13Context *ds13_active_context(void);
void ds13_error(uint32_t);
void ds13_unsupported(const char *,uint32_t);
int ds13_integer_values(uint32_t name,int32_t out[4]);
int ds13_real_values(uint32_t name,float out[16],int *normalized);
#endif
