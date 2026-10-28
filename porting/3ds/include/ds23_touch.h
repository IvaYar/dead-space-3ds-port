#ifndef DS23_TOUCH_H
#define DS23_TOUCH_H
#include "ds10_jni.h"
/* Selected donor's verified TouchSurfaceAndroid (IIIFF)V, Android softfp ABI. */
typedef void (*DS23Pointer)(DSJniHandle *,void *,int32_t,int32_t,int32_t,float,float) DS_JNI_SOFT;
enum {DS23_CANCEL=12,DS23_DOWN=0x6000c,DS23_MOVE=0x4000c,DS23_UP=0x8000c,DS23_SCREEN=1000};
typedef struct {
    uint32_t magic,source_width,source_height,active,x,y,events;
    DS10Context *bridge;
    DS23Pointer emit;
} DS23Touch;
/* Zero-initialize first. Caller serializes with the donor render thread and
 * closes this borrowed bridge before ds10_cleanup. One pointer (ID 0). */
int ds23_touch_init(DS23Touch *,DS10Context *,uint32_t,uint32_t,DS23Pointer);
/* pressed=0 ignores incoming coordinates and releases at the last position.
 * Returns 1 for an emitted event, 0 for no change, -1 for invalid input. */
int ds23_touch_sample(DS23Touch *,uint32_t pressed,uint32_t x,uint32_t y);
int ds23_touch_close(DS23Touch *);
#endif
