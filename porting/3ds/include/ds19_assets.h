#ifndef DS19_ASSETS_H
#define DS19_ASSETS_H
#include "ds_jni.h"
#include "ds18_strings.h"
#define DS19_ARRAYS 8
#define DS19_ELEMENTS 2048
#define DS19_EXTRA_STRINGS 2048
typedef struct {char name[256];} DS19Name;
/* Count when names=NULL. Fill at most capacity; return total or negative error.
 * Names are immediate children in filesystem UTF-8, not JNI modified UTF-8. */
typedef int32_t (*DS19List)(void *,const char *,DS19Name *,uint32_t);
/* Open returns a descriptor from the shared ds_io pool, or -1 with errno.
 * Modes 0..3 are Android access modes; 4 requests openFd (stored entries only). */
typedef int32_t (*DS19Open)(void *,const char *,int32_t);
typedef int (*DS19Path)(const char *,char out[256]);
typedef struct {uint32_t kind,identity;} DS19Element;
typedef struct {uint32_t used,length;DS19Element *items;} DS19Array;
typedef struct DS19String {
    DSJniString string;
    DS18Text text;
    uint32_t holds;
    struct DS19String *next;
} DS19String;
/* JNI path -> canonical relative filesystem UTF-8. published is a root alias. */
int ds19_path(const char *,char out[256]);
/* Genuine APK paths have no appbundle:/ or published/ mount aliases. */
int ds19_apk_path(const char *,char out[256]);
int ds19_name_units(const char *,uint16_t out[255]);
int ds19_snapshot(DS19List,void *,const char *,DS19Name **,uint32_t *);
int32_t ds19_native_list(void *,const char *,DS19Name *,uint32_t);
#endif
