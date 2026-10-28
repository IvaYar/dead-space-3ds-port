"""Verify genuine APK assets, JNI/FD contracts and shared-pool native progress."""
import json,re,zlib
from check_first_frame import P,read,sha
from check_input_save import validate as capture_validate
def validate():
    report=capture_validate('analysis/apk-assets-frame/',180,apk=True,shared=True)
    build=read('3ds/build-emulator/build-manifest.json');core=build['outputs_sha256']['core-test.elf']
    assert build['semaphore_capacity']==64
    for name,n in (('apk-assets',23),('jni-monitors',12),('shared-memory',12),('emulator-threads',4)):
        t=read('analysis/'+name+'-tests.json')
        assert t['tests_run']==n and not t['errors'] and not t['failures'] and t['core_sha256']==core
    contract=read('analysis/android-abi/apk-asset-namespace-contract.json');assets=read('analysis/emulator-apk-assets.json')
    assert assets['apk_sha256']==contract['apk_sha256'] and assets['files']==contract['asset_files']==20
    assert assets['root_children']==contract['asset_root_children'] and len(assets['root_children'])==7
    expected={item['path']:item for item in contract['manifest']}
    assert len(assets['manifest'])==len(expected) and {x['path'] for x in assets['manifest']}==set(expected)
    root=P/'analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace/apk-assets'
    assert {x.relative_to(root).as_posix() for x in root.rglob('*') if x.is_file()}==set(expected)
    for item in assets['manifest']:
        data=(root/item['path']).read_bytes();source=expected[item['path']]
        assert len(data)==item['bytes']==source['bytes'] and item['zip_method']==source['zip_method']
        assert f'{zlib.crc32(data):08x}'==source['zip_crc32'] and sha(root/item['path'])==item['sha256']
    assert assets['bytes']==sum(x['bytes'] for x in expected.values())==163995411
    assert (root.parent/'apk-assets-verified.txt').read_bytes()==(assets['receipt']+'\n').encode('ascii')
    folder='analysis/apk-assets-frame/';log=(P/folder/'run.log').read_text()
    for marker in ('APK AssetManager attached: 20 genuine files; EAMCore.ini bytes=3119 CRC32=33c9beb3',
        'JNI AssetManager.openFd IOException: android/content/res/AssetManager.EAMCore.ini',
        'JNI CallMethod: java/io/InputStream.read ([BII)I',
        'JNI AssetManager.open IOException: android/content/res/AssetManager.data.zip',
        'JNI AssetManager.list returned: android/content/res/AssetManager. 7',
        'Donor shared arena: 100MiB; bottom brk + top-down mmap'):
        assert marker in log,marker
    assert 'JNI AssetManager.open IOException: android/content/res/AssetManager.EAMCore.ini' not in log
    prefix='analysis/azahar-smoke/engine-apk600-shared100'
    run=read(prefix+'-result.json');extended=(P/(prefix+'.log')).read_text()
    assert run['apk_assets'] and run['shared_arena'] and run['donor_arena_mib']==[100] and run['capture_frame']==600
    assert run['exploratory'] and not run['checkpoint_validated'] and not run['first_game_frame_rendered']
    assert run['cxi_sha256']==build['outputs_sha256']['engine-audit.cxi'] and run['log_sha256']==sha(prefix+'.log')
    assert 'STOP unsupported: glGenFramebuffersOES\n' in extended and 'Caller offset: 00378aec\n' in extended
    for bad in ('STOP arena refusal:','DIAGNOSTIC WATCHDOG STOPPED','Thread event: 5','CLOCK failure:'):
        assert bad not in extended,bad
    returned=[int(n) for n in re.findall(r'^Frame (\d+) returned$',extended,re.M)]
    assert returned==list(range(1,len(returned)+1)) and len(returned)>=180
    brk,peak,pages,refusals=map(int,re.search(r'Donor arenas: break=(\d+) peak=(\d+) mapped-pages=(\d+) refusals=(\d+)',extended).groups())
    assert brk==peak==33558528 and not refusals and brk+pages*4096<=100*1024*1024
    report.update(apk_asset_files=20,apk_root_children=7,apk_sha256=assets['apk_sha256'],
        apk_asset_tests_passed=23,jni_monitor_tests_passed=12,shared_memory_tests_passed=12,emulator_thread_tests_passed=4,
        stored_openfd_profile='extracted file, offset 0, original ZIP_STORED entries only',
        shared_pool_bytes=100*1024*1024,next_stop={'api':'glGenFramebuffersOES','caller_offset':'00378aec',
            'frames_returned':len(returned),'break_bytes':brk,'mapped_bytes':pages*4096,'arena_refusals':refusals})
    report['witnesses_sha256'].update({name:sha(name) for name in (prefix+'.log',prefix+'-result.json',
        'analysis/apk-assets-tests.json','analysis/jni-monitors-tests.json','analysis/shared-memory-tests.json','analysis/emulator-threads-tests.json',
        'analysis/emulator-apk-assets.json','analysis/android-abi/apk-asset-namespace-contract.json')})
    (P/'analysis/apk-assets-result.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':print(json.dumps(validate(),indent=2))
