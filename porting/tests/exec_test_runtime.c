/* Standalone backend tests link the real libctru SVC wrappers without a CRT. */
#include <stddef.h>
void *memset(void *destination, int value, size_t length) {
    unsigned char *p = destination;
    for (size_t i = 0; i < length; ++i) p[i] = (unsigned char)value;
    return destination;
}
