#include <3ds.h>
#include "ds11_platform.h"
#include <stdio.h>
#include <string.h>
int ds11_native_keep_awake(int enabled) {
    if(enabled!=0 && enabled!=1)return -1;
    aptSetSleepAllowed(!enabled);return 0;
}
int ds11_native_content_ready(void) {
    FILE *input=fopen("sdmc:/3ds/deadspace/assets-verified.txt","rb");if(!input)return 0;
    char text[128]={0};size_t n=fread(text,1,sizeof(text)-1,input);fclose(input);
    const char expected[]="DS_ASSETS_V1 dd42272365d0abd8ad9c89450bb7f869ee4ac0ad548525758e6a1e7df4d3c1eb 1728 414822611\n";
    return n==sizeof(expected)-1 && !memcmp(text,expected,n);
}
