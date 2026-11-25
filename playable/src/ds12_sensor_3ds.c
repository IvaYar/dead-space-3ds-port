#include <3ds.h>
#include "ds12_sensor.h"
static int set_enabled(void *user,int enabled){
    DS12Hid *hid=user;
    if(!hid || !hidSharedMem || (enabled!=0 && enabled!=1))return -1;
    if(hid->enabled==(uint32_t)enabled)return 0;
    Result result=enabled?HIDUSER_EnableAccelerometer():HIDUSER_DisableAccelerometer();
    if(R_FAILED(result))return -1;
    hid->enabled=(uint32_t)enabled;return 0;
}
static int read_raw(void *user,int16_t raw[3]){
    DS12Hid *hid=user;
    if(!hid || !hid->enabled || !hidSharedMem || !raw)return -1;
    hidScanInput();
    /* Same availability condition used by libctru 2.7's HID scanner. The
     * result is the latest cached sample; no claim of a fresh hardware event. */
    vu32 *section=hidSharedMem+66;u32 index=section[4];
    if(index>7)return 0;
    if(index==0 && ((section[0]==section[2] && section[1]==section[3]) ||
                   (s32)section[1]<0 || (s32)section[3]<0))return 0;
    accelVector vector;hidAccelRead(&vector);
    raw[0]=vector.x;raw[1]=vector.y;raw[2]=vector.z;return 1;
}
int ds12_hid_ops(DS12Hid *hid,DS12SensorOps *ops){
    if(!hid || !ops || hid->enabled || !hidSharedMem)return -1;
    *ops=(DS12SensorOps){set_enabled,read_raw,hid};return 0;
}
