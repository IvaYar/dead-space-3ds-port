#include "ds_elf.h"

#define MAX_IMAGE (64u * 1024u * 1024u)
#define PT_LOAD 1u
#define PT_DYNAMIC 2u
#define PT_TLS 7u
#define SHN_ABS 0xfff1u

static uint32_t u16(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8; }
static uint32_t u32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void put32(uint8_t *p, uint32_t v) {
    p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}
static int range(uint32_t off, uint32_t len, uint32_t total) { return off <= total && len <= total - off; }
static const uint8_t *ph(const uint8_t *file, const DSInfo *info, uint32_t i) {
    return file + info->phoff + i * 32;
}
/* Translate only bytes actually present in PT_LOAD, never BSS or holes. */
static int file_offset(const uint8_t *file, const DSInfo *info, uint32_t va, uint32_t len, uint32_t *out) {
    for (uint32_t i = 0; i < info->phnum; ++i) {
        const uint8_t *p = ph(file, info, i);
        if (u32(p) != PT_LOAD) continue;
        uint32_t start = u32(p + 8), size = u32(p + 16);
        if (va >= start && range(va - start, len, size)) {
            *out = u32(p + 4) + va - start;
            return 1;
        }
    }
    return 0;
}
static int memory_range(const uint8_t *file, const DSInfo *info, uint32_t va, uint32_t len) {
    for (uint32_t i = 0; i < info->phnum; ++i) {
        const uint8_t *p = ph(file, info, i);
        uint32_t start = u32(p + 8);
        if (u32(p) == PT_LOAD && va >= start && range(va - start, len, u32(p + 20))) return 1;
    }
    return 0;
}
static int valid_string(const uint8_t *file, const DSInfo *info, uint32_t index) {
    if (index >= info->strsize) return 0;
    for (uint32_t i = index; i < info->strsize; ++i)
        if (file[info->stroff + i] == 0) return 1;
    return 0;
}
const char *ds_elf_symbol_name(const uint8_t *file, const DSInfo *info, uint32_t index) {
    if (index >= info->symcount) return "";
    return (const char *)file + info->stroff + u32(file + info->symoff + index * 16);
}
int ds_elf_symbol_is_import(const uint8_t *file, const DSInfo *info, uint32_t index) {
    if (!index || index >= info->symcount) return 0;
    const uint8_t *s = file + info->symoff + index * 16;
    return u16(s + 14) == 0 && u32(s) != 0;
}

static int check_relocations(const uint8_t *file, DSInfo *info, uint32_t off, uint32_t count) {
    for (uint32_t i = 0; i < count; ++i) {
        const uint8_t *r = file + off + i * 8;
        uint32_t target = u32(r), value = u32(r + 4), type = value & 255, symbol = value >> 8;
        if (type == 0) continue;
        if ((target & 3) || !memory_range(file, info, target, 4)) return DS_BAD_RELOCATIONS;
        if (type == 23) {
            if (symbol) return DS_BAD_RELOCATIONS;
            ++info->relative;
            ++info->local_relocations;
            continue;
        }
        if (symbol >= info->symcount) return DS_BAD_RELOCATIONS;
        switch (type) {
            case 2: ++info->abs32; break;
            case 21: ++info->glob_dat; break;
            case 22: ++info->jump_slot; break;
            default: ++info->unsupported; continue;
        }
        const uint8_t *s = file + info->symoff + symbol * 16;
        uint32_t section = u16(s + 14), address = u32(s + 4);
        if (section == 0) {
            if (!symbol) return DS_BAD_RELOCATIONS;
            ++info->external_relocations;
        } else {
            if (section != SHN_ABS && (section >= 0xff00 ||
                !memory_range(file, info, address & ~1u, 1))) return DS_BAD_SYMBOLS;
            ++info->local_relocations;
        }
    }
    return DS_OK;
}

