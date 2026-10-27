#include <3ds.h>
#include <inttypes.h>
#include <malloc.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include "ds_elf.h"
#include "ds_exec.h"
#include "donor_config.h"
#include "stage2_fixture.h"

#define DATA_DIR "sdmc:/3ds/deadspace"
#define LOG_PATH DATA_DIR "/stage2-v0.2.2-log.txt"

typedef int (*SoftInteger)(int) __attribute__((pcs("aapcs")));
typedef int (*SoftNoArgs)(void) __attribute__((pcs("aapcs")));
typedef float (*SoftFloat)(float, float) __attribute__((pcs("aapcs")));
typedef int (*SoftConstant)(void *, void *) __attribute__((pcs("aapcs")));

static PrintConsole top, bottom;
static FILE *log_file;
static bool retry_allowed = true;
static char status_line[80];

static void persist_log(void) {
    if (!log_file) return;
    fflush(log_file);
    fclose(log_file);
    log_file = fopen(LOG_PATH, "a");
}

static void report(const char *format, ...) {
    va_list args;
    va_start(args, format); vprintf(format, args); va_end(args);
    if (log_file) {
        va_start(args, format); vfprintf(log_file, format, args); va_end(args);
        persist_log(); /* Close the SD file at each checkpoint, before any cache operation. */
    }
}

static void report_exec_details(const DSExec *exec, bool show_on_screen) {
    /* Successful per-page details go only to the SD log to keep the screens readable. */
    if (!show_on_screen && !log_file) return;
    FILE *out = show_on_screen ? stdout : log_file;
    fprintf(out, "RX page %08" PRIx32 ", step %" PRIu32 "\n", exec->last_address, exec->last_step);
    fprintf(out, "flush=%08" PRIx32 " protect=%08" PRIx32 " query=%08" PRIx32 "\n",
            (uint32_t)exec->flush_result, (uint32_t)exec->protect_result, (uint32_t)exec->query_result);
    if (exec->observed_valid)
        fprintf(out, "QueryProcessMemory: perm=%" PRIu32 " base=%08" PRIx32 " size=%08" PRIx32 " state=%" PRIu32 " flags=%08" PRIx32 "\n",
                exec->observed_memory.perm, exec->observed_memory.base_addr, exec->observed_memory.size,
                exec->observed_memory.state, exec->observed_page.flags);
    if (show_on_screen && log_file) report_exec_details(exec, false);
    persist_log();
}

static void exec_checkpoint(u32 step, u32 address) {
    if (!log_file) return;
    fprintf(log_file, "CHECKPOINT step=%" PRIu32 " page=%08" PRIx32 " I-cache=entire (0x94)\n", step, address);
    persist_log();
}

static int __attribute__((pcs("aapcs"), noinline)) host_integer(int value) { return value * 3 + 1; }
static float __attribute__((pcs("aapcs"), noinline)) host_add_float(float a, float b) { return a + b; }

static void *find_function(const uint8_t *file, const DSInfo *info, uint8_t *image, const char *name) {
    uint32_t value = 0, size = 0;
    if (ds_elf_find_export(file, info, name, &value, &size) != DS_OK) return NULL;
    return image + value - info->load_min;
}

