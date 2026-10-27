#ifndef DS8_H
#define DS8_H
#include "ds7.h"
typedef struct {
    uint32_t acquires,releases,aborts,waits,active_guards;
    uint32_t registered,called,pending,running,failures;
} DS8Stats;
/* Call after ds7_init. Reset refuses live guards or registered destructors. */
int ds8_init(void);
void DS_IO_SOFT ds8_stats(DS8Stats *out);
int DS_IO_SOFT ds8_guard_acquire(uint32_t *guard);
void DS_IO_SOFT ds8_guard_release(uint32_t *guard);
void DS_IO_SOFT ds8_guard_abort(uint32_t *guard);
int DS_IO_SOFT ds8_atexit(void (*destroy)(void *) DS_IO_SOFT,void *object,void *dso);
int DS_IO_SOFT ds8_aeabi_atexit(void *object,void (*destroy)(void *) DS_IO_SOFT,void *dso);
void DS_IO_SOFT ds8_finalize(void *dso);
uint32_t ds8_bindings(DSBinding *out,uint32_t capacity);
#endif
