#include "ds25_assets.h"
#include "ds6.h"
#include <stdio.h>
#include <errno.h>
#include <string.h>
#include "apk_fd_contract.h"
int32_t ds25_native_open(void *user,const char *relative,int32_t mode){
    const char *root=user?(const char *)user:DS25_ROOT;
    if(!relative || !*relative || mode<0 || mode>4){*ds_io_errno()=22;return -1;}
    if(mode==4){
        int stored=0;for(unsigned i=0;i<sizeof(apk_stored_assets)/sizeof(apk_stored_assets[0]);++i)if(!strcmp(relative,apk_stored_assets[i]))stored=1;
        if(!stored){*ds_io_errno()=95;return -1;}
    }
    size_t prefix=strlen(root),length=strlen(relative);
    if(relative[length-1]=='/'){*ds_io_errno()=20;return -1;}
    if(prefix+length>=DS_IO_PATH_BYTES){*ds_io_errno()=36;return -1;}
    if(!ds_io_free_slots()){*ds_io_errno()=24;return -1;}
    char path[DS_IO_PATH_BYTES];memcpy(path,root,prefix);memcpy(path+prefix,relative,length+1);
    FILE *file=fopen(path,"rb");if(!file){*ds_io_errno()=ds6_host_error(errno);return -1;}
    if(setvbuf(file,NULL,_IONBF,0)){fclose(file);*ds_io_errno()=5;return -1;}
    int32_t fd=ds_io_adopt_handle(file);
    if(fd<0){int32_t saved=*ds_io_errno();fclose(file);*ds_io_errno()=saved;}
    return fd;
}
