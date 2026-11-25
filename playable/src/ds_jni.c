#include "ds_jni.h"

enum { JNI_OK = 0, JNI_ERR = -1, JNI_EVERSION = -3 };
enum { BAD_HANDLE = 1, NO_STRINGS = 2, STRING_TOO_LONG = 3, BAD_RELEASE = 4, STRING_PINNED = 5 };

static DSJniString *string_object(DSJniContext *context, void *handle) {
    for (uint32_t i = 0; i < DS_JNI_STRING_COUNT; ++i)
        if (handle == &context->strings[i] && context->strings[i].used) return &context->strings[i];
    context->error = BAD_HANDLE;
    return NULL;
}

static int DS_JNI_SOFT get_version(DSJniHandle *env) { (void)env; return DS_JNI_VERSION_1_4; }

static void *DS_JNI_SOFT new_string(DSJniHandle *env, const char *bytes) {
    DSJniContext *context = env->owner;
    if (!bytes) { context->error = BAD_HANDLE; return NULL; }
    uint32_t length = 0;
    while (length < DS_JNI_STRING_BYTES && bytes[length]) ++length;
    if (length == DS_JNI_STRING_BYTES) { context->error = STRING_TOO_LONG; return NULL; }
    for (uint32_t i = 0; i < DS_JNI_STRING_COUNT; ++i) {
        DSJniString *s = &context->strings[i];
        if (s->used) continue;
        for (uint32_t j = 0; j <= length; ++j) s->bytes[j] = bytes[j];
        s->length = length; s->pins = 0; s->used = 1;
        ++context->new_strings;
        return s;
    }
    context->error = NO_STRINGS;
    return NULL;
}

static int DS_JNI_SOFT utf_length(DSJniHandle *env, void *handle) {
    DSJniString *s = string_object(env->owner, handle);
    return s ? (int)s->length : 0;
}

static const char *DS_JNI_SOFT get_utf_chars(DSJniHandle *env, void *handle, uint8_t *is_copy) {
    DSJniContext *context = env->owner;
    DSJniString *s = string_object(context, handle);
    if (!s) return NULL;
    if (is_copy) *is_copy = 0; /* Borrow this stable object's byte storage. */
    ++s->pins; ++context->get_chars;
    return s->bytes;
}

static void DS_JNI_SOFT release_utf_chars(DSJniHandle *env, void *handle, const char *bytes) {
    DSJniContext *context = env->owner;
    DSJniString *s = string_object(context, handle);
    if (!s) return;
    if (!s->pins || bytes != s->bytes) { context->error = BAD_RELEASE; return; }
    --s->pins; ++context->releases;
}

static void DS_JNI_SOFT delete_local_ref(DSJniHandle *env, void *handle) {
    if (!handle) return;
    DSJniContext *context = env->owner;
    DSJniString *s = string_object(context, handle);
    if (!s) return;
    if (s->pins) { context->error = STRING_PINNED; return; }
    s->used = 0;
}

static int DS_JNI_SOFT get_java_vm(DSJniHandle *env, void **out) {
    if (!out) return JNI_ERR;
    *out = &env->owner->vm;
    return JNI_OK;
}

static int DS_JNI_SOFT vm_get_env(DSJniHandle *vm, void **out, int version) {
    DSJniContext *context = vm->owner;
    ++context->get_env_calls;
    if (!out) return JNI_ERR;
    *out = NULL;
    if (version != 0x00010001 && version != 0x00010002 && version != DS_JNI_VERSION_1_4) return JNI_EVERSION;
    *out = &context->env;
    return JNI_OK;
}

void ds_jni_init(DSJniContext *context) {
    uint8_t *p = (uint8_t *)context;
    for (uint32_t i = 0; i < sizeof(*context); ++i) p[i] = 0;
    context->env.functions = context->env_functions; context->env.owner = context;
    context->vm.functions = context->vm_functions; context->vm.owner = context;
    context->env_functions[4] = (uintptr_t)get_version;
    context->env_functions[23] = (uintptr_t)delete_local_ref;
    context->env_functions[167] = (uintptr_t)new_string;
    context->env_functions[168] = (uintptr_t)utf_length;
    context->env_functions[169] = (uintptr_t)get_utf_chars;
    context->env_functions[170] = (uintptr_t)release_utf_chars;
    context->env_functions[219] = (uintptr_t)get_java_vm;
    context->vm_functions[6] = (uintptr_t)vm_get_env;
}

void *ds_jni_new_string(DSJniContext *context, const char *bytes) { return new_string(&context->env, bytes); }
void ds_jni_delete_string(DSJniContext *context, void *string) { delete_local_ref(&context->env, string); }
int ds_jni_get_env(DSJniContext *context, int version, void **out) { return vm_get_env(&context->vm, out, version); }
uint32_t ds_jni_context_size(void) { return sizeof(DSJniContext); }
