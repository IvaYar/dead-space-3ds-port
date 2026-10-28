#include "ds_io.h"
#include <stddef.h>
#include <stdarg.h>
#include <string.h>
void ds_fs_trace(const char *,const char *,int) __attribute__((weak));

static DSIO *current;
static int32_t inactive_error = DS_EIO;
static int32_t *(*errno_provider)(void);
static void (*closed_observer)(int32_t);
static void (*duplicated_observer)(int32_t,int32_t);
static uint32_t generations[DS_IO_FILES],next_generation;
static DSIOReadOverride read_override;
int ds_io_read_override(DSIOReadOverride next){if(ds_io_free_slots()!=DS_IO_FILES){*ds_io_errno()=16;return -1;}read_override=next;return 0;}
int ds_io_resolve_read_path(char *path){
    if(!read_override)return 0;
    char copy[DS_IO_PATH_BYTES];strcpy(copy,path);int result=read_override(copy,sizeof(copy));
    if(result)return result;
    if(!memchr(copy,0,sizeof(copy)))return DS_ENAMETOOLONG;
    strcpy(path,copy);return 0;
}
void ds_io_close_observer(void (*fn)(int32_t)){closed_observer=fn;}
void ds_io_dup_observer(void (*fn)(int32_t,int32_t)){duplicated_observer=fn;}
uint32_t ds_io_free_slots(void){
    uint32_t count=0;if(current)for(unsigned i=0;i<DS_IO_FILES;++i)count+=current->handles[i]==NULL;
    return count;
}

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
        "/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/published/",
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
    read_override=NULL;
    for(unsigned i=0;i<DS_IO_FILES;++i)generations[i]=0;
}
void ds_io_set_errno_provider(int32_t *(*provider)(void)) { errno_provider=provider; }
int32_t *DS_IO_SOFT ds_io_errno(void) { return errno_provider?errno_provider():current ? &current->error : &inactive_error; }
static int32_t fail(int32_t error) { *ds_io_errno() = error ? error : DS_EIO; return -1; }
static int32_t open_fail(const char *path,int32_t error){
    int32_t result=fail(error);
    if(ds_fs_trace)ds_fs_trace("open failure",path?path:"<null>",-*ds_io_errno());
    return result;
}
static int index_for(int32_t fd) {
    if (!current || fd < DS_IO_FD_BASE || fd >= DS_IO_FD_BASE + DS_IO_FILES) return -1;
    int index = fd - DS_IO_FD_BASE;
    return current->handles[index] ? index : -1;
}
static int32_t adopt_from(void *handle,uint32_t first) {
    if (!current || !handle) return fail(DS_EIO);
    if(next_generation==UINT32_MAX)return fail(DS_EOVERFLOW);
    for (uint32_t i = first; i < DS_IO_FILES; ++i) if (!current->handles[i]) {
        current->handles[i] = handle;generations[i]=++next_generation; ++current->opens; ++current->active;
        return DS_IO_FD_BASE + (int32_t)i;
    }
    return fail(DS_EMFILE);
}
int32_t ds_io_adopt_handle(void *handle){return adopt_from(handle,0);}
void *ds_io_native_handle(int32_t fd) {
    int index = index_for(fd);
    if (index < 0) { fail(DS_EBADF); return NULL; }
    return current->handles[index];
}
uint32_t ds_io_generation(int32_t fd){int i=index_for(fd);return i<0?0:generations[i];}
int32_t DS_IO_SOFT ds_io_dup(int32_t fd){
    int source=index_for(fd);if(source<0)return fail(DS_EBADF);
    int32_t result=ds_io_adopt_handle(current->handles[source]);
    if(result>=0 && duplicated_observer)duplicated_observer(fd,result);
    return result;
}
int32_t DS_IO_SOFT ds_io_fcntl(int32_t fd,int32_t command,...){
    int source=index_for(fd);if(source<0)return fail(DS_EBADF);
    if(command!=0){if(ds_fs_trace)ds_fs_trace("fcntl unsupported command","<descriptor>",command);return fail(DS_EINVAL);}
    va_list args;va_start(args,command);int32_t minimum=va_arg(args,int32_t);va_end(args);
    if(minimum<0 || minimum>=DS_IO_FD_BASE+DS_IO_FILES)return fail(DS_EINVAL);
    uint32_t first=minimum>DS_IO_FD_BASE?(uint32_t)(minimum-DS_IO_FD_BASE):0;
    int32_t result=adopt_from(current->handles[source],first);
    if(result>=0 && duplicated_observer)duplicated_observer(fd,result);
    return result;
}

int32_t DS_IO_SOFT ds_io_open(const char *path, int32_t flags, ...) {
    if (!current) return open_fail(path,DS_EIO);
    if(next_generation==UINT32_MAX)return open_fail(path,DS_EOVERFLOW);
    /* Android ARM: O_RDONLY=0, O_LARGEFILE=0x20000. Never pass flags to newlib. */
    if (flags & (3 | 0x40 | 0x200 | 0x400)) return open_fail(path,DS_EROFS);
    if ((uint32_t)flags & ~0x20000u) return open_fail(path,DS_EINVAL);
    char mapped[DS_IO_PATH_BYTES];
    int result = ds_io_map_path(path, mapped, sizeof(mapped));
    if(!result)result=ds_io_resolve_read_path(mapped);
    if (result) return open_fail(path,result);
    if (!current->ops.open) return open_fail(path,DS_EIO);
    for (uint32_t i = 0; i < DS_IO_FILES; ++i) {
        if (current->handles[i]) continue;
        int32_t error = 0;
        void *handle = current->ops.open(mapped, &error);
        if (!handle) return open_fail(path,error);
        current->handles[i] = handle;generations[i]=++next_generation; ++current->opens; ++current->active;
        if(ds_fs_trace)ds_fs_trace("open fd",path,DS_IO_FD_BASE+(int)i);
        return DS_IO_FD_BASE + (int32_t)i;
    }
    return open_fail(path,DS_EMFILE);
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
    int shared=0;for(unsigned i=0;i<DS_IO_FILES;++i)if((int)i!=index && current->handles[i]==current->handles[index])shared=1;
    int32_t result = shared?0:current->ops.close ? current->ops.close(current->handles[index], &error) : -1;
    current->handles[index] = NULL; --current->active; ++current->closes;
    generations[index]=0;
    if(closed_observer)closed_observer(fd);
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
