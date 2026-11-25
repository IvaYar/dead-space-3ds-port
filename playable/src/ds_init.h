#ifndef DS_INIT_H
#define DS_INIT_H
#include "ds_elf.h"
#define DS_INIT_MAX 256u
enum { DS_INIT_EMPTY=0,DS_INIT_READY=1,DS_INIT_RUNNING=2,DS_INIT_DONE=3 };
enum { DS_INIT_BAD_TARGET=11,DS_INIT_BAD_STATE=12 };
typedef struct { uint32_t count,state,executed,functions[DS_INIT_MAX]; } DSInitPlan;
/* Fresh prepare() image only. Resolves once, then snapshots all constructor
 * targets before any invocation. On error plan is empty; calls no module code. */
int ds_init_bind_plan(const uint8_t *file,uint32_t size,uint8_t *image,uint32_t base,
                      const DSBinding *bindings,uint32_t count,DSInitPlan *plan,DSResolve *resolved);
/* Platform must make code RX first. A plan can run only once, including reentry. */
int ds_init_run(DSInitPlan *plan);
#endif
