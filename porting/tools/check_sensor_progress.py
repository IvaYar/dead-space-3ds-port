"""Validate isolated sensor evidence against current source and output hashes."""
import hashlib,json,re
from pathlib import Path
P=Path(__file__).resolve().parents[1]
def read(path):return json.loads((P/path).read_text())
def sha(path):return hashlib.sha256((P/path).read_bytes()).hexdigest()
def main():
    build=read('3ds/build-sensor/build-manifest.json');cpu=read('analysis/sensor-tests.json');native=read('analysis/sensor-native-result.json')
    for path,digest in build['sources_sha256'].items():assert sha(path)==digest,path
    for path,digest in build['outputs_sha256'].items():assert sha('3ds/build-sensor/'+path)==digest,path
    assert build['backend_sha256']==read('dist/stage8/build-manifest.json')['backend_sha256']
    assert cpu['tests_run']==14 and not cpu['errors'] and not cpu['failures']
    assert cpu['core_sha256']==build['outputs_sha256']['sensor-test.elf']
    assert cpu['fixture_sha256']==build['outputs_sha256']['fixture-sensor.so']
    assert native['passed'] and native['cxi_sha256']==build['outputs_sha256']['sensor-audit.cxi']
    assert native['log_sha256']==sha('analysis/azahar-smoke/sensor-native.log')
    log=(P/'analysis/azahar-smoke/sensor-native.log').read_text()
    assert 'Backend=0 init=0 enable=0 close=0 active=0' in log and 'SENSOR BACKEND PASSED' in log
    sample=re.search(r'Samples=(\d+) errors=(\d+)',log);assert sample and int(sample[1])>0 and int(sample[2])==0
    assert all(not x['hardware_tested'] and not x['game_adapter_enabled'] for x in (build,cpu,native))
    report={'isolated_sensor_tests_passed':14,'native_hid_azahar_passed':True,'samples_observed':int(sample[1]),
        'hardware_tested':False,'game_adapter_enabled':False,'native_rx_backend_unchanged':True,
        'engine_checkpoint':'551 core ARM tests and 9 Azahar cases; lighting/default depth pass, corridor visible in intermediate capture but final scene remains black; see lighting-result.json',
        'limitations':['identity axes and nominal 512 counts/g are test configuration, not hardware calibration',
            'delivery rate limiter does not configure HID hardware sample rate','cached samples may repeat',
            'JNI bridge is opt-in in engine audit; six original callbacks observed in the frame capture case, physical calibration remains unverified'],
        'witnesses_sha256':{p:sha(p) for p in ('analysis/sensor-tests.json','analysis/sensor-native-result.json','analysis/azahar-smoke/sensor-native.log','3ds/build-sensor/build-manifest.json')}}
    (P/'analysis/sensor-progress.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
