#ifndef DS20_DIRS_H
#define DS20_DIRS_H
#include "ds6.h"
#include <stddef.h>
#define DS20_DIRS 8
typedef struct {uint64_t ino;int64_t off;uint16_t reclen;uint8_t type;char name[256];} DS20Dirent;
_Static_assert(sizeof(DS20Dirent)==280 && offsetof(DS20Dirent,name)==19,"Gingerbread ARM dirent64 ABI");
typedef struct {uint64_t ino;uint32_t type;char name[256];} DS20HostEntry;
typedef struct {
    void *(*open)(const char *,int *);
    int (*next)(void *,DS20HostEntry *,int *); /* 1 entry, 0 EOF, -1 error */
    int (*close)(void *,int *); /* consumes handle even on error */
} DS20Ops;
int ds20_init(const DS20Ops *);
uint32_t ds20_active(void);
void *DS_IO_SOFT ds20_opendir(const char *);
int DS_IO_SOFT ds20_readdir_r(void *,DS20Dirent *,DS20Dirent **);
int DS_IO_SOFT ds20_closedir(void *);
uint32_t ds20_bindings(DSBinding *,uint32_t);
const DS20Ops *ds20_native_ops(void);
#endif