int ds_elf_inspect(const uint8_t *file, uint32_t size, DSInfo *info) {
    uint8_t *clear = (uint8_t *)info;
    for (uint32_t i = 0; i < sizeof(*info); ++i) clear[i] = 0;
    if (size < 52 || file[0] != 0x7f || file[1] != 'E' || file[2] != 'L' || file[3] != 'F' ||
        file[4] != 1 || file[5] != 1 || file[6] != 1 || u16(file + 16) != 3 ||
        u16(file + 18) != 40 || u32(file + 20) != 1 || u16(file + 40) != 52 ||
        u16(file + 42) != 32) return DS_BAD_HEADER;
    info->phoff = u32(file + 28); info->phnum = u16(file + 44);
    info->arm_flags = u32(file + 36); info->entry = u32(file + 24);
    if (!info->phnum || info->phnum > 64 || !range(info->phoff, info->phnum * 32, size)) return DS_BAD_BOUNDS;
    uint32_t dynoff = 0, dynsize = 0, dynamic_found = 0;
    info->load_min = 0xffffffffu;
    for (uint32_t i = 0; i < info->phnum; ++i) {
        const uint8_t *p = ph(file, info, i);
        uint32_t type = u32(p), off = u32(p + 4), va = u32(p + 8);
        uint32_t filesz = u32(p + 16), memsz = u32(p + 20), align = u32(p + 28);
        if (type == PT_TLS) return DS_UNSUPPORTED;
        if (type == PT_DYNAMIC) {
            if (++dynamic_found != 1 || !filesz || filesz % 8 || !range(off, filesz, size)) return DS_BAD_DYNAMIC;
            dynoff = off; dynsize = filesz;
        }
        if (type != PT_LOAD) continue;
        if (!memsz || filesz > memsz || !range(off, filesz, size) || memsz > 0xffffffffu - va ||
            (align > 1 && ((align & (align - 1)) || (off & (align - 1)) != (va & (align - 1)))))
            return DS_BAD_SEGMENTS;
        for (uint32_t j = 0; j < i; ++j) {
            const uint8_t *q = ph(file, info, j);
            if (u32(q) == PT_LOAD && va < u32(q + 8) + u32(q + 20) && u32(q + 8) < va + memsz)
                return DS_BAD_SEGMENTS;
        }
        if (va < info->load_min) info->load_min = va;
        if (va + memsz > info->load_max) info->load_max = va + memsz;
        ++info->load_count;
    }
    if (!info->load_count || !dynamic_found) return DS_BAD_SEGMENTS;
    info->load_min &= ~4095u;
    if (info->load_max > 0xfffff000u) return DS_BAD_SEGMENTS;
    info->load_max = (info->load_max + 4095) & ~4095u;
    info->image_size = info->load_max - info->load_min;
    if (!info->image_size || info->image_size > MAX_IMAGE) return DS_BAD_SEGMENTS;
    uint32_t hash = 0, sym = 0, str = 0, rel = 0, relsz = 0, plt = 0, pltsz = 0;
    uint32_t syment = 0, relent = 8, plttype = 17, initsize = 0, terminated = 0;
    for (uint32_t i = 0; i < dynsize; i += 8) {
        uint32_t tag = u32(file + dynoff + i), value = u32(file + dynoff + i + 4);
        if (!tag) { terminated = 1; break; }
        switch (tag) {
            case 1: ++info->needed; break;
            case 2: pltsz = value; break;
            case 4: hash = value; break;
            case 5: str = value; break;
            case 6: sym = value; break;
            case 7: case 8: case 9: case 35: case 36: case 37:
            case 0x6000000f: case 0x60000010: case 0x60000011: case 0x60000012:
                return DS_UNSUPPORTED; /* RELA, RELR and Android packed relocations. */
            case 10: info->strsize = value; break;
            case 11: syment = value; break;
            case 12: info->init_function = value; break;
            case 17: rel = value; break;
            case 18: relsz = value; break;
            case 19: relent = value; break;
            case 20: plttype = value; break;
            case 23: plt = value; break;
            case 25: info->init_array = value; break;
            case 27: initsize = value; break;
            default: break;
        }
    }
    uint32_t hashoff;
    if (!terminated || !hash || !sym || !str || syment != 16 || !info->strsize ||
        !file_offset(file, info, hash, 8, &hashoff)) return DS_BAD_DYNAMIC;
    uint32_t buckets = u32(file + hashoff);
    info->symcount = u32(file + hashoff + 4);
    if (!info->symcount || info->symcount > 65536 || buckets > 65536 ||
        !file_offset(file, info, hash, (2 + buckets + info->symcount) * 4, &hashoff) ||
        !file_offset(file, info, sym, info->symcount * 16, &info->symoff) ||
        !file_offset(file, info, str, info->strsize, &info->stroff)) return DS_BAD_SYMBOLS;
    for (uint32_t i = 0; i < info->symcount; ++i) {
        const uint8_t *s = file + info->symoff + i * 16;
        uint32_t name = u32(s);
        if (!valid_string(file, info, name)) return DS_BAD_SYMBOLS;
        if (ds_elf_symbol_is_import(file, info, i)) {
            ++info->imports;
            if ((s[12] >> 4) == 2) ++info->weak_imports;
        } else if (u16(s + 14) != 0 && info->strsize - name >= 5) {
            const uint8_t *n = file + info->stroff + name;
            if (n[0] == 'J' && n[1] == 'a' && n[2] == 'v' && n[3] == 'a' && n[4] == '_') ++info->jni_exports;
        }
    }
    for (uint32_t i = 0; i < dynsize; i += 8) {
        uint32_t tag = u32(file + dynoff + i);
        if (!tag) break;
        if (tag == 1 && !valid_string(file, info, u32(file + dynoff + i + 4))) return DS_BAD_DYNAMIC;
    }
    if (relent != 8 || relsz % 8 || pltsz % 8 || (pltsz && plttype != 17) ||
        (relsz && !file_offset(file, info, rel, relsz, &info->reloff)) ||
        (pltsz && !file_offset(file, info, plt, pltsz, &info->pltoff)) ||
        initsize % 4 || (initsize && !memory_range(file, info, info->init_array, initsize)) ||
        (info->init_function && !memory_range(file, info, info->init_function & ~1u, 1)))
        return DS_BAD_RELOCATIONS;
    info->relcount = relsz / 8; info->pltcount = pltsz / 8; info->init_count = initsize / 4;
    int result = check_relocations(file, info, info->reloff, info->relcount);
    if (result != DS_OK) return result;
    return check_relocations(file, info, info->pltoff, info->pltcount);
}

