#include <3ds.h>
#include <inttypes.h>
#include <malloc.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "ds_elf.h"
#include "ds_exec.h"
#include "ds_jni.h"
#include "ds_bootstrap.h"
#include "donor_config.h"

#define DATA_DIR "sdmc:/3ds/deadspace"
#define LOG_PATH DATA_DIR "/stage3-v0.3.0-log.txt"
static PrintConsole top, bottom;
static DSJniContext jni;
static FILE *log_file;
static bool retry_allowed = true;
static char status_line[80];

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

static void run_probe(void) {
    consoleSelect(&top); consoleClear();
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 3 v0.3.0\n");
    report("JNI bootstrap diagnostics\n");
    report("Gameplay is not implemented.\n\n");
    bool new_model = false;
    Result model = APT_CheckNew3DS(&new_model);
    report("New 3DS: %s\n", R_SUCCEEDED(model) && new_model ? "yes" : "no");
    FILE *input = fopen(DATA_DIR "/libEAMGameDeadSpace_orig.so", "rb");
    uint8_t *file = NULL, *image = NULL;
    DSExec exec = {0};
    bool passed = false;
    if (!input) { report("Missing library on SD card.\n"); goto done; }
    if (fseek(input, 0, SEEK_END)) goto done;
    long length = ftell(input);
    if (length != DS_DONOR_SIZE || fseek(input, 0, SEEK_SET)) { report("Donor size mismatch.\n"); goto done; }
    file = malloc((size_t)length);
    if (!file || fread(file, 1, (size_t)length, input) != (size_t)length) goto done;
    fclose(input); input = NULL;
    if (ds_crc32(file, (uint32_t)length) != DS_DONOR_CRC32) { report("Donor CRC mismatch.\n"); goto done; }
    DSInfo info;
    int result = ds_elf_inspect(file, (uint32_t)length, &info);
    if (result != DS_OK) { report("ELF: %s\n", ds_elf_error(result)); goto done; }
    image = memalign(4096, info.image_size);
    if (!image) goto done;
    if (ds_elf_prepare(file, (uint32_t)length, image, info.image_size, (uint32_t)(uintptr_t)image, &info) != DS_OK) goto done;
    DSBootstrap plan;
    result = ds_bootstrap_verify(file, (uint32_t)length, image, info.image_size, (uint32_t)(uintptr_t)image, &info, &plan);
    report("JNI code + writable VM slot: %s\n", ds_elf_error(result));
    if (result != DS_OK) goto done;
    ds_jni_init(&jni);
    void *env = NULL;
    typedef int (*VMGetEnv)(DSJniHandle *, void **, int) DS_JNI_SOFT;
    int env_result = ((VMGetEnv)jni.vm.functions[6])(&jni.vm, &env, DS_JNI_VERSION_1_4);
    report("JavaVM.GetEnv: %d, env matches: %s\n", env_result, env == &jni.env ? "yes" : "no");
    if (env_result || env != &jni.env) goto done;
    Result native = ds_exec_open(&exec);
    if (R_FAILED(native)) { report("Backend error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    exec.trace = checkpoint;
    report("Backend: %s\n", exec.emulator ? "emulator (RX not tested)" : "Luma3DS native RX");
    uint32_t functions[] = {plan.on_load, plan.get_chars, plan.release_chars};
    for (uint32_t i = 0; i < 3; ++i) {
        native = ds_exec_page(&exec, image + functions[i] - info.load_min);
        if (R_FAILED(native)) { report("RX/cache error: %08" PRIx32 ", query perm=%" PRIu32 "\n", (uint32_t)native, exec.observed_memory.perm); goto done; }
    }
    typedef int (*OnLoad)(void *, void *) DS_JNI_SOFT;
    report("Calling verified JNI_OnLoad...\n");
    int version = ((OnLoad)(image + plan.on_load - info.load_min))(&jni.vm, NULL);
    uint32_t saved_vm = *(uint32_t *)(image + plan.vm_storage - info.load_min);
    report("JNI_OnLoad: %08" PRIx32 " (expected 00010004)\n", (uint32_t)version);
    report("Game stored JavaVM pointer: %s\n", saved_vm == (uint32_t)(uintptr_t)&jni.vm ? "MATCH" : "MISMATCH");
    if (version != DS_JNI_VERSION_1_4 || saved_vm != (uint32_t)(uintptr_t)&jni.vm) goto done;
    static const char path[] = "sdmc:/3ds/deadspace/assets/published/";
    void *string = ds_jni_new_string(&jni, path);
    if (!string) goto done;
    typedef const char *(*GetChars)(DSJniHandle *, void *, uint8_t *) DS_JNI_SOFT;
    typedef void (*ReleaseChars)(DSJniHandle *, void *, const char *) DS_JNI_SOFT;
    uint8_t is_copy = 99;
    report("Calling game JNI string wrappers...\n");
    const char *bytes = ((GetChars)(image + plan.get_chars - info.load_min))(&jni.env, string, &is_copy);
    if (bytes != jni.strings[0].bytes || strcmp(bytes, path) || is_copy != 0) { report("JNI string roundtrip failed.\n"); goto done; }
    ((ReleaseChars)(image + plan.release_chars - info.load_min))(&jni.env, string, bytes);
    ds_jni_delete_string(&jni, string);
    report("Game -> JNI callback -> game: MATCH\n");
    report("Callbacks: get=%" PRIu32 " release=%" PRIu32 " errors=%" PRIu32 "\n", jni.get_chars, jni.releases, jni.error);
    report("String released: %s\n", !jni.strings[0].used && !jni.strings[0].pins ? "yes" : "no");
    if (jni.error || jni.get_chars != 1 || jni.releases != 1 || jni.strings[0].used || jni.strings[0].pins) goto done;
    report("No constructors or engine entry point called.\n");
    passed = true;
done:
    if (input) fclose(input);
    Result restore = ds_exec_close(&exec);
    if (R_FAILED(restore)) {
        report("RW restore failed: %08" PRIx32 "\n", (uint32_t)restore);
        image = NULL; passed = false; retry_allowed = false;
    }
    free(image); free(file);
    report("\nSTAGE 3 %s\n", passed ? "PASSED" : "STOPPED; see log.");
    snprintf(status_line, sizeof(status_line), "Stage 3 %s; send new log", passed ? "passed" : "stopped");
    report("Log: %s\n", log_file ? "stage3-v0.3.0-log.txt saved" : "SD log unavailable");
    if (log_file) { fclose(log_file); log_file = NULL; }
}

int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP, &top); consoleInit(GFX_BOTTOM, &bottom);
    consoleSelect(&top);
    mkdir("sdmc:/3ds", 0777); mkdir(DATA_DIR, 0777);
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 3 v0.3.0\n\n");
    report("STAGE 3 READY - press A\n\n");
    report("A starts the JNI bootstrap test.\n");
    report("START exits without running it.\n");
    if (log_file) { fclose(log_file); log_file = NULL; }
    snprintf(status_line, sizeof(status_line), "Ready: A starts JNI test");
    while (aptMainLoop()) {
        hidScanInput();
        if (hidKeysDown() & KEY_START) break;
        if ((hidKeysDown() & KEY_A) && retry_allowed) run_probe();
        consoleSelect(&bottom);
        printf("\x1b[0;0HDS LOADER TEST 3\n\nA: run test    START: exit\n\n");
        printf("%-38.38s\n\n", status_line);
        printf("JNI subset, no Java runtime.\n");
        printf("Engine startup is not called.\n\n");
        printf("Log: /3ds/deadspace/\n");
        printf("     stage3-v0.3.0-log.txt\n");
        gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    }
    gfxExit(); return 0;
}
