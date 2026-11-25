#ifndef DS_BOOTSTRAP_H
#define DS_BOOTSTRAP_H
#include "ds_elf.h"

typedef struct { uint32_t on_load, vm_storage, get_chars, release_chars; } DSBootstrap;
/* Inspect the chosen donor's bounded JNI paths and their mapped instructions.
 * No code is executed. Only the selected SD release is accepted. */
int ds_bootstrap_verify(const uint8_t *file, uint32_t size, const uint8_t *image,
                         uint32_t capacity, uint32_t runtime_base, DSInfo *info, DSBootstrap *plan);
#endif
