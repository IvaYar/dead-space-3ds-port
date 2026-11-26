#ifndef NATIVE_LOADER_BUDGET_H
#define NATIVE_LOADER_BUDGET_H
#include <stdint.h>
/* Positive completed bytes/files and monotonic original task progress only.
 * Active handles, sleep/wait changes, repeated EOF and HID do not extend it. */
typedef struct {uint64_t start,last_progress;uint32_t bytes,files,progress;} LoaderBudget;
static inline void loader_budget_begin(LoaderBudget *b,uint64_t now,uint32_t bytes,uint32_t files,uint32_t progress){
    *b=(LoaderBudget){now,now,bytes,files,progress};
}
static inline unsigned loader_budget_poll(LoaderBudget *b,uint64_t now,uint32_t bytes,uint32_t files,uint32_t progress,uint32_t idle,uint32_t hard){
    if(bytes!=b->bytes || files!=b->files || (progress>b->progress && progress<=0x3f800000u))b->last_progress=now;
    b->bytes=bytes;b->files=files;if(progress<=0x3f800000u && progress>b->progress)b->progress=progress;
    if(now-b->start>=hard)return 2;
    if(now-b->last_progress>=idle)return 1;
    return 0;
}
#endif
