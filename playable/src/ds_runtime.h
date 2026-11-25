#ifndef DS_RUNTIME_H
#define DS_RUNTIME_H
#include <stddef.h>
#include <stdint.h>
#include "ds_io.h"

typedef struct {
    uint32_t alloc_calls, calloc_calls, realloc_calls, free_calls;
    uint32_t live_blocks, live_bytes, peak_bytes, failures, invalid_frees;
} DSRuntimeStats;

/* Single-threaded allocation tracking over native newlib malloc/realloc/free.
 * limit=0 disables the diagnostic byte limit. Init refuses outstanding blocks. */
int ds_runtime_init(uint32_t limit);
uint32_t ds_runtime_cleanup(void);
void ds_runtime_stats(DSRuntimeStats *out);
void ds_runtime_set_lock(void (*lock)(void),void (*unlock)(void));
uint32_t ds_runtime_bindings(DSBinding *bindings, uint32_t capacity);
uint32_t ds_platform_bindings(DSBinding *bindings, uint32_t capacity);
void *DS_IO_SOFT ds_rt_malloc(size_t size);
void *DS_IO_SOFT ds_rt_calloc(size_t count, size_t size);
void *DS_IO_SOFT ds_rt_realloc(void *pointer, size_t size);
void DS_IO_SOFT ds_rt_free(void *pointer);

#define DS_RT_UNARY(name, type) type DS_IO_SOFT ds_rt_##name(type x);
#define DS_RT_BINARY(name, type) type DS_IO_SOFT ds_rt_##name(type x, type y);
DS_RT_UNARY(acos, double) DS_RT_UNARY(acosf, float) DS_RT_UNARY(asinf, float)
DS_RT_UNARY(atan, double) DS_RT_BINARY(atan2, double) DS_RT_BINARY(atan2f, float)
DS_RT_UNARY(ceil, double) DS_RT_UNARY(ceilf, float)
DS_RT_UNARY(cos, double) DS_RT_UNARY(cosf, float)
DS_RT_UNARY(exp, double) DS_RT_UNARY(expf, float)
DS_RT_UNARY(floor, double) DS_RT_UNARY(floorf, float)
DS_RT_BINARY(fmodf, float)
DS_RT_UNARY(log, double) DS_RT_UNARY(logf, float)
DS_RT_UNARY(log10, double) DS_RT_UNARY(log10f, float)
DS_RT_BINARY(pow, double) DS_RT_BINARY(powf, float)
DS_RT_UNARY(sin, double) DS_RT_UNARY(sinf, float)
DS_RT_UNARY(sqrt, double) DS_RT_UNARY(sqrtf, float)
DS_RT_UNARY(tan, double) DS_RT_UNARY(tanf, float)
#undef DS_RT_UNARY
#undef DS_RT_BINARY
double DS_IO_SOFT ds_rt_ldexp(double x, int exponent);
double DS_IO_SOFT ds_rt_modf(double x, double *integer);
int DS_IO_SOFT ds_rt_isinf(double x);
#endif