static bool fixture_probe(DSExec *exec) {
    DSInfo info;
    uint8_t *image = NULL;
    bool passed = false;
    if (ds_elf_inspect(stage2_fixture, sizeof(stage2_fixture), &info) != DS_OK) goto done;
    image = memalign(4096, info.image_size);
    if (!image) goto done;
    int result = ds_elf_prepare(stage2_fixture, sizeof(stage2_fixture), image, info.image_size,
                              (uint32_t)(uintptr_t)image, &info);
    if (result != DS_OK) goto done;
    DSBinding bindings[] = {
        { "host_integer", (uint32_t)(uintptr_t)host_integer },
        { "host_add_float", (uint32_t)(uintptr_t)host_add_float },
    };
    DSResolve resolved;
    result = ds_elf_resolve(stage2_fixture, &info, image, bindings, 2, &resolved);
    report("Fixture bindings: %s, weak-null %" PRIu32 "\n", ds_elf_error(result), resolved.weak_zero);
    if (result != DS_OK || resolved.weak_zero != 1) goto done;
    void *integer = find_function(stage2_fixture, &info, image, "probe_integer");
    void *floating = find_function(stage2_fixture, &info, image, "probe_float");
    void *weak = find_function(stage2_fixture, &info, image, "probe_weak");
    if (!integer || !floating || !weak) goto done;
    void *functions[] = {integer, floating, weak};
    for (uint32_t i = 0; i < 3; ++i) {
        Result permission = ds_exec_page(exec, functions[i]);
        report_exec_details(exec, R_FAILED(permission));
        if (R_FAILED(permission)) { report("Fixture RX/cache error: %08" PRIx32 "\n", (uint32_t)permission); goto done; }
    }
    report("Calling original test module...\n");
    int integer_value = ((SoftInteger)integer)(5);
    float float_value = ((SoftFloat)floating)(1.25f, 2.5f);
    int weak_value = ((SoftNoArgs)weak)();
    report("Integer bridge: %d (expected 58)\n", integer_value);
    report("Float softfp bridge: %.2f (expected 4.25)\n", (double)float_value);
    report("Weak import: %d (expected 7)\n", weak_value);
    passed = integer_value == 58 && float_value == 4.25f && weak_value == 7;
done:
    {
        Result restore = ds_exec_close(exec);
        if (R_FAILED(restore)) {
            report("RW restore failed: %08" PRIx32 "\n", (uint32_t)restore);
            report("Allocation retained; exit before retry.\n");
            retry_allowed = false;
            return false;
        }
    }
    free(image);
    return passed;
}

static bool game_constants_probe(DSExec *exec) {
    FILE *input = fopen(DATA_DIR "/libEAMGameDeadSpace_orig.so", "rb");
    uint8_t *file = NULL, *image = NULL;
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
    if (result != DS_OK) { report("Donor ELF: %s\n", ds_elf_error(result)); goto done; }
    struct {
        const char *name;
        const char *label;
        uint32_t instruction;
        int expected;
    } probes[] = {
        {"Java_com_ea_blast_ModuleCatalog_NativeGetModuleTypeIdInvalid", "Invalid module ID", 0xe3e00000u, -1},
        {"Java_com_ea_blast_DisplayAndroidDelegate_NativeGetOrientationNormal", "Normal orientation", 0xe3a00001u, 1},
        {"Java_com_ea_blast_DeviceOrientationHandlerAndroidDelegate_NativeGetDeviceOrientationUnknown", "Unknown orientation", 0xe3a00000u, 0},
    };
    uint32_t addresses[3];
    for (uint32_t i = 0; i < 3; ++i) {
        if (ds_elf_constant_export(file, &info, probes[i].name, probes[i].instruction, &addresses[i]) != DS_OK) {
            report("Getter instruction verification failed.\n"); goto done;
        }
    }
    image = memalign(4096, info.image_size);
    if (!image) goto done;
    if (ds_elf_prepare(file, (uint32_t)length, image, info.image_size, (uint32_t)(uintptr_t)image, &info) != DS_OK) goto done;
    report("Donor mapped; 3 getter bodies verified.\n");
    for (uint32_t i = 0; i < 3; ++i) {
        uint8_t *function = image + addresses[i] - info.load_min;
        const uint32_t *instructions = (const uint32_t *)function;
        if (instructions[0] != probes[i].instruction || instructions[1] != 0xe12fff1eu) {
            report("Mapped getter instruction verification failed.\n"); goto done;
        }
        Result permission = ds_exec_page(exec, function);
        report_exec_details(exec, R_FAILED(permission));
        if (R_FAILED(permission)) { report("Donor RX/cache error: %08" PRIx32 "\n", (uint32_t)permission); goto done; }
        report("Calling %s...\n", probes[i].label);
        int value = ((SoftConstant)function)(NULL, NULL);
        report("Returned %d (expected %d).\n", value, probes[i].expected);
        if (value != probes[i].expected) goto done;
    }
    passed = true;
    report("No engine entry point or constructors called.\n");
done:
    if (input) fclose(input);
    {
        Result restore = ds_exec_close(exec);
        if (R_FAILED(restore)) {
            report("RW restore failed: %08" PRIx32 "\n", (uint32_t)restore);
            retry_allowed = false;
            image = NULL; /* Retain this allocation until process exit. */
            passed = false;
        }
    }
    free(image); free(file);
    return passed;
}