static void apply_table(const uint8_t *file, const DSInfo *info, uint8_t *image,
                        uint32_t bias, uint32_t offset, uint32_t count) {
    for (uint32_t i = 0; i < count; ++i) {
        const uint8_t *r = file + offset + i * 8;
        uint32_t type = u32(r + 4) & 255, symbol = u32(r + 4) >> 8;
        if (!type) continue;
        uint8_t *target = image + u32(r) - info->load_min;
        if (type == 23) { put32(target, u32(target) + bias); continue; }
        const uint8_t *s = file + info->symoff + symbol * 16;
        if (u16(s + 14) == 0) continue; /* Unresolved imports remain untouched and must never be called. */
        uint32_t address = u32(s + 4) + (u16(s + 14) == SHN_ABS ? 0 : bias);
        put32(target, type == 2 ? address + u32(target) : address);
    }
}

int ds_elf_prepare(const uint8_t *file, uint32_t size, uint8_t *image,
                   uint32_t capacity, uint32_t runtime_base, DSInfo *info) {
    int result = ds_elf_inspect(file, size, info);
    if (result != DS_OK) return result;
    if (info->unsupported) return DS_UNSUPPORTED;
    if (capacity < info->image_size || info->image_size > 0xffffffffu - runtime_base) return DS_IMAGE_TOO_SMALL;
    for (uint32_t i = 0; i < info->image_size; ++i) image[i] = 0;
    for (uint32_t i = 0; i < info->phnum; ++i) {
        const uint8_t *p = ph(file, info, i);
        if (u32(p) != PT_LOAD) continue;
        uint32_t off = u32(p + 4), dest = u32(p + 8) - info->load_min, len = u32(p + 16);
        for (uint32_t j = 0; j < len; ++j) image[dest + j] = file[off + j];
    }
    uint32_t bias = runtime_base - info->load_min;
    apply_table(file, info, image, bias, info->reloff, info->relcount);
    apply_table(file, info, image, bias, info->pltoff, info->pltcount);
    return DS_OK;
}

const char *ds_elf_error(int code) {
    switch (code) {
        case DS_OK: return "OK";
        case DS_BAD_HEADER: return "Not an ARM ELF32 shared library";
        case DS_BAD_BOUNDS: return "Invalid file bounds";
        case DS_BAD_SEGMENTS: return "Invalid load segments";
        case DS_BAD_DYNAMIC: return "Invalid dynamic table";
        case DS_BAD_SYMBOLS: return "Invalid symbol table";
        case DS_BAD_RELOCATIONS: return "Invalid relocation table";
        case DS_UNSUPPORTED: return "Unsupported ELF feature";
        case DS_IMAGE_TOO_SMALL: return "Image buffer/address too small";
        case DS_UNRESOLVED_IMPORTS: return "Required import is not bound";
        case DS_SYMBOL_NOT_FOUND: return "Export not found or not verified";
        default: return "Unknown error";
    }
}

