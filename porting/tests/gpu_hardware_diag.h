#ifndef GPU_HARDWARE_DIAG_H
#define GPU_HARDWARE_DIAG_H
#include <stdio.h>
#define GPU_HARDWARE_ROOT "sdmc:/3ds/ds34-gpu-test-v" GPU_TEST_VERSION "/"
void gpu_diag_init(FILE *journal,int emulator);
int gpu_diag_timed_out(void);
const char *gpu_diag_timeout_phase(void);
int gpu_diag_can_exit(void);
void gpu_queue_init(FILE *journal);
void gpu_queue_snapshot(const char *phase);
#endif
