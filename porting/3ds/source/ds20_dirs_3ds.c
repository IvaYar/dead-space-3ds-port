#include "ds20_dirs.h"
#include <dirent.h>
#include <errno.h>
#include <string.h>
static void *open_dir(const char *path,int *error){DIR *dir=opendir(path);if(!dir)*error=ds6_host_error(errno);return dir;}
static int next_entry(void *dir,DS20HostEntry *out,int *error){
    errno=0;struct dirent *entry=readdir(dir);if(!entry){if(errno){*error=ds6_host_error(errno);return -1;}return 0;}
    size_t n=strlen(entry->d_name);if(n>255){*error=36;return -1;}
    out->ino=entry->d_ino;out->type=entry->d_type;memcpy(out->name,entry->d_name,n+1);return 1;
}
static int close_dir(void *dir,int *error){int result=closedir(dir);if(result)*error=ds6_host_error(errno);return result;}
const DS20Ops *ds20_native_ops(void){static const DS20Ops ops={open_dir,next_entry,close_dir};return &ops;}
