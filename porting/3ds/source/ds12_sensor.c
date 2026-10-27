#include "ds12_sensor.h"
#include <math.h>
#include <string.h>
#define MAGIC 0x44533132u
static int valid(const DS12Sensor *s){return s && s->magic==MAGIC;}
int ds12_sensor_init(DS12Sensor *s,const DS12Calibration *c,const DS12SensorOps *ops){
    if(!s || !c || !ops || !ops->enable || !ops->read || (valid(s) && s->enabled))return -1;
    unsigned seen=0;
    for(unsigned i=0;i<3;++i){
        int a=c->axis[i];unsigned n=(unsigned)(a<0?-a:a);
        if(n<1 || n>3 || (seen&(1u<<n)))return -1;
        seen|=1u<<n;
        if(!isfinite(c->bias[i]) || fabsf(c->bias[i])>32768.0f || !isfinite(c->counts_per_g[i]) ||
           c->counts_per_g[i]<16.0f || c->counts_per_g[i]>8192.0f)return -1;
    }
    DS12Sensor next={0};next.magic=MAGIC;next.hz=20;next.calibration=*c;next.ops=*ops;*s=next;return 0;
}
int ds12_sensor_enable(DS12Sensor *s,int enabled){
    if(!valid(s) || (enabled!=0 && enabled!=1))return -1;
    if(s->enabled==(uint32_t)enabled)return 0;
    if(s->ops.enable(s->ops.user,enabled))return -2;
    s->enabled=(uint32_t)enabled;s->has_sample=0;s->has_clock=0;return 0;
}
int ds12_sensor_rate(DS12Sensor *s,uint32_t hz){
    if(!valid(s) || hz<1 || hz>200)return -1;
    if(s->hz!=hz){s->hz=hz;s->has_sample=0;}return 0;
}
int ds12_sensor_poll(DS12Sensor *s,uint64_t now,float out[3]){
    if(!valid(s) || !out)return -1;
    if(!s->enabled)return 0;
    if(s->has_clock && now<s->last_poll_us)return -1;
    s->has_clock=1;s->last_poll_us=now;
    /* Subtraction avoids deadline overflow near UINT64_MAX. Round up interval. */
    if(s->has_sample && now-s->last_sample_us<(1000000u+s->hz-1)/s->hz)return 0;
    int16_t raw[3];int status=s->ops.read(s->ops.user,raw);
    if(status<0)return -2;
    if(status==0)return 0;
    if(status!=1)return -2;
    float converted[3];
    for(unsigned i=0;i<3;++i){
        int axis=s->calibration.axis[i];unsigned n=(unsigned)(axis<0?-axis:axis)-1;
        converted[i]=((float)raw[n]-s->calibration.bias[n])*9.80665f/s->calibration.counts_per_g[n];
        if(axis<0)converted[i]=-converted[i];
    }
    memcpy(out,converted,sizeof(converted));s->has_sample=1;s->last_sample_us=now;return 1;
}
int ds12_sensor_dispatch(DS12Sensor *s,uint64_t now,DSJniHandle *env,void *object,DS12Acceleration callback){
    if(!env || !callback)return -1;
    float xyz[3];int result=ds12_sensor_poll(s,now,xyz);
    if(result==1)callback(env,object,xyz[0],xyz[1],xyz[2]);
    return result;
}
int ds12_sensor_close(DS12Sensor *s){
    if(!valid(s))return -1;
    if(ds12_sensor_enable(s,0))return -2;
    memset(s,0,sizeof(*s));return 0;
}
