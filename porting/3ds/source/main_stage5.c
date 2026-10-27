#include <3ds.h>
#include <inttypes.h>
#include <malloc.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include "ds_elf.h"
#include "ds_exec.h"
#include "ds_io.h"
#include "ds_runtime.h"
#include "donor_config.h"
#include "stage5_fixture.h"

#define DATA_DIR "sdmc:/3ds/deadspace"
#define LOG_PATH DATA_DIR "/stage5-v0.5.0-log.txt"
static PrintConsole top, bottom;
static FILE *log_file;
static bool retry_allowed = true;
static char status_line[80];
static DSIO io;
static uint32_t probe_runs;

static void persist(void) {
    if (!log_file) return;
    fflush(log_file); fclose(log_file); log_file = fopen(LOG_PATH, "a");
}
static void report(const char *format, ...) {
    va_list args;
    va_start(args, format); vprintf(format, args); va_end(args);
    if (log_file) { va_start(args, format); vfprintf(log_file, format, args); va_end(args); persist(); }
}
static void checkpoint(u32 step, u32 address) {
    if (log_file) { fprintf(log_file, "CHECKPOINT step=%" PRIu32 " page=%08" PRIx32 " I-cache=entire (0x94)\n", step, address); persist(); }
}

static bool donor_preflight(const DSBinding *bindings, uint32_t count) {
    bool passed = false;
    uint8_t *file = NULL, *image = NULL;
    FILE *input = fopen(DATA_DIR "/libEAMGameDeadSpace_orig.so", "rb");
    if (!input) { report("Missing library on SD card.\n"); return false; }
    if (fseek(input, 0, SEEK_END)) goto done;
    long length = ftell(input);
    if (length != DS_DONOR_SIZE || fseek(input, 0, SEEK_SET)) { report("Donor size mismatch.\n"); goto done; }
    file = malloc((size_t)length);
    if (!file || fread(file, 1, (size_t)length, input) != (size_t)length) goto done;
    if (ds_crc32(file, (uint32_t)length) != DS_DONOR_CRC32) { report("Donor CRC mismatch.\n"); goto done; }
    DSInfo info;
    if (ds_elf_inspect(file, (uint32_t)length, &info) != DS_OK) goto done;
    image = memalign(4096, info.image_size);
    if (!image || ds_elf_prepare(file, (uint32_t)length, image, info.image_size, (uint32_t)(uintptr_t)image, &info) != DS_OK) goto done;
    uint32_t before = ds_crc32(image, info.image_size);
    DSResolve resolved;
    int result = ds_elf_resolve(file, &info, image, bindings, count, &resolved);
    report("Donor imports: bound=%" PRIu32 " missing=%" PRIu32 " weak-null=%" PRIu32 "\n", resolved.resolved, resolved.missing, resolved.weak_zero);
    bool unchanged = before == ds_crc32(image, info.image_size);
    report("Incomplete donor binding: %s\n", result == DS_UNRESOLVED_IMPORTS && unchanged && !resolved.patched_sites ? "REFUSED, image unchanged" : "FAILED");
    passed = result == DS_UNRESOLVED_IMPORTS && unchanged && !resolved.patched_sites &&
             resolved.resolved == 53 && resolved.missing == 335 && resolved.weak_zero == 4;
done:
    fclose(input); free(image); free(file);
    return passed;
}

