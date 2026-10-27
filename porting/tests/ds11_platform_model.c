/* CPU-only state model. The Azahar build uses the real libctru APT policy. */
#include "ds11_platform.h"
static int policy;
static int content;
int ds11_native_keep_awake(int enabled){if(enabled!=0 && enabled!=1)return -1;policy=enabled;return 0;}
int ds11_test_keep_awake(void){return policy;}
void ds11_test_content_ready(int ready){content=ready;}
int ds11_native_content_ready(void){return content;}
