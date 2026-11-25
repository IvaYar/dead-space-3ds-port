#define _GNU_SOURCE
#include "ds24_files.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
void ds_fs_trace(const char *,const char *,int) __attribute__((weak));
static void *open_file(const char *path,uint32_t flags,uint32_t mode,int32_t *error){
    int access=(flags&3)==DS24_RDWR?O_RDWR:(flags&3)==DS24_WRONLY?O_WRONLY:O_RDONLY;
    int native=access;
    if(flags&DS24_CREAT)native|=O_CREAT;
    if(flags&DS24_EXCL)native|=O_EXCL;
    if(flags&DS24_TRUNC)native|=O_TRUNC;
    if(flags&DS24_APPEND)native|=O_APPEND;
    int fd=open(path,native,(mode_t)(mode&0777u));
    if(fd<0){int saved=errno;if(ds_fs_trace)ds_fs_trace("private native open errno",path,saved);*error=ds6_host_error(saved);return NULL;}
    FILE *file=fdopen(fd,access==O_RDWR?"r+b":access==O_WRONLY?"wb":"rb");
    if(!file){int saved=errno;close(fd);*error=ds6_host_error(saved);return NULL;}
    /* POSIX descriptor writes must be visible to other descriptors at once. */
    if(setvbuf(file,NULL,_IONBF,0)){fclose(file);*error=DS_EIO;return NULL;}
    return file;
}
static int32_t read_file(void *handle,void *out,uint32_t n,int32_t *error){
    FILE *file=handle;clearerr(file);size_t result=fread(out,1,n,file);
    if(!result && ferror(file)){*error=ds6_host_error(errno);return -1;}return (int32_t)result;
}
static int32_t write_file(void *handle,const void *in,uint32_t n,int32_t *error){
    FILE *file=handle;size_t result=fwrite(in,1,n,file);
    if(!result && ferror(file)){*error=ds6_host_error(errno);return -1;}return (int32_t)result;
}
static int32_t close_file(void *handle,int32_t *error){int result=fclose(handle);if(result)*error=ds6_host_error(errno);return result?-1:0;}
const DS24Ops *ds24_native_ops(void){static const DS24Ops native={open_file,read_file,write_file,close_file};return &native;}
