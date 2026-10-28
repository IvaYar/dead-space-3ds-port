#define _GNU_SOURCE
#include "ds6.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
enum { READ=4,WRITE=8,EOF_FLAG=32,ERROR_FLAG=64,COUNT=3+DS_IO_FILES };
static DS6File files[COUNT];
static FILE *native[COUNT];
static int used[COUNT],orientation[COUNT];
static char appdata_root[96]="sdmc:/3ds/deadspace/test-output/";
void ds_fs_trace(const char *,const char *,int) __attribute__((weak));
static int fail(int error) { *ds_io_errno()=error; return -1; }
int ds6_appdata_namespace(const char *name){
    if(!name)return fail(22);
    size_t n=strlen(name);if(n>32)return fail(36);
    for(size_t i=0;i<n;++i)if(!((name[i]>='a' && name[i]<='z') || (name[i]>='A' && name[i]<='Z') ||
        (name[i]>='0' && name[i]<='9') || name[i]=='_' || name[i]=='-'))return fail(22);
    for(unsigned i=3;i<COUNT;++i)if(used[i])return fail(16);
    if(ds_io_free_slots()!=DS_IO_FILES)return fail(16);
    strcpy(appdata_root,"sdmc:/3ds/deadspace/test-output/");
    if(n){strcat(appdata_root,name);strcat(appdata_root,"/");}return 0;
}
static int index_for(DS6File *file) {
    for(int i=0;i<COUNT;++i) if(file==&files[i] && used[i]) {
        if(i>=3 && ds_io_native_handle(file->fd)!=native[i]) return -1;
        return i;
    }
    fail(9); return -1;
}
static void sync_flags(int i) {
    if(feof(native[i])) files[i].flags|=EOF_FLAG; else files[i].flags&=~EOF_FLAG;
    if(ferror(native[i])) files[i].flags|=ERROR_FLAG;
}
static int byte_stream(DS6File *file) {
    int i=index_for(file); if(i<0) return -1;
    if(orientation[i]>0) { file->flags|=ERROR_FLAG; return fail(22); }
    orientation[i]=-1; return i;
}
static int DS_IO_SOFT cookie_read(void *cookie,char *out,int n) { return n<0?fail(22):(int)ds6_fread(out,1,(size_t)n,cookie); }
static int DS_IO_SOFT cookie_write(void *cookie,const char *in,int n) { return n<0?fail(22):(int)ds6_fwrite(in,1,(size_t)n,cookie); }
static int32_t DS_IO_SOFT cookie_seek(void *cookie,int32_t offset,int whence) { return ds6_fseek(cookie,offset,whence)?-1:ds6_ftell(cookie); }
static void setup(int i,int flags,int fd) {
    memset(&files[i],0,sizeof(files[i])); used[i]=1; orientation[i]=0;
    files[i].flags=flags|2; files[i].fd=(int16_t)fd;
    files[i].p=(uint32_t)&files[i].nbuf; files[i].cookie=(uint32_t)&files[i];
    files[i].close=(uint32_t)ds6_fclose; files[i].read=(uint32_t)cookie_read;
    files[i].write=(uint32_t)cookie_write; files[i].seek=(uint32_t)cookie_seek;
}
void ds6_stdio_init(void) {
    strcpy(appdata_root,"sdmc:/3ds/deadspace/test-output/");
    native[0]=stdin; native[1]=stdout; native[2]=stderr;
    for(int i=0;i<3;++i) setup(i,i?WRITE:READ,i);
    orientation[1]=orientation[2]=-1;
}
int ds6_map_path(const char *path,char out[DS_IO_PATH_BYTES],int writable) {
    if(!path) return fail(14);
    if(!strncmp(path,"appdata:/",9)) {
        char logical[DS_IO_PATH_BYTES],mapped[DS_IO_PATH_BYTES];
        const char *relative=path+9;if(*relative=='/')++relative;
        if(*relative=='/')return fail(22);
        size_t length=strlen(relative);if(length && relative[length-1]=='/')--length;
        if(!length){strcpy(out,appdata_root);return 0;}
        if(length+11>=sizeof(logical)) return fail(36);
        strcpy(logical,"published/");memcpy(logical+10,relative,length);logical[10+length]=0;
        int result=ds_io_map_path(logical,mapped,sizeof(mapped));
        if(result) return fail(result);
        size_t tail=strlen(mapped+sizeof(DS_IO_ROOT)-1);
        if(strlen(appdata_root)+tail>=DS_IO_PATH_BYTES)return fail(36);
        strcpy(out,appdata_root); strcat(out,mapped+sizeof(DS_IO_ROOT)-1);
        return 0;
    }
    if(writable) return fail(30);
    if(!strcmp(path,"/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/Downloaded.indicate")){strcpy(out,"sdmc:/3ds/deadspace/assets/Downloaded.indicate");return 0;}
    if(!strcmp(path,"/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/published") || !strcmp(path,"/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/published/")){strcpy(out,DS_IO_ROOT);return 0;}
    if(!strcmp(path,"/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/") || !strcmp(path,"/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace")){strcpy(out,"sdmc:/3ds/deadspace/assets/");return 0;}
    if(!strcmp(path,"appbundle:/published/") || !strcmp(path,DS_IO_ROOT) || !strcmp(path,"published/")) { strcpy(out,DS_IO_ROOT); return 0; }
    char logical[DS_IO_PATH_BYTES];size_t n=strlen(path);
    if(n>=sizeof(logical))return fail(36);
    if(n && path[n-1]=='/'){memcpy(logical,path,n-1);logical[n-1]=0;path=logical;}
    int result=ds_io_map_path(path,out,DS_IO_PATH_BYTES);
    if(!result)result=ds_io_resolve_read_path(out);
    return result?fail(result):0;
}
DS6File *DS_IO_SOFT ds6_fopen(const char *path,const char *mode) {
    if(!mode) { fail(14); return NULL; }
    int flags=0,writable=0;
    const char *modes[]={"r","rb","r+","rb+","r+b","w","wb","w+","wb+","w+b","a","ab","a+","ab+","a+b"};
    for(uint32_t i=0;i<sizeof(modes)/sizeof(modes[0]);++i) if(!strcmp(mode,modes[i])) {
        writable=mode[0]!='r' || strchr(mode,'+'); flags=strchr(mode,'+')?16:(writable?WRITE:READ); break;
    }
    if(!flags) { fail(22); return NULL; }
    char mapped[DS_IO_PATH_BYTES]; if(ds6_map_path(path,mapped,writable)) return NULL;
    for(int i=3;i<COUNT;++i) if(!used[i]) {
        FILE *handle=fopen(mapped,mode);
        if(!handle) { ds6_result_error(-1);if(ds_fs_trace)ds_fs_trace("fopen failure",path,-*ds_io_errno());return NULL; }
        int fd=ds_io_adopt_handle(handle);
        if(fd<0) { fclose(handle); return NULL; }
        native[i]=handle; setup(i,flags,fd);if(ds_fs_trace)ds_fs_trace("fopen fd",path,fd);return &files[i];
    }
    fail(24); return NULL;
}
int DS_IO_SOFT ds6_fclose(DS6File *file) {
    int i=index_for(file); if(i<0) return -1;
    int result=i<3?0:ds_io_close(file->fd);
    used[i]=0; native[i]=NULL; files[i].flags=0; return result;
}
uint32_t ds6_stdio_cleanup(void) {
    uint32_t remaining=0;
    for(int i=3;i<COUNT;++i) if(used[i]) { ++remaining; ds6_fclose(&files[i]); }
    return remaining;
}
size_t DS_IO_SOFT ds6_fread(void *out,size_t size,size_t count,DS6File *file) {
    if(!size || !count) return 0;
    int i=byte_stream(file); if(i<0) return 0;
    if((uint64_t)size*count>UINT32_MAX) { file->flags|=ERROR_FLAG; fail(75); return 0; }
    size_t result=fread(out,size,count,native[i]); sync_flags(i);
    if(ferror(native[i])) ds6_result_error(-1);
    return result;
}
size_t DS_IO_SOFT ds6_fwrite(const void *in,size_t size,size_t count,DS6File *file) {
    if(!size || !count) return 0;
    int i=byte_stream(file); if(i<0) return 0;
    if((uint64_t)size*count>UINT32_MAX) { file->flags|=ERROR_FLAG; fail(75); return 0; }
    size_t result=fwrite(in,size,count,native[i]); sync_flags(i);
    if(result<count) ds6_result_error(-1);
    return result;
}
int DS_IO_SOFT ds6_fseek(DS6File *file,int32_t offset,int whence) {
    int i=index_for(file); if(i<0) return -1;
    if(whence<0 || whence>2) return fail(22);
    long old=ftell(native[i]); if(old<0) { ds6_result_error(-1); return -1; }
    int64_t base=whence==1?old:0;
    if(whence==2) {
        if(fseek(native[i],0,SEEK_END)) { ds6_result_error(-1); return -1; }
        long end=ftell(native[i]);
        if(fseek(native[i],old,SEEK_SET)) { ds6_result_error(-1); return -1; }
        if(end<0) return fail(75);
        base=end;
    }
    int64_t target=base+offset;
    if(target<0 || target>INT32_MAX) return fail(target<0?22:75);
    int result=fseek(native[i],(long)target,SEEK_SET); ds6_result_error(result); sync_flags(i); return result;
}
int32_t DS_IO_SOFT ds6_ftell(DS6File *file) {
    int i=index_for(file); if(i<0) return -1;
    long value=ftell(native[i]); if(value<0) ds6_result_error(-1); return value;
}
int DS_IO_SOFT ds6_fflush(DS6File *file) {
    if(!file) {
        int result=0; for(int i=0;i<COUNT;++i) if(used[i] && ds6_fflush(&files[i])) result=-1;
        return result;
    }
    int i=index_for(file); if(i<0) return -1;
    int result=fflush(native[i]); ds6_result_error(result); sync_flags(i); return result;
}
int DS_IO_SOFT ds6_fgetc(DS6File *file) {
    int i=byte_stream(file); if(i<0) return -1;
    int result=fgetc(native[i]); sync_flags(i); if(ferror(native[i])) ds6_result_error(-1); return result;
}
char *DS_IO_SOFT ds6_fgets(char *out,int count,DS6File *file) {
    int i=byte_stream(file); if(i<0) return NULL;
    if(count<=0) { fail(22); return NULL; }
    char *result=fgets(out,count,native[i]); sync_flags(i); if(ferror(native[i])) ds6_result_error(-1); return result;
}
int DS_IO_SOFT ds6_ungetc(int value,DS6File *file) {
    int i=byte_stream(file); if(i<0) return -1;
    int result=ungetc(value,native[i]); sync_flags(i); return result;
}
int DS_IO_SOFT ds6_fputs(const char *text,DS6File *file) {
    int i=byte_stream(file); if(i<0) return -1;
    int result=fputs(text,native[i]); sync_flags(i); ds6_result_error(result); return result;
}
int DS_IO_SOFT ds6_fprintf(DS6File *file,const char *format,...) {
    int i=byte_stream(file); if(i<0) return -1;
    va_list args; va_start(args,format); int result=vfprintf(native[i],format,args); va_end(args);
    sync_flags(i); ds6_result_error(result); return result;
}
int DS_IO_SOFT ds6_fwide(DS6File *file,int mode) {
    int i=index_for(file); if(i<0) return 0;
    if(!orientation[i] && mode) orientation[i]=mode>0?1:-1;
    return orientation[i];
}
static void put32(uint8_t *p,uint32_t value) { for(int i=0;i<4;++i) p[i]=(uint8_t)(value>>(i*8)); }
static void put64(uint8_t *p,uint64_t value) { put32(p,(uint32_t)value); put32(p+4,(uint32_t)(value>>32)); }
int ds6_stat_pack(void *out,const void *native_stat) {
    if(!out || !native_stat) return fail(14);
    const struct stat *s=native_stat;
    if(s->st_atime<INT32_MIN || s->st_atime>INT32_MAX || s->st_mtime<INT32_MIN || s->st_mtime>INT32_MAX ||
       s->st_ctime<INT32_MIN || s->st_ctime>INT32_MAX) return fail(75);
    uint8_t packed[104]={0};
    put64(packed,s->st_dev); put32(packed+12,(uint32_t)s->st_ino); put32(packed+16,s->st_mode);
    put32(packed+20,s->st_nlink); put32(packed+24,s->st_uid); put32(packed+28,s->st_gid);
    put64(packed+32,s->st_rdev); put64(packed+48,(uint64_t)s->st_size); put32(packed+56,s->st_blksize);
    put64(packed+64,s->st_blocks); put32(packed+72,(uint32_t)s->st_atime); put32(packed+76,s->st_atim.tv_nsec);
    put32(packed+80,(uint32_t)s->st_mtime); put32(packed+84,s->st_mtim.tv_nsec);
    put32(packed+88,(uint32_t)s->st_ctime); put32(packed+92,s->st_ctim.tv_nsec); put64(packed+96,s->st_ino);
    memcpy(out,packed,sizeof(packed)); return 0;
}
int DS_IO_SOFT ds6_stat(const char *path,void *out) {
    if(ds_fs_trace)ds_fs_trace("stat begin",path?path:"<null>",0);
    if(!out) return fail(14);
    char mapped[DS_IO_PATH_BYTES];
    if(path && !strcmp(path,"/"))strcpy(mapped,"sdmc:/3ds/deadspace/");
    else if(ds6_map_path(path,mapped,0)) return -1;
    if(ds_fs_trace)ds_fs_trace("stat mapped",mapped,0);
    struct stat s={0}; int result=stat(mapped,&s);
    if(ds_fs_trace)ds_fs_trace("stat native",mapped,result);
    ds6_result_error(result);
    if(ds_fs_trace)ds_fs_trace("stat end",mapped,result);
    return result?-1:ds6_stat_pack(out,&s);
}
int DS_IO_SOFT ds6_mkdir(const char *path,uint32_t mode){
    if(ds_fs_trace)ds_fs_trace("mkdir begin",path?path:"<null>",0);
    char mapped[DS_IO_PATH_BYTES];if(ds6_map_path(path,mapped,1))return -1;
    if(mode&~07777u)return fail(22);
    int result=mkdir(mapped,mode&0777u);ds6_result_error(result);
    if(ds_fs_trace)ds_fs_trace("mkdir end",mapped,result);
    return result;
}
int DS_IO_SOFT ds6_fstat(int fd,void *out) {
    if(!out) return fail(14);
    FILE *handle=ds_io_native_handle(fd); if(!handle) return -1;
    struct stat s={0}; int result=fstat(fileno(handle),&s); ds6_result_error(result);
    return result?-1:ds6_stat_pack(out,&s);
}
int DS_IO_SOFT ds6_remove(const char *path) {
    char mapped[DS_IO_PATH_BYTES]; if(ds6_map_path(path,mapped,1)) return -1;
    int result=remove(mapped); ds6_result_error(result); return result;
}
int DS_IO_SOFT ds6_rename(const char *old_path,const char *new_path) {
    char old[DS_IO_PATH_BYTES],next[DS_IO_PATH_BYTES];
    if(ds6_map_path(old_path,old,1) || ds6_map_path(new_path,next,1)) return -1;
    int result=rename(old,next); ds6_result_error(result); return result;
}
uint32_t ds6_stdio_bindings(DSBinding *out,uint32_t capacity) {
    const DSBinding list[]={
        {"fopen",(uint32_t)ds6_fopen},{"fclose",(uint32_t)ds6_fclose},{"fread",(uint32_t)ds6_fread},{"fwrite",(uint32_t)ds6_fwrite},
        {"fseek",(uint32_t)ds6_fseek},{"ftell",(uint32_t)ds6_ftell},{"fflush",(uint32_t)ds6_fflush},{"fgetc",(uint32_t)ds6_fgetc},
        {"fgets",(uint32_t)ds6_fgets},{"ungetc",(uint32_t)ds6_ungetc},{"fputs",(uint32_t)ds6_fputs},{"fprintf",(uint32_t)ds6_fprintf},
        {"fwide",(uint32_t)ds6_fwide},{"__sF",(uint32_t)files},{"stat",(uint32_t)ds6_stat},{"fstat",(uint32_t)ds6_fstat},
        {"remove",(uint32_t)ds6_remove},{"rename",(uint32_t)ds6_rename}
    };
    uint32_t count=sizeof(list)/sizeof(list[0]); if(capacity<count) return 0;
    for(uint32_t i=0;i<count;++i) out[i]=list[i];
    return count;
}
