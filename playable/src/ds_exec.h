#ifndef DS_EXEC_H
#define DS_EXEC_H
#include <3ds.h>
#define DS_EXEC_NO_BACKEND ((Result)-1001)
#define DS_EXEC_PAGE_LIMIT ((Result)-1002)
#define DS_EXEC_BAD_PERMISSION ((Result)-1003)
#define DS_EXEC_NOT_ATTEMPTED ((Result)-1004)

typedef struct {
    Handle process;
    bool emulator;
    u32 luma_version;
    u32 pages[16], page_count;
    u32 last_address, last_step;
    Result flush_result, protect_result, query_result;
    MemInfo observed_memory;
    PageInfo observed_page;
    bool observed_valid;
    void (*trace)(u32 step, u32 address);
} DSExec;

enum {
    DS_EXEC_STEP_NONE = 0, DS_EXEC_STEP_FLUSH = 1, DS_EXEC_STEP_PROTECT = 2,
    DS_EXEC_STEP_QUERY = 3, DS_EXEC_STEP_VERIFY = 4, DS_EXEC_STEP_ICACHE = 5,
    DS_EXEC_STEP_READY = 6
};

Result ds_exec_open(DSExec *state);
Result ds_exec_page(DSExec *state, const void *function);
/* On failure the protected allocation must be retained until process exit. */
Result ds_exec_close(DSExec *state);

#endif
