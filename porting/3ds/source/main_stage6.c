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
#include "ds6.h"
#include "donor_config.h"
#include "stage6_fixture.h"

#define DATA_DIR "sdmc:/3ds/deadspace"
#define LOG_PATH DATA_DIR "/stage6-v0.6.0-log.txt"
static PrintConsole top, bottom;
static FILE *log_file;
static bool retry_allowed = true;
static char status_line[80];
static DSIO io;
static uint32_t probe_runs, log_calls;

static void persist(void) {
    if (!log_file) return;
    fflush(log_file); fclose(log_file); log_file = fopen(LOG_PATH, "a");
}
static void report(const char *format, ...) {
    va_list args;
    va_start(args, format); vprintf(format, args); va_end(args);
    if (log_file) { va_start(args, format); vfprintf(log_file, format, args); va_end(args); persist(); }
}
static void android_log(const char *text) { ++log_calls; report("ANDROID: %s\n",text); }
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
             resolved.resolved == 108 && resolved.missing == 280 && resolved.weak_zero == 4;
done:
    fclose(input); free(image); free(file);
    return passed;
}

static void run_probe(void) {
    consoleSelect(&top); consoleClear();
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 6 v0.6.0\n");
    report("Bionic structures and libc diagnostics\n");
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
    ds6_init(android_log); log_calls=0;
    DSBinding bindings[128];
    uint32_t count = ds6_bindings(bindings, 128);
    if (count != 108 || !donor_preflight(bindings, count)) goto done;
    DSInfo info;
    if (ds_elf_inspect(stage6_fixture, sizeof(stage6_fixture), &info) != DS_OK) goto done;
    image = memalign(4096, info.image_size);
    if (!image || ds_elf_prepare(stage6_fixture, sizeof(stage6_fixture), image, info.image_size,
                                 (uint32_t)(uintptr_t)image, &info) != DS_OK) goto done;
    DSResolve resolved;
    int result = ds_elf_resolve(stage6_fixture, &info, image, bindings, count, &resolved);
    report("Bionic probe bindings: %s (%" PRIu32 "/57)\n", ds_elf_error(result), resolved.resolved);
    if (result != DS_OK || resolved.resolved != 57) goto done;
    const char *names[] = {"probe_basics", "probe_files", "probe_time"};
    uint32_t functions[3];
    for (uint32_t i = 0; i < 3; ++i) {
        uint32_t size;
        if (ds_elf_find_export(stage6_fixture, &info, names[i], &functions[i], &size) != DS_OK) goto done;
    }
    Result native = ds_exec_open(&exec);
    if (R_FAILED(native)) { report("Backend error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    exec.trace = checkpoint;
    report("Backend: %s\n", exec.emulator ? "emulator (RX not tested)" : "Luma3DS native RX");
    for (uint32_t i = 0; i < sizeof(stage6_exec_pages) / sizeof(stage6_exec_pages[0]); ++i) {
        native = ds_exec_page(&exec, image + stage6_exec_pages[i] - info.load_min);
        if (R_FAILED(native)) { report("RX/cache error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    }
    typedef int (*Probe)(uint32_t *) DS_IO_SOFT;
    uint32_t output[3][8]={{0}};
    report("Calling original softfp Bionic probes...\n");
    int basics=((Probe)(image+functions[0]-info.load_min))(output[0]);
    report("Formatting/numeric/env/atomic: %d, checks=%" PRIu32 "\n",basics,output[0][1]);
    report("Android log callbacks: %" PRIu32 " (expected 3)\n",log_calls);
    report("Constructor marker: %" PRIu32 " (expected 42)\n",output[0][2]);
    if(basics || output[0][2]!=42 || log_calls!=3) goto done;
    int files=((Probe)(image+functions[1]-info.load_min))(output[1]);
    report("Bionic FILE/stat + SD roundtrip: %d\n",files);
    report("Asset bytes=%" PRIu32 " CRC32=%08" PRIx32 "\n",output[1][1],output[1][2]);
    if(files) goto done;
    int timing=((Probe)(image+functions[2]-info.load_min))(output[2]);
    report("Time/calendar/sleep: %d, checks=%" PRIu32 "\n",timing,output[2][1]);
    passed=!timing && output[1][1]==3568 && output[1][2]==0x4a8d9499u;
    report("No game functions or constructors called.\n");
done:
    {
        uint32_t unclosed = ds6_cleanup();
        DSRuntimeStats stats; ds_runtime_stats(&stats);
        report("Runtime heap before cleanup: live=%" PRIu32 " bytes=%" PRIu32 "\n",stats.live_blocks,stats.live_bytes);
        uint32_t leaked = ds_runtime_cleanup();
        int cleanup = ds_io_shutdown(&io);
        report("Cleanup: leaked-blocks=%" PRIu32 " active-files=%" PRIu32 "\n", leaked, io.active);
        if (unclosed || leaked || cleanup || io.active) passed = false;
        Result restore = ds_exec_close(&exec);
        if (R_FAILED(restore)) {
            report("RW restore failed: %08" PRIx32 "\n", (uint32_t)restore);
            image = NULL; passed = false; retry_allowed = false;
        }
    }
    free(image);
    report("\nSTAGE 6 %s\n", passed ? "PASSED" : "STOPPED; see log.");
    snprintf(status_line, sizeof(status_line), "Stage 6 %s; send new log", passed ? "passed" : "stopped");
    report("Log: %s\n", log_file ? "stage6-v0.6.0-log.txt saved" : "SD log unavailable");
    if (log_file) { fclose(log_file); log_file = NULL; }
}
int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP, &top); consoleInit(GFX_BOTTOM, &bottom);
    consoleSelect(&top);
    mkdir("sdmc:/3ds", 0777); mkdir(DATA_DIR, 0777); mkdir(DATA_DIR "/test-output",0777);
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 6 v0.6.0\n\nSTAGE 6 READY - press A\n\n");
    report("A starts the runtime bridge test.\nSTART exits without running it.\n");
    if (log_file) { fclose(log_file); log_file = NULL; }
    snprintf(status_line, sizeof(status_line), "Ready: A starts runtime test");
    while (aptMainLoop()) {
        hidScanInput();
        if (hidKeysDown() & KEY_START) break;
        if ((hidKeysDown() & KEY_A) && retry_allowed) run_probe();
        consoleSelect(&bottom);
        printf("\x1b[0;0HDS LOADER TEST 6\n\nA: run test    START: exit\n\n%-38.38s\n\n", status_line);
        printf("Original Bionic test modules.\nstdio, stat, time and atomics.\nEngine startup is not called.\n\n");
        printf("Log: /3ds/deadspace/\n     stage6-v0.6.0-log.txt\n");
        gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    }
    gfxExit(); return 0;
}
