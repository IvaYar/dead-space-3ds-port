/* Hardware02 early SD gate. No engine, GPU, heap reservation or gameplay writes. */
#ifndef NATIVE_GAMEPLAY_HW_SD_H
#define NATIVE_GAMEPLAY_HW_SD_H
#include <3ds.h>
#define HW_SD_MIN_FREE (1024ull*1024ull*1024ull)
typedef enum {HW_SD_PASS,HW_SD_QUERY,HW_SD_ABSENT,HW_SD_READONLY,HW_SD_ACCESS,
              HW_SD_INVALID,HW_SD_LOW,HW_SD_WRITE,HW_SD_CLOSE} HWSdStatus;
typedef struct {
    u32 called,status,stage,marker_written;
    Result detect_rc,writable_rc,open_rc,legacy_rc,resource_rc,close_rc,marker_rc;
    u32 detected,writable,marker_bytes;
    u64 legacy_free,free_bytes,total_bytes;
    FS_ArchiveResource resource;
    char marker[128];
} HWSdDiag;
enum {HW_SD_DETECT=1,HW_SD_WRITABLE=2,HW_SD_OPEN=4,HW_SD_LEGACY=8,
      HW_SD_RESOURCE=16,HW_SD_CLOSE_CALL=32,HW_SD_MARKER=64};
int hw_sd_capacity(HWSdDiag *d);
int hw_sd_preflight(HWSdDiag *d);
const char *hw_sd_status_name(u32 status);
#endif
