#include "ds28_font.h"
#include <string.h>
int ds28_font_path(char *path,uint32_t capacity){
    if(strcmp(path,DS_IO_ROOT"fonts/Ascender_Uni.ttf"))return 0;
    if(sizeof(DS28_FONT_PATH)>capacity)return DS_ENAMETOOLONG;
    memcpy(path,DS28_FONT_PATH,sizeof(DS28_FONT_PATH));return 0;
}
