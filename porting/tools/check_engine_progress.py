"""Validate the two emulator witnesses and the last hardware result; no reruns."""
import hashlib,json,re
from verify_asset_directories import contract as asset_contract
from verify_directory_delegate import contract as directory_contract
from check_first_frame import validate as first_frame_validate
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
    sensor_tests=read('analysis/sensor-jni-tests.json');assert sensor_tests['tests_run']==8 and not sensor_tests['errors'] and not sensor_tests['failures']
    gl_tests=read('analysis/gles-tests.json');assert gl_tests['tests_run']==17 and not gl_tests['errors'] and not gl_tests['failures']
    array_tests=read('analysis/arrays-tests.json');assert array_tests['tests_run']==17 and not array_tests['errors'] and not array_tests['failures']
    texture_tests=read('analysis/textures-tests.json');assert texture_tests['tests_run']==22 and not texture_tests['errors'] and not texture_tests['failures']
    pipeline_tests=read('analysis/pipeline-tests.json');assert pipeline_tests['tests_run']==18 and not pipeline_tests['errors'] and not pipeline_tests['failures']
    jump_tests=read('analysis/jump-tests.json');assert jump_tests['tests_run']==13 and not jump_tests['errors'] and not jump_tests['failures']
    string_tests=read('analysis/strings-tests.json');assert string_tests['tests_run']==22 and not string_tests['errors'] and not string_tests['failures']
    asset_tests=read('analysis/assets-tests.json');assert asset_tests['tests_run']==26 and not asset_tests['errors'] and not asset_tests['failures']
    directories=read('analysis/asset-directory-contract.json');assert directories==asset_contract()
    assert read('analysis/android-abi/directory-delegate-contract.json')==directory_contract()
    trace=read('analysis/engine-first-entry-experiment.json')
    assert tests['core_sha256']==trace['core_sha256']==build['outputs_sha256']['core-test.elf']
    assert jni_tests['core_sha256']==tests['core_sha256']
    assert platform_tests['core_sha256']==tests['core_sha256']
    assert sensor_tests['core_sha256']==tests['core_sha256']
    assert gl_tests['core_sha256']==tests['core_sha256']
    assert gl_tests['fixture_sha256']==build['outputs_sha256']['fixture-graphics.so']
    assert array_tests['core_sha256']==tests['core_sha256']
    assert array_tests['fixture_sha256']==build['outputs_sha256']['fixture-arrays.so']
    assert texture_tests['core_sha256']==tests['core_sha256']
    assert texture_tests['fixture_sha256']==build['outputs_sha256']['fixture-textures.so']
    assert pipeline_tests['core_sha256']==tests['core_sha256']
    assert pipeline_tests['fixture_sha256']==build['outputs_sha256']['fixture-pipeline.so']
    assert jump_tests['core_sha256']==tests['core_sha256']
    for name,digest in jump_tests['fixtures_sha256'].items():assert digest==build['outputs_sha256'][name]
    assert string_tests['core_sha256']==tests['core_sha256']
    assert string_tests['fixture_sha256']==build['outputs_sha256']['fixture-strings.so']
    assert asset_tests['core_sha256']==tests['core_sha256']
    assert asset_tests['fixture_sha256']==build['outputs_sha256']['fixture-assets.so']
    jump_abi=read('analysis/android-abi/jump-abi-contract.json')
    assert jump_abi['jmp_buf_bytes']==256 and jump_abi['layout_words']=={'magic':0,'signal_mask':1,'vfp_d8_d15':2,'fpscr':18,'core_r4_r14':19,'reserved':30}
    graphics_trace=read('analysis/engine-graphics-entry.json');graphics_stop=graphics_trace['stop']
    assert graphics_trace['core_sha256']==tests['core_sha256']
    assert graphics_stop['kind']=='arena_refusal_guard' and graphics_stop['name']=='mmap'
    assert graphics_stop['bytes_requested']==13139968 and graphics_stop['android_errno']==12
    assert graphics_stop['phase']=='NativeOnDrawFrame[2]'
    assert graphics_trace['donor_arena_stats']==[16781312,16781312,4097,4097,2,2,0,1]
    assert graphics_trace['string_stats']=={'new16':1,'newUTF':33,'get16':12,'getUTF':30,'regions':0,'errors':0}
    assert graphics_trace['asset_stats']=={'lists':1,'names':12,'gets':12,'sets':0,'extra_strings':0,'arrays':0}
    assert any(r['operation']=='AssetManager.list returned' and r['signature']=='12' and r['status']==0 for r in graphics_trace['java_requests'])
    assert graphics_trace['runtime_calls']['emulator:native_stat']==3
    assert any(r['api']=='open' and r['path'].endswith('/ea/deadspace/published/fonts/Ascender_Uni.ttf') for r in graphics_trace['file_operations'])
    assert any(r['operation']=='AssetManager.list requested' and r['name']=='' and r['status']==0 for r in graphics_trace['java_requests'])
    assert graphics_trace['jump_stats']=={'saves':20,'restores':0,'refusals':0} and graphics_trace['runtime_calls']['setjmp']==20
    assert graphics_trace['graphics_stats']=={'queries':7,'clears':0,'pixels':0,'flushes':0}
    assert graphics_trace['graphics_context']['bindings']==99 and graphics_trace['frames_returned']==1
    assert graphics_trace['texture_stats']=={'names':1,'bytes':1048576,'uploads':1,'patches':0}
    assert graphics_trace['first_texture']=={'name':1,'level':0,'width':512,'height':512,'format':'1908','bytes':1048576,'stored_crc32':'a738ea1c'}
    upload=[op for op in graphics_trace['graphics_operations'] if op['api']=='glTexImage2D'];assert len(upload)==1
    assert upload[0]['args'][:8]==['00000de1','00000000','00001908','00000200','00000200','00000000','00001908','00001401']
    assert upload[0]['source_crc32']==graphics_trace['first_texture']['stored_crc32']
    assert graphics_trace['graphics_error']=='00000000' and graphics_trace['runtime_allocation_limit']==4194304
    assert graphics_trace['runtime_calls']['glGenTextures']==1
    sensor_trace=read('analysis/engine-sensor-entry.json')
    assert sensor_trace['core_sha256']==tests['core_sha256']
    assert sensor_trace['production_preflight']==trace['production_preflight']
    assert sensor_trace['constructors_completed']==209 and sensor_trace['jni_bootstrap']==trace['jni_bootstrap']
    assert sensor_trace['frames_returned']==1 and not sensor_trace['gameplay']
    gl_stop=sensor_trace['stop']
    assert gl_stop['kind']=='unimplemented_import' and gl_stop['name']=='glGetIntegerv' and gl_stop['phase']=='NativeOnDrawFrame[2]'
    assert gl_stop['args'][0]=='00000ba2'
    requests=sensor_trace['java_requests']
    assert any(r['operation']=='PropertyValue' and r['name']=='GetAccelerometerCount' and r['signature']=='1' for r in requests)
    assert any(r['operation']=='SensorDelay' and r['signature']=='3' for r in requests)
    assert [r['signature'] for r in requests if r['operation']=='SensorEnabled']==['0','1']
    assert trace['production_preflight']=={'resolved':154,'missing':234,'weak_zero':4,'image_unchanged':True}
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
    for case in ('ready','missing','wrong','present','asset-missing','asset-wrong','content-unverified','sensor','graphics'):
        result=read(f'analysis/azahar-smoke/engine-{case}-result.json')
        assert result['expected_status_found'] and not result['hardware_tested'] and not result['gameplay']
        assert result['cxi_sha256']==build['outputs_sha256']['engine-audit.cxi']
        assert result['log_sha256']==sha(f'analysis/azahar-smoke/engine-{case}.log')
        cases[case]=True
    log=(PORTING/'analysis/azahar-smoke/engine-present.log').read_text(encoding='utf-8')
    for marker in ('Donor constructors completed: 209','JNI_OnLoad: 00010004; stored VM: MATCH','NativeOnCreate returned',
                   'Jump probe ARM: OK cases=8 core/VFP=OK','Jump probe Thumb: OK cases=8 core/VFP=OK','Jump probe counters: saves=18 restores=18 refusals=0',
                   'String probe: 0 checks=43 units=7 bytes=17','String cleanup: files=0 heap=0',
                   'Asset probe: 0 checks=378 names=176 CRC32-xor=3a761eb9','Asset cleanup: files=0 heap=0',
                   'NativeOnSurfaceCreated returned','NativeOnSurfaceChanged returned','Frame 1 returned','Frame 2 begin',
                   'JNI NativeEAIOStartup returned: com/ea/EAIO/EAIO.Startup',
                   'JNI accelerometer backend missing: com/ea/blast/DeviceOrientationHandlerAndroidDelegate.SetEnabled (Z)V MISSING',
                   'Platform probe: 0 checks=168 properties=29','Platform cleanup: files=0 heap=0',
                   'JNI I/O probe: 0 checks=201 bytes=3568 CRC32=4a8d9499','JNI I/O cleanup: files=0 heap=0','ENGINE EXPERIMENT STOPPED'):
        assert marker in log,marker
    waiting=(PORTING/'analysis/azahar-smoke/engine-content-unverified.log').read_text(encoding='utf-8')
    assert 'Frame 120 returned' in waiting and 'FRAME BUDGET STOPPED' in waiting
    assert 'Frame budget refs=4 failures=2' in waiting and 'accelerometer backend missing' not in waiting
    sensor_log=(PORTING/'analysis/azahar-smoke/engine-sensor.log').read_text(encoding='utf-8')
    for marker in ('Sensor bridge attached: native HID','STOP unsupported: glGetIntegerv','Caller offset: 003235b0',
                   'Sensor shutdown: result=0 active=0 events=0 delay=3','JNI SensorEnabled: com/ea/blast/AccelerometerAndroidDelegate.SetEnabled 1'):
        assert marker in sensor_log,marker
    assert 'accelerometer backend missing' not in sensor_log
    frame=first_frame_validate()
    graphics_log=(PORTING/'analysis/azahar-smoke/engine-graphics.log').read_text(encoding='utf-8')
    for marker in ('GLES surface probe: OK 400x240; black clear + green scissor; pixels=97200 format=2',
                   'Asset probe: 0 checks=378 names=176 CRC32-xor=3a761eb9','Asset cleanup: files=0 heap=0',
                   'String probe: 0 checks=43 units=7 bytes=17','String cleanup: files=0 heap=0',
                   'Jump probe ARM: OK cases=8 core/VFP=OK','Jump probe Thumb: OK cases=8 core/VFP=OK',
                   'GLES buffer probe: OK upload=24 sub=12 readback=12 active=0',
                   'GLES texture probe: OK upload=16 sub=4 readback=4 active=0','GLES pipeline probe: OK cull=2 alpha=2 blend=4 typed=1'):
        assert marker in graphics_log,marker
    arena=re.search(r'break=(\d+) peak=(\d+) mapped-pages=(\d+) refusals=(\d+)',log)
    brk,peak,pages,refusals=map(int,arena.groups())
    assert (brk,peak,pages,refusals)==(16781312,16781312,4097,0)
    assert trace['donor_arena_stats'][:3]==[brk,peak,pages] and trace['donor_arena_stats'][7]==0
    report={'workflow':'emulator first; no per-stage SD swaps','stage8_hardware_passed':True,'computer_tests_passed':331,
        'azahar_cases_passed':cases,'constructors_completed':209,'jni_onload':'00010004','stored_vm_matches':True,
        'lifecycle_returns':['NativeOnCreate','NativeOnSurfaceCreated','NativeOnSurfaceChanged'],'first_frame_attempted':True,
        'first_game_frame_rendered':True,'eaio_native_startup_returned':True,'draw_callbacks_returned':8,
        'first_frame':frame,
        'platform_probe':{'checks':168,'properties':29,'active_files_after_cleanup':0,'heap_blocks_after_cleanup':0},
        'assets':{'files':1728,'bytes':414822611,'copied_and_sha256_verified':True,'readiness_receipt_checked':True,'rehash_each_frame':False},
        'jni_frames':{'waiting_callbacks':120,'live_refs_at_end':4,'reference_capacity_exhausted':False},
        'jni_file_probe':{'checks':201,'bytes':3568,'crc32':'4a8d9499','active_files_after_cleanup':0,'heap_blocks_after_cleanup':0},
        'stop':{'phase':'NativeOnDrawFrame[8] returned','kind':'first_frame_capture','mode':'Azahar New3DS 124MiB, 20+80MiB donor arenas',
            'reason':'completed donor frame captured and presented; menu/gameplay remain unverified'},
        'cpu_graphics_guard_stop':graphics_stop,
        'asset_bridge':{'tests_passed':26,'native_probe_checks':378,'native_probe_names':176,'native_names_crc32_xor':'3a761eb9',
            'native_cleanup_files':0,'native_cleanup_heap':0,'profile':directories['profile'],'limits':directories['limits'],
            'game_stats':graphics_trace['asset_stats'],'apk_root_assets_mirrored':False,'font':directories['font']},
        'graphics_arena_bytes_in_use':frame['arena_stats']['break_bytes']+frame['arena_stats']['mapped_pages']*4096,
        'graphics_arena_reserved_bytes':100*1024*1024,
        'string_bridge':{'tests_passed':22,'native_probe_checks':43,'native_probe_utf16_units':7,'native_probe_mutf8_bytes':17,
            'native_cleanup_files':0,'native_cleanup_heap':0,'guarded_cpu_game_stats':graphics_trace['string_stats'],
            'pool_size':8,'maximum_mutf8_bytes_per_string':255,'utf16_and_mutf8_lengths_are_distinct':True,'stage3_bootstrap_unchanged':True},
        'jump_bridge':{'tests_passed':13,'native_probe_cases':16,'native_probe_saves':18,'native_probe_restores':18,
            'guarded_cpu_game':graphics_trace['jump_stats'],'native_game_at_capture':frame['jump_contexts'],'jmp_buf_bytes':256,'vfp_registers':'d8-d15','minimum_alignment':4,
            'cross_thread_refused':True,'signal_profile':jump_abi['signal_profile'],'native_newlib_reinterpretation':False},
        'sensor_only_stop':{'phase':gl_stop['phase'],'api':gl_stop['name'],'parameter':'GL_VIEWPORT (0x0ba2)','caller_offset':'003235b0'},
        'graphics_context':{'state_tests_passed':17,'array_tests_passed':17,'texture_tests_passed':22,'pipeline_tests_passed':18,'filesystem_matrix_draw_tests_passed':30,'opt_in_bindings':99,'surface':[400,240],'native_format':'RGB565','native_probe_pixels':97200,
            'native_buffer_probe':{'upload_bytes':24,'patch_bytes':12,'readback_bytes':12,'active_after_cleanup':0},
            'native_texture_probe':{'upload_bytes':16,'patch_bytes':4,'readback_bytes':4,'active_after_cleanup':0},
            'native_pipeline_probe':{'cull_checks':2,'alpha_checks':2,'blend_components':4,'typed_queries':1},
            'game_texture_stores_at_native_capture':frame['texture_stores_at_capture'],
            'first_game_texture_guarded_cpu':dict(graphics_trace['first_texture'],cpu_source_matches_store=True),
            'error_at_stop':graphics_trace['graphics_error'],
            'game_queries_completed':14,'game_clears':0,'triangle_renderer_implemented':True,'texture_storage_implemented':True,'texture_sampling_implemented':True,
            'renderer_scope':'unlit CPU triangles, no depth/stencil attachments, nonmip matching min/mag filters only'},
        'guarded_baseline_stop':{'phase':stop['phase'],'api':stop['name'],'class':stop['request']['class'],'method':'SetEnabled(Z)V'},
        'sensor_bridge':{'jni_tests_passed':8,'android_delay_at_capture':1,'interval_us_at_capture':20000,'native_shutdown_active':0,'native_original_acceleration_callbacks_observed':6,
            'native_backend':'libctru HID','cpu_backend':'injected model','calibration':'emulator-only nominal scale/identity axes; hardware unverified'},
        'import_bindings':{'portable':154,'strong_missing':234,'weak_null':4,'opt_in_filesystem':4,'opt_in_gl':99,'instrumentation_does_not_count_as_implementation':True},
        'donor_arena_bytes_in_use':brk+pages*4096,'total_process_memory_measured':False,'new_runtime_hardware_tested':False,
        'new_hardware_install_requested':False,'new_cia_produced':False,'native_rx_backend_unchanged':True,
        'limitations':['clock models are emulator-only','mmap supports private anonymous RW only','selected JNI subset; no Java interpreter',
            'AssetManager openFd not implemented; list uses bounded virtual published root, not original APK assets','physical sensor axes/calibration unverified','display DPI is configured, not measured',
            'Android API/version identify compatibility profile, not native OS','unlit CPU rasterizer; no PICA200 acceleration, lighting, fog, custom FBOs or texture combiners',
            'compressed textures and automatic mipmap generation not implemented','jump bridge has no POSIX signal delivery and rejects nonempty saved masks',
            'jump buffer frame lifetime and arbitrary pointer validity remain caller responsibilities',
            'JNI strings are bounded; one retained pinned string prevents a local frame pop at startup','object arrays support String component only; assets read-only, private appdata directories writable',
            'CPU guard profile still uses 20+20MiB and deliberately stops before worker execution','APK bootstrap assets and fd-based appdata writes remain incomplete','menu, gameplay and audio unverified','full-module native RX untested'],
        'witnesses_sha256':{p:sha(p) for p in ('analysis/engine-first-entry-experiment.json','analysis/azahar-smoke/engine-present.log',
            'analysis/emulator-runtime-tests.json','analysis/jni10-tests.json','analysis/platform-jni-tests.json','analysis/emulator-assets.json',
            'analysis/android-abi/candidate-sd-package.json','analysis/hardware/stage8-v0.8.0-user.log','3ds/build-emulator/build-manifest.json',
            'analysis/sensor-jni-tests.json','analysis/engine-sensor-entry.json','analysis/azahar-smoke/engine-sensor.log','analysis/android-abi/sensor-delay-contract.json',
            'analysis/gles-tests.json','analysis/arrays-tests.json','analysis/textures-tests.json','analysis/pipeline-tests.json','analysis/jump-tests.json','analysis/strings-tests.json','analysis/android-abi/jump-abi-contract.json','analysis/engine-graphics-entry.json','analysis/azahar-smoke/engine-graphics.log',
            'analysis/assets-tests.json','analysis/asset-directory-contract.json','analysis/android-abi/directory-delegate-contract.json',
            'analysis/first-frame-tests.json','analysis/first-frame-result.json')}}
    target=PORTING/'analysis/engine-progress.json';target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
