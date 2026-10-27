#ifndef DS_ELF_H
#define DS_ELF_H

#include <stdint.h>

/* ELF operations never execute constructors; platform code controls execution. */
typedef struct {
    uint32_t phoff, phnum, load_count, load_min, load_max, image_size;
    uint32_t symoff, symcount, stroff, strsize;
    uint32_t reloff, relcount, pltoff, pltcount;
    uint32_t init_array, init_count, init_function;
    uint32_t needed, imports, weak_imports, jni_exports;
    uint32_t relative, abs32, glob_dat, jump_slot, unsupported;
    uint32_t local_relocations, external_relocations;
    uint32_t arm_flags, entry;
} DSInfo;

enum {
    DS_OK = 0, DS_BAD_HEADER = 1, DS_BAD_BOUNDS = 2, DS_BAD_SEGMENTS = 3,
    DS_BAD_DYNAMIC = 4, DS_BAD_SYMBOLS = 5, DS_BAD_RELOCATIONS = 6,
    DS_UNSUPPORTED = 7, DS_IMAGE_TOO_SMALL = 8, DS_UNRESOLVED_IMPORTS = 9,
    DS_SYMBOL_NOT_FOUND = 10
};

typedef struct { const char *name; uint32_t address; } DSBinding;
typedef struct { uint32_t imports, resolved, missing, weak_zero, patched_sites; } DSResolve;

int ds_elf_inspect(const uint8_t *file, uint32_t size, DSInfo *info);
/* image must not overlap file. runtime_base is the address represented by image[0]. */
int ds_elf_prepare(const uint8_t *file, uint32_t size, uint8_t *image,
                   uint32_t capacity, uint32_t runtime_base, DSInfo *info);
const char *ds_elf_symbol_name(const uint8_t *file, const DSInfo *info, uint32_t index);
int ds_elf_symbol_is_import(const uint8_t *file, const DSInfo *info, uint32_t index);
/* All strong imports must resolve before any external relocation is written.
 * Call once after prepare(); do not reapply ABS32 addends to an already bound image. */
int ds_elf_resolve(const uint8_t *file, const DSInfo *info, uint8_t *image,
                   const DSBinding *bindings, uint32_t count, DSResolve *result);
int ds_elf_find_export(const uint8_t *file, const DSInfo *info, const char *name,
                       uint32_t *value, uint32_t *size);
/* Require a file-backed executable symbol whose entire declared body is exactly
 * `mov/mvn r0, #constant; bx lr`, matching both supplied instruction words. */
int ds_elf_constant_export(const uint8_t *file, const DSInfo *info, const char *name,
                           uint32_t first_instruction, uint32_t *value);
const char *ds_elf_error(int code);
uint32_t ds_crc32(const uint8_t *data, uint32_t size);

#endif
