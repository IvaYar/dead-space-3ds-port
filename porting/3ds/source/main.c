#include <3ds.h>
#include <errno.h>
#include <inttypes.h>
#include <malloc.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "ds_elf.h"
#include "donor_config.h"

#define DATA_DIR "sdmc:/3ds/deadspace"
#define LIB_PATH DATA_DIR "/libEAMGameDeadSpace_orig.so"
#define LOG_PATH DATA_DIR "/stage1-log.txt"

static PrintConsole top, bottom;
static FILE *log_file;
static char status_line[96];

static void report(const char *format, ...) {
    va_list ap;
    va_start(ap, format); vprintf(format, ap); va_end(ap);
    if (log_file) { va_start(ap, format); vfprintf(log_file, format, ap); va_end(ap); }
}

static void run_probe(bool is_new) {
    consoleSelect(&top); consoleClear();
    mkdir("sdmc:/3ds", 0777);
    mkdir(DATA_DIR, 0777);
    log_file = fopen(LOG_PATH, "w");
    report("Dead Space 3DS - stage 1\n");
    report("ELF loader diagnostics v0.1.0\n");
    report("Game execution: NOT IMPLEMENTED\n\n");
    report("New 3DS: %s\n", is_new ? "yes" : "no");
    report("libctru build: %s\n", DS_LIBCTRU_VERSION);
    report("Configured heap: %" PRIu32 " KiB\n", envGetHeapSize() / 1024);
    report("Checking SD donor...\n");
    FILE *input = fopen(LIB_PATH, "rb");
    uint8_t *file = NULL, *image = NULL;
    if (!input) {
        report("\nMissing library (errno %d).\n", errno);
        report("Copy SD card files from the release\n");
        report("folder; see README.ru.md.\n");
        snprintf(status_line, sizeof(status_line), "Library not found on SD card");
        goto done;
    }
    if (fseek(input, 0, SEEK_END)) goto read_error;
    long length = ftell(input);
    if (length <= 0 || length > 64 * 1024 * 1024 || fseek(input, 0, SEEK_SET)) goto read_error;
    file = malloc((size_t)length);
    if (!file) { report("Out of memory reading donor.\n"); goto failed; }
    if (fread(file, 1, (size_t)length, input) != (size_t)length) goto read_error;
    fclose(input); input = NULL;
    uint32_t crc = ds_crc32(file, (uint32_t)length);
    report("File: %ld bytes, CRC32 %08" PRIx32 "\n", length, crc);
    bool selected = (uint32_t)length == DS_DONOR_SIZE && crc == DS_DONOR_CRC32;
    report("Selected 1.1.33 SD donor: %s\n", selected ? "MATCH" : "MISMATCH");
    DSInfo info;
    int result = ds_elf_inspect(file, (uint32_t)length, &info);
    report("ELF validation: %s (%d)\n", ds_elf_error(result), result);
    if (result != DS_OK) goto failed;
    report("Segments: %" PRIu32 ", image: %" PRIu32 " KiB\n", info.load_count, info.image_size / 1024);
    report("Imports: %" PRIu32 ", JNI exports: %" PRIu32 "\n", info.imports, info.jni_exports);
    report("RELATIVE: %" PRIu32 ", ABS32: %" PRIu32 "\n", info.relative, info.abs32);
    report("GLOB_DAT: %" PRIu32 ", JMP_SLOT: %" PRIu32 "\n", info.glob_dat, info.jump_slot);
    report("Unsupported relocations: %" PRIu32 "\n", info.unsupported);
    if (!selected) {
        report("Mapping skipped: unexpected donor.\n");
        snprintf(status_line, sizeof(status_line), "Wrong donor; see log");
        goto done;
    }
    image = memalign(4096, info.image_size);
    if (!image) { report("Out of memory mapping image.\n"); goto failed; }
    result = ds_elf_prepare(file, (uint32_t)length, image, info.image_size, (uint32_t)(uintptr_t)image, &info);
    report("Map + internal relocations: %s\n", ds_elf_error(result));
    if (result != DS_OK) goto failed;
    report("Applied: %" PRIu32 ", unresolved sites: %" PRIu32 "\n", info.local_relocations, info.external_relocations);
    report("Image base: %08" PRIx32 "\n", (uint32_t)(uintptr_t)image);
    report("Constructors NOT called (%" PRIu32 ").\n", info.init_count);
    report("\nSTAGE 1 PASSED - game is not running.\n");
    snprintf(status_line, sizeof(status_line), "Stage 1 passed; Android bridge is next");
    if (log_file) {
        fprintf(log_file, "\nSelected donor SHA256: %s\n", DS_DONOR_SHA256);
        fprintf(log_file, "Resource marker: %s\n", access(DATA_DIR "/assets/published/data/achievements.sb", F_OK) == 0 ? "present" : "absent (not needed for stage 1)");
        fprintf(log_file, "\nUnresolved import symbols (not resolved or called):\n");
        for (uint32_t i = 1; i < info.symcount; ++i)
            if (ds_elf_symbol_is_import(file, &info, i)) fprintf(log_file, "%s\n", ds_elf_symbol_name(file, &info, i));
    }
    goto done;
read_error:
    report("SD file read failed (errno %d).\n", errno);
failed:
    snprintf(status_line, sizeof(status_line), "Probe failed; see stage1-log.txt");
done:
    if (input) fclose(input);
    free(image); free(file);
    report("\nLog: %s\n", log_file ? "stage1-log.txt saved" : "unavailable (check SD write access)");
    if (log_file) { fclose(log_file); log_file = NULL; }
}

int main(void) {
    gfxInitDefault();
    consoleInit(GFX_TOP, &top); consoleInit(GFX_BOTTOM, &bottom);
    bool is_new = false;
    Result model_result = APT_CheckNew3DS(&is_new);
    if (R_FAILED(model_result)) is_new = false;
    /* Keep clocks at the system default until the actual runtime needs tuning. */
    run_probe(is_new);
    while (aptMainLoop()) {
        hidScanInput();
        uint32_t pressed = hidKeysDown();
        if (pressed & KEY_START) break;
        if (pressed & KEY_A) run_probe(is_new);
        circlePosition circle = {0}, cstick = {0};
        touchPosition touch = {0};
        hidCircleRead(&circle); hidTouchRead(&touch);
        if (is_new) hidCstickRead(&cstick);
        consoleSelect(&bottom);
        printf("\x1b[0;0H%-39s\n", "DEAD SPACE / LOADER TEST");
        printf("\nA: rerun probe     START: exit\n\n");
        printf("Circle pad: %5d %5d\n", circle.dx, circle.dy);
        printf("C-stick:    %5d %5d\n", cstick.dx, cstick.dy);
        printf("Touch:      %5u %5u\n", touch.px, touch.py);
        printf("Held keys:  %08" PRIx32 "\n\n", hidKeysHeld());
        printf("%-38.38s\n", status_line);
        printf("\nLog: /3ds/deadspace/stage1-log.txt\n");
        printf("\nThis is a development diagnostic.\n");
        gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    }
    gfxExit();
    return 0;
}
