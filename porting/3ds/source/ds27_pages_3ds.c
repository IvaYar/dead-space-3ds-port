#include "ds27_pages.h"
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>
#include "ds6.h"
#define ROOT "sdmc:/3ds/deadspace/test-output/texture-pages/"
static uint32_t serial;
static void path(char out[128],uint32_t token){snprintf(out,128,ROOT"page-%08lx.bin",(unsigned long)token);}
static int save(uint32_t *token,const void *data,uint32_t bytes){
    if(serial==UINT32_MAX)return -1;
    uint32_t next=++serial,header[2]={bytes,ds_crc32(data,bytes)};char name[128];path(name,next);
    FILE *f=fopen(name,"wb");if(!f)return -1;
    int failed=fwrite(header,1,8,f)!=8 || fwrite(data,1,bytes,f)!=bytes;
    if(fclose(f))failed=1;
    if(failed){remove(name);return -1;}
    if(*token){char old[128];path(old,*token);remove(old);}*token=next;return 0;
}
static int load(uint32_t token,void *data,uint32_t bytes){
    char name[128];path(name,token);FILE *f=fopen(name,"rb");if(!f)return -1;
    uint32_t header[2];int failed=fread(header,1,8,f)!=8 || header[0]!=bytes || fread(data,1,bytes,f)!=bytes;
    if(!failed && (fgetc(f)!=EOF || ferror(f) || ds_crc32(data,bytes)!=header[1]))failed=1;
    if(fclose(f))failed=1;
    return failed?-1:0;
}
static void drop(uint32_t token){char name[128];path(name,token);remove(name);}
const DS15Backing *ds27_sd_backing(void){
    if((mkdir("sdmc:/3ds/deadspace/test-output",0700) && ds6_host_error(errno)!=17) ||
       (mkdir(ROOT,0700) && ds6_host_error(errno)!=17))return NULL;
    static const DS15Backing ops={save,load,drop};return &ops;
}
