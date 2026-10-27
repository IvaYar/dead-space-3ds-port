/* CPU-only injected sensor. Native engine uses ds12_sensor_3ds.c instead. */
#include "ds10_jni.h"
#include <string.h>
static DS12Sensor sensor;
static int failure,status=1;
static uint32_t enable_calls,read_calls,callback_calls,received_env,received_object,same_object;
static float received[3];
static int set_enabled(void *u,int value){(void)u;(void)value;++enable_calls;return failure;}
static int read_raw(void *u,int16_t out[3]){(void)u;++read_calls;out[0]=512;out[1]=-256;out[2]=-512;return status;}
static void DS_JNI_SOFT callback(DSJniHandle *env,void *object,float x,float y,float z){
    ++callback_calls;received_env=(uint32_t)env;received_object=(uint32_t)object;
    received[0]=x;received[1]=y;received[2]=z;
    typedef uint8_t (*Same)(DSJniHandle *,void *,void *) DS_JNI_SOFT;
    same_object=((Same)env->functions[24])(env,object,((DS10Context *)env->owner)->acceleration_object);
    typedef void *(*Find)(DSJniHandle *,const char *) DS_JNI_SOFT;
    /* Deliberately leave a local ref for the pump's native frame to release. */
    ((Find)env->functions[6])(env,"com/ea/blast/MainActivity");
}
int ds12_test_attach(DS10Context *c,uint32_t target){
    if(c->accelerometer)return -1;
    DS12Calibration calibration={{1,2,3},{0,0,0},{512,512,512}};
    DS12SensorOps ops={set_enabled,read_raw,0};
    if(ds12_sensor_init(&sensor,&calibration,&ops))return -1;
    return ds12_jni_sensor(c,&sensor,target?(DS12Acceleration)target:callback);
}
void ds12_test_failure(int error,int read_status){failure=error;status=read_status;}
int ds12_test_pump(DS10Context *c,uint32_t lo,uint32_t hi){return ds12_jni_pump(c,((uint64_t)hi<<32)|lo);}
void ds12_test_stats(DS10Context *c,uint32_t *out){
    out[0]=sensor.enabled;out[1]=sensor.interval_us;out[2]=c->acceleration_events;out[3]=enable_calls;out[4]=read_calls;
    out[5]=callback_calls;out[6]=received_env;out[7]=received_object;memcpy(out+8,received,sizeof(received));out[11]=(uint32_t)c->acceleration_delay;out[12]=same_object;
}
