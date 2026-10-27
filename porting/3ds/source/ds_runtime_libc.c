#include "ds_runtime.h"
#include <stdlib.h>
#include <string.h>

typedef struct Block { struct Block *previous, *next; uint32_t bytes, reserved; } Block;
_Static_assert(sizeof(Block) == 16, "ARM32 allocation header");
static Block *head;
static DSRuntimeStats stats;
static uint32_t byte_limit;
static void (*lock_hook)(void),(*unlock_hook)(void);
void ds_runtime_set_lock(void (*lock)(void),void (*unlock)(void)) { lock_hook=lock; unlock_hook=unlock; }
static void enter(void) { if(lock_hook) lock_hook(); }
static void leave(void) { if(unlock_hook) unlock_hook(); }

static void *no_memory(void) { ++stats.failures; *ds_io_errno() = 12; return NULL; }
static Block *find_block(void *pointer) {
    for (Block *b = head; b; b = b->next) if ((void *)(b + 1) == pointer) return b;
    ++stats.invalid_frees; *ds_io_errno() = DS_EINVAL; return NULL;
}
static int room_for(uint32_t old_size, size_t new_size) {
    if (new_size > UINT32_MAX - sizeof(Block)) return 0;
    uint64_t total = (uint64_t)stats.live_bytes - old_size + new_size;
    return total <= UINT32_MAX && (!byte_limit || total <= byte_limit);
}
static void update_peak(void) { if (stats.live_bytes > stats.peak_bytes) stats.peak_bytes = stats.live_bytes; }

static int init_impl(uint32_t limit) {
    if (head) return -1;
    memset(&stats, 0, sizeof(stats)); byte_limit = limit;
    return 0;
}
static void stats_impl(DSRuntimeStats *out) { *out = stats; }
static void *malloc_impl(size_t size) {
    ++stats.alloc_calls;
    if (!room_for(0, size)) return no_memory();
    Block *b = malloc(sizeof(*b) + (size ? size : 1));
    if (!b) return no_memory();
    b->previous = NULL; b->next = head; b->bytes = size; b->reserved = 0;
    if (head) head->previous = b;
    head = b; ++stats.live_blocks; stats.live_bytes += size; update_peak();
    return b + 1;
}
static void free_impl(void *pointer) {
    if (!pointer) return;
    Block *b = find_block(pointer);
    if (!b) return;
    if (b->previous) b->previous->next = b->next; else head = b->next;
    if (b->next) b->next->previous = b->previous;
    --stats.live_blocks; stats.live_bytes -= b->bytes; ++stats.free_calls;
    free(b);
}
static void *calloc_impl(size_t count, size_t size) {
    ++stats.calloc_calls;
    uint64_t bytes = (uint64_t)count * size;
    if (bytes > UINT32_MAX) return no_memory();
    void *p = ds_rt_malloc((size_t)bytes);
    if (p) memset(p, 0, (size_t)bytes);
    return p;
}
static void *realloc_impl(void *pointer, size_t size) {
    ++stats.realloc_calls;
    if (!pointer) return ds_rt_malloc(size);
    if (!size) { ds_rt_free(pointer); return NULL; }
    Block *b = find_block(pointer);
    if (!b) return NULL;
    uint32_t old_size = b->bytes;
    if (!room_for(old_size, size)) return no_memory();
    Block *previous = b->previous, *next = b->next;
    Block *moved = realloc(b, sizeof(*b) + size);
    if (!moved) return no_memory();
    if (previous) previous->next = moved; else head = moved;
    if (next) next->previous = moved;
    moved->bytes = size;
    stats.live_bytes = stats.live_bytes - old_size + size; update_peak();
    return moved + 1;
}
static uint32_t cleanup_impl(void) {
    uint32_t remaining = stats.live_blocks;
    while (head) ds_rt_free(head + 1);
    return remaining;
}

int ds_runtime_init(uint32_t limit) { enter(); int result=init_impl(limit); leave(); return result; }
void ds_runtime_stats(DSRuntimeStats *out) { enter(); stats_impl(out); leave(); }
void *DS_IO_SOFT ds_rt_malloc(size_t size) { enter(); void *p=malloc_impl(size); leave(); return p; }
void *DS_IO_SOFT ds_rt_calloc(size_t count,size_t size) { enter(); void *p=calloc_impl(count,size); leave(); return p; }
void *DS_IO_SOFT ds_rt_realloc(void *p,size_t size) { enter(); void *next=realloc_impl(p,size); leave(); return next; }
void DS_IO_SOFT ds_rt_free(void *p) { enter(); free_impl(p); leave(); }
uint32_t ds_runtime_cleanup(void) { enter(); uint32_t result=cleanup_impl(); leave(); return result; }

static void *DS_IO_SOFT ds_rt_memcpy(void *out, const void *in, size_t n) { return memcpy(out, in, n); }
static void *DS_IO_SOFT ds_rt_memmove(void *out, const void *in, size_t n) { return memmove(out, in, n); }
static void *DS_IO_SOFT ds_rt_memset(void *out, int value, size_t n) { return memset(out, value, n); }
static int DS_IO_SOFT ds_rt_memcmp(const void *a, const void *b, size_t n) { return memcmp(a, b, n); }
static size_t DS_IO_SOFT ds_rt_strlen(const char *s) { return strlen(s); }
static int DS_IO_SOFT ds_rt_strcmp(const char *a, const char *b) { return strcmp(a, b); }
static int DS_IO_SOFT ds_rt_strncmp(const char *a, const char *b, size_t n) { return strncmp(a, b, n); }
static char *DS_IO_SOFT ds_rt_strcpy(char *out, const char *in) { return strcpy(out, in); }
static char *DS_IO_SOFT ds_rt_strncpy(char *out, const char *in, size_t n) { return strncpy(out, in, n); }
static char *DS_IO_SOFT ds_rt_strcat(char *out, const char *in) { return strcat(out, in); }
static char *DS_IO_SOFT ds_rt_strchr(const char *s, int c) { return strchr(s, c); }
static char *DS_IO_SOFT ds_rt_strrchr(const char *s, int c) { return strrchr(s, c); }
static char *DS_IO_SOFT ds_rt_strstr(const char *s, const char *part) { return strstr(s, part); }
static char *DS_IO_SOFT ds_rt_strdup(const char *s) {
    size_t n = strlen(s);
    if (n == UINT32_MAX) return no_memory();
    char *copy = ds_rt_malloc(n + 1);
    if (copy) memcpy(copy, s, n + 1);
    return copy;
}
uint32_t ds_runtime_bindings(DSBinding *bindings, uint32_t capacity) {
    static const DSBinding list[] = {
#define DS_BIND(name, function) {name, (uint32_t)(uintptr_t)function},
#include "ds_runtime_bindings.def"
#undef DS_BIND
    };
    uint32_t count = sizeof(list) / sizeof(list[0]);
    if (capacity < count) return 0;
    for (uint32_t i = 0; i < count; ++i) bindings[i] = list[i];
    return count;
}
uint32_t ds_platform_bindings(DSBinding *bindings, uint32_t capacity) {
    if (capacity < 53) return 0;
    if (ds_io_bindings(bindings, capacity) != 5) return 0;
    uint32_t count = ds_runtime_bindings(bindings + 5, capacity - 5);
    return count ? count + 5 : 0;
}
