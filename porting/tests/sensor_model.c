/* Isolated injected backend; never linked into the native HID build. */
#include "ds12_sensor.h"
#include <string.h>
static DS12Sensor sensor;
static int enabled_error,read_status,enable_calls,read_calls;
static int16_t raw[3];
static float output[3];
static int enable(void *u,int value){(void)u;(void)value;++enable_calls;return enabled_error;}
static int read_sample(void *u,int16_t out[3]){(void)u;++read_calls;memcpy(out,raw,sizeof(raw));return read_status;}
int sensor_test_init(const DS12Calibration *c){DS12SensorOps ops={enable,read_sample,0};return ds12_sensor_init(&sensor,c,&ops);}
void sensor_test_reset(void){memset(&sensor,0,sizeof(sensor));enabled_error=0;read_status=1;enable_calls=read_calls=0;memset(output,0,sizeof(output));}
int sensor_test_enable(int value){return ds12_sensor_enable(&sensor,value);}
int sensor_test_rate(unsigned hz){return ds12_sensor_rate(&sensor,hz);}
void sensor_test_backend(int error,int status){enabled_error=error;read_status=status;}
void sensor_test_raw(int x,int y,int z){raw[0]=(int16_t)x;raw[1]=(int16_t)y;raw[2]=(int16_t)z;}
int sensor_test_poll(uint32_t lo,uint32_t hi){return ds12_sensor_poll(&sensor,((uint64_t)hi<<32)|lo,output);}
int sensor_test_dispatch(uint32_t lo,uint32_t hi,uint32_t callback){return ds12_sensor_dispatch(&sensor,((uint64_t)hi<<32)|lo,(DSJniHandle *)0x12345678,(void *)0x87654321,(DS12Acceleration)callback);}
int sensor_test_close(void){return ds12_sensor_close(&sensor);}
uint32_t sensor_test_output(void){return (uint32_t)output;}
uint32_t sensor_test_enabled(void){return sensor.enabled;}
uint32_t sensor_test_enable_calls(void){return (uint32_t)enable_calls;}
uint32_t sensor_test_read_calls(void){return (uint32_t)read_calls;}
