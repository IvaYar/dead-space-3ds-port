#ifndef DS_IO_H
#define DS_IO_H
#include <stdint.h>
#include "ds_elf.h"

#define DS_IO_SOFT __attribute__((pcs("aapcs")))
#define DS_IO_FILES 8
#define DS_IO_PATH_BYTES 512
#define DS_IO_FD_BASE 1024
#define DS_IO_ROOT "sdmc:/3ds/deadspace/assets/published/"
/* Android ARM errno values, independent of the host C library's constants. */
enum { DS_ENOENT=2, DS_EIO=5, DS_EBADF=9, DS_EFAULT=14, DS_EINVAL=22,
       DS_EMFILE=24, DS_EROFS=30, DS_ENAMETOOLONG=36, DS_EOVERFLOW=75 };

/* Native callbacks consume private host handles; close consumes even on error. */
typedef struct {
    void *(*open)(const char *path, int32_t *error);
    int32_t (*read)(void *handle, void *buffer, uint32_t count, int32_t *error);
    int32_t (*seek)(void *handle, int32_t offset, int32_t whence, int32_t *error);
    int32_t (*close)(void *handle, int32_t *error);
} DSIOOps;
typedef struct {
    DSIOOps ops;
    void *handles[DS_IO_FILES];
    int32_t error;
    uint32_t opens, reads, seeks, closes, bytes, active;
} DSIO;

/* One active, single-threaded context. Shut it down before reinitializing. */
void ds_io_init(DSIO *context, const DSIOOps *ops);
int ds_io_shutdown(DSIO *context);
int ds_io_map_path(const char *path, char *out, uint32_t capacity);
uint32_t ds_io_bindings(DSBinding *bindings, uint32_t capacity);
uint32_t ds_io_context_size(void);
/* Internal adapter for stdio using this same native backend and descriptor pool. */
int32_t ds_io_adopt_handle(void *handle);
void *ds_io_native_handle(int32_t fd);
int32_t DS_IO_SOFT ds_io_open(const char *path, int32_t flags, ...);
int32_t DS_IO_SOFT ds_io_read(int32_t fd, void *buffer, uint32_t count);
int32_t DS_IO_SOFT ds_io_seek(int32_t fd, int32_t offset, int32_t whence);
int32_t DS_IO_SOFT ds_io_close(int32_t fd);
int32_t *DS_IO_SOFT ds_io_errno(void);
void ds_io_set_errno_provider(int32_t *(*provider)(void));
const DSIOOps *ds_io_sd_ops(void);
#endif
