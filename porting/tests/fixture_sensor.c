/* Built separately with -mfloat-abi=softfp: checks 5-argument JNI callback. */
#include "ds_jni.h"
void DS_JNI_SOFT probe_acceleration(DSJniHandle *env,void *object,float x,float y,float z){
    volatile uint32_t *out=(uint32_t *)0x06009000;
    union {float f;uint32_t u;} a={x},b={y},c={z};
    out[0]=(uint32_t)env;out[1]=(uint32_t)object;out[2]=a.u;out[3]=b.u;out[4]=c.u;out[5]++;
}
