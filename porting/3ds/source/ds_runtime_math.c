#include "ds_runtime.h"
#include <errno.h>
#include <math.h>

static int begin_call(void) { int saved = errno; errno = 0; return saved; }
static void end_call(int saved) {
    int error = errno; errno = saved;
    if (error) *ds_io_errno() = error == EDOM ? 33 : error == ERANGE ? 34 : DS_EIO;
}
#define UNARY(name, type) type DS_IO_SOFT ds_rt_##name(type x) { \
    int saved = begin_call(); type value = name(x); end_call(saved); return value; }
#define BINARY(name, type) type DS_IO_SOFT ds_rt_##name(type x, type y) { \
    int saved = begin_call(); type value = name(x, y); end_call(saved); return value; }
UNARY(acos, double) UNARY(acosf, float) UNARY(asinf, float)
UNARY(atan, double) BINARY(atan2, double) BINARY(atan2f, float)
UNARY(ceil, double) UNARY(ceilf, float)
UNARY(cos, double) UNARY(cosf, float)
UNARY(exp, double) UNARY(expf, float)
UNARY(floor, double) UNARY(floorf, float)
BINARY(fmodf, float)
UNARY(log, double) UNARY(logf, float)
UNARY(log10, double) UNARY(log10f, float)
BINARY(pow, double) BINARY(powf, float)
UNARY(sin, double) UNARY(sinf, float)
UNARY(sqrt, double) UNARY(sqrtf, float)
UNARY(tan, double) UNARY(tanf, float)
double DS_IO_SOFT ds_rt_ldexp(double x, int exponent) {
    int saved = begin_call(); double value = ldexp(x, exponent); end_call(saved); return value;
}
double DS_IO_SOFT ds_rt_modf(double x, double *integer) {
    int saved = begin_call(); double value = modf(x, integer); end_call(saved); return value;
}
int DS_IO_SOFT ds_rt_isinf(double x) { return isinf(x) ? 1 : 0; }
