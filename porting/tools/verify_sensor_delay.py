"""Verify the selected DEX setter body and Gingerbread SensorManager delay map."""
import base64,hashlib,json,struct,urllib.request
from inspect_android_sensor import Dex,PORTING
def main():
    root=PORTING/'analysis/android-abi';blob=(root/'candidate-sd-classes.dex').read_bytes()
    origin=json.loads((root/'candidate-sd-dex-source.json').read_text());assert hashlib.sha256(blob).hexdigest()==origin['sha256']
    dex=Dex(blob);cls=dex.inspect('Lcom/ea/blast/AccelerometerAndroidDelegate;')
    m=next(x for x in cls['methods'] if x['name']=='SetUpdateFrequency')
    code=m['code_offset'];words=struct.unpack_from('<15H',blob,code+16)
    # iput v2,v1,mSensorDelay; iget-boolean v0,v1,mEnabled; if disabled return;
    # else SetEnabled(false), SetEnabled(true), return. No Hz conversion.
    assert words==(0x1259,0x25,0x1055,0x23,0x0038,0x000a,0x0012,0x206e,0x0135,0x0001,0x1012,0x206e,0x0135,0x0001,0x000e)
    assert dex.fields[0x25]['name']=='mSensorDelay' and dex.fields[0x23]['name']=='mEnabled'
    assert dex.methods[0x135]['name']=='SetEnabled' and dex.methods[0x135]['signature']=='(Z)V'
    constructor=next(x for x in cls['methods'] if x['name']=='<init>')
    constructor_words=struct.unpack_from('<33H',blob,constructor['code_offset']+16)
    assert constructor_words[6:9]==(0x3012,0x2059,0x25)
    source='https://android.googlesource.com/platform/frameworks/base/+/android-2.3.3_r1/core/java/android/hardware/SensorManager.java?format=TEXT'
    local=root/'SensorManager-android-2.3.3.java'
    if not local.exists():local.write_bytes(base64.b64decode(urllib.request.urlopen(source,timeout=25).read()))
    raw=local.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    assert digest=='c4c1b00ef275513ba8bcd66dea883147edd9d3ed83e2e94055f9326ba4ac1951'
    text=raw.decode();mapping={'SENSOR_DELAY_FASTEST':0,'SENSOR_DELAY_GAME':20000,'SENSOR_DELAY_UI':60000,'SENSOR_DELAY_NORMAL':200000}
    for name,delay in mapping.items():assert 'delay = '+str(delay)+';' in text.split('case '+name+':',1)[1].split('break;',1)[0]
    assert 'default:\n                delay = rate;' in text
    report={'dex_sha256':origin['sha256'],'setter_code_sha256':m['code_sha256'],'argument':'SensorManager delay code, or microseconds; not Hz',
        'named_delay_us':{'0':0,'1':20000,'2':60000,'3':200000},'default_constructor_delay':3,
        'enabled_rate_change':'unregister and register again','aosp_source':source,'aosp_sha256':digest,
        'sensor_manager_register_listener_returns_boolean':True,'java_listener_result_is_ignored_by_this_apk':True}
    (root/'sensor-delay-contract.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
