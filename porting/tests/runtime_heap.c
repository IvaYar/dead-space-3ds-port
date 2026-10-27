/* Test-only newlib sbrk backend; production uses libctru's allocator. */
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <sys/reent.h>
#include <sys/lock.h>
static uint8_t heap[2 * 1024 * 1024] __attribute__((aligned(8)));
static uint32_t used;
/* Only malloc and errno use this object; no test invokes stdio/locale setup. */
static struct _reent reentrancy;
struct _reent *__getreent(void) { return &reentrancy; }
/* The Unicorn harness has one thread. Production links libctru's real locks. */
void __libc_lock_acquire_recursive(_LOCK_RECURSIVE_T *lock) { (void)lock; }
void __libc_lock_release_recursive(_LOCK_RECURSIVE_T *lock) { (void)lock; }
void *_sbrk(ptrdiff_t increment) {
    int64_t next = (int64_t)used + increment;
    if (next < 0 || next > (int64_t)sizeof(heap)) { errno = ENOMEM; return (void *)-1; }
    void *p = heap + used; used = (uint32_t)next; return p;
}
void *_sbrk_r(struct _reent *r, ptrdiff_t increment) { (void)r; return _sbrk(increment); }
