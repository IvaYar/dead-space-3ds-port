#ifndef DS_JNI_H
#define DS_JNI_H
#include <stdint.h>
#include <stddef.h>

#define DS_JNI_VERSION_1_4 0x00010004
#define DS_JNI_ENV_SLOTS 233
#define DS_JNI_STRING_COUNT 8
#define DS_JNI_STRING_BYTES 256
#define DS_JNI_SOFT __attribute__((pcs("aapcs")))

typedef struct DSJniContext DSJniContext;
typedef struct { const uintptr_t *functions; DSJniContext *owner; } DSJniHandle;
typedef struct {
    uint32_t used, length, pins;
    char bytes[DS_JNI_STRING_BYTES];
} DSJniString;
struct DSJniContext {
    DSJniHandle env, vm;
    uintptr_t env_functions[DS_JNI_ENV_SLOTS], vm_functions[8];
    DSJniString strings[DS_JNI_STRING_COUNT];
    uint32_t error, new_strings, get_chars, releases, get_env_calls;
};

/* A single-threaded bootstrap subset, not a JVM. Unimplemented slots stay NULL. */
void ds_jni_init(DSJniContext *context);
void *ds_jni_new_string(DSJniContext *context, const char *bytes);
void ds_jni_delete_string(DSJniContext *context, void *string);
int ds_jni_get_env(DSJniContext *context, int version, void **out);
uint32_t ds_jni_context_size(void);

#endif
