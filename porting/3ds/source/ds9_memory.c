#include "ds9_memory.h"
#include <string.h>
enum { PAGE=4096,MAX_PAGES=8192 };
static uint8_t *break_base,*map_base;
static uint32_t break_capacity,page_count;
static uint8_t pages[MAX_PAGES];
static DS9MemoryStats stats;
static void *refuse(int error) { ++stats.refusals; *ds_io_errno()=error; ds7_gate_unlock(); return (void *)-1; }
int ds9_memory_init(void *brk_arena,uint32_t brk_size,void *map_arena,uint32_t map_size) {
    uintptr_t a=(uintptr_t)brk_arena,b=(uintptr_t)map_arena;
    if(!a || !b || !brk_size || !map_size || ((a|b|brk_size|map_size)&(PAGE-1)) ||
       brk_size>UINT32_MAX-a || map_size>UINT32_MAX-b || map_size/PAGE>MAX_PAGES ||
       (a<b+map_size && b<a+brk_size)) return 22;
    ds7_gate_lock();
    if(stats.break_bytes || stats.mapped_pages) { ds7_gate_unlock(); return 16; }
    break_base=brk_arena; break_capacity=brk_size; map_base=map_arena; page_count=map_size/PAGE;
    memset(pages,0,sizeof(pages)); memset(&stats,0,sizeof(stats)); ds7_gate_unlock(); return 0;
}
void ds9_memory_stats(DS9MemoryStats *out) { ds7_gate_lock(); *out=stats; ds7_gate_unlock(); }
void *DS_IO_SOFT ds9_sbrk(int32_t increment) {
    ds7_gate_lock(); ++stats.sbrk_calls;
    int64_t next=(int64_t)stats.break_bytes+increment;
    if(!break_base || next<0 || next>break_capacity) return refuse(12);
    void *old=break_base+stats.break_bytes; stats.break_bytes=(uint32_t)next;
    if(stats.break_bytes>stats.break_peak) stats.break_peak=stats.break_bytes;
    ds7_gate_unlock(); return old;
}
void *DS_IO_SOFT ds9_mmap(void *hint,uint32_t size,int protection,int flags,int fd,int32_t offset) {
    (void)hint; ds7_gate_lock(); ++stats.mmap_calls;
    if(!map_base || !size || size>UINT32_MAX-(PAGE-1) || offset) return refuse(22);
    if(protection!=3) return refuse(95);
    if(flags!=0x22 || fd!=-1) return refuse(95);
    uint32_t n=(size+PAGE-1)/PAGE,run=0;
    for(uint32_t i=0;i<page_count;++i) {
        run=pages[i]?0:run+1;
        if(run==n) {
            uint32_t start=i+1-n;
            for(uint32_t j=start;j<=i;++j) pages[j]=1;
            stats.mapped_pages+=n; if(stats.mapped_pages>stats.map_peak) stats.map_peak=stats.mapped_pages;
            uint8_t *memory=map_base+start*PAGE; memset(memory,0,n*PAGE);
            ds7_gate_unlock(); return memory;
        }
    }
    return refuse(12);
}
int DS_IO_SOFT ds9_munmap(void *address,uint32_t size) {
    ds7_gate_lock(); ++stats.munmap_calls;
    uintptr_t start=(uintptr_t)address,base=(uintptr_t)map_base;
    if(!map_base || !size || (start&(PAGE-1)) || size>UINT32_MAX-(PAGE-1) || start<base) { refuse(22); return -1; }
    uint32_t index=(start-base)/PAGE,n=(size+PAGE-1)/PAGE;
    if(index>page_count || n>page_count-index) { refuse(22); return -1; }
    for(uint32_t i=index;i<index+n;++i) if(pages[i]) { pages[i]=0; --stats.mapped_pages; }
    ds7_gate_unlock(); return 0;
}
uint32_t ds9_memory_bindings(DSBinding *out,uint32_t capacity) {
    const DSBinding list[]={ {"sbrk",(uint32_t)ds9_sbrk},{"mmap",(uint32_t)ds9_mmap},{"munmap",(uint32_t)ds9_munmap} };
    if(capacity<3) return 0;
    for(uint32_t i=0;i<3;++i) out[i]=list[i];
    return 3;
}
