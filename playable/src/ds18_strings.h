#ifndef DS18_STRINGS_H
#define DS18_STRINGS_H
#include <stdint.h>
#define DS18_MAX_UNITS 255
typedef struct {uint16_t *units;uint32_t length,utf_pins,wide_pins,critical_pins;} DS18Text;
/* Canonical JNI modified UTF-8, preserving every UTF-16 code unit.
 * Counted buffers; no terminator is read/written. Failures leave output intact. */
int ds18_encode(const uint16_t *,uint32_t length,char *,uint32_t capacity);
int ds18_decode(const char *,uint32_t bytes,uint16_t *,uint32_t capacity);
#endif
