#ifndef DS28_FONT_H
#define DS28_FONT_H
#include "ds_io.h"
#define DS28_FONT_PATH "sdmc:/3ds/deadspace/test-output/font-subset/Ascender_Uni.ttf"
/* Only the validated read-only Ascender font maps to its private derivative. */
int ds28_font_path(char *,uint32_t);
#endif
