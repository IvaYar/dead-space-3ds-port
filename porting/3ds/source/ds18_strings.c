#include "ds18_strings.h"
#include <string.h>
int ds18_encode(const uint16_t *src,uint32_t length,char *out,uint32_t capacity){
    if(length>DS18_MAX_UNITS || (length && !src))return -1;
    uint32_t bytes=0;for(uint32_t i=0;i<length;++i){uint32_t v=src[i];bytes+=v && v<128?1:v<2048?2:3;}
    if(bytes>capacity || (bytes && !out))return -1;
    uint32_t n=0;for(uint32_t i=0;i<length;++i){uint32_t v=src[i];
        if(v && v<128)out[n++]=(char)v;
        else if(v<2048){out[n++]=(char)(0xc0|(v>>6));out[n++]=(char)(0x80|(v&63));}
        else{out[n++]=(char)(0xe0|(v>>12));out[n++]=(char)(0x80|((v>>6)&63));out[n++]=(char)(0x80|(v&63));}
    }return (int)n;
}
int ds18_decode(const char *src,uint32_t bytes,uint16_t *out,uint32_t capacity){
    if(bytes>255 || (bytes && !src))return -1;
    uint16_t decoded[DS18_MAX_UNITS];uint32_t n=0;
    for(uint32_t i=0;i<bytes;){uint32_t a=(uint8_t)src[i++],v;
        if(a && a<128)v=a;
        else if(a>=0xc0 && a<=0xdf){
            if(i>=bytes)return -1;
            uint32_t b=(uint8_t)src[i++];if((b&0xc0)!=0x80)return -1;v=((a&31)<<6)|(b&63);
            if(v<128 && !(a==0xc0 && b==0x80))return -1;
        }else if(a>=0xe0 && a<=0xef){
            if(bytes-i<2)return -1;
            uint32_t b=(uint8_t)src[i++],c=(uint8_t)src[i++];if((b&0xc0)!=0x80 || (c&0xc0)!=0x80)return -1;
            v=((a&15)<<12)|((b&63)<<6)|(c&63);if(v<2048)return -1;
        }else return -1;
        decoded[n++]=(uint16_t)v;
    }
    if(n>capacity || (n && !out))return -1;
    if(n)memcpy(out,decoded,n*2);
    return (int)n;
}
