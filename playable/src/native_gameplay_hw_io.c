/* Hardware-profile-only SDK filesystem envelope. No buffers, threads or donor edits.
 * Reserve counts attempted bytes conservatively, including rewrites. All writes
 * and removes must target the exclusive run directory; resources are read-only. */
#include <3ds.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include "native_gameplay_hw_policy.h"
char ds_hw_pages_root[128],ds_hw_morton_root[128],ds_hw_appdata_root[96];
char ds_hw_run_root[128];
static LightLock hw_write_lock;
static uint32_t hw_written,hw_denied,hw_cleanup;
void ds_hw_io_init(void){LightLock_Init(&hw_write_lock);}
void ds_hw_io_cleanup(void){hw_cleanup=1;}
uint32_t ds_hw_io_bytes(void){return __atomic_load_n(&hw_written,__ATOMIC_ACQUIRE);}
uint32_t ds_hw_io_denied(void){return __atomic_load_n(&hw_denied,__ATOMIC_ACQUIRE);}
static int allowed(const char *p){
    size_t n=strlen(ds_hw_run_root);
    return n && !strncmp(p,ds_hw_run_root,n) && !strstr(p,"..") && !strchr(p,'\\');
}
static int reserve(FILE *f,size_t bytes){
    if(f==stdout || f==stderr)return 0;
    LightLock_Lock(&hw_write_lock);
    int bad=bytes>UINT32_MAX || hw_budget_take(&hw_written,(uint32_t)bytes,(int)hw_cleanup);
    if(bad)++hw_denied;
    LightLock_Unlock(&hw_write_lock);
    if(bad)errno=ENOSPC;
    return bad?-1:0;
}
FILE *__real_fopen(const char *,const char *);
FILE *__wrap_fopen(const char *p,const char *mode){
    if((strchr(mode,'w') || strchr(mode,'a') || strchr(mode,'+')) && !allowed(p)){
        __atomic_fetch_add(&hw_denied,1,__ATOMIC_RELEASE);errno=EACCES;return NULL;
    }
    return __real_fopen(p,mode);
}
size_t __real_fwrite(const void *,size_t,size_t,FILE *);
size_t __wrap_fwrite(const void *p,size_t size,size_t count,FILE *f){
    if(size && count>SIZE_MAX/size){errno=EOVERFLOW;return 0;}
    if(reserve(f,size*count))return 0;
    return __real_fwrite(p,size,count,f);
}
int __real_vfprintf(FILE *,const char *,va_list);
int __wrap_vfprintf(FILE *f,const char *fmt,va_list args){
    va_list copy;va_copy(copy,args);int n=vsnprintf(NULL,0,fmt,copy);va_end(copy);
    if(n<0 || reserve(f,(size_t)n))return -1;
    return __real_vfprintf(f,fmt,args);
}
int __wrap_fprintf(FILE *f,const char *fmt,...){
    va_list args;va_start(args,fmt);int n=__wrap_vfprintf(f,fmt,args);va_end(args);return n;
}
int __real_fputs(const char *,FILE *);
int __wrap_fputs(const char *p,FILE *f){if(reserve(f,strlen(p)))return EOF;return __real_fputs(p,f);}
int __real_remove(const char *);
int __wrap_remove(const char *p){if(!allowed(p)){errno=EACCES;return -1;}return __real_remove(p);}
