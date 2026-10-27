#ifndef DS12_SENSOR_H
#define DS12_SENSOR_H
#include <stdint.h>
#include "ds_jni.h"
/* Single-owner sampler. Caller serializes calls and initially zeroes state.
 * Rate limits delivery, not the hardware sampling rate. No axes are guessed. */
typedef struct { int8_t axis[3]; float bias[3],counts_per_g[3]; } DS12Calibration;
typedef struct {
    int (*enable)(void *user,int enabled);
    int (*read)(void *user,int16_t raw[3]); /* 1=sample, 0=not ready, <0=error */
    void *user;
} DS12SensorOps;
typedef struct {
    uint32_t magic,enabled,hz,has_sample,has_clock;
    uint64_t last_sample_us,last_poll_us;
    DS12Calibration calibration;
    DS12SensorOps ops;
} DS12Sensor;
typedef void (*DS12Acceleration)(DSJniHandle *,void *,float,float,float) DS_JNI_SOFT;
int ds12_sensor_init(DS12Sensor *,const DS12Calibration *,const DS12SensorOps *);
int ds12_sensor_enable(DS12Sensor *,int enabled);
int ds12_sensor_rate(DS12Sensor *,uint32_t hz);
int ds12_sensor_poll(DS12Sensor *,uint64_t now_us,float out[3]);
int ds12_sensor_dispatch(DS12Sensor *,uint64_t now_us,DSJniHandle *,void *,DS12Acceleration);
/* On disable failure retains ownership; caller must retry before discarding. */
int ds12_sensor_close(DS12Sensor *);
/* Native HID must already be initialized by the application. */
typedef struct { uint32_t enabled; } DS12Hid;
int ds12_hid_ops(DS12Hid *,DS12SensorOps *);
#endif
