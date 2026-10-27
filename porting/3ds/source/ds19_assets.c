#include "ds19_assets.h"
#include "ds_runtime.h"
#include <stdlib.h>
#include <string.h>
static int component(const char *s,uint32_t n){return n && !(n==1 && s[0]=='.') && !(n==2 && s[0]=='.' && s[1]=='.');}
int ds19_path(const char *input,char out[256]){
    if(!input || !out)return -1;
    uint32_t n=0;while(n<256 && input[n])++n;if(n==256)return -1;
    uint16_t units[255];int count=ds18_decode(input,n,units,255);if(count<0)return -1;
    char path[256];uint32_t pos=0;
    for(int i=0;i<count;++i){uint32_t v=units[i];
        if(!v)return -1;
        if(v>=0xd800 && v<=0xdbff){if(i+1==count || units[i+1]<0xdc00 || units[i+1]>0xdfff)return -1;v=0x10000+((v-0xd800)<<10)+(units[++i]-0xdc00);}
        else if(v>=0xdc00 && v<=0xdfff)return -1;
        if(v<128)path[pos++]=(char)v;
        else if(v<2048){path[pos++]=(char)(0xc0|(v>>6));path[pos++]=(char)(0x80|(v&63));}
        else if(v<65536){path[pos++]=(char)(0xe0|(v>>12));path[pos++]=(char)(0x80|((v>>6)&63));path[pos++]=(char)(0x80|(v&63));}
        else{path[pos++]=(char)(0xf0|(v>>18));path[pos++]=(char)(0x80|((v>>12)&63));path[pos++]=(char)(0x80|((v>>6)&63));path[pos++]=(char)(0x80|(v&63));}
    }path[pos]=0;
    const char *p=path;
    if(!strncmp(p,"appbundle:/published/",21))p+=21;
    else if(!strcmp(p,"appbundle:/published"))p+=20;
    else if(!strncmp(p,"published/",10))p+=10;
    else if(!strcmp(p,"published"))p+=9;
    if(*p=='/')return -1;
    uint32_t length=(uint32_t)strlen(p);if(length && p[length-1]=='/')--length;
    uint32_t start=0;
    for(uint32_t i=0;i<length;++i){unsigned char c=(unsigned char)p[i];if(c==':' || c=='\\' || c<32 || c==127)return -1;
        if(c=='/'){if(!component(p+start,i-start))return -1;start=i+1;}}
    if(length && !component(p+start,length-start))return -1;
    memcpy(out,p,length);out[length]=0;return 0;
}
int ds19_name_units(const char *input,uint16_t out[255]){
    uint32_t length=0;while(length<256 && input[length])++length;if(!length || length==256 || !component(input,length))return -1;
    uint32_t n=0;for(uint32_t i=0;i<length;){uint32_t a=(uint8_t)input[i++],v,continuations,min;
        if(a<128){if(a<32 || a==127 || a=='/' || a=='\\' || a==':')return -1;v=a;continuations=0;min=0;}
        else if(a>=0xc2 && a<=0xdf){v=a&31;continuations=1;min=128;}
        else if(a>=0xe0 && a<=0xef){v=a&15;continuations=2;min=2048;}
        else if(a>=0xf0 && a<=0xf4){v=a&7;continuations=3;min=65536;}
        else return -1;
        if(length-i<continuations)return -1;
        for(uint32_t j=0;j<continuations;++j){uint32_t b=(uint8_t)input[i++];if((b&0xc0)!=0x80)return -1;v=(v<<6)|(b&63);}
        if(v<min || v>0x10ffff || (v>=0xd800 && v<=0xdfff))return -1;
        if(v<65536)out[n++]=(uint16_t)v;else{v-=0x10000;out[n++]=(uint16_t)(0xd800+(v>>10));out[n++]=(uint16_t)(0xdc00+(v&1023));}
    }return (int)n;
}
static int compare_names(const void *a,const void *b){return strcmp(((const DS19Name *)a)->name,((const DS19Name *)b)->name);}
int ds19_snapshot(DS19List list,void *user,const char *path,DS19Name **out,uint32_t *count){
    if(!list || !path || !out || !count)return -1;
    int32_t n=list(user,path,NULL,0);if(n<0 || n>DS19_ELEMENTS)return -1;
    DS19Name *names=n?ds_rt_calloc((uint32_t)n,sizeof(*names)):NULL;if(n && !names)return -1;
    if(n && list(user,path,names,(uint32_t)n)!=n){ds_rt_free(names);return -1;}
    uint16_t units[255];for(int32_t i=0;i<n;++i)if(ds19_name_units(names[i].name,units)<0){ds_rt_free(names);return -1;}
    if(n)qsort(names,(uint32_t)n,sizeof(*names),compare_names);
    uint32_t unique=0;for(int32_t i=0;i<n;++i)if(!unique || strcmp(names[i].name,names[unique-1].name)){if(unique!=(uint32_t)i)names[unique]=names[i];++unique;}
    *out=names;*count=unique;return 0;
}
