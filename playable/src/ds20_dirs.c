#include "ds20_dirs.h"
#include "ds7.h"
#include <string.h>
typedef struct {uint32_t token;void *native;uint64_t offset;} Directory;
static Directory dirs[DS20_DIRS];static DS20Ops ops;static uint32_t serial;
uint32_t ds20_active(void){uint32_t n=0;ds7_gate_lock();for(unsigned i=0;i<DS20_DIRS;++i)n+=dirs[i].token!=0;ds7_gate_unlock();return n;}
int ds20_init(const DS20Ops *backend){
    if(!backend || !backend->open || !backend->next || !backend->close)return 22;
    ds7_gate_lock();for(unsigned i=0;i<DS20_DIRS;++i)if(dirs[i].token){ds7_gate_unlock();return 16;}
    ops=*backend;ds7_gate_unlock();return 0;
}
static Directory *lookup(void *handle){for(unsigned i=0;i<DS20_DIRS;++i)if(dirs[i].token && dirs[i].token==(uint32_t)handle)return &dirs[i];return NULL;}
void *DS_IO_SOFT ds20_opendir(const char *path){
    char mapped[DS_IO_PATH_BYTES];if(ds6_map_path(path,mapped,0))return NULL;
    ds7_gate_lock();int error=24;void *result=NULL;
    if(!ops.open){error=38;goto done;}
    for(unsigned i=0;i<DS20_DIRS;++i)if(!dirs[i].token){
        if(serial==0x0fffffffu){error=75;break;}
        error=0;void *native=ops.open(mapped,&error);if(!native){if(!error)error=5;break;}
        dirs[i]=(Directory){0xd0000000u|++serial,native,0};result=(void *)dirs[i].token;break;
    }
done:ds7_gate_unlock();if(!result)*ds_io_errno()=error;return result;
}
int DS_IO_SOFT ds20_readdir_r(void *handle,DS20Dirent *entry,DS20Dirent **result){
    if(!result || !entry)return 22;
    *result=NULL;
    ds7_gate_lock();Directory *d=lookup(handle);int error=0;
    if(!d){error=9;goto done;}
    DS20HostEntry host={0};int next=ops.next(d->native,&host,&error);
    if(next<0){if(!error)error=5;goto done;}
    if(!next){error=0;goto done;}
    uint32_t n=0;while(n<256 && host.name[n]){unsigned char c=(unsigned char)host.name[n];if(c<32 || c==127 || c=='/' || c=='\\' || c==':'){error=5;goto done;}++n;}
    if(!n || n==256){error=n?36:5;goto done;}
    DS20Dirent packed={0};packed.ino=host.ino;packed.off=(int64_t)++d->offset;
    packed.reclen=(uint16_t)((20+n+7)&~7u);packed.type=(uint8_t)host.type;
    if(host.type!=0 && host.type!=1 && host.type!=2 && host.type!=4 && host.type!=6 && host.type!=8 && host.type!=10 && host.type!=12 && host.type!=14)packed.type=0;
    memcpy(packed.name,host.name,n);memcpy(entry,&packed,sizeof(packed));*result=entry;
done:ds7_gate_unlock();return error;
}
int DS_IO_SOFT ds20_closedir(void *handle){
    ds7_gate_lock();Directory *d=lookup(handle);int error=0,result=-1;
    if(!d)error=9;
    else{result=ops.close(d->native,&error);memset(d,0,sizeof(*d));if(result && !error)error=5;}
    ds7_gate_unlock();if(result)*ds_io_errno()=error;return result;
}
uint32_t ds20_bindings(DSBinding *out,uint32_t capacity){
    const DSBinding list[]={{"opendir",(uint32_t)ds20_opendir},{"readdir_r",(uint32_t)ds20_readdir_r},{"closedir",(uint32_t)ds20_closedir},{"mkdir",(uint32_t)ds6_mkdir}};
    if(capacity<4)return 0;
    memcpy(out,list,sizeof(list));return 4;
}