static int same_string(const char *a, const char *b) {
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}

static uint32_t binding_address(const char *name, const DSBinding *bindings, uint32_t count) {
    for (uint32_t i = 0; i < count; ++i)
        if (bindings[i].name && same_string(name, bindings[i].name)) return bindings[i].address;
    return 0;
}

int ds_elf_find_export(const uint8_t *file, const DSInfo *info, const char *name,
                       uint32_t *value, uint32_t *size) {
    for (uint32_t i = 1; i < info->symcount; ++i) {
        const uint8_t *s = file + info->symoff + i * 16;
        if (!u16(s + 14) || u16(s + 14) >= 0xff00 || (s[12] & 15) != 2) continue;
        if (same_string(name, ds_elf_symbol_name(file, info, i))) {
            uint32_t va = u32(s + 4), length = u32(s + 8);
            if (!length || !memory_range(file, info, va & ~1u, length)) return DS_BAD_SYMBOLS;
            *value = va; *size = length;
            return DS_OK;
        }
    }
    return DS_SYMBOL_NOT_FOUND;
}

int ds_elf_constant_export(const uint8_t *file, const DSInfo *info, const char *name,
                           uint32_t instruction, uint32_t *value) {
    uint32_t va = 0, length = 0, offset = 0;
    if ((instruction & 0xfffff000u) != 0xe3a00000u &&
        (instruction & 0xfffff000u) != 0xe3e00000u) return DS_SYMBOL_NOT_FOUND;
    if (ds_elf_find_export(file, info, name, &va, &length) != DS_OK || length != 8 || (va & 3) ||
        !file_offset(file, info, va, 8, &offset) || u32(file + offset) != instruction ||
        u32(file + offset + 4) != 0xe12fff1eu) return DS_SYMBOL_NOT_FOUND;
    for (uint32_t i = 0; i < info->phnum; ++i) {
        const uint8_t *p = ph(file, info, i);
        if (u32(p) == PT_LOAD && (u32(p + 24) & 1) && va >= u32(p + 8) &&
            range(va - u32(p + 8), 8, u32(p + 16))) { *value = va; return DS_OK; }
    }
    return DS_SYMBOL_NOT_FOUND;
}

int ds_elf_resolve(const uint8_t *file, const DSInfo *info, uint8_t *image,
                   const DSBinding *bindings, uint32_t count, DSResolve *result) {
    result->imports = result->resolved = result->missing = result->weak_zero = result->patched_sites = 0;
    if (count > 1024 || info->unsupported) return DS_UNSUPPORTED;
    for (uint32_t i = 1; i < info->symcount; ++i) {
        if (!ds_elf_symbol_is_import(file, info, i)) continue;
        ++result->imports;
        const uint8_t *s = file + info->symoff + i * 16;
        if (binding_address(ds_elf_symbol_name(file, info, i), bindings, count)) ++result->resolved;
        else if ((s[12] >> 4) == 2) ++result->weak_zero;
        else ++result->missing;
    }
    if (result->missing) return DS_UNRESOLVED_IMPORTS;
    for (uint32_t table = 0; table < 2; ++table) {
        uint32_t off = table ? info->pltoff : info->reloff, n = table ? info->pltcount : info->relcount;
        for (uint32_t i = 0; i < n; ++i) {
            const uint8_t *r = file + off + i * 8;
            uint32_t entry = u32(r + 4), type = entry & 255, symbol = entry >> 8;
            if (type != 2 && type != 21 && type != 22) continue;
            if (!ds_elf_symbol_is_import(file, info, symbol)) continue;
            uint32_t address = binding_address(ds_elf_symbol_name(file, info, symbol), bindings, count);
            uint8_t *target = image + u32(r) - info->load_min;
            put32(target, type == 2 ? address + u32(target) : address);
            ++result->patched_sites;
        }
    }
    return DS_OK;
}

uint32_t ds_crc32(const uint8_t *data, uint32_t size) {
    uint32_t crc = 0xffffffffu;
    for (uint32_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (uint32_t bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1)));
    }
    return ~crc;
}
