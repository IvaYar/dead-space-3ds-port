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
#include "donor_config.h"
#include "stage4_fixture.h"

#define DATA_DIR "sdmc:/3ds/deadspace"
#define LOG_PATH DATA_DIR "/stage4-v0.4.0-log.txt"
static PrintConsole top, bottom;
static FILE *log_file;
static bool retry_allowed = true;
static char status_line[80];
static DSIO io;

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
             resolved.resolved == 5 && resolved.missing == 383 && resolved.weak_zero == 4;
done:
    fclose(input); free(image); free(file);
    return passed;
}

static void run_probe(void) {
    consoleSelect(&top); consoleClear();
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 4 v0.4.0\n");
    report("Android file I/O bridge diagnostics\n");
    report("Gameplay is not implemented.\n\n");
    bool new_model = false;
    Result model = APT_CheckNew3DS(&new_model);
    report("New 3DS: %s\n", R_SUCCEEDED(model) && new_model ? "yes" : "no");
    DSExec exec = {0};
    uint8_t *image = NULL;
    bool passed = false;
    ds_io_init(&io, ds_io_sd_ops());
    DSBinding bindings[5];
    uint32_t count = ds_io_bindings(bindings, 5);
    if (count != 5 || !donor_preflight(bindings, count)) goto done;
    DSInfo info;
    if (ds_elf_inspect(stage4_fixture, sizeof(stage4_fixture), &info) != DS_OK) goto done;
    image = memalign(4096, info.image_size);
    if (!image || ds_elf_prepare(stage4_fixture, sizeof(stage4_fixture), image, info.image_size, (uint32_t)(uintptr_t)image, &info) != DS_OK) goto done;
    DSResolve resolved;
    int result = ds_elf_resolve(stage4_fixture, &info, image, bindings, count, &resolved);
    report("I/O probe bindings: %s (%" PRIu32 "/5)\n", ds_elf_error(result), resolved.resolved);
    if (result != DS_OK || resolved.resolved != 5) goto done;
    uint32_t address = 0, size = 0;
    if (ds_elf_find_export(stage4_fixture, &info, "probe_io", &address, &size) != DS_OK) goto done;
    if ((address & 3) || address < info.load_min || size > 4096 || (address & 4095) + size > 4096) goto done;
    Result native = ds_exec_open(&exec);
    if (R_FAILED(native)) { report("Backend error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    exec.trace = checkpoint;
    report("Backend: %s\n", exec.emulator ? "emulator (RX not tested)" : "Luma3DS native RX");
    /* Prepare PLT and body, whether or not they share a page. No constructors. */
    for (uint32_t i = 0; i < 2; ++i) {
        uint32_t function = i ? address : DS_FIXTURE_PLT_VA;
        native = ds_exec_page(&exec, image + function - info.load_min);
        if (R_FAILED(native)) { report("RX/cache error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    }
    typedef int (*Probe)(const char *, const char *, uint32_t, uint32_t, uint32_t *) DS_IO_SOFT;
    uint32_t output[12] = {0};
    report("Calling original Android-ABI I/O test module...\n");
    int code = ((Probe)(image + address - info.load_min))("appbundle:/published/data/achievements.sb",
        "appbundle:/published/data/.stage4-missing-7f49b20a", DS_ASSET_SIZE, DS_ASSET_CRC32, output);
    report("Asset: data/achievements.sb\n");
    report("Probe result: %d (expected 0)\n", code);
    if (code == 1 && output[8] == DS_ENOENT) report("Missing test asset; copy SD_CARD contents.\n");
    report("Asset bytes: %" PRIu32 " (expected %u)\n", output[1], DS_ASSET_SIZE);
    report("Asset CRC32: %08" PRIx32 " (expected %08x)\n", output[2], DS_ASSET_CRC32);
    report("Seek/EOF: %s\n", output[3] == DS_ASSET_SIZE && output[4] == 0 && output[5] == DS_ASSET_SIZE - 1 && output[6] == 1 && output[7] == 0 ? "MATCH" : "FAILED");
    report("Android errno: badfd=%" PRIu32 " missing=%" PRIu32 " readonly=%" PRIu32 "\n", output[8], output[9], output[10]);
    report("Constructor marker: %" PRIu32 " (expected 42)\n", output[11]);
    report("Bridge handles before cleanup: %" PRIu32 "\n", io.active);
    passed = code == 0 && output[0] == 0 && output[11] == 42 && !io.active && io.opens == io.closes;
    report("No game functions or constructors called.\n");
done:
    {
        int cleanup = ds_io_shutdown(&io);
        report("Bridge cleanup: %s, active=%" PRIu32 "\n", !cleanup && !io.active ? "OK" : "FAILED", io.active);
        if (cleanup || io.active) passed = false;
        Result restore = ds_exec_close(&exec);
        if (R_FAILED(restore)) {
            report("RW restore failed: %08" PRIx32 "\n", (uint32_t)restore);
            image = NULL; passed = false; retry_allowed = false;
        }
    }
    free(image);
    report("\nSTAGE 4 %s\n", passed ? "PASSED" : "STOPPED; see log.");
    snprintf(status_line, sizeof(status_line), "Stage 4 %s; send new log", passed ? "passed" : "stopped");
    report("Log: %s\n", log_file ? "stage4-v0.4.0-log.txt saved" : "SD log unavailable");
    if (log_file) { fclose(log_file); log_file = NULL; }
}
int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP, &top); consoleInit(GFX_BOTTOM, &bottom);
    consoleSelect(&top);
    mkdir("sdmc:/3ds", 0777); mkdir(DATA_DIR, 0777);
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 4 v0.4.0\n\nSTAGE 4 READY - press A\n\n");
    report("A starts the file I/O bridge test.\nSTART exits without running it.\n");
    if (log_file) { fclose(log_file); log_file = NULL; }
    snprintf(status_line, sizeof(status_line), "Ready: A starts file I/O test");
    while (aptMainLoop()) {
        hidScanInput();
        if (hidKeysDown() & KEY_START) break;
        if ((hidKeysDown() & KEY_A) && retry_allowed) run_probe();
        consoleSelect(&bottom);
        printf("\x1b[0;0HDS LOADER TEST 4\n\nA: run test    START: exit\n\n%-38.38s\n\n", status_line);
        printf("Original I/O test module.\nRead-only game asset from SD.\nEngine startup is not called.\n\n");
        printf("Log: /3ds/deadspace/\n     stage4-v0.4.0-log.txt\n");
        gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    }
    gfxExit(); return 0;
}
