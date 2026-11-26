#include <3ds.h>
#include "ds6.h"
int ds6_native_clock(int id,DS6Time *out) {
    if(id==0) {
        uint64_t milliseconds=osGetTime();
        int64_t seconds=(int64_t)(milliseconds/1000)-INT64_C(2208988800);
        if(seconds<INT32_MIN || seconds>INT32_MAX) { *ds_io_errno()=75; return -1; }
        out->sec=(int32_t)seconds; out->nsec=(int32_t)(milliseconds%1000)*1000000;
    } else {
        uint64_t ticks=svcGetSystemTick();
        if(ticks/SYSCLOCK_ARM11>INT32_MAX) { *ds_io_errno()=75; return -1; }
        out->sec=(int32_t)(ticks/SYSCLOCK_ARM11);
        out->nsec=(int32_t)((ticks%SYSCLOCK_ARM11)*UINT64_C(1000000000)/SYSCLOCK_ARM11);
    }
    return 0;
}
int ds6_native_sleep(const DS6Time *request) {
    int64_t ns=(int64_t)request->sec*INT64_C(1000000000)+request->nsec;
    svcSleepThread(ns);
    return 0;
}
