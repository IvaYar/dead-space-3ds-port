#include <stdint.h>
extern void *__dso_handle;
extern int __aeabi_atexit(void *,void (*)(void *),void *);
static uint32_t marker;
static void destroy(void *object) { *(uint32_t *)object=2; }
__attribute__((constructor)) static void initialize(void) { marker=1; __aeabi_atexit(&marker,destroy,&__dso_handle); }
uint32_t probe_legacy_marker(void) { return marker; }
uint32_t probe_legacy_token(void) { return (uint32_t)&__dso_handle; }
