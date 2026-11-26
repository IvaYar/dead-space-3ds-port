#ifndef NATIVE_GAMEPLAY_HW03_SHUTDOWN_H
#define NATIVE_GAMEPLAY_HW03_SHUTDOWN_H
#include "ds_io.h"
/* Ordered prefix of completed phases. Never infer completion from worker/IO counts. */
enum {
    H3_RELEASE_INPUT, H3_CLOSE_INPUT, H3_LOADERS, H3_LIFECYCLE, H3_DESTRUCTORS,
    H3_AUDIO_WORKERS, H3_JOB_WORKERS, H3_PERIODIC, H3_QUIET, H3_AUDIO_RELEASE,
    H3_JNI, H3_STDIO, H3_APPDATA, H3_IO, H3_JOIN, H3_SENSOR,
    H3_GPU_FINISH, H3_GPU_DRAIN, H3_GPU_FINI, H3_AFTER, H3_EXIT, H3_PHASES
};
typedef struct {
    uint32_t done, io_failed, io_seal, io_closed;
    DSIO *owner;
    DSIOOps ops;
} H3Shutdown;
typedef int (*H3CleanupOp)(unsigned, void *);
void hw03_shutdown_bind(H3Shutdown *, DSIO *);
int hw03_phase_run(H3Shutdown *, unsigned, H3CleanupOp, void *);
int hw03_close_io(H3Shutdown *, DSIO *);
int hw03_io_current(const DSIO *);
int hw03_io_detached(void);
#endif
