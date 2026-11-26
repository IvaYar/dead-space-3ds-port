#ifndef DS10_JNI_H
#define DS10_JNI_H
#include "ds_jni.h"
#include "ds11_platform.h"
#include "ds12_sensor.h"
#include "ds18_strings.h"
#include "ds19_assets.h"
typedef void (*DS10Observe)(const char *operation,const char *class_name,const char *name,const char *signature,int missing);
typedef void (*DS10Startup)(DSJniHandle *env,void *object,void *manager) DS_JNI_SOFT;
typedef void (*DS11Orientation)(DSJniHandle *env,void *object,int orientation) DS_JNI_SOFT;
typedef union { int32_t i; int64_t j; void *l; double d; float f; } DS10Value;
_Static_assert(sizeof(DS10Value)==8,"JNI jvalue stride");
typedef struct { uint32_t token,kind,identity,global; } DS10Ref;
typedef struct { uint8_t *bytes; uint32_t size,used; } DS10Array;
typedef struct { void *copy; uint32_t array; } DS10Pin;
typedef struct { uint32_t token; int32_t fd; } DS10Stream;
typedef struct {uint32_t token,generation;int32_t fd;int64_t length;} DS10AssetFile;
typedef struct {uint32_t kind,identity,mutex,users;} DS10Monitor;
typedef struct { uint32_t mark; } DS11Frame;
typedef struct {
    DSJniContext base;
    DS10Ref refs[128];
    DS10Array arrays[8];
    DS10Pin pins[16];
    DS10Stream streams[8];
    DS10AssetFile asset_files[8];
    DS10Monitor monitors[16];
    uint32_t asset_file_serial;
    DS10Observe observe;
    DS10Startup startup;
    uint32_t pending_exception,lookups,calls,failures,live_refs,peak_refs,startup_calls;
    uint32_t magic,stream_serial,read_bytes;
    DS11Platform platform;
    uint32_t object_serial;
    DS11Frame frames[16];
    uint32_t frame_depth;
    DS18Text text[DS_JNI_STRING_COUNT];
    uint32_t string_stats[6]; /* new16, newUTF, gets16, getsUTF, regions, errors */
    uint32_t string_holds[DS_JNI_STRING_COUNT];
    DS19Array objects[DS19_ARRAYS];
    DS19String *extra_strings;
    uint32_t extra_count;
    DS19List asset_list;
    DS19Open asset_open;
    DS19Path asset_path;
    void *asset_user;
    uint32_t asset_stats[4]; /* list calls, names returned, element gets, sets */
    uint32_t query_object_bool_compat;
    DS11Orientation orientation_callback;
    uint32_t orientation_enabled,orientation_pending,orientation_events,orientation_value;
    DS12Sensor *accelerometer;
    DS12Acceleration acceleration_callback;
    void *acceleration_object;
    int32_t acceleration_delay;
    uint32_t acceleration_events;
} DS10Context;
/* Observer status: 0=request, 1=missing implementation, 2=pending JNI exception.
 * A bounded native service adapter, not a Java interpreter. Unknown class/method
 * or unsupported invocation reports an exception and invokes the audit observer. */
/* Context must initially be zeroed; reinit refuses outstanding objects. */
int ds10_init(DS10Context *context,DS10Observe observe,DS10Startup startup);
/* Caller must first stop all JNI users. Returns resources reclaimed, or
 * UINT32_MAX if monitors remain entered or sensor disable fails (context
 * retained so caller can retry). Never force-unlocks another native thread. */
uint32_t ds10_cleanup(DS10Context *context);
uint32_t ds10_context_size(void);
void ds10_stats(DS10Context *context,uint32_t out[7]);
void ds18_jni_stats(DS10Context *,uint32_t out[6]);
void ds19_assets_backend(DS10Context *,DS19List,void *);
/* Set all three operations together, before native users start. NULL open/path
 * retains the legacy published-cache profile; full APK profiles supply both. */
void ds19_assets_backend_full(DS10Context *,DS19List,DS19Open,DS19Path,void *);
void ds19_jni_stats(DS10Context *,uint32_t out[6]);
void ds10_query_compat(DS10Context *context,int enabled);
void ds11_orientation_backend(DS10Context *context,DS11Orientation callback,int orientation);
void ds11_pump_events(DS10Context *context);
/* Attach an initialized, disabled, externally owned sensor. Cleanup disables
 * it; owner closes it after all JNI users stop. Return -1 on invalid attach. */
int ds12_jni_sensor(DS10Context *,DS12Sensor *,DS12Acceleration);
int ds12_jni_pump(DS10Context *,uint64_t now_us);
#endif
