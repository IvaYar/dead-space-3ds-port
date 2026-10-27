/* Original ARM softfp runtime probe; no EA code. Built without libc/libm. */
#include <stddef.h>
#include <stdint.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
extern int *__errno(void);
extern char *strdup(const char *);
extern int __isinf(double);
static volatile int constructor_state = 42;
__attribute__((constructor)) static void must_not_run(void) { constructor_state = 99; }

int probe_memory(uint32_t *out) {
    for (int i = 0; i < 8; ++i) out[i] = 0;
    out[1] = (uint32_t)constructor_state;
    char *a = malloc(32), *b = calloc(8, 4), *copy = NULL;
    int code = 1;
    if (!a || !b || ((uintptr_t)a & 7) || ((uintptr_t)b & 7)) goto done;
    for (int i = 0; i < 32; ++i) if (b[i]) { code = 2; goto done; }
    memset(a, 0x5a, 32); memcpy(b, a, 32);
    code = 3;
    if (memcmp(a, b, 32)) goto done;
    strcpy(a, "deadspace"); strcat(a, "-3ds");
    code = 4;
    if (strlen(a) != 13 || strcmp(a, "deadspace-3ds") || strncmp(a, "dead", 4)) goto done;
    if (strchr(a, 's') != a + 4 || strrchr(a, 's') != a + 12 || strstr(a, "space") != a + 4) goto done;
    copy = strdup(a);
    code = 5;
    if (!copy || strcmp(copy, a)) goto done;
    memset(b, 0x5a, 32); strncpy(b, "abc", 8);
    for (int i = 3; i < 8; ++i) if (b[i]) { code = 6; goto done; }
    strcpy(b, "0123456789"); memmove(b + 2, b, 9);
    code = 7;
    if (memcmp(b, "01012345678", 11)) goto done;
    char *grown = realloc(a, 4096);
    code = 8;
    if (!grown) goto done;
    a = grown;
    if (((uintptr_t)a & 7) || strcmp(a, "deadspace-3ds")) goto done;
    char *shrunk = realloc(a, 24);
    code = 9;
    if (!shrunk) goto done;
    a = shrunk;
    if (strcmp(a, "deadspace-3ds")) goto done;
    volatile size_t overflowing_size = 0xffffffffu;
    volatile size_t overflowing_count = 0x80000000u;
    void *failure = realloc(a, overflowing_size);
    out[2] = (uint32_t)*__errno();
    code = 10;
    if (failure) { a = failure; goto done; }
    if (out[2] != 12 || strcmp(a, "deadspace-3ds")) goto done;
    failure = calloc(overflowing_count, 2);
    out[3] = (uint32_t)*__errno();
    code = 11;
    if (failure) { free(failure); goto done; }
    if (out[3] != 12) goto done;
    code = constructor_state == 42 ? 0 : 12;
done:
    free(copy); free(b); free(a);
    out[0] = (uint32_t)code;
    return code;
}

static int near64(double actual, double expected) {
    double difference = actual - expected;
    return actual == actual && difference < 1e-10 && difference > -1e-10;
}
static int near32(float actual, float expected) {
    float difference = actual - expected;
    return actual == actual && difference < 2e-6f && difference > -2e-6f;
}
int probe_math(uint32_t *out) {
    uint32_t failed = 0, checks = 0;
#define CHECK(condition) do { ++checks; if (!(condition) && !failed) failed = checks; } while (0)
    CHECK(near64(acos(0.5), 1.0471975511965976));
    CHECK(near32(acosf(0.5f), 1.0471975512f));
    CHECK(near32(asinf(0.5f), 0.5235987756f));
    CHECK(near64(atan(1.0), 0.7853981633974483));
    CHECK(near64(atan2(1.0, -1.0), 2.356194490192345));
    CHECK(near32(atan2f(1.0f, -1.0f), 2.35619449f));
    CHECK(ceil(-1.25) == -1.0); CHECK(ceilf(1.25f) == 2.0f);
    CHECK(near64(cos(0.5), 0.8775825618903728)); CHECK(near32(cosf(0.5f), 0.87758256f));
    CHECK(near64(exp(1.0), 2.718281828459045)); CHECK(near32(expf(1.0f), 2.7182818f));
    CHECK(floor(-1.25) == -2.0); CHECK(floorf(1.25f) == 1.0f);
    CHECK(fmodf(5.5f, 2.0f) == 1.5f);
    CHECK(ldexp(0.75, 4) == 12.0);
    CHECK(near64(log(2.0), 0.6931471805599453)); CHECK(near32(logf(2.0f), 0.69314718f));
    CHECK(log10(100.0) == 2.0); CHECK(log10f(100.0f) == 2.0f);
    double integer = 0.0;
    CHECK(modf(-3.25, &integer) == -0.25 && integer == -3.0);
    CHECK(pow(2.0, -3.0) == 0.125); CHECK(powf(4.0f, 0.5f) == 2.0f);
    CHECK(near64(sin(0.5), 0.479425538604203)); CHECK(near32(sinf(0.5f), 0.47942554f));
    CHECK(sqrt(2.25) == 1.5); CHECK(sqrtf(6.25f) == 2.5f);
    CHECK(near64(tan(0.5), 0.5463024898437905)); CHECK(near32(tanf(0.5f), 0.54630249f));
    union { uint64_t bits; double value; } special;
    special.bits = UINT64_C(0x7ff0000000000000); CHECK(__isinf(special.value) != 0);
    special.bits = UINT64_C(0xfff0000000000000); CHECK(__isinf(special.value) != 0);
    special.bits = UINT64_C(0x7ff8000000000001); CHECK(__isinf(special.value) == 0);
    special.bits = UINT64_C(0x8000000000000000);
    union { uint64_t bits; double value; } negative_zero;
    negative_zero.value = sqrt(special.value); CHECK(negative_zero.bits == special.bits);
    *__errno() = 0; volatile double bad = sqrt(-1.0);
    out[2] = (uint32_t)*__errno(); CHECK(bad != bad && out[2] == 33);
    *__errno() = 0; volatile double huge = exp(1000.0);
    out[3] = (uint32_t)*__errno(); CHECK(__isinf(huge) != 0 && out[3] == 34);
    out[0] = failed; out[1] = checks;
#undef CHECK
    return (int)failed;
}
