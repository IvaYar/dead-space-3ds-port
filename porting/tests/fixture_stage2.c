/* Original ARM softfp module for loader/ABI validation; no EA code. */
extern int host_integer(int value);
extern float host_add_float(float a, float b);
extern int optional_feature(void) __attribute__((weak));
static volatile int data = 42;
static volatile int bss[16];
static volatile int *volatile pointer = &data;
__attribute__((constructor)) static void must_not_run(void) { data = 99; }

int probe_integer(int x) { return *pointer + bss[3] + host_integer(x); }
float probe_float(float a, float b) { return host_add_float(a, b) + 0.5f; }
int probe_weak(void) { return optional_feature ? optional_feature() : 7; }
