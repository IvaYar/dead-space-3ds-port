#ifndef DS6_H
#define DS6_H
#include <stdarg.h>
#include <stdint.h>
#include "ds_runtime.h"
/* ARM32 Bionic ABI, not native newlib structures. Pointer fields are 32 bits. */
typedef struct {
    uint32_t p; int32_t r, w; int16_t flags, fd;
    uint32_t buffer; int32_t buffer_size, line_size;
    uint32_t cookie, close, read, seek, write, extension; int32_t extension_size;
    uint32_t unget; int32_t unget_size; uint8_t ubuf[3], nbuf;
    uint32_t line; int32_t line_capacity, block_size, offset;
} DS6File;
_Static_assert(sizeof(DS6File)==84, "Bionic FILE size");
_Static_assert(offsetof(DS6File,flags)==12 && offsetof(DS6File,fd)==14 && offsetof(DS6File,offset)==80,"Bionic FILE offsets");
typedef struct { int32_t sec, nsec; } DS6Time;
typedef struct { int32_t field[9], offset; uint32_t zone; } DS6TM;
typedef void (*DS6Log)(const char *text);
int ds6_init(DS6Log log);
uint32_t ds6_cleanup(void);
uint32_t ds6_basics_bindings(DSBinding *out,uint32_t capacity);
uint32_t ds6_stdio_bindings(DSBinding *out,uint32_t capacity);
uint32_t ds6_time_bindings(DSBinding *out,uint32_t capacity);
uint32_t ds6_bindings(DSBinding *out,uint32_t capacity);
void ds6_basics_init(DS6Log log);
void ds6_basics_cleanup(void);
void ds6_stdio_init(void);
uint32_t ds6_stdio_cleanup(void);
void ds6_time_init(void);
int ds6_native_clock(int id,DS6Time *out);
int ds6_native_sleep(const DS6Time *request);
int ds6_host_error(int error);
void ds6_result_error(int result);
int ds6_map_path(const char *path,char out[DS_IO_PATH_BYTES],int writable);
int ds6_stat_pack(void *out,const void *native_stat);
int DS_IO_SOFT ds6_snprintf(char *out,size_t size,const char *format,...);
int DS_IO_SOFT ds6_sprintf(char *out,const char *format,...);
int DS_IO_SOFT ds6_sscanf(const char *in,const char *format,...);
int DS_IO_SOFT ds6_vsnprintf(char *out,size_t size,const char *format,va_list args);
int DS_IO_SOFT ds6_vsprintf(char *out,const char *format,va_list args);
int DS_IO_SOFT ds6_vsscanf(const char *in,const char *format,va_list args);
DS6File *DS_IO_SOFT ds6_fopen(const char *path,const char *mode);
int DS_IO_SOFT ds6_fclose(DS6File *file);
size_t DS_IO_SOFT ds6_fread(void *out,size_t size,size_t count,DS6File *file);
size_t DS_IO_SOFT ds6_fwrite(const void *in,size_t size,size_t count,DS6File *file);
int DS_IO_SOFT ds6_fseek(DS6File *file,int32_t offset,int whence);
int32_t DS_IO_SOFT ds6_ftell(DS6File *file);
int DS_IO_SOFT ds6_fflush(DS6File *file);
int DS_IO_SOFT ds6_fgetc(DS6File *file);
char *DS_IO_SOFT ds6_fgets(char *out,int count,DS6File *file);
int DS_IO_SOFT ds6_ungetc(int value,DS6File *file);
int DS_IO_SOFT ds6_fputs(const char *text,DS6File *file);
int DS_IO_SOFT ds6_fprintf(DS6File *file,const char *format,...);
int DS_IO_SOFT ds6_fwide(DS6File *file,int mode);
int DS_IO_SOFT ds6_stat(const char *path,void *out);
int DS_IO_SOFT ds6_mkdir(const char *path,uint32_t mode);
int DS_IO_SOFT ds6_fstat(int fd,void *out);
int DS_IO_SOFT ds6_remove(const char *path);
int DS_IO_SOFT ds6_rename(const char *old_path,const char *new_path);
int DS_IO_SOFT ds6_gettimeofday(DS6Time *out,void *zone);
int DS_IO_SOFT ds6_clock_gettime(int id,DS6Time *out);
int32_t DS_IO_SOFT ds6_time(int32_t *out);
DS6TM *DS_IO_SOFT ds6_gmtime(const int32_t *seconds);
DS6TM *DS_IO_SOFT ds6_localtime(const int32_t *seconds);
int32_t DS_IO_SOFT ds6_mktime(DS6TM *calendar);
int DS_IO_SOFT ds6_nanosleep(const DS6Time *request,DS6Time *remaining);
int DS_IO_SOFT ds6_usleep(uint32_t microseconds);
int DS_IO_SOFT ds6_sched_yield(void);
int32_t DS_IO_SOFT ds6_sysconf(int name);
#endif
