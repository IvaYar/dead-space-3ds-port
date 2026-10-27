#define _GNU_SOURCE
#include "ds6.h"
#include <errno.h>
#include <time.h>
#include <sys/time.h>
#include <unistd.h>
#include <sched.h>
static DS6TM calendar;
static char utc[]="UTC";
static char *zones[2]={utc,utc};
void ds6_time_init(void) { }
static int fail(int error) { *ds_io_errno()=error; return -1; }
int DS_IO_SOFT ds6_clock_gettime(int id,DS6Time *out) {
    if(!out) return fail(14);
    if(id!=0 && id!=1) return fail(22);
    return ds6_native_clock(id,out);
}
int DS_IO_SOFT ds6_gettimeofday(DS6Time *out,void *zone) {
    DS6Time now; if(ds6_native_clock(0,&now)) return -1;
    if(out) { out->sec=now.sec; out->nsec=now.nsec/1000; }
    if(zone) { int32_t *p=zone; p[0]=p[1]=0; }
    return 0;
}
int32_t DS_IO_SOFT ds6_time(int32_t *out) {
    DS6Time now; if(ds6_clock_gettime(0,&now)) return -1;
    if(out) *out=now.sec;
    return now.sec;
}
static void from_native(const struct tm *in,DS6TM *out) {
    int32_t values[9]={in->tm_sec,in->tm_min,in->tm_hour,in->tm_mday,in->tm_mon,in->tm_year,in->tm_wday,in->tm_yday,0};
    for(int i=0;i<9;++i) out->field[i]=values[i];
    out->offset=0; out->zone=(uint32_t)utc;
}
DS6TM *DS_IO_SOFT ds6_gmtime(const int32_t *seconds) {
    if(!seconds) { fail(14); return NULL; }
    time_t value=*seconds; struct tm native;
    if(!gmtime_r(&value,&native)) { ds6_result_error(-1); return NULL; }
    from_native(&native,&calendar); return &calendar;
}
/* The port runtime is explicitly configured for UTC, independent of native TZ. */
DS6TM *DS_IO_SOFT ds6_localtime(const int32_t *seconds) { return ds6_gmtime(seconds); }
int32_t DS_IO_SOFT ds6_mktime(DS6TM *in) {
    if(!in) return fail(14);
    int64_t year=(int64_t)in->field[5]+1900,month=in->field[4];
    int64_t years=month>=0?month/12:(month-11)/12;
    year+=years; month=month-years*12+1;
    year-=month<=2;
    int64_t era=year>=0?year/400:(year-399)/400,yoe=year-era*400;
    int64_t doy=(153*(month+(month>2?-3:9))+2)/5;
    int64_t days=era*146097+yoe*365+yoe/4-yoe/100+doy-719468+(int64_t)in->field[3]-1;
    int64_t value=days*86400+(int64_t)in->field[2]*3600+(int64_t)in->field[1]*60+in->field[0];
    if(value<INT32_MIN || value>INT32_MAX) return fail(75);
    time_t epoch=(time_t)value; struct tm native;
    if(!gmtime_r(&epoch,&native)) { ds6_result_error(-1); return -1; }
    from_native(&native,in); return (int32_t)value;
}
int DS_IO_SOFT ds6_nanosleep(const DS6Time *request,DS6Time *remaining) {
    if(!request) return fail(14);
    if(request->sec<0 || request->nsec<0 || request->nsec>=1000000000) return fail(22);
    int result=ds6_native_sleep(request);
    if(!result && remaining) remaining->sec=remaining->nsec=0;
    return result;
}
int DS_IO_SOFT ds6_usleep(uint32_t microseconds) {
    DS6Time request={(int32_t)(microseconds/1000000),(int32_t)(microseconds%1000000)*1000};
    return ds6_nanosleep(&request,NULL);
}
int DS_IO_SOFT ds6_sched_yield(void) {
    DS6Time request={0,0}; return ds6_nanosleep(&request,NULL);
}
int32_t DS_IO_SOFT ds6_sysconf(int name) {
    switch(name) {
        case 0x27: case 0x28:return 4096;
        case 0x0b:return DS_IO_FILES+3;
        case 0x60: case 0x61:return 1; /* Application CPU affinity is one core. */
        default:return fail(22);
    }
}
uint32_t ds6_time_bindings(DSBinding *out,uint32_t capacity) {
    const DSBinding list[]={
        {"time",(uint32_t)ds6_time},{"gettimeofday",(uint32_t)ds6_gettimeofday},{"clock_gettime",(uint32_t)ds6_clock_gettime},
        {"gmtime",(uint32_t)ds6_gmtime},{"localtime",(uint32_t)ds6_localtime},
        {"mktime",(uint32_t)ds6_mktime},{"tzname",(uint32_t)zones},{"nanosleep",(uint32_t)ds6_nanosleep},
        {"usleep",(uint32_t)ds6_usleep},{"sched_yield",(uint32_t)ds6_sched_yield},{"sysconf",(uint32_t)ds6_sysconf}
    };
    uint32_t count=sizeof(list)/sizeof(list[0]); if(capacity<count) return 0;
    for(uint32_t i=0;i<count;++i) out[i]=list[i];
    return count;
}
