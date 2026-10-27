/* An original test module: no EA code or data. Never calls Android functions. */
static volatile int value = 42;
static volatile int bss_values[16];
static volatile int *volatile pointer = &value;
volatile int exported_value = 17;
volatile int *volatile exported_pointer = &exported_value;
extern int missing_android_function(int);

__attribute__((constructor)) static void constructor_must_not_run(void) { value = 99; }
int fixture_read(void) { return *pointer + bss_values[3]; }
int fixture_exported(void) { return exported_value + *exported_pointer; }
int fixture_unresolved(int x) { return missing_android_function(x); }
