#include "ds_io.h"
#include <errno.h>
#include <stdio.h>
#include <stdint.h>

static int32_t android_error(int error) {
    switch (error) {
        case ENOENT: return DS_ENOENT;
        case EBADF: return DS_EBADF;
        case EINVAL: return DS_EINVAL;
        case EMFILE: return DS_EMFILE;
        case ENAMETOOLONG: return DS_ENAMETOOLONG;
        case EOVERFLOW: return DS_EOVERFLOW;
        default: return DS_EIO;
    }
}
static void *sd_open(const char *path, int32_t *error) {
    FILE *file = fopen(path, "rb");
    if (!file) *error = android_error(errno);
    return file;
}
static int32_t sd_read(void *handle, void *buffer, uint32_t count, int32_t *error) {
    FILE *file = handle;
    size_t n = fread(buffer, 1, count, file);
    if (!n && ferror(file)) { *error = android_error(errno); return -1; }
    return (int32_t)n;
}
static int32_t sd_seek(void *handle, int32_t offset, int32_t whence, int32_t *error) {
    FILE *file = handle;
    long original = ftell(file);
    if (original < 0) { *error = android_error(errno); return -1; }
    int64_t base = 0;
    if (whence == 1) base = original;
    if (whence == 2) {
        if (fseek(file, 0, SEEK_END)) { *error = android_error(errno); return -1; }
        long end = ftell(file);
        if (fseek(file, original, SEEK_SET)) { *error = android_error(errno); return -1; }
        if (end < 0) { *error = DS_EOVERFLOW; return -1; }
        base = end;
    }
    int64_t target = base + offset;
    if (target < 0) { *error = DS_EINVAL; return -1; }
    if (target > INT32_MAX) { *error = DS_EOVERFLOW; return -1; }
    if (fseek(file, (long)target, SEEK_SET)) { *error = android_error(errno); return -1; }
    return (int32_t)target;
}
static int32_t sd_close(void *handle, int32_t *error) {
    int result = fclose(handle);
    if (result) *error = android_error(errno);
    return result ? -1 : 0;
}
const DSIOOps *ds_io_sd_ops(void) {
    static const DSIOOps ops = {sd_open, sd_read, sd_seek, sd_close};
    return &ops;
}
