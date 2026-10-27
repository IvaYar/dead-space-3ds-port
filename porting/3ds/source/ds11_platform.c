#include "ds11_platform.h"
#include <stdio.h>
#include <string.h>
void ds11_platform_default(DS11Platform *p){*p=(DS11Platform){64*1024*1024,400,240,0,0,1,0,96.0f,96.0f};}
/* Read from the selected SD APK's AndroidManifest.xml. Query.getVersion reads
 * PackageInfo.versionName in that APK; its fallback literal is not used here. */
const char *ds11_package_version(void){return "1.1.33 Universal SD (Default)";}
int ds11_property(const DS11Platform *p,const char *method,char *out,uint32_t capacity) {
    if(!p || !method || !out || !capacity)return -1;
    const char *value=NULL;char number[16];
    if(!strcmp(method,"GetAccelerometerCount"))value=p->capabilities&DS11_CAP_ACCELEROMETER?"1":"0";
    else if(!strcmp(method,"GetChipset"))value="ARM11/PICA200";
    else if(!strcmp(method,"GetManufacturer"))value="Nintendo";
    else if(!strcmp(method,"GetDeviceModel"))value="New Nintendo 3DS";
    else if(!strcmp(method,"GetDeviceName"))value="new3ds";
    else if(!strcmp(method,"GetPhoneNumber") || !strcmp(method,"GetDeviceSubscriberID") || !strcmp(method,"GetDeviceUniqueId"))value="";
    else if(!strcmp(method,"GetDisplayCount"))value="1"; /* One logical render surface. */
    else if(!strcmp(method,"GetLocationAvailable"))value="false";
    else if(!strcmp(method,"GetApiLevel"))value="10";
    else if(!strcmp(method,"GetPlatformRawName"))value="Nintendo 3DS";
    else if(!strcmp(method,"GetPlatformStdName"))value="Android";
    else if(!strcmp(method,"GetPlatformVersion"))value="2.3.3";
    else if(!strcmp(method,"GetProcessorArchitecture"))value="armeabi";
    else if(!strcmp(method,"GetLanguage"))value="en";
    else if(!strcmp(method,"GetLocale"))value="en_US";
    else if(!strcmp(method,"GetTotalRAM")){snprintf(number,sizeof(number),"%lu",(unsigned long)p->app_memory_bytes);value=number;}
    else {
        /* Unported input/sensor services are advertised as unavailable. */
        static const char *zero[]={"GetAccelerometerCount","IsBatteryStateAvailable","GetCameraCount","GetCompassCount","GetGyroscopeCount",
            "GetMicrophoneCount","GetPhysicalKeyboardCount","GetTouchPadCount","GetTouchScreenCount","GetTrackBallCount","GetVibratorCount","GetVirtualKeyboardCount"};
        for(unsigned i=0;i<sizeof(zero)/sizeof(zero[0]);++i)if(!strcmp(method,zero[i]))value="0";
    }
    if(!value || strlen(value)+1>capacity)return -1;
    strcpy(out,value);return 0;
}
