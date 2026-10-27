/* Test-only callback for the separate I/O probe; engine uses its real export. */
#include "ds10_jni.h"
static uint32_t calls,errors;
void DS_JNI_SOFT ds10_test_startup(DSJniHandle *env,void *object,void *manager) {
    (void)object;
    typedef void *(*Class)(DSJniHandle *,void *) DS_JNI_SOFT;
    typedef void *(*Find)(DSJniHandle *,const char *) DS_JNI_SOFT;
    typedef uint8_t (*Same)(DSJniHandle *,void *,void *) DS_JNI_SOFT;
    typedef void (*Delete)(DSJniHandle *,void *) DS_JNI_SOFT;
    void *a=((Class)env->functions[31])(env,manager);
    void *b=((Find)env->functions[6])(env,"android/content/res/AssetManager");
    ++calls;if(!((Same)env->functions[24])(env,a,b))++errors;
    ((Delete)env->functions[23])(env,a);((Delete)env->functions[23])(env,b);
}
uint32_t ds10_test_callback_calls(void){return calls;}
uint32_t ds10_test_callback_errors(void){return errors;}
static uint32_t orientation_calls;
static int orientation_value;
void ds11_test_accelerometer(DS10Context *c,int present){c->platform.capabilities=present?DS11_CAP_ACCELEROMETER:0;}
void DS_JNI_SOFT ds11_test_orientation(DSJniHandle *e,void *object,int value){(void)e;(void)object;++orientation_calls;orientation_value=value;}
uint32_t ds11_test_orientation_calls(void){return orientation_calls;}
int ds11_test_orientation_value(void){return orientation_value;}
