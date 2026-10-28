#include "ds29_allocator.h"
#include <string.h>
static uint32_t growth_return;
int ds29_allocator_init(const void *image,uint32_t bytes){
    /* Exact unrelocated ARM instructions spanning both sbrk calls and the
     * erroneous comparison; refuse another donor/version before enabling. */
    static const uint32_t expected[]={
        0xe3a00000,0x858d5004,0xebf78db6,0xe1a06000,0xe59d0004,
        0xebf78db3,0xe3760001,0x13700001,0x1a00000b,0xe28d2008,
        0xe5225004,0xe1a01005,0xe1a00004,0xebffff44,0xe2506000,
        0x01a00006,0x0a00003e,0xe59d3004,0xe3a0c003,0xe3a05001,
        0xea000007,0xe1560000,0x2afffff1,0xe3560000,0xe0663000
    };
    uintptr_t base=(uintptr_t)image;
    if(!base || (base&3) || bytes<0x253424+sizeof(expected) || bytes>UINT32_MAX-base ||
       memcmp((const uint8_t *)image+0x253424,expected,sizeof(expected)))return 22;
    growth_return=(uint32_t)base+0x25343c;return 0;
}
void ds29_allocator_reset(void){growth_return=0;}
void *DS_IO_SOFT ds29_sbrk(int32_t increment,uint32_t caller){
    void *old=ds9_sbrk(increment);
    if(old!=(void *)-1 && increment>0 && growth_return && caller==growth_return)
        return (uint8_t *)old+(uint32_t)increment;
    return old;
}
