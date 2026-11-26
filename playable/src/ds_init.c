#include "ds_init.h"
#include "ds_io.h"
static uint32_t word(const uint8_t *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static int executable(const uint8_t *file,const DSInfo *info,uint32_t base,uint32_t pointer) {
    uint32_t pc=pointer&~1u,bytes=pointer&1?2:4;
    if(pc<base || (pc-base)>info->image_size || bytes>info->image_size-(pc-base) || (!(pointer&1) && (pc&3))) return 0;
    uint32_t va=pc-base+info->load_min;
    for(uint32_t i=0;i<info->phnum;++i) {
        const uint8_t *p=file+info->phoff+i*32;
        uint32_t start=word(p+8),length=word(p+16);
        if(word(p)==1 && (word(p+24)&1) && va>=start && va-start<=length && bytes<=length-(va-start)) return 1;
    }
    return 0;
}
int ds_init_bind_plan(const uint8_t *file,uint32_t size,uint8_t *image,uint32_t base,
                      const DSBinding *bindings,uint32_t count,DSInitPlan *plan,DSResolve *resolved) {
    plan->count=plan->state=plan->executed=0;
    *resolved=(DSResolve){0};
    DSInfo info; int result=ds_elf_inspect(file,size,&info);
    if(result!=DS_OK) return result;
    if(info.image_size>UINT32_MAX-base) return DS_IMAGE_TOO_SMALL;
    result=ds_elf_resolve(file,&info,image,bindings,count,resolved);
    if(result!=DS_OK) return result;
    if(info.init_count>DS_INIT_MAX-(info.init_function!=0)) return DS_INIT_BAD_TARGET;
    uint32_t n=0;
    if(info.init_function) {
        uint32_t pointer=base+info.init_function-info.load_min;
        if(!executable(file,&info,base,pointer)) return DS_INIT_BAD_TARGET;
        plan->functions[n++]=pointer;
    }
    for(uint32_t i=0;i<info.init_count;++i) {
        uint32_t pointer=word(image+info.init_array-info.load_min+i*4);
        if(!pointer || pointer==UINT32_MAX) continue;
        if(!executable(file,&info,base,pointer)) return DS_INIT_BAD_TARGET;
        plan->functions[n++]=pointer;
    }
    plan->count=n; plan->state=DS_INIT_READY; return DS_OK;
}
int ds_init_run(DSInitPlan *plan) {
    if(plan->state!=DS_INIT_READY || plan->count>DS_INIT_MAX) return DS_INIT_BAD_STATE;
    plan->state=DS_INIT_RUNNING;
    typedef void (*Init)(void) DS_IO_SOFT;
    while(plan->executed<plan->count) { ((Init)plan->functions[plan->executed])(); ++plan->executed; }
    plan->state=DS_INIT_DONE; return DS_OK;
}