static void run_probe(void) {
    consoleSelect(&top); consoleClear();
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 5 v0.5.0\n");
    report("Memory, strings and math diagnostics\n");
    report("Gameplay is not implemented.\n\n");
    report("Run: %" PRIu32 "\n", ++probe_runs);
    bool new_model = false;
    Result model = APT_CheckNew3DS(&new_model);
    report("New 3DS: %s\n", R_SUCCEEDED(model) && new_model ? "yes" : "no");
    DSExec exec = {0};
    uint8_t *image = NULL;
    bool passed = false;
    ds_io_init(&io, ds_io_sd_ops());
    if (ds_runtime_init(1048576)) { report("Runtime initialization failed.\n"); goto done; }
    DSBinding bindings[64];
    uint32_t count = ds_platform_bindings(bindings, 64);
    if (count != 53 || !donor_preflight(bindings, count)) goto done;
    DSInfo info;
    if (ds_elf_inspect(stage5_fixture, sizeof(stage5_fixture), &info) != DS_OK) goto done;
    image = memalign(4096, info.image_size);
    if (!image || ds_elf_prepare(stage5_fixture, sizeof(stage5_fixture), image, info.image_size,
                                 (uint32_t)(uintptr_t)image, &info) != DS_OK) goto done;
    DSResolve resolved;
    int result = ds_elf_resolve(stage5_fixture, &info, image, bindings, count, &resolved);
    report("Runtime probe bindings: %s (%" PRIu32 "/49)\n", ds_elf_error(result), resolved.resolved);
    if (result != DS_OK || resolved.resolved != 49) goto done;
    const char *names[] = {"probe_memory", "probe_math"};
    uint32_t functions[2];
    for (uint32_t i = 0; i < 2; ++i) {
        uint32_t size;
        if (ds_elf_find_export(stage5_fixture, &info, names[i], &functions[i], &size) != DS_OK) goto done;
    }
    Result native = ds_exec_open(&exec);
    if (R_FAILED(native)) { report("Backend error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    exec.trace = checkpoint;
    report("Backend: %s\n", exec.emulator ? "emulator (RX not tested)" : "Luma3DS native RX");
    for (uint32_t i = 0; i < sizeof(stage5_exec_pages) / sizeof(stage5_exec_pages[0]); ++i) {
        native = ds_exec_page(&exec, image + stage5_exec_pages[i] - info.load_min);
        if (R_FAILED(native)) { report("RX/cache error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    }
    typedef int (*Probe)(uint32_t *) DS_IO_SOFT;
    uint32_t memory[8] = {0}, math[4] = {0};
    report("Calling original softfp runtime probes...\n");
    int memory_code = ((Probe)(image + functions[0] - info.load_min))(memory);
    report("Memory/string probe: %d (expected 0)\n", memory_code);
    report("Allocation overflow errno: %" PRIu32 "/%" PRIu32 " (expected 12/12)\n", memory[2], memory[3]);
    report("Constructor marker: %" PRIu32 " (expected 42)\n", memory[1]);
    DSRuntimeStats state;
    ds_runtime_stats(&state);
    report("Heap: live=%" PRIu32 " bytes=%" PRIu32 " peak=%" PRIu32 "\n", state.live_blocks, state.live_bytes, state.peak_bytes);
    report("Heap refusals=%" PRIu32 " invalid-free=%" PRIu32 "\n", state.failures, state.invalid_frees);
    if (memory_code || memory[0] || memory[1] != 42 || state.live_blocks || state.live_bytes || state.invalid_frees || state.failures != 2) goto done;
    int math_code = ((Probe)(image + functions[1] - info.load_min))(math);
    report("Float/double math: %" PRIu32 " checks, failure=%d\n", math[1], math_code);
    report("Math errno: domain=%" PRIu32 " range=%" PRIu32 " (expected 33/34)\n", math[2], math[3]);
    passed = !math_code && !math[0] && math[1] == 35 && math[2] == 33 && math[3] == 34;
    report("No game functions or constructors called.\n");
done:
    {
        uint32_t leaked = ds_runtime_cleanup();
        int cleanup = ds_io_shutdown(&io);
        report("Cleanup: leaked-blocks=%" PRIu32 " active-files=%" PRIu32 "\n", leaked, io.active);
        if (leaked || cleanup || io.active) passed = false;
        Result restore = ds_exec_close(&exec);
        if (R_FAILED(restore)) {
            report("RW restore failed: %08" PRIx32 "\n", (uint32_t)restore);
            image = NULL; passed = false; retry_allowed = false;
        }
    }
    free(image);
    report("\nSTAGE 5 %s\n", passed ? "PASSED" : "STOPPED; see log.");
    snprintf(status_line, sizeof(status_line), "Stage 5 %s; send new log", passed ? "passed" : "stopped");
    report("Log: %s\n", log_file ? "stage5-v0.5.0-log.txt saved" : "SD log unavailable");
    if (log_file) { fclose(log_file); log_file = NULL; }
}
int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP, &top); consoleInit(GFX_BOTTOM, &bottom);
    consoleSelect(&top);
    mkdir("sdmc:/3ds", 0777); mkdir(DATA_DIR, 0777);
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 5 v0.5.0\n\nSTAGE 5 READY - press A\n\n");
    report("A starts the runtime bridge test.\nSTART exits without running it.\n");
    if (log_file) { fclose(log_file); log_file = NULL; }
    snprintf(status_line, sizeof(status_line), "Ready: A starts runtime test");
    while (aptMainLoop()) {
        hidScanInput();
        if (hidKeysDown() & KEY_START) break;
        if ((hidKeysDown() & KEY_A) && retry_allowed) run_probe();
        consoleSelect(&bottom);
        printf("\x1b[0;0HDS LOADER TEST 5\n\nA: run test    START: exit\n\n%-38.38s\n\n", status_line);
        printf("Original softfp test modules.\nMemory, strings and math.\nEngine startup is not called.\n\n");
        printf("Log: /3ds/deadspace/\n     stage5-v0.5.0-log.txt\n");
        gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    }
    gfxExit(); return 0;
}
