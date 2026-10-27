/* Test-only link boundary. No filesystem or clock calls are allowed in the
 * numeric/ABI Unicorn tests. Integration tests use real newlib in Azahar. */
#define _GNU_SOURCE
#include <sys/reent.h>
#include <sys/lock.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/times.h>
#include <errno.h>
#include <stddef.h>
#include <time.h>
#include "ds6.h"
static unsigned unexpected_calls;
unsigned ds6_test_unexpected_os_calls(void) { return unexpected_calls; }
static int fail(struct _reent *r) { ++unexpected_calls; r->_errno=ENOSYS; return -1; }
int _open_r(struct _reent *r,const char *p,int f,int m) { (void)p;(void)f;(void)m; return fail(r); }
int _close_r(struct _reent *r,int fd) { (void)fd; return fail(r); }
_ssize_t _read_r(struct _reent *r,int fd,void *p,size_t n) { (void)fd;(void)p;(void)n; return fail(r); }
_ssize_t _write_r(struct _reent *r,int fd,const void *p,size_t n) { (void)fd;(void)p;(void)n; return fail(r); }
_off_t _lseek_r(struct _reent *r,int fd,_off_t off,int w) { (void)fd;(void)off;(void)w; return fail(r); }
int _fstat_r(struct _reent *r,int fd,struct stat *s) { (void)fd;(void)s; return fail(r); }
int _stat_r(struct _reent *r,const char *p,struct stat *s) { (void)p;(void)s; return fail(r); }
int _isatty_r(struct _reent *r,int fd) { (void)fd; return fail(r); }
int _unlink_r(struct _reent *r,const char *p) { (void)p; return fail(r); }
int _rename_r(struct _reent *r,const char *a,const char *b) { (void)a;(void)b; return fail(r); }
int _rmdir_r(struct _reent *r,const char *p) { (void)p; return fail(r); }
int __attribute__((noinline)) _mkdir_r(struct _reent *r,const char *p,int mode) { (void)p;(void)mode;return fail(r); }
int mkdir(const char *p,mode_t mode) { return _mkdir_r(__getreent(),p,(int)mode); }
int _getpid_r(struct _reent *r) { return fail(r); }
int _kill_r(struct _reent *r,int pid,int signal) { (void)pid;(void)signal; return fail(r); }
int _gettimeofday_r(struct _reent *r,struct timeval *p,void *z) { (void)p;(void)z; return fail(r); }
clock_t _times_r(struct _reent *r,struct tms *p) { (void)p; return (clock_t)fail(r); }
void __libc_lock_acquire(_LOCK_T *lock) { (void)lock; }
void __libc_lock_release(_LOCK_T *lock) { (void)lock; }
int __syscall_clock_gettime(clockid_t id,struct timespec *out) { (void)id;(void)out; return fail(__getreent()); }
int __syscall_nanosleep(const struct timespec *in,struct timespec *out) { (void)in;(void)out; return fail(__getreent()); }
int ds6_native_clock(int id,DS6Time *out) { (void)id;(void)out; return fail(__getreent()); }
int ds6_native_sleep(const DS6Time *request) { (void)request; return fail(__getreent()); }
