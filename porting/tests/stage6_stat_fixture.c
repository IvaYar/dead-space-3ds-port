/* Test-only native input for independent verification of Bionic stat layout. */
#include "ds6.h"
#include <sys/stat.h>
#include <sys/reent.h>
#include <stddef.h>
/* Host filesystem metadata is packed using the linked newlib layout, then the
 * real ds6_stat_pack converts it to the donor's Bionic structure. */
void ds6_test_host_stat_layout(uint32_t *out){
    *out++=sizeof(struct stat);*out++=offsetof(struct _reent,_errno);
#define FIELD(name) *out++=offsetof(struct stat,name);*out++=sizeof(((struct stat *)0)->name)
    FIELD(st_mode);FIELD(st_size);FIELD(st_blksize);FIELD(st_blocks);
    FIELD(st_nlink);FIELD(st_atim.tv_sec);FIELD(st_mtim.tv_sec);FIELD(st_ctim.tv_sec);
#undef FIELD
}
int ds6_test_stat_pack(void *out,int overflow) {
    struct stat s={0};
    s.st_dev=17; s.st_ino=0x12345678; s.st_mode=0100644; s.st_nlink=2;
    s.st_uid=19; s.st_gid=23; s.st_rdev=29; s.st_size=123456;
    s.st_blksize=4096; s.st_blocks=242;
    s.st_atim.tv_sec=overflow?INT64_C(2147483648):123;
    s.st_atim.tv_nsec=456; s.st_mtim.tv_sec=789; s.st_mtim.tv_nsec=1234;
    s.st_ctim.tv_sec=5678; s.st_ctim.tv_nsec=9876;
    return ds6_stat_pack(out,&s);
}
