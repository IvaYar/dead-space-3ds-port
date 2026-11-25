#ifndef DS11_PLATFORM_H
#define DS11_PLATFORM_H
#include <stdint.h>
/* Explicit adapter profile. Android version identifies the compatibility
 * contract, not the operating system actually running on the console. */
typedef struct { uint32_t app_memory_bytes,width,height,capabilities,keep_awake,orientation,focused; float dpi_x,dpi_y; } DS11Platform;
#define DS11_CAP_ACCELEROMETER 1u
#define DS11_CAP_TOUCHSCREEN 2u
int ds11_native_keep_awake(int enabled);
int ds11_native_content_ready(void);
const char *ds11_package_version(void);
void ds11_platform_default(DS11Platform *profile);
int ds11_property(const DS11Platform *profile,const char *method,char *out,uint32_t capacity);
#define DS11_PROPERTIES(X) \
 X(GetAccelerometerCount) X(IsBatteryStateAvailable) X(GetCameraCount) X(GetChipset) \
 X(GetCompassCount) X(GetManufacturer) X(GetDeviceModel) X(GetDeviceName) \
 X(GetPhoneNumber) X(GetDeviceSubscriberID) X(GetDeviceUniqueId) X(GetDisplayCount) \
 X(GetGyroscopeCount) X(GetLocationAvailable) X(GetMicrophoneCount) X(GetApiLevel) \
 X(GetPlatformRawName) X(GetPlatformStdName) X(GetPlatformVersion) X(GetPhysicalKeyboardCount) \
 X(GetProcessorArchitecture) X(GetLanguage) X(GetLocale) X(GetTotalRAM) \
 X(GetTouchPadCount) X(GetTouchScreenCount) X(GetTrackBallCount) X(GetVibratorCount) X(GetVirtualKeyboardCount)
#endif
