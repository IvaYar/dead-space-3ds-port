#ifndef DS25_ASSETS_H
#define DS25_ASSETS_H
#include "ds19_assets.h"
#define DS25_ROOT "sdmc:/3ds/deadspace/apk-assets/"
/* Read-only extracted assets from the pinned APK. Handle ownership is shared
 * with InputStream and the bounded ds_io descriptor pool. */
int32_t ds25_native_open(void *,const char *,int32_t mode);
#endif
