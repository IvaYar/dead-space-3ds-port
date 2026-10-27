"""Validate the two emulator witnesses and the last hardware result; no reruns."""
import hashlib,json,re
from pathlib import Path
PORTING=Path(__file__).resolve().parents[1]
def read(path):return json.loads((PORTING/path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256((PORTING/path).read_bytes()).hexdigest()
def main():
    build=read('3ds/build-emulator/build-manifest.json')
    for path,digest in build['sources_sha256'].items():assert sha(path)==digest,path
    for name,digest in build['outputs_sha256'].items():assert sha('3ds/build-emulator/'+name)==digest,name
    for name,digest in build['backend_sha256'].items():assert sha('3ds/source/'+name)==digest,name
    assert build['backend_sha256']==read('dist/stage8/build-manifest.json')['backend_sha256']
    hardware=read('analysis/hardware/stage8-v0.8.0-result.json')
    assert hardware['hardware_tested'] and hardware['result']=='STAGE 8 PASSED'
    assert hardware['log_sha256']==sha('analysis/hardware/stage8-v0.8.0-user.log')
    tests=read('analysis/emulator-runtime-tests.json');assert tests['tests_run']==122 and not tests['errors'] and not tests['failures']
    jni_tests=read('analysis/jni10-tests.json');assert jni_tests['tests_run']==20 and not jni_tests['errors'] and not jni_tests['failures']
    platform_tests=read('analysis/platform-jni-tests.json');assert platform_tests['tests_run']==16 and not platform_tests['errors'] and not platform_tests['failures']
    trace=read('analysis/engine-first-entry-experiment.json')
    assert tests['core_sha256']==trace['core_sha256']==build['outputs_sha256']['core-test.elf']
    assert jni_tests['core_sha256']==tests['core_sha256']
    assert platform_tests['core_sha256']==tests['core_sha256']
    assert trace['production_preflight']=={'resolved':152,'missing':236,'weak_zero':4,'image_unchanged':True}
    assert trace['constructors_completed']==209 and trace['constructors_passed']
    assert trace['jni_bootstrap']=={'return':'00010004','stored_vm_matches':True}
    assert trace['engine_entry_attempted'] and not trace['gameplay']
    assert [p['name'] for p in trace['phases']]==['donor constructors','JNI_OnLoad','NativeOnCreate','NativeOnSurfaceCreated','NativeOnSurfaceChanged','NativeOnDrawFrame[1]','orientation pump[1]']
    stop=trace['stop'];assert stop['kind']=='unimplemented_java_adapter' and stop['name']=='accelerometer backend missing'
    assert stop['phase']=='NativeOnDrawFrame[2]' and stop['request']['class']=='com/ea/blast/DeviceOrientationHandlerAndroidDelegate'
    assert stop['request']['name']=='SetEnabled' and stop['request']['signature']=='(Z)V'
    assert trace['frames_returned']==1 and trace['frame_attempt']==2 and trace['verified_asset_cache_available']
    assert trace['jni_stats']['startup_calls']==1
    assert any(r['operation']=='NativeEAIOStartup returned' for r in trace['java_requests'])
    properties={r['name']:r['signature'] for r in trace['java_requests'] if r['operation']=='PropertyValue'}
    assert len(properties)==28 and properties['GetAccelerometerCount']=='0'
    assert properties['GetTotalRAM']=='67108864' and properties['GetProcessorArchitecture']=='armeabi'
    assert any(r['operation']=='JNI compatibility' for r in trace['java_requests'])
    assert not any(r['operation'] in ('invalid method invocation','reference capacity') for r in trace['java_requests'])
    assets=read('analysis/emulator-assets.json')
    assert assets['sha256_verified'] and assets['files']==1728 and assets['bytes']==414822611
    receipt='DS_ASSETS_V1 dd42272365d0abd8ad9c89450bb7f869ee4ac0ad548525758e6a1e7df4d3c1eb 1728 414822611\n'
    assert (PORTING/'analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace/assets-verified.txt').read_bytes()==receipt.encode('ascii')
    package=read('analysis/android-abi/candidate-sd-package.json')
    assert package['versionName']=='1.1.33 Universal SD (Default)'
    cases={}
    for case in ('ready','missing','wrong','present','asset-missing','asset-wrong','content-unverified'):
        result=read(f'analysis/azahar-smoke/engine-{case}-result.json')
        assert result['expected_status_found'] and not result['hardware_tested'] and not result['gameplay']
        assert result['cxi_sha256']==build['outputs_sha256']['engine-audit.cxi']
        assert result['log_sha256']==sha(f'analysis/azahar-smoke/engine-{case}.log')
        cases[case]=True
    log=(PORTING/'analysis/azahar-smoke/engine-present.log').read_text(encoding='utf-8')
    for marker in ('Donor constructors completed: 209','JNI_OnLoad: 00010004; stored VM: MATCH','NativeOnCreate returned',
                   'NativeOnSurfaceCreated returned','NativeOnSurfaceChanged returned','Frame 1 returned','Frame 2 begin',
                   'JNI NativeEAIOStartup returned: com/ea/EAIO/EAIO.Startup',
                   'JNI accelerometer backend missing: com/ea/blast/DeviceOrientationHandlerAndroidDelegate.SetEnabled (Z)V MISSING',
                   'Platform probe: 0 checks=168 properties=29','Platform cleanup: files=0 heap=0',
                   'JNI I/O probe: 0 checks=201 bytes=3568 CRC32=4a8d9499','JNI I/O cleanup: files=0 heap=0','ENGINE EXPERIMENT STOPPED'):
        assert marker in log,marker
    waiting=(PORTING/'analysis/azahar-smoke/engine-content-unverified.log').read_text(encoding='utf-8')
    assert 'Frame 120 returned' in waiting and 'FRAME BUDGET STOPPED' in waiting
    assert 'Frame budget refs=4 failures=2' in waiting and 'accelerometer backend missing' not in waiting
    arena=re.search(r'break=(\d+) peak=(\d+) mapped-pages=(\d+) refusals=(\d+)',log)
    brk,peak,pages,refusals=map(int,arena.groups())
    assert (brk,peak,pages,refusals)==(16781312,16781312,4097,0)
    assert trace['donor_arena_stats'][:3]==[brk,peak,pages] and trace['donor_arena_stats'][7]==0
    report={'workflow':'emulator first; no per-stage SD swaps','stage8_hardware_passed':True,'computer_tests_passed':158,
        'azahar_cases_passed':cases,'constructors_completed':209,'jni_onload':'00010004','stored_vm_matches':True,
        'lifecycle_returns':['NativeOnCreate','NativeOnSurfaceCreated','NativeOnSurfaceChanged'],'first_frame_attempted':True,
        'first_game_frame_rendered':False,'eaio_native_startup_returned':True,'draw_callbacks_returned':1,
        'platform_probe':{'checks':168,'properties':29,'active_files_after_cleanup':0,'heap_blocks_after_cleanup':0},
        'assets':{'files':1728,'bytes':414822611,'copied_and_sha256_verified':True,'readiness_receipt_checked':True,'rehash_each_frame':False},
        'jni_frames':{'waiting_callbacks':120,'live_refs_at_end':4,'reference_capacity_exhausted':False},
        'jni_file_probe':{'checks':201,'bytes':3568,'crc32':'4a8d9499','active_files_after_cleanup':0,'heap_blocks_after_cleanup':0},
        'stop':{'phase':stop['phase'],'api':stop['name'],'class':stop['request']['class'],'method':'SetEnabled(Z)V'},
        'import_bindings':{'portable':152,'strong_missing':236,'weak_null':4,'instrumentation_does_not_count_as_implementation':True},
        'donor_arena_bytes_in_use':brk+pages*4096,'total_process_memory_measured':False,'new_runtime_hardware_tested':False,
        'new_hardware_install_requested':False,'new_cia_produced':False,'native_rx_backend_unchanged':True,
        'limitations':['clock models are emulator-only','mmap supports private anonymous RW only','selected JNI subset; no Java interpreter',
            'AssetManager openFd/list not implemented','accelerometer/HID adapter missing','display DPI is configured, not measured',
            'Android API/version identify compatibility profile, not native OS','no GLES renderer','full-module native RX untested'],
        'witnesses_sha256':{p:sha(p) for p in ('analysis/engine-first-entry-experiment.json','analysis/azahar-smoke/engine-present.log',
            'analysis/emulator-runtime-tests.json','analysis/jni10-tests.json','analysis/platform-jni-tests.json','analysis/emulator-assets.json',
            'analysis/android-abi/candidate-sd-package.json','analysis/hardware/stage8-v0.8.0-user.log','3ds/build-emulator/build-manifest.json')}}
    target=PORTING/'analysis/engine-progress.json';target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
