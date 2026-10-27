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
#include "ds7.h"
#include "ds8.h"
#include "ds_init.h"
#include "donor_config.h"
#include "stage8_fixture.h"

#define DATA_DIR "sdmc:/3ds/deadspace"
#define LOG_PATH DATA_DIR "/stage8-v0.8.0-log.txt"
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
             resolved.resolved == 149 && resolved.missing == 239 && resolved.weak_zero == 4;
done:
    fclose(input); free(image); free(file);
    return passed;
}

static void run_probe(void) {
    consoleSelect(&top); consoleClear();
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 8 v0.8.0\n");
    report("C++ constructors, guards and destructors\n");
    report("Gameplay is not implemented.\n\n");
    report("Run: %" PRIu32 "\n", ++probe_runs);
    bool new_model = false;
    Result model = APT_CheckNew3DS(&new_model);
    report("New 3DS: %s\n", R_SUCCEEDED(model) && new_model ? "yes" : "no");
    DSExec exec = {0};
    uint8_t *image = NULL;
    bool passed = false, threads_ready=false, cpp_ready=false, initialized=false;
    DSInitPlan plan={0}; uint32_t functions[3]={0}; DSInfo info;
    ds_io_init(&io, ds_io_sd_ops());
    if (ds_runtime_init(1048576)) { report("Runtime initialization failed.\n"); goto done; }
    ds6_init(android_log); log_calls=0;
    if(ds7_init()) goto done;
    threads_ready=true;
    if(ds8_init()) goto done;
    cpp_ready=true;
    DSBinding bindings[192];
    uint32_t count = ds6_bindings(bindings,192);
    count+=ds7_bindings(bindings+count,192-count);
    count+=ds8_bindings(bindings+count,192-count);
    if (count != 156 || !donor_preflight(bindings, count)) goto done;
    if (ds_elf_inspect(stage8_fixture, sizeof(stage8_fixture), &info) != DS_OK) goto done;
    image = memalign(4096, info.image_size);
    if (!image || ds_elf_prepare(stage8_fixture, sizeof(stage8_fixture), image, info.image_size,
                                 (uint32_t)(uintptr_t)image, &info) != DS_OK) goto done;
#ifdef DS8_BAD_CTOR
    if(info.init_count) *(uint32_t *)(image+info.init_array-info.load_min+(info.init_count-1)*4)=(uint32_t)image+info.image_size+4;
#endif
    DSResolve resolved;
    int result=ds_init_bind_plan(stage8_fixture,sizeof(stage8_fixture),image,(uint32_t)image,bindings,count,&plan,&resolved);
    report("C++ probe bindings: %s (%" PRIu32 "/18)\n",resolved.missing?"FAILED":"OK",resolved.resolved);
    report("Constructor plan: %s, entries=%" PRIu32 "\n",result==DS_OK?"OK":"REFUSED",plan.count);
    if(result!=DS_OK || resolved.resolved!=18) goto done;
    const char *names[]={
#ifdef DS8_INJECT_STALL
        "probe_stall",
#else
        "probe_cpp",
#endif
        "probe_snapshot","probe_snapshot"
    };
    for(uint32_t i=0;i<3;++i) {
        uint32_t size;
        if(ds_elf_find_export(stage8_fixture,&info,names[i],&functions[i],&size)!=DS_OK) goto done;
        functions[i]=(uint32_t)image+functions[i]-info.load_min;
    }
    Result native = ds_exec_open(&exec);
    if (R_FAILED(native)) { report("Backend error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    exec.trace = checkpoint;
    report("Backend: %s\n", exec.emulator ? "emulator (RX not tested)" : "Luma3DS native RX");
    for (uint32_t i = 0; i < sizeof(stage8_exec_pages) / sizeof(stage8_exec_pages[0]); ++i) {
        native = ds_exec_page(&exec, image + stage8_exec_pages[i] - info.load_min);
        if (R_FAILED(native)) { report("RX/cache error: %08" PRIx32 "\n", (uint32_t)native); goto done; }
    }
    typedef void (*Snapshot)(uint32_t *) DS_IO_SOFT;
    typedef int (*Probe)(uint32_t *) DS_IO_SOFT;
    uint32_t output[8]={0};
    ((Snapshot)functions[1])(output);
    report("Before constructors: objects=%" PRIu32 " order=%" PRIu32 "\n",output[0],output[1]);
    if(output[0] || output[1]) goto done;
    report("Running verified test-module constructors...\n");
    if(ds_init_run(&plan)!=DS_OK) goto done;
    initialized=true;
    ((Snapshot)functions[1])(output);
    report("After constructors: objects=%" PRIu32 " order=%" PRIu32 " (expected 2/912)\n",output[0],output[1]);
    int repeat=ds_init_run(&plan);
    report("Repeated constructor run: %s\n",repeat==DS_INIT_BAD_STATE?"REFUSED":"FAILED");
    if(output[0]!=2 || output[1]!=912 || repeat!=DS_INIT_BAD_STATE) goto done;
    report("Calling original softfp C++ probe...\n");
    int code=((Probe)functions[0])(output);
    report("C++ probe: %d, checks=%" PRIu32 "\n",code,output[1]);
    report("Static objects: %" PRIu32 " order=%" PRIu32 " (expected 3/9123)\n",output[2],output[3]);
    report("Filtered/reentrant destructor calls: %" PRIu32 " (expected 6)\n",output[5]);
    DS8Stats cpp; ds8_stats(&cpp);
    report("Guards: release=%" PRIu32 " abort=%" PRIu32 " waits=%" PRIu32 " active=%" PRIu32 "\n",cpp.releases,cpp.aborts,cpp.waits,cpp.active_guards);
    DS7Stats state; ds7_stats(&state);
    report("Threads: active=%" PRIu32 " finished=%" PRIu32 "\n",state.active_threads,state.finished_threads);
    report("Pools: mutex=%" PRIu32 " cond=%" PRIu32 " sem=%" PRIu32 " keys=%" PRIu32 "\n",state.mutexes,state.conditions,state.semaphores,state.keys);
    passed=!code && output[2]==3 && output[3]==9123 && !output[4] && output[5]==6 &&
           cpp.releases==2 && cpp.aborts==1 && cpp.waits && !cpp.active_guards && cpp.pending==3 && !cpp.failures &&
           !state.active_threads && !state.finished_threads && !state.mutexes && !state.conditions && !state.semaphores && !state.keys;
    report("No game functions or game constructors called.\n");
done:
    if(threads_ready) {
        uint32_t live=ds7_shutdown(INT64_C(5000000000));
        report("Thread shutdown: live=%" PRIu32 "\n",live);
        if(live) {
            report("Active workers: module retained; exit before retry.\n");
            retry_allowed=false; passed=false;
            goto finish_log;
        }
    }
    if(cpp_ready) {
        DS8Stats cpp; ds8_stats(&cpp);
        if(cpp.active_guards || cpp.running) {
            report("C++ objects still busy: module retained; exit before retry.\n");
            retry_allowed=false; passed=false; goto finish_log;
        }
        report("Finalizing test module before unloading code...\n");
        ds8_finalize(NULL); ds8_stats(&cpp);
        if(initialized) {
            typedef void (*Snapshot)(uint32_t *) DS_IO_SOFT;
            uint32_t output[8]={0}; ((Snapshot)functions[1])(output);
            report("Destruction: objects=%" PRIu32 " order=%" PRIu32 " (expected 3/321)\n",output[2],output[3]);
            if(output[2]!=3 || output[3]!=321 || output[4]) passed=false;
        }
        report("C++ registry: pending=%" PRIu32 " active-guards=%" PRIu32 " failures=%" PRIu32 "\n",cpp.pending,cpp.active_guards,cpp.failures);
        if(cpp.pending || cpp.running || cpp.active_guards || cpp.failures) passed=false;
    }
    {
        uint32_t unclosed=ds6_cleanup();
        DSRuntimeStats stats; ds_runtime_stats(&stats);
        report("Runtime heap before cleanup: live=%" PRIu32 " bytes=%" PRIu32 "\n",stats.live_blocks,stats.live_bytes);
        uint32_t leaked=ds_runtime_cleanup();
        int cleanup=ds_io_shutdown(&io);
        report("Cleanup: leaked-blocks=%" PRIu32 " active-files=%" PRIu32 "\n",leaked,io.active);
        if(unclosed || leaked || cleanup || io.active) passed=false;
        Result restore=ds_exec_close(&exec);
        if(R_FAILED(restore)) { report("RW restore failed: %08" PRIx32 "\n",(uint32_t)restore); image=NULL; passed=false; retry_allowed=false; }
    }
    free(image);
finish_log:
    report("\nSTAGE 8 %s\n", passed ? "PASSED" : "STOPPED; see log.");
    snprintf(status_line, sizeof(status_line), "Stage 8 %s; send new log", passed ? "passed" : "stopped");
    report("Log: %s\n", log_file ? "stage8-v0.8.0-log.txt saved" : "SD log unavailable");
    if (log_file) { fclose(log_file); log_file = NULL; }
}
int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP, &top); consoleInit(GFX_BOTTOM, &bottom);
    consoleSelect(&top);
    mkdir("sdmc:/3ds", 0777); mkdir(DATA_DIR, 0777); mkdir(DATA_DIR "/test-output",0777);
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 8 v0.8.0\n\nSTAGE 8 READY - press A\n\n");
    report("A starts the runtime bridge test.\nSTART exits without running it.\n");
    if (log_file) { fclose(log_file); log_file = NULL; }
    snprintf(status_line, sizeof(status_line), "Ready: A starts runtime test");
    while (aptMainLoop()) {
        hidScanInput();
        if (hidKeysDown() & KEY_START) break;
        if ((hidKeysDown() & KEY_A) && retry_allowed) run_probe();
        consoleSelect(&bottom);
        printf("\x1b[0;0HDS LOADER TEST 8\n\nA: run test    START: exit\n\n%-38.38s\n\n", status_line);
        printf("Original C++ lifecycle module.\nConstructors, static guards, cleanup.\nEngine startup is not called.\n\n");
        printf("Log: /3ds/deadspace/\n     stage8-v0.8.0-log.txt\n");
        gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    }
    gfxExit(); return 0;
}
