/* Isolated emulator-only HID service test; no game code or JNI registration. */
#include <3ds.h>
#include <stdio.h>
#include <sys/stat.h>
#include "ds_exec.h"
#include "ds12_sensor.h"
int main(void){
    gfxInitDefault();consoleInit(GFX_TOP,NULL);
    DSExec exec;Result opened=ds_exec_open(&exec);
    if(R_FAILED(opened) || !exec.emulator){if(R_SUCCEEDED(opened))ds_exec_close(&exec);gfxExit();return 0;}
    mkdir("sdmc:/3ds",0777);mkdir("sdmc:/3ds/deadspace",0777);
    FILE *log=fopen("sdmc:/3ds/deadspace/sensor-azahar-log.txt","wb");
    if(!log){ds_exec_close(&exec);gfxExit();return 0;}
    DS12Hid hid={0};DS12SensorOps ops={0};DS12Sensor sensor={0};
    /* Identity axes are a test profile, not validated EA/3DS orientation. */
    DS12Calibration calibration={{1,2,3},{0,0,0},{512,512,512}};
    int backend=ds12_hid_ops(&hid,&ops),init=backend?-1:ds12_sensor_init(&sensor,&calibration,&ops);
    int enable=init?-1:ds12_sensor_enable(&sensor,1),samples=0,errors=0;float xyz[3]={0};u64 start=svcGetSystemTick();
    if(!enable)for(unsigned frame=0;frame<120;++frame){
        int status=ds12_sensor_poll(&sensor,(svcGetSystemTick()-start)*1000000/SYSCLOCK_ARM11,xyz);
        if(status==1)++samples;else if(status<0)++errors;
        gspWaitForVBlank();
    }
    int close=init?-1:ds12_sensor_close(&sensor);
    fprintf(log,"Isolated HID sampler; emulator only; game adapter disabled\nBackend=%d init=%d enable=%d close=%d active=%lu\n",backend,init,enable,close,(unsigned long)hid.enabled);
    fprintf(log,"Samples=%d errors=%d latest=%.5f %.5f %.5f\n",samples,errors,xyz[0],xyz[1],xyz[2]);
    fprintf(log,"Calibration: configured identity axes, nominal 512 counts/g; hardware untested\n");
    fprintf(log,"%s\n",!backend && !init && !enable && !close && !hid.enabled && samples>0 && !errors?"SENSOR BACKEND PASSED":"SENSOR BACKEND STOPPED");
    fclose(log);ds_exec_close(&exec);
    while(aptMainLoop()){hidScanInput();if(hidKeysDown()&KEY_START)break;gspWaitForVBlank();}
    gfxExit();return 0;
}
