#include "ds_io.h"
#include <stddef.h>

static DSIO *current;
static int32_t inactive_error = DS_EIO;
static int32_t *(*errno_provider)(void);

static int prefix(const char *path, const char *text) {
    int length = 0;
    while (text[length]) {
        if (path[length] != text[length]) return 0;
        ++length;
    }
    return length;
}

int ds_io_map_path(const char *path, char *out, uint32_t capacity) {
    if (!path || !out) return DS_EFAULT;
    const char *prefixes[] = {"appbundle:/published/", "published/",
        "/sdcard/Android/data/com.ea.deadspace/files/published/", DS_IO_ROOT};
    uint32_t start = 0;
    for (uint32_t i = 0; i < sizeof(prefixes) / sizeof(prefixes[0]); ++i) {
        int n = prefix(path, prefixes[i]);
        if (n) { start = (uint32_t)n; break; }
    }
    if (!start) return DS_EINVAL;
    uint32_t length = 0, component = 0;
    while (path[start + length]) {
        unsigned char c = (unsigned char)path[start + length];
        if (length >= DS_IO_PATH_BYTES - sizeof(DS_IO_ROOT)) return DS_ENAMETOOLONG;
        if (c == ':' || c == '\\' || c < 32 || c == 127) return DS_EINVAL;
        if (c == '/') {
            if (!component || (component == 1 && path[start + length - 1] == '.') ||
                (component == 2 && path[start + length - 1] == '.' && path[start + length - 2] == '.')) return DS_EINVAL;
            component = 0;
        } else ++component;
        ++length;
    }
    if (!component || (component == 1 && path[start + length - 1] == '.') ||
        (component == 2 && path[start + length - 1] == '.' && path[start + length - 2] == '.')) return DS_EINVAL;
    uint32_t root_length = sizeof(DS_IO_ROOT) - 1;
    if (capacity <= root_length + length) return DS_ENAMETOOLONG;
    for (uint32_t i = 0; i < root_length; ++i) out[i] = DS_IO_ROOT[i];
    for (uint32_t i = 0; i <= length; ++i) out[root_length + i] = path[start + i];
    return 0;
}

void ds_io_init(DSIO *context, const DSIOOps *ops) {
    uint8_t *p = (uint8_t *)context;
    for (uint32_t i = 0; i < sizeof(*context); ++i) p[i] = 0;
    context->ops = *ops; current = context;
}
void ds_io_set_errno_provider(int32_t *(*provider)(void)) { errno_provider=provider; }
int32_t *DS_IO_SOFT ds_io_errno(void) { return errno_provider?errno_provider():current ? &current->error : &inactive_error; }
static int32_t fail(int32_t error) { *ds_io_errno() = error ? error : DS_EIO; return -1; }
static int index_for(int32_t fd) {
    if (!current || fd < DS_IO_FD_BASE || fd >= DS_IO_FD_BASE + DS_IO_FILES) return -1;
    int index = fd - DS_IO_FD_BASE;
    return current->handles[index] ? index : -1;
}
int32_t ds_io_adopt_handle(void *handle) {
    if (!current || !handle) return fail(DS_EIO);
    for (uint32_t i = 0; i < DS_IO_FILES; ++i) if (!current->handles[i]) {
        current->handles[i] = handle; ++current->opens; ++current->active;
        return DS_IO_FD_BASE + (int32_t)i;
    }
    return fail(DS_EMFILE);
}
void *ds_io_native_handle(int32_t fd) {
    int index = index_for(fd);
    if (index < 0) { fail(DS_EBADF); return NULL; }
    return current->handles[index];
}

int32_t DS_IO_SOFT ds_io_open(const char *path, int32_t flags, ...) {
    if (!current) return fail(DS_EIO);
    /* Android ARM: O_RDONLY=0, O_LARGEFILE=0x20000. Never pass flags to newlib. */
    if (flags & (3 | 0x40 | 0x200 | 0x400)) return fail(DS_EROFS);
    if ((uint32_t)flags & ~0x20000u) return fail(DS_EINVAL);
    char mapped[DS_IO_PATH_BYTES];
    int result = ds_io_map_path(path, mapped, sizeof(mapped));
    if (result) return fail(result);
    if (!current->ops.open) return fail(DS_EIO);
    for (uint32_t i = 0; i < DS_IO_FILES; ++i) {
        if (current->handles[i]) continue;
        int32_t error = 0;
        void *handle = current->ops.open(mapped, &error);
        if (!handle) return fail(error);
        current->handles[i] = handle; ++current->opens; ++current->active;
        return DS_IO_FD_BASE + (int32_t)i;
    }
    return fail(DS_EMFILE);
}
int32_t DS_IO_SOFT ds_io_read(int32_t fd, void *buffer, uint32_t count) {
    int index = index_for(fd);
    if (index < 0) return fail(DS_EBADF);
    if (count > 0x7fffffffu) return fail(DS_EINVAL);
    if (count && !buffer) return fail(DS_EFAULT);
    if (!count) return 0;
    if (!current->ops.read) return fail(DS_EIO);
    int32_t error = 0;
    int32_t n = current->ops.read(current->handles[index], buffer, count, &error);
    ++current->reads;
    if (n < 0) return fail(error);
    if ((uint32_t)n > count) return fail(DS_EIO);
    current->bytes += (uint32_t)n;
    return n;
}
int32_t DS_IO_SOFT ds_io_seek(int32_t fd, int32_t offset, int32_t whence) {
    int index = index_for(fd);
    if (index < 0) return fail(DS_EBADF);
    if (whence < 0 || whence > 2) return fail(DS_EINVAL);
    if (!current->ops.seek) return fail(DS_EIO);
    int32_t error = 0;
    int32_t result = current->ops.seek(current->handles[index], offset, whence, &error);
    ++current->seeks;
    return result < 0 ? fail(error) : result;
}
int32_t DS_IO_SOFT ds_io_close(int32_t fd) {
    int index = index_for(fd);
    if (index < 0) return fail(DS_EBADF);
    int32_t error = 0;
    int32_t result = current->ops.close ? current->ops.close(current->handles[index], &error) : -1;
    current->handles[index] = NULL; --current->active; ++current->closes;
    return result < 0 ? fail(error) : 0;
}
int ds_io_shutdown(DSIO *context) {
    if (context != current) return -1;
    int result = 0;
    for (int i = 0; i < DS_IO_FILES; ++i)
        if (context->handles[i] && ds_io_close(DS_IO_FD_BASE + i)) result = -1;
    current = NULL;
    return result;
}
uint32_t ds_io_bindings(DSBinding *bindings, uint32_t capacity) {
    if (capacity < 5) return 0;
    const DSBinding list[] = {
        {"open", (uint32_t)(uintptr_t)ds_io_open}, {"read", (uint32_t)(uintptr_t)ds_io_read},
        {"lseek", (uint32_t)(uintptr_t)ds_io_seek}, {"close", (uint32_t)(uintptr_t)ds_io_close},
        {"__errno", (uint32_t)(uintptr_t)ds_io_errno}
    };
    for (uint32_t i = 0; i < 5; ++i) bindings[i] = list[i];
    return 5;
}
uint32_t ds_io_context_size(void) { return sizeof(DSIO); }
