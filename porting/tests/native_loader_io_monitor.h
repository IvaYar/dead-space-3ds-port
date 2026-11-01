#ifndef NATIVE_LOADER_IO_MONITOR_H
#define NATIVE_LOADER_IO_MONITOR_H
/* New native entry adapter only. Underlying SDK IO and old DS7/GPU unchanged.
 * Per-generation pthread tokens prevent unrelated audio/main activity from
 * concealing a stuck loader. Counters describe IO operations, not donor jobs. */
typedef struct {u32 token,bytes,positive_reads,files,opens,completed,active,errors;} LoaderIO;
static LightLock loader_io_lock;
static LoaderIO loader_io[17];
static u32 (*loader_self)(void) DS_IO_SOFT;
#ifdef TEST_LATE_PENDING
static volatile u32 fixture_active,fixture_release;
static u32 fixture_loader_token;
static u64 fixture_started;
#endif
static u32 loader_waiting,close_start_seen;
static LoaderIO loader_io_copy(u32 token){
    if((token&255)>=17)return (LoaderIO){0};
    LoaderIO value;LightLock_Lock(&loader_io_lock);value=loader_io[token&255];LightLock_Unlock(&loader_io_lock);
    if(value.token!=token)memset(&value,0,sizeof(value));
    return value;
}
static u32 loader_io_begin(void){
    u32 token=loader_self?loader_self():0,index=token&255;
    if(index>=17)return UINT32_MAX;
    LightLock_Lock(&loader_io_lock);
    LoaderIO *m=&loader_io[index];if(m->token!=token){memset(m,0,sizeof(*m));m->token=token;}
    ++m->active;LightLock_Unlock(&loader_io_lock);return token;
}
static void loader_io_end(u32 token,int operation,int result){
    if((token&255)>=17)return;
    LightLock_Lock(&loader_io_lock);LoaderIO *m=&loader_io[token&255];
    --m->active;++m->completed;if(result<0)++m->errors;
    else if(operation==1 && result>0){m->bytes+=(u32)result;++m->positive_reads;}
    else if(operation==0)++m->opens;
    else if(operation==3)++m->files;
    LightLock_Unlock(&loader_io_lock);
}
static void *loader_open(const char *path,int32_t *error){
    u32 token=loader_io_begin();void *r=ds_io_sd_ops()->open(path,error);loader_io_end(token,0,r?0:-1);return r;
}
static int32_t loader_read(void *handle,void *buffer,uint32_t count,int32_t *error){
    u32 token=loader_io_begin();
#ifdef TEST_STALL_IO
    while(fixture_active && token==fixture_loader_token && !__atomic_load_n(&fixture_release,__ATOMIC_ACQUIRE))svcSleepThread(1000000);
#endif
    int32_t r=ds_io_sd_ops()->read(handle,buffer,count,error);
#ifdef TEST_SLOW_IO
    if(fixture_active && token==fixture_loader_token && r>0)svcSleepThread(3000000);
#endif
    loader_io_end(token,1,r);return r;
}
static int32_t loader_seek(void *handle,int32_t offset,int32_t whence,int32_t *error){
    u32 token=loader_io_begin();int32_t r=ds_io_sd_ops()->seek(handle,offset,whence,error);loader_io_end(token,2,r);return r;
}
static int32_t loader_close(void *handle,int32_t *error){
    u32 token=loader_io_begin();int32_t r=ds_io_sd_ops()->close(handle,error);loader_io_end(token,3,r);return r;
}
static const DSIOOps loader_ops={loader_open,loader_read,loader_seek,loader_close};
#endif
