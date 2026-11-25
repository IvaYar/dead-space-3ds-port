#define _GNU_SOURCE
#include "ds6.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
_Static_assert(sizeof(va_list)==4 && sizeof(wchar_t)==4,"ARM32 varargs and wchar_t");
static uint8_t character_flags[257];
static int16_t lowercase[257],uppercase[257];
static const uint8_t *ctype_pointer=character_flags;
static const int16_t *lower_pointer=lowercase,*upper_pointer=uppercase;
static uint32_t page_size=4096;
static char *env_names[16],*env_values[16];
static DS6Log logger;
static uint64_t random_state;

int ds6_host_error(int error) {
    /* The native 3DS file device can return a raw Horizon FS Result in errno.
     * Decode only identified FS descriptions; unknown failures remain EIO. */
    uint32_t result=(uint32_t)error;
    if(error<0 && ((result>>10)&255u)==17u){
        uint32_t description=result&1023u;
        if(description==112 || description==113 || description==120)return 2;
        if(description==180 || description==185 || description==190)return 17;
    }
    switch(error) {
        case EPERM:return 1; case ENOENT:return 2; case EBADF:return 9;
        case ENOMEM:return 12; case EACCES:return 13; case EFAULT:return 14;
        case EEXIST:return 17; case ENOTDIR:return 20; case EISDIR:return 21;
        case EINVAL:return 22; case EMFILE:return 24; case EROFS:return 30;
        case EDOM:return 33; case ERANGE:return 34; case ENAMETOOLONG:return 36;
        case ENOSYS:return 38; case EOVERFLOW:return 75; case EILSEQ:return 84;
        default:return 5;
    }
}
void ds6_result_error(int result) { if(result<0) *ds_io_errno()=ds6_host_error(errno); }
void ds6_basics_init(DS6Log log) {
    logger=log; random_state=UINT64_C(0x1234abcd330e);
    for(int c=0;c<256;++c) {
        uint8_t f=0;
        if(c<32 || (c>=127 && c<160)) f|=32;
        if(c>=9 && c<=13) f|=8;
        if(c==32) f|=8|128;
        if(c>='A' && c<='Z') f|=1;
        if(c>='a' && c<='z') f|=2;
        if(c>='0' && c<='9') f|=4;
        if((c>='A' && c<='F') || (c>='a' && c<='f')) f|=64;
        if((c>32 && c<127 && !(f&7)) || c>=160) f|=16;
        character_flags[c+1]=f;
        lowercase[c+1]=(int16_t)(c>='A' && c<='Z'?c+32:c);
        uppercase[c+1]=(int16_t)(c>='a' && c<='z'?c-32:c);
    }
    lowercase[0]=uppercase[0]=-1;
}
void ds6_basics_cleanup(void) {
    for(int i=0;i<16;++i) { ds_rt_free(env_names[i]); ds_rt_free(env_values[i]); env_names[i]=env_values[i]=NULL; }
    logger=NULL;
}
static int parse_error_begin(void) { int saved=errno; errno=0; return saved; }
static void parse_error_end(int saved) { int error=errno; errno=saved; if(error) *ds_io_errno()=ds6_host_error(error); }
static int DS_IO_SOFT number_atoi(const char *s) { return atoi(s); }
static int32_t DS_IO_SOFT number_strtol(const char *s,char **end,int base) {
    int saved=parse_error_begin(); long value=strtol(s,end,base); parse_error_end(saved); return value;
}
static uint32_t DS_IO_SOFT number_strtoul(const char *s,char **end,int base) {
    int saved=parse_error_begin(); unsigned long value=strtoul(s,end,base); parse_error_end(saved); return value;
}
static double DS_IO_SOFT number_strtod(const char *s,char **end) {
    int saved=parse_error_begin(); double value=strtod(s,end); parse_error_end(saved); return value;
}
typedef int (*Compare)(const void *,const void *) DS_IO_SOFT;
static void DS_IO_SOFT sort_values(void *base,size_t count,size_t size,Compare compare) {
    /* Both PCS variants use the same registers for this integer-only callback. */
    qsort(base,count,size,(int (*)(const void *,const void *))compare);
}
static size_t DS_IO_SOFT wide_length(const uint32_t *s) { return wcslen((const wchar_t *)s); }
int DS_IO_SOFT ds6_vsnprintf(char *out,size_t size,const char *format,va_list args) {
    int result=vsnprintf(out,size,format,args); ds6_result_error(result); return result;
}
int DS_IO_SOFT ds6_vsprintf(char *out,const char *format,va_list args) {
    int result=vsprintf(out,format,args); ds6_result_error(result); return result;
}
int DS_IO_SOFT ds6_vsscanf(const char *in,const char *format,va_list args) { return vsscanf(in,format,args); }
int DS_IO_SOFT ds6_snprintf(char *out,size_t size,const char *format,...) {
    va_list args; va_start(args,format); int result=ds6_vsnprintf(out,size,format,args); va_end(args); return result;
}
int DS_IO_SOFT ds6_sprintf(char *out,const char *format,...) {
    va_list args; va_start(args,format); int result=ds6_vsprintf(out,format,args); va_end(args); return result;
}
int DS_IO_SOFT ds6_sscanf(const char *in,const char *format,...) {
    va_list args; va_start(args,format); int result=ds6_vsscanf(in,format,args); va_end(args); return result;
}
static char *DS_IO_SOFT env_get(const char *name) {
    if(!name) return NULL;
    for(int i=0;i<16;++i) if(env_names[i] && !strcmp(env_names[i],name)) return env_values[i];
    return NULL;
}
static int DS_IO_SOFT env_set(const char *name,const char *value,int overwrite) {
    if(!name || !*name || strchr(name,'=')) { *ds_io_errno()=22; return -1; }
    if(!value) { *ds_io_errno()=14; return -1; }
    int slot=-1;
    for(int i=0;i<16;++i) if(env_names[i] && !strcmp(env_names[i],name)) { slot=i; if(!overwrite) return 0; break; }
    if(slot<0) for(int i=0;i<16;++i) if(!env_names[i]) { slot=i; break; }
    if(slot<0) { *ds_io_errno()=12; return -1; }
    char *new_name=ds_rt_malloc(strlen(name)+1),*new_value=ds_rt_malloc(strlen(value)+1);
    if(!new_name || !new_value) { ds_rt_free(new_name); ds_rt_free(new_value); return -1; }
    strcpy(new_name,name); strcpy(new_value,value);
    ds_rt_free(env_names[slot]); ds_rt_free(env_values[slot]);
    env_names[slot]=new_name; env_values[slot]=new_value; return 0;
}
static int32_t DS_IO_SOFT random_next(void) {
    random_state=(random_state*UINT64_C(0x5deece66d)+11)&UINT64_C(0xffffffffffff);
    return (int32_t)(random_state>>17);
}
static int DS_IO_SOFT log_write(int priority,const char *tag,const char *text) {
    (void)priority; (void)tag;
    if(!text) return -1;
    if(logger) logger(text);
    return (int)strlen(text);
}
static int DS_IO_SOFT log_vprint(int priority,const char *tag,const char *format,va_list args) {
    char text[512]; int result=ds6_vsnprintf(text,sizeof(text),format,args);
    if(result>=0) log_write(priority,tag,text);
    return result;
}
static int DS_IO_SOFT log_print(int priority,const char *tag,const char *format,...) {
    va_list args; va_start(args,format); int result=log_vprint(priority,tag,format,args); va_end(args); return result;
}
static int DS_IO_SOFT atomic_swap(int value,int *pointer) { return __atomic_exchange_n(pointer,value,__ATOMIC_SEQ_CST); }
static int DS_IO_SOFT atomic_inc(int *pointer) { return __atomic_fetch_add(pointer,1,__ATOMIC_SEQ_CST); }
static int DS_IO_SOFT atomic_dec(int *pointer) { return __atomic_fetch_sub(pointer,1,__ATOMIC_SEQ_CST); }
static int DS_IO_SOFT atomic_compare(int old,int value,int *pointer) {
    return __atomic_compare_exchange_n(pointer,&old,value,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST)?0:1;
}
uint32_t ds6_basics_bindings(DSBinding *out,uint32_t capacity) {
    const DSBinding list[]={
        {"atoi",(uint32_t)number_atoi},{"strtol",(uint32_t)number_strtol},{"strtoul",(uint32_t)number_strtoul},
        {"strtod",(uint32_t)number_strtod},{"qsort",(uint32_t)sort_values},{"wcslen",(uint32_t)wide_length},
        {"snprintf",(uint32_t)ds6_snprintf},{"sprintf",(uint32_t)ds6_sprintf},{"sscanf",(uint32_t)ds6_sscanf},
        {"vsnprintf",(uint32_t)ds6_vsnprintf},{"vsprintf",(uint32_t)ds6_vsprintf},{"vsscanf",(uint32_t)ds6_vsscanf},
        {"getenv",(uint32_t)env_get},{"setenv",(uint32_t)env_set},{"lrand48",(uint32_t)random_next},
        {"_ctype_",(uint32_t)&ctype_pointer},{"_tolower_tab_",(uint32_t)&lower_pointer},
        {"_toupper_tab_",(uint32_t)&upper_pointer},{"__page_size",(uint32_t)&page_size},
        {"__android_log_write",(uint32_t)log_write},{"__android_log_print",(uint32_t)log_print},{"__android_log_vprint",(uint32_t)log_vprint},
        {"__atomic_swap",(uint32_t)atomic_swap},{"__atomic_inc",(uint32_t)atomic_inc},
        {"__atomic_dec",(uint32_t)atomic_dec},{"__atomic_cmpxchg",(uint32_t)atomic_compare}
    };
    uint32_t count=sizeof(list)/sizeof(list[0]); if(capacity<count) return 0;
    for(uint32_t i=0;i<count;++i) out[i]=list[i];
    return count;
}
