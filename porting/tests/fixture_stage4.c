/* Original Android-ABI I/O probe. No game engine code. */
#include <stdint.h>
extern int open(const char *, int, ...);
extern int read(int, void *, unsigned);
extern int lseek(int, int, int);
extern int close(int);
extern int *__errno(void);
static volatile int constructor_state = 42;
__attribute__((constructor)) static void must_not_run(void) { constructor_state = 99; }

int probe_io(const char *path, const char *missing, uint32_t size, uint32_t expected_crc, uint32_t *out) {
    for (int i = 0; i < 12; ++i) out[i] = 0;
    out[11] = (uint32_t)constructor_state;
    int fd = open(path, 0x20000), code = 1;
    if (fd < 0) { out[0] = code; out[8] = (uint32_t)*__errno(); return code; }
    uint32_t total = 0, crc = 0xffffffffu;
    unsigned char buffer[127];
    for (;;) {
        int n = read(fd, buffer, sizeof(buffer));
        code = 2;
        if (n < 0 || n > (int)sizeof(buffer)) goto done;
        if (!n) break;
        if ((uint32_t)n > size - total) { code = 3; goto done; }
        for (int i = 0; i < n; ++i) {
            crc ^= buffer[i];
            for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1)));
        }
        total += (uint32_t)n;
    }
    out[1] = total; out[2] = ~crc;
    code = 4;
    if (total != size || ~crc != expected_crc) goto done;
    out[3] = (uint32_t)lseek(fd, 0, 2);
    out[4] = (uint32_t)lseek(fd, 0, 0);
    out[5] = (uint32_t)lseek(fd, -1, 2);
    code = 5;
    if (out[3] != size || out[4] || !size || out[5] != size - 1) goto done;
    code = 12;
    if (lseek(fd, -1, 0) != -1 || *__errno() != 22) goto done;
    if (lseek(fd, 0x7fffffff, 1) != -1 || *__errno() != 75) goto done;
    if (lseek(fd, 0, 1) != (int)(size - 1)) goto done;
    out[6] = (uint32_t)read(fd, buffer, 1);
    out[7] = (uint32_t)read(fd, buffer, 1);
    code = 6;
    if (out[6] != 1 || out[7]) goto done;
    code = 7;
    if (close(fd)) { fd = -1; goto done; }
    int old = fd; fd = -1;
    code = 8;
    if (read(old, buffer, 1) != -1) goto done;
    out[8] = (uint32_t)*__errno();
    if (out[8] != 9) goto done;
    code = 9;
    fd = open(missing, 0);
    if (fd != -1) goto done;
    out[9] = (uint32_t)*__errno();
    if (out[9] != 2) goto done;
    code = 10;
    fd = open(path, 0x242, 0600);
    if (fd != -1) goto done;
    out[10] = (uint32_t)*__errno();
    if (out[10] != 30) goto done;
    code = constructor_state == 42 ? 0 : 11;
done:
    if (fd >= 0) close(fd);
    out[0] = (uint32_t)code;
    return code;
}
