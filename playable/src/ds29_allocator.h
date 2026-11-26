#ifndef DS29_ALLOCATOR_H
#define DS29_ALLOCATOR_H
#include "ds9_memory.h"
/* Opt-in compatibility for the verified SD 1.1.33 EA allocator. The growth
 * call at 0x253438 incorrectly consumes sbrk's result as the NEW break. Other
 * callers retain the Android/POSIX old-break contract. No donor bytes change. */
int ds29_allocator_init(const void *image,uint32_t bytes);
void ds29_allocator_reset(void);
void *DS_IO_SOFT ds29_sbrk(int32_t increment,uint32_t caller);
#endif
