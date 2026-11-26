#include "native_gameplay_hw_sd.h"
#include <stdio.h>
#include <string.h>
#include <limits.h>

/* Match the SD-specific libctru statvfs source: clusterSize is BYTES, not sectors.
 * Restrict malformed geometry before multiplying. Both operands are u32, cast
 * to u64 BEFORE multiplication. Even UINT32_MAX^2 cannot overflow u64. */
int hw_sd_capacity(HWSdDiag *d){
    const FS_ArchiveResource *r=&d->resource;
    d->free_bytes=d->total_bytes=0;
    if(!(d->called&HW_SD_RESOURCE) || R_FAILED(d->resource_rc)){d->status=HW_SD_QUERY;return -1;}
    if(r->sectorSize<512 || r->sectorSize>4096 || (r->sectorSize&(r->sectorSize-1)) ||
       r->clusterSize<r->sectorSize || r->clusterSize>1024*1024 ||
       (r->clusterSize&(r->clusterSize-1)) || !r->totalClusters || r->freeClusters>r->totalClusters){
        d->status=HW_SD_INVALID;return -1;
    }
    d->free_bytes=(u64)r->clusterSize*(u64)r->freeClusters;
    d->total_bytes=(u64)r->clusterSize*(u64)r->totalClusters;
    if(d->free_bytes<HW_SD_MIN_FREE){d->status=HW_SD_LOW;return -1;}
    d->status=HW_SD_PASS;return 0;
}

const char *hw_sd_status_name(u32 status){
    switch(status){
        case HW_SD_PASS:return "SD SPACE PASS";
        case HW_SD_QUERY:return "SD QUERY FAILED";
        case HW_SD_ABSENT:return "SD NOT DETECTED";
        case HW_SD_READONLY:return "SD WRITE PROTECTED";
        case HW_SD_ACCESS:return "SD ARCHIVE UNAVAILABLE";
        case HW_SD_INVALID:return "SD INVALID CAPACITY";
        case HW_SD_LOW:return "SD BELOW 1 GiB FREE";
        case HW_SD_WRITE:return "SD MARKER WRITE FAILED";
        default:return "SD ARCHIVE CLOSE FAILED";
    }
}

/* Only this new, exclusively created directory is writable. The fixed marker
 * is <=1024 bytes and never replaces an earlier preflight/run/evidence file.
 * Direct SDK IO is intentional: the gameplay fopen envelope has no run yet. */
