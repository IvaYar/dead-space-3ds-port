#include "ds19_assets.h"
#include "ds_io.h"
#include <dirent.h>
#include <errno.h>
#include <string.h>
int32_t ds19_native_list(void *user,const char *relative,DS19Name *out,uint32_t capacity){
    (void)user;char path[DS_IO_PATH_BYTES];size_t n=strlen(relative);
    if(sizeof(DS_IO_ROOT)+n>sizeof(path))return -1;
    strcpy(path,DS_IO_ROOT);strcat(path,relative);DIR *dir=opendir(path);
    if(!dir)return errno==ENOENT || errno==ENOTDIR?0:-1;
    uint32_t count=0;int32_t result=0;struct dirent *entry;
    errno=0;
    while((entry=readdir(dir))){
        if(!strcmp(entry->d_name,".") || !strcmp(entry->d_name,".."))continue;
        if(count==DS19_ELEMENTS || strlen(entry->d_name)>255 || (out && count>=capacity)){result=-1;break;}
        if(out)strcpy(out[count].name,entry->d_name);
        ++count;
    }
    if(!result && errno)result=-1;
    if(closedir(dir))result=-1;
    return result?result:(int32_t)count;
}
