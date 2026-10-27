#ifndef DS10_JNI_H
#define DS10_JNI_H
#include "ds_jni.h"
#include "ds11_platform.h"
typedef void (*DS10Observe)(const char *operation,const char *class_name,const char *name,const char *signature,int missing);
typedef void (*DS10Startup)(DSJniHandle *env,void *object,void *manager) DS_JNI_SOFT;
typedef void (*DS11Orientation)(DSJniHandle *env,void *object,int orientation) DS_JNI_SOFT;
typedef union { int32_t i; int64_t j; void *l; double d; float f; } DS10Value;
_Static_assert(sizeof(DS10Value)==8,"JNI jvalue stride");
typedef struct { uint32_t token,kind,identity,global; } DS10Ref;
typedef struct { uint8_t *bytes; uint32_t size,used; } DS10Array;
typedef struct { void *copy; uint32_t array; } DS10Pin;
typedef struct { uint32_t token; int32_t fd; } DS10Stream;
typedef struct { uint32_t mark; } DS11Frame;
typedef struct {
    DSJniContext base;
    DS10Ref refs[128];
    DS10Array arrays[8];
    DS10Pin pins[16];
    DS10Stream streams[8];
    DS10Observe observe;
    DS10Startup startup;
    uint32_t pending_exception,lookups,calls,failures,live_refs,peak_refs,startup_calls;
    uint32_t magic,stream_serial,read_bytes;
    DS11Platform platform;
    uint32_t object_serial;
    DS11Frame frames[16];
    uint32_t frame_depth;
    uintptr_t string_functions[3];
    uint32_t query_object_bool_compat;
    DS11Orientation orientation_callback;
    uint32_t orientation_enabled,orientation_pending,orientation_events,orientation_value;
} DS10Context;
/* Observer status: 0=request, 1=missing implementation, 2=pending JNI exception.
 * A bounded native service adapter, not a Java interpreter. Unknown class/method
 * or unsupported invocation reports an exception and invokes the audit observer. */
/* Context must initially be zeroed; reinit refuses outstanding objects. */
int ds10_init(DS10Context *context,DS10Observe observe,DS10Startup startup);
/* Caller must first stop all JNI users. Returns resources reclaimed. */
uint32_t ds10_cleanup(DS10Context *context);
uint32_t ds10_context_size(void);
void ds10_stats(DS10Context *context,uint32_t out[7]);
void ds10_query_compat(DS10Context *context,int enabled);
void ds11_orientation_backend(DS10Context *context,DS11Orientation callback,int orientation);
void ds11_pump_events(DS10Context *context);
#endif
