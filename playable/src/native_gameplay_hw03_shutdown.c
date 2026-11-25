#include "native_gameplay_hw03_shutdown.h"
#include <string.h>
void hw03_shutdown_bind(H3Shutdown *s, DSIO *io){
    memset(s,0,sizeof(*s));s->owner=io;s->ops=io->ops;
}
int hw03_phase_run(H3Shutdown *s,unsigned p,H3CleanupOp op,void *user){
    if(!s || !s->owner || !op || p>=H3_PHASES || s->done>=(1u<<H3_PHASES) ||
       (s->done & (s->done+1u)))return -100;
    uint32_t bit=1u<<p;
    if(s->done & bit)return 0;
    if(s->done!=bit-1u)return -100;
    int r=op(p,user);if(!r)s->done|=bit;return r;
}
static uint32_t seal(const DSIO *io){
    /* errno may change independently. Everything else must remain closed/immutable. */
    uint32_t h=2166136261u;
    const unsigned char *p=(const unsigned char *)io;
    for(unsigned i=0;i<sizeof(*io);++i){
        if(i>=__builtin_offsetof(DSIO,error) && i<__builtin_offsetof(DSIO,error)+sizeof(io->error))continue;
        h=(h^p[i])*16777619u;
    }return h;
}
int hw03_close_io(H3Shutdown *s,DSIO *io){
    if(!s || !io || s->owner!=io || s->io_failed ||
       memcmp(&s->ops,&io->ops,sizeof(io->ops)) || !io->ops.open || !io->ops.read ||
       !io->ops.seek || !io->ops.close)return -1;
    if(s->io_closed){
        if(!hw03_io_detached() || io->active || io->opens!=io->closes || seal(io)!=s->io_seal)return -1;
        for(unsigned i=0;i<DS_IO_FILES;++i)if(io->handles[i])return -1;
        return 0;
    }
    if(!hw03_io_current(io))return -1;
    if(ds_io_shutdown(io)){s->io_failed=1;return -1;}
    if(!hw03_io_detached() || io->active || io->opens!=io->closes){s->io_failed=1;return -1;}
    for(unsigned i=0;i<DS_IO_FILES;++i)if(io->handles[i]){s->io_failed=1;return -1;}
    s->io_seal=seal(io);s->io_closed=1;return 0;
}
