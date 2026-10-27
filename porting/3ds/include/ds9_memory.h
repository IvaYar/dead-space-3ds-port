#ifndef DS9_MEMORY_H
#define DS9_MEMORY_H
#include "ds7.h"
typedef struct { uint32_t break_bytes,break_peak,mapped_pages,map_peak,sbrk_calls,mmap_calls,munmap_calls,refusals; } DS9MemoryStats;
/* Caller owns two disjoint, writable arenas until all donor users have stopped.
 * No native newlib heap pointers are exposed to the donor's sbrk allocator. */
int ds9_memory_init(void *brk_arena,uint32_t brk_size,void *map_arena,uint32_t map_size);
void ds9_memory_stats(DS9MemoryStats *out);
void *DS_IO_SOFT ds9_sbrk(int32_t increment);
/* Private anonymous RW mappings only; executable/file/shared/fixed modes refuse. */
void *DS_IO_SOFT ds9_mmap(void *hint,uint32_t size,int protection,int flags,int fd,int32_t offset);
int DS_IO_SOFT ds9_munmap(void *address,uint32_t size);
uint32_t ds9_memory_bindings(DSBinding *out,uint32_t capacity);
#endif
