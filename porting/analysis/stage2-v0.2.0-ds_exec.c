#include "ds_exec.h"
#include <string.h>

/* Luma ABI: custom SVC 0x93, gated by the CFW/emulator checks below. */
extern void ds_invalidate_instruction_cache(void *address, u32 size);

Result ds_exec_open(DSExec *state) {
    memset(state, 0, sizeof(*state));
    s64 info = 0;
    Result probe = svcGetSystemInfo(&info, 0x20000, 0);
    state->emulator = probe == 0; /* Luma deliberately returns 1 for this probe. */
    if (!state->emulator) {
        probe = svcGetSystemInfo(&info, 0x10000, 0);
        if (R_FAILED(probe) || info < SYSTEM_VERSION(10, 0, 0) || info > 0x7fffffffLL)
            return DS_EXEC_NO_BACKEND;
        state->luma_version = (u32)info;
    }
    return svcDuplicateHandle(&state->process, CUR_PROCESS_HANDLE);
}

Result ds_exec_page(DSExec *state, const void *function) {
    u32 address = (u32)(uintptr_t)function & ~4095u;
    for (u32 i = 0; i < state->page_count; ++i) if (state->pages[i] == address) return 0;
    if (state->page_count == 16) return DS_EXEC_PAGE_LIMIT;
    Result result = svcFlushProcessDataCache(state->process, address, 4096);
    if (R_FAILED(result)) return result;
    if (!state->emulator) {
        result = svcControlProcessMemory(state->process, address, 0, 4096, MEMOP_PROT, MEMPERM_READEXECUTE);
        if (R_FAILED(result)) return result;
        state->pages[state->page_count++] = address;
        MemInfo memory; PageInfo page;
        result = svcQueryMemory(&memory, &page, address);
        if (R_FAILED(result)) return result;
        if (memory.perm != MEMPERM_READEXECUTE) return DS_EXEC_BAD_PERMISSION;
    }
    /* Azahar does not implement ControlProcessMemory and does not enforce NX.
     * Its branch only tests execution/relocation; native permissions remain untested. */
    ds_invalidate_instruction_cache((void *)(uintptr_t)address, 4096);
    return 0;
}

Result ds_exec_close(DSExec *state) {
    Result first = 0;
    for (u32 i = 0; i < state->page_count; ++i) {
        Result result = svcControlProcessMemory(state->process, state->pages[i], 0, 4096, MEMOP_PROT, MEMPERM_READWRITE);
        if (R_FAILED(result) && R_SUCCEEDED(first)) first = result;
    }
    state->page_count = 0;
    if (state->process) svcCloseHandle(state->process);
    state->process = 0;
    return first;
}
