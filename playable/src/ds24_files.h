#ifndef DS24_FILES_H
#define DS24_FILES_H
#include "ds6.h"
/* Android ARM flags, decoded before the native backend sees them. */
enum {DS24_WRONLY=1,DS24_RDWR=2,DS24_CREAT=0x40,DS24_EXCL=0x80,
      DS24_TRUNC=0x200,DS24_APPEND=0x400,DS24_LARGEFILE=0x20000};
typedef struct {
    void *(*open)(const char *,uint32_t flags,uint32_t mode,int32_t *error);
    int32_t (*read)(void *,void *,uint32_t,int32_t *error);
    int32_t (*write)(void *,const void *,uint32_t,int32_t *error);
    int32_t (*discard)(void *,int32_t *error);
} DS24Ops;
/* Uses the existing bounded descriptor pool, compatible with fstat/fdopen.
 * Caller serializes file operations and closes all users before shutdown. */
int ds24_init(const DS24Ops *);
uint32_t ds24_shutdown(void);
int32_t DS_IO_SOFT ds24_open(const char *,int32_t flags,...);
int32_t DS_IO_SOFT ds24_read(int32_t,void *,uint32_t);
int32_t DS_IO_SOFT ds24_write(int32_t,const void *,uint32_t);
uint32_t ds24_bindings(DSBinding *,uint32_t);
const DS24Ops *ds24_native_ops(void);
#endif
