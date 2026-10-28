#include "ds24_files.h"
#include <stdarg.h>
#include <string.h>
static const DS24Ops *ops;
static struct {void *handle;uint32_t flags;} owned[DS_IO_FILES];
void ds_fs_trace(const char *,const char *,int) __attribute__((weak));
static int fail(int error){*ds_io_errno()=error?error:DS_EIO;return -1;}
static void closed(int32_t fd){if(fd>=DS_IO_FD_BASE && fd<DS_IO_FD_BASE+DS_IO_FILES)memset(&owned[fd-DS_IO_FD_BASE],0,sizeof(owned[0]));}
static void duplicated(int32_t from,int32_t to){owned[to-DS_IO_FD_BASE]=owned[from-DS_IO_FD_BASE];}
int ds24_init(const DS24Ops *next){
    if(ops || !next || !next->open || !next->read || !next->write || !next->discard)return -1;
    memset(owned,0,sizeof(owned));ops=next;ds_io_close_observer(closed);ds_io_dup_observer(duplicated);return 0;
}
uint32_t ds24_shutdown(void){
    uint32_t count=0;for(unsigned i=0;i<DS_IO_FILES;++i)if(owned[i].handle){ds_io_close(DS_IO_FD_BASE+(int32_t)i);++count;}
    ops=NULL;ds_io_close_observer(NULL);ds_io_dup_observer(NULL);return count;
}
int32_t DS_IO_SOFT ds24_open(const char *path,int32_t flags,...){
    if(!path)return fail(DS_EFAULT);
    if(strncmp(path,"appdata:/",9))return ds_io_open(path,flags);
    if(!ops)return fail(DS_EIO);
    uint32_t allowed=3|DS24_CREAT|DS24_EXCL|DS24_TRUNC|DS24_APPEND|DS24_LARGEFILE;
    if(((uint32_t)flags&~allowed) || (flags&3)==3 || ((flags&DS24_EXCL) && !(flags&DS24_CREAT)) ||
       ((flags&DS24_TRUNC) && !(flags&3)))return fail(DS_EINVAL);
    uint32_t mode=0;if(flags&DS24_CREAT){va_list args;va_start(args,flags);mode=va_arg(args,uint32_t);va_end(args);if(mode&~07777u)return fail(DS_EINVAL);}
    char mapped[DS_IO_PATH_BYTES];if(ds6_map_path(path,mapped,(flags&3)!=0))return -1;
    if(!ds_io_free_slots())return fail(DS_EMFILE);
    int32_t error=0;void *handle=ops->open(mapped,(uint32_t)flags,mode,&error);
    if(!handle){if(ds_fs_trace)ds_fs_trace("private open failure",path,-error);return fail(error);}
    int32_t fd=ds_io_adopt_handle(handle);
    if(fd<0){int32_t saved=*ds_io_errno();ops->discard(handle,&error);return fail(saved);}
    owned[fd-DS_IO_FD_BASE].handle=handle;owned[fd-DS_IO_FD_BASE].flags=(uint32_t)flags;
    if(ds_fs_trace)ds_fs_trace("private open",path,fd);
    return fd;
}
static int index_for(int32_t fd){
    if(!ops || fd<DS_IO_FD_BASE || fd>=DS_IO_FD_BASE+DS_IO_FILES)return -1;
    int i=fd-DS_IO_FD_BASE;
    return owned[i].handle && ds_io_native_handle(fd)==owned[i].handle?i:-1;
}
int32_t DS_IO_SOFT ds24_read(int32_t fd,void *out,uint32_t bytes){
    int i=index_for(fd);if(i<0)return ds_io_read(fd,out,bytes);
    if((owned[i].flags&3)==DS24_WRONLY)return fail(DS_EBADF);
    if(bytes>INT32_MAX)return fail(DS_EINVAL);
    if(bytes && !out)return fail(DS_EFAULT);
    if(!bytes)return 0;
    int32_t error=0,result=ops->read(owned[i].handle,out,bytes,&error);
    return result<0?fail(error):(uint32_t)result>bytes?fail(DS_EIO):result;
}
int32_t DS_IO_SOFT ds24_write(int32_t fd,const void *in,uint32_t bytes){
    int i=index_for(fd);if(i<0 || !(owned[i].flags&3))return fail(DS_EBADF);
    if(bytes>INT32_MAX)return fail(DS_EINVAL);
    if(bytes && !in)return fail(DS_EFAULT);
    if(!bytes)return 0;
    int32_t error=0,result=ops->write(owned[i].handle,in,bytes,&error);
    if(ds_fs_trace && result<0)ds_fs_trace("private write failure","<descriptor>",-error);
    return result<0?fail(error):(uint32_t)result>bytes?fail(DS_EIO):result;
}
uint32_t ds24_bindings(DSBinding *out,uint32_t capacity){
    if(!out || capacity<5)return 0;
    const DSBinding list[]={{"open",(uint32_t)ds24_open},{"read",(uint32_t)ds24_read},{"write",(uint32_t)ds24_write},
        {"close",(uint32_t)ds_io_close},{"lseek",(uint32_t)ds_io_seek}};
    memcpy(out,list,sizeof(list));return 5;
}
