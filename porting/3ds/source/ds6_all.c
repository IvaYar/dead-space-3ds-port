#include "ds6.h"
int ds6_init(DS6Log logger) {
    ds6_basics_init(logger); ds6_stdio_init(); ds6_time_init(); return 0;
}
uint32_t ds6_cleanup(void) {
    uint32_t files=ds6_stdio_cleanup(); ds6_basics_cleanup(); return files;
}
uint32_t ds6_bindings(DSBinding *out,uint32_t capacity) {
    if(capacity<108) return 0;
    uint32_t n=ds_platform_bindings(out,capacity);
    n+=ds6_basics_bindings(out+n,capacity-n);
    n+=ds6_stdio_bindings(out+n,capacity-n);
    n+=ds6_time_bindings(out+n,capacity-n);
    return n;
}
