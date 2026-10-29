#ifndef DS34_GPU_H
#define DS34_GPU_H
#include "ds15_textures.h"
struct DS13Context;
typedef struct {float p[4],color[4],tex[2][4];} DS34Vertex;
int ds34_attach(struct DS13Context *);
int ds34_present(struct DS13Context *);
void ds34_stats(uint32_t out[4]);
#ifdef DS34_FRAME_DIAGNOSTICS
/* Implemented only by the standalone native fixture, never the game backend. */
void ds34_diagnostic_mark(const char *phase);
int ds34_diagnostic_begin(uint32_t flags);
int ds34_diagnostic_sync(void);
void ds34_diagnostic_end(void);
#endif
#ifdef DS34_SEQUENCE_AUDIT
typedef struct {
    uint32_t presents,drains,peak_vertices,upload_checks,upload_mismatches;
    uint32_t vertex_checks,vertex_mismatches,texture_checks,texture_mismatches;
    uint32_t pending_staging,stream_used,cached_textures,texture_digest;
} DS34Audit;
int ds34_sequence_audit(DS34Audit *);
#endif
int ds34_active(struct DS13Context *) __attribute__((weak));
int ds34_begin_draw(struct DS13Context *) __attribute__((weak));
int ds34_triangle(struct DS13Context *,const DS34Vertex v[3]) __attribute__((weak));
void ds34_end_draw(struct DS13Context *) __attribute__((weak));
int ds34_clear(struct DS13Context *,uint32_t) __attribute__((weak));
int ds34_integer(struct DS13Context *,uint32_t,int32_t *) __attribute__((weak));
void ds34_texture_dirty(DS15State *,DS15Object *) __attribute__((weak));
void ds34_fbo_dirty(struct DS13Context *);
#endif
