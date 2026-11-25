#include "ds_bootstrap.h"
#include <stddef.h>

static uint32_t read32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static int span(uint32_t start, uint32_t length, uint32_t base, uint32_t size) {
    return start >= base && start - base <= size && length <= size - (start - base);
}
static int segment(const uint8_t *file, const DSInfo *info, uint32_t address, uint32_t length, uint32_t flags, int backed, uint32_t *offset) {
    for (uint32_t i = 0; i < info->phnum; ++i) {
        const uint8_t *p = file + info->phoff + i * 32;
        if (read32(p) == 1 && (read32(p + 24) & flags) == flags &&
            span(address, length, read32(p + 8), read32(p + (backed ? 16 : 20)))) {
            if (offset) *offset = read32(p + 4) + address - read32(p + 8);
            return 1;
        }
    }
    return 0;
}
static int body(const uint8_t *file, const DSInfo *info, const uint8_t *image, const char *name,
                const uint32_t *instructions, uint32_t count, uint32_t *address) {
    uint32_t length = 0, offset = 0;
    if (ds_elf_find_export(file, info, name, address, &length) != DS_OK || (*address & 3) ||
        length != count * 4 || !segment(file, info, *address, length, 1, 1, &offset)) return 0;
    for (uint32_t i = 0; i < count; ++i)
        if (read32(file + offset + i * 4) != instructions[i] ||
            read32(image + *address - info->load_min + i * 4) != instructions[i]) return 0;
    return 1;
}

int ds_bootstrap_verify(const uint8_t *file, uint32_t size, const uint8_t *image,
                         uint32_t capacity, uint32_t runtime_base, DSInfo *info, DSBootstrap *plan) {
    int result = ds_elf_inspect(file, size, info);
    if (result != DS_OK) return result;
    if (capacity < info->image_size || runtime_base > 0xffffffffu - info->image_size) return DS_IMAGE_TOO_SMALL;
    static const uint32_t on_load[] = {
        0xe59f3018,0xe59f2018,0xe08f3003,0xe7932002,0xe5820000,
        0xe3a00801,0xe2800004,0xe12fff1e,0x00208764,0x000006a4
    };
    static const uint32_t get_chars[] = {
        0xe92d4800,0xe28db004,0xe24dd010,0xe50b0008,0xe50b100c,0xe50b2010,
        0xe51b3008,0xe5933000,0xe59332a4,0xe51b0008,0xe51b100c,0xe51b2010,
        0xe12fff33,0xe1a03000,0xe1a00003,0xe24bd004,0xe8bd8800
    };
    static const uint32_t release_chars[] = {
        0xe92d4800,0xe28db004,0xe24dd010,0xe50b0008,0xe50b100c,0xe50b2010,
        0xe51b3008,0xe5933000,0xe59332a8,0xe51b0008,0xe51b100c,0xe51b2010,
        0xe12fff33,0xe24bd004,0xe8bd8800
    };
    if (!body(file, info, image, "JNI_OnLoad", on_load, 10, &plan->on_load) ||
        !body(file, info, image, "_ZN7_JNIEnv17GetStringUTFCharsEP8_jstringPh", get_chars, 17, &plan->get_chars) ||
        !body(file, info, image, "_ZN7_JNIEnv21ReleaseStringUTFCharsEP8_jstringPKc", release_chars, 15, &plan->release_chars))
        return DS_SYMBOL_NOT_FOUND;
    if (plan->on_load > 0xffffffffu - 16 - on_load[8] - on_load[9]) return DS_BAD_SYMBOLS;
    uint32_t got = plan->on_load + 16 + on_load[8], slot = got + on_load[9], offset = 0;
    if (!segment(file, info, slot, 4, 2, 1, &offset)) return DS_BAD_SYMBOLS;
    plan->vm_storage = read32(file + offset);
    if ((plan->vm_storage & 3) || !segment(file, info, plan->vm_storage, 4, 2, 0, NULL)) return DS_BAD_SYMBOLS;
    uint32_t target = runtime_base + plan->vm_storage - info->load_min;
    if (read32(image + slot - info->load_min) != target ||
        read32(image + plan->vm_storage - info->load_min) != 0) return DS_BAD_SYMBOLS;
    return DS_OK;
}
