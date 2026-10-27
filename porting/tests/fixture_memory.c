/* Original six-argument softfp mmap and arena ownership probe. */
#include <stdint.h>
extern void *sbrk(int32_t);
extern void *mmap(void *,uint32_t,int,int,int,int32_t);
extern int munmap(void *,uint32_t);
int probe_memory(uint32_t *out,uint32_t base) {
    unsigned checks=0;int failure=0;
#define CHECK(x) do { ++checks; if(!(x)) { failure=__LINE__; goto done; } } while(0)
    uint8_t *a,*b;
    CHECK((uint32_t)sbrk(0)==base);
    CHECK((uint32_t)sbrk(8192)==base);
    for(unsigned i=0;i<8192;++i) ((uint8_t *)base)[i]=(uint8_t)i;
    CHECK((uint32_t)sbrk(-8192)==base+8192);
    CHECK((uint32_t)sbrk(0)==base);
    a=mmap(0,8193,3,0x22,-1,0); CHECK(a!=(void *)-1 && !((uint32_t)a&4095));
    for(unsigned i=0;i<12288;++i) if(a[i]) { failure=__LINE__; goto done; }
    for(unsigned i=0;i<12288;++i) a[i]=0xaa;
    CHECK(!munmap(a+4096,4096));
    b=mmap(0,4096,3,0x22,-1,0); CHECK(b==a+4096);
    for(unsigned i=0;i<4096;++i) if(b[i]) { failure=__LINE__; goto done; }
    CHECK(!munmap(b,4096)); CHECK(!munmap(a,12288));
done:
    out[0]=(uint32_t)failure;out[1]=checks;return failure;
}