static int marker(FS_Archive card,HWSdDiag *d){
    const char *root="/3ds/ds-8fps27";
    FS_Path p=fsMakePath(PATH_ASCII,root);
    Result rc=FSUSER_CreateDirectory(card,p,0);
    if(R_FAILED(rc)){
        Handle dir=0;Result probe=FSUSER_OpenDirectory(&dir,card,p);
        if(R_FAILED(probe)){d->marker_rc=rc;return -1;}
        rc=FSDIR_Close(dir);if(R_FAILED(rc)){d->marker_rc=rc;return -1;}
    }
    char directory[96];int made=0;
    for(u32 i=1;i<=9999;++i){
        snprintf(directory,sizeof(directory),"%s/preflight-%04lu",root,(unsigned long)i);
        p=fsMakePath(PATH_ASCII,directory);rc=FSUSER_CreateDirectory(card,p,0);
        if(R_SUCCEEDED(rc)){made=1;break;}
        Handle dir=0;Result probe=FSUSER_OpenDirectory(&dir,card,p);
        if(R_FAILED(probe)){d->marker_rc=rc;return -1;}
        rc=FSDIR_Close(dir);if(R_FAILED(rc)){d->marker_rc=rc;return -1;}
    }
    if(!made){d->marker_rc=MAKERESULT(RL_PERMANENT,RS_OUTOFRESOURCE,RM_APPLICATION,RD_OUT_OF_RANGE);return -1;}
    snprintf(d->marker,sizeof(d->marker),"%s/sd-preflight.json",directory);
    p=fsMakePath(PATH_ASCII,d->marker);
    rc=FSUSER_CreateFile(card,p,0,0);
    if(R_FAILED(rc)){d->marker_rc=rc;return -1;}
    Handle file=0;rc=FSUSER_OpenFile(&file,card,p,FS_OPEN_WRITE,0);
    if(R_FAILED(rc)){d->marker_rc=rc;return -1;}
    char text[1024];
    int n=snprintf(text,sizeof(text),
        "{\"version\":2,\"phase\":\"queries_before_marker_and_archive_close\",\"status\":%lu,\"called\":%lu,\"detect_rc\":\"%08lx\",\"writable_rc\":\"%08lx\",\"open_rc\":\"%08lx\",\"legacy_GetFreeBytes_rc\":\"%08lx\",\"resource_rc\":\"%08lx\",\"legacy_bytes\":%llu,\"free_bytes\":%llu,\"total_bytes\":%llu,\"sector_bytes\":%lu,\"cluster_bytes\":%lu,\"total_clusters\":%lu,\"free_clusters\":%lu,\"minimum_free_bytes\":1073741824,\"engine_loaded\":false,\"safe_exit_claim\":false}\n",
        (unsigned long)d->status,(unsigned long)d->called,(unsigned long)(u32)d->detect_rc,
        (unsigned long)(u32)d->writable_rc,(unsigned long)(u32)d->open_rc,
        (unsigned long)(u32)d->legacy_rc,(unsigned long)(u32)d->resource_rc,
        (unsigned long long)d->legacy_free,(unsigned long long)d->free_bytes,(unsigned long long)d->total_bytes,
        (unsigned long)d->resource.sectorSize,(unsigned long)d->resource.clusterSize,
        (unsigned long)d->resource.totalClusters,(unsigned long)d->resource.freeClusters);
    u32 written=0;
    if(n<0 || (unsigned)n>=sizeof(text))rc=MAKERESULT(RL_PERMANENT,RS_INVALIDARG,RM_APPLICATION,RD_INVALID_SIZE);
    else rc=FSFILE_Write(file,&written,0,text,(u32)n,FS_WRITE_FLUSH);
    Result closed=FSFILE_Close(file);
    d->marker_bytes=written;
    d->marker_rc=R_FAILED(rc)?rc:closed;
    if(R_FAILED(d->marker_rc) || written!=(u32)n)return -1;
    d->marker_written=1;return 0;
}

int hw_sd_preflight(HWSdDiag *d){
    memset(d,0,sizeof(*d));d->status=HW_SD_QUERY;d->legacy_free=UINT64_MAX;
    bool detected=false,writable=false;
    d->stage=1;d->called|=HW_SD_DETECT;
    d->detect_rc=FSUSER_IsSdmcDetected(&detected);d->detected=detected;
    if(R_FAILED(d->detect_rc))return -1;
    if(!detected){d->status=HW_SD_ABSENT;return -1;}
    d->stage=2;d->called|=HW_SD_WRITABLE;
    d->writable_rc=FSUSER_IsSdmcWritable(&writable);d->writable=writable;
    if(R_FAILED(d->writable_rc))return -1;
    if(!writable){d->status=HW_SD_READONLY;return -1;}
    FS_Archive card=0;d->stage=3;d->called|=HW_SD_OPEN;
    d->open_rc=FSUSER_OpenArchive(&card,ARCHIVE_SDMC,fsMakePath(PATH_EMPTY,""));
    if(R_FAILED(d->open_rc)){d->status=HW_SD_ACCESS;return -1;}
    /* Old API retained ONLY to capture its actual Result/value next time.
     * It never grants space admission, regardless of success or failure. */
    d->stage=4;d->called|=HW_SD_LEGACY;
    d->legacy_rc=FSUSER_GetFreeBytes(&d->legacy_free,card);
    d->stage=5;d->called|=HW_SD_RESOURCE;
    d->resource_rc=FSUSER_GetSdmcArchiveResource(&d->resource);
    int capacity=hw_sd_capacity(d);
    d->called|=HW_SD_MARKER;
    int saved=marker(card,d);
    d->called|=HW_SD_CLOSE_CALL;d->close_rc=FSUSER_CloseArchive(card);
    if(R_FAILED(d->close_rc)){d->stage=7;d->status=HW_SD_CLOSE;return -1;}
    if(saved){d->stage=6;d->status=HW_SD_WRITE;return -1;}
    d->stage=5;return capacity;
}