static void run_probe(void) {
    consoleSelect(&top); consoleClear();
    mkdir("sdmc:/3ds", 0777); mkdir(DATA_DIR, 0777);
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 2 v0.2.2\n");
    report("Execution and ABI diagnostics\n");
    report("Gameplay is not implemented.\n\n");
    bool new_model = false;
    Result model = APT_CheckNew3DS(&new_model);
    report("New 3DS: %s\n", R_SUCCEEDED(model) && new_model ? "yes" : "no");
    DSExec exec;
    Result result = ds_exec_open(&exec);
    if (R_FAILED(result)) { report("Execution backend unavailable: %08" PRIx32 "\n", (uint32_t)result); goto failed; }
    report("Backend: %s\n", exec.emulator ? "emulator (RX not tested)" : "Luma3DS native RX");
    exec.trace = exec_checkpoint;
    if (!exec.emulator) report("Luma version raw: %08" PRIx32 "\n", exec.luma_version);
    if (!fixture_probe(&exec)) goto failed;
    result = ds_exec_open(&exec);
    if (R_FAILED(result)) goto failed;
    exec.trace = exec_checkpoint;
    if (!game_constants_probe(&exec)) goto failed;
    report("\nSTAGE 2 PASSED\n");
    snprintf(status_line, sizeof(status_line), "Stage 2 passed; send v0.2.2 log");
    goto done;
failed:
    report("\nSTAGE 2 STOPPED; see log.\n");
    snprintf(status_line, sizeof(status_line), "Stage 2 stopped; send v0.2.2 log");
done:
    report("Log: %s\n", log_file ? "stage2-v0.2.2-log.txt saved" : "SD log unavailable");
    if (log_file) { fclose(log_file); log_file = NULL; }
}

int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP, &top); consoleInit(GFX_BOTTOM, &bottom);
    consoleSelect(&top);
    mkdir("sdmc:/3ds", 0777); mkdir(DATA_DIR, 0777);
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 2 v0.2.2\n\n");
    report("STAGE 2 READY - press A\n\n");
    report("No loaded code executed at startup.\n");
    report("A starts the execution/ABI test.\n");
    report("START exits.\n\n");
    report("I-cache: whole-cache operation (0x94).\n");
    if (log_file) { fclose(log_file); log_file = NULL; }
    snprintf(status_line, sizeof(status_line), "Ready: A starts test, START exits");
    while (aptMainLoop()) {
        hidScanInput();
        if (hidKeysDown() & KEY_START) break;
        if ((hidKeysDown() & KEY_A) && retry_allowed) run_probe();
        consoleSelect(&bottom);
        printf("\x1b[0;0HDS LOADER TEST 2\n\n");
        printf("A: rerun test   START: exit\n\n");
        printf("%-38.38s\n\n", status_line);
        printf("Original game getters only.\n");
        printf("No game startup / audio / graphics.\n\n");
        printf("Log: /3ds/deadspace/\n");
        printf("     stage2-v0.2.2-log.txt\n");
        gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    }
    gfxExit(); return 0;
}
