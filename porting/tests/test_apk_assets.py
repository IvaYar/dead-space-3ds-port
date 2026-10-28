"""Exercise exact APK AssetManager paths and callbacks through ARM JNI."""
import hashlib,json,struct,time,unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_PC,UC_ARM_REG_LR
import test_assets as assets
import test_strings as strings
import test_jni10 as jni
OPEN=0x06007100;USER=0x12345678
class ApkAssets(assets.AssetTests):
    def setUp(self):
        super().setUp();self.contract=json.loads((jni.cpp.PORTING/'analysis/android-abi/apk-asset-namespace-contract.json').read_text())
        self.entries={'':self.contract['asset_root_children'],'downloadcontent':['en.txt','ru.txt']}
        self.open_calls=[];self.ready=[]
        def callback(uc,address,size,user):
            owner,path,mode=[uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
            name=self.io.cstring(path);self.open_calls.append((owner,name,mode))
            accepted=(name=='EAMCore.ini' and mode<4) or (name=='bundled-game.zip' and mode==4)
            fd=self.ready.pop(0) if accepted and self.ready else 0xffffffff
            uc.reg_write(UC_ARM_REG_R0,fd);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        self.open_hook=self.arm.uc.hook_add(UC_HOOK_CODE,callback,begin=OPEN,end=OPEN)
        self.attach()
    def tearDown(self):
        self.arm.uc.hook_del(self.open_hook);super().tearDown()
    def attach(self):self.arm.call('ds19_assets_backend_full',jni.CTX,assets.HOOK,OPEN,self.arm.exports['ds19_apk_path'],USER)
    def allocate(self,n=1):
        self.io.data=b'genuine APK bytes\r\n'
        for _ in range(n):self.ready.append(self.io.open())
    def apk_path(self,data):
        self.arm.uc.mem_write(assets.PATH,data+b'\0');self.arm.uc.mem_write(assets.DEST,b'Z'*256)
        r=self.arm.call('ds19_apk_path',assets.PATH,assets.DEST);return r,bytes(self.arm.uc.mem_read(assets.DEST,256))
    def test_root_lists_seven_real_apk_children(self):
        a=self.listing();self.assertEqual(self.names(a),[x.encode() for x in sorted(self.contract['asset_root_children'])])
        self.assertEqual(self.backend_calls[0][0],'')
    def test_published_is_an_ordinary_directory_and_not_a_mount_alias(self):
        self.entries['published/data']=['literal.txt'];a=self.listing('published/data');self.assertEqual(self.names(a),[b'literal.txt'])
        self.assertEqual(self.backend_calls[0][0],'published/data')
    def test_external_asset_does_not_leak_into_apk_open(self):
        self.assertEqual(self.open('data/achievements.sb'),0);self.assertTrue(self.exception())
        self.assertEqual(self.open_calls,[(USER,'data/achievements.sb',2)]);self.assertEqual(self.io.active(),0)
    def test_apk_open_uses_configured_owner_and_default_streaming_mode(self):
        self.allocate();s=self.open('EAMCore.ini');self.assertTrue(s);self.assertEqual(self.open_calls,[(USER,'EAMCore.ini',2)])
        self.delete(s);self.assertEqual(self.io.active(),0)
    def test_opened_apk_stream_reads_actual_backend_bytes_and_closes(self):
        self.allocate();s=self.open('EAMCore.ini');read,_,close=self.stream_methods();array=self.env(176,64)
        n=self.env(49,s,read,array,0,64);self.assertEqual(n,len(self.io.data))
        self.env(200,array,0,n,jni.OUT);self.assertEqual(bytes(self.arm.uc.mem_read(jni.OUT,n)),self.io.data)
        self.env(61,s,close);self.assertEqual(self.io.active(),0);self.assertFalse(self.exception())
    def test_all_four_access_modes_are_forwarded_without_becoming_write_modes(self):
        self.allocate(4);manager,c=self.objects();m=self.method(c,'open','(Ljava/lang/String;I)Ljava/io/InputStream;');name=self.make_string('EAMCore.ini')
        for mode in range(4):s=self.env(34,manager,m,name,mode);self.assertTrue(s);self.delete(s)
        self.assertEqual([x[2] for x in self.open_calls],[0,1,2,3])
    def test_invalid_access_modes_never_reach_native_open(self):
        manager,c=self.objects();m=self.method(c,'open','(Ljava/lang/String;I)Ljava/io/InputStream;');name=self.make_string('EAMCore.ini')
        for mode in (-1,4):self.assertEqual(self.env(34,manager,m,name,mode),0);self.assertTrue(self.exception());self.clear()
        self.assertEqual(self.open_calls,[])
    def test_empty_open_raises_exception_but_empty_list_means_root(self):
        self.assertEqual(self.open(''),0);self.assertTrue(self.exception());self.clear();self.assertTrue(self.listing(''))
        self.assertEqual(self.open_calls,[])
    def test_missing_apk_file_is_an_exception_instead_of_published_fallback(self):
        self.assertEqual(self.open('missing.ini'),0);self.assertTrue(self.exception());self.assertEqual(self.open_calls,[(USER,'missing.ini',2)])
    def test_unsafe_paths_fail_atomically_before_backends(self):
        for name in (b'/outside',b'../outside',b'a/../b',b'a//b',b'a\\b',b'appbundle:/published/x',b'a:b',b'.',b'x'*256):
            r,out=self.apk_path(name);self.assertEqual(r,0xffffffff,name);self.assertEqual(out,b'Z'*256)
        self.assertEqual(self.open_calls,[]);self.assertEqual(self.backend_calls,[])
    def test_canonical_paths_keep_published_prefix_and_trailing_separator(self):
        for name in (b'published/data',b'published/',b'EAMCore.ini/',b'downloadcontent/'):
            r,out=self.apk_path(name);self.assertEqual(r,0);self.assertEqual(out[:len(name)+1],name+b'\0')
    def test_utf16_surrogate_path_is_converted_to_filesystem_utf8(self):
        r,out=self.apk_path(strings.mutf((0xd83d,0xde80)));self.assertEqual(r,0);self.assertEqual(out[:5],b'\xf0\x9f\x9a\x80\0')
    def test_malformed_modified_utf8_and_embedded_nul_are_rejected(self):
        for name in (b'\xc0\x80',b'\x80',b'\xed\xa0\x80',b'\xf0\x9f\x9a\x80'):
            r,out=self.apk_path(name);self.assertEqual(r,0xffffffff);self.assertEqual(out,b'Z'*256)
    def test_legacy_setter_resets_exact_path_and_open_callbacks_together(self):
        self.arm.call('ds19_assets_backend',jni.CTX,assets.HOOK,0)
        s=self.open('data/achievements.sb');self.assertTrue(s);self.delete(s);self.assertEqual(self.open_calls,[])
        self.entries['data']=['legacy.txt'];a=self.listing('published/data');self.assertEqual(self.names(a),[b'legacy.txt'])
    def test_context_cleanup_releases_outstanding_apk_stream(self):
        self.allocate();self.assertTrue(self.open('EAMCore.ini'));self.assertEqual(self.io.active(),1)
        self.arm.call('ds10_cleanup',jni.CTX);self.assertEqual(self.io.active(),0)
    def test_failed_jni_reference_allocation_closes_the_opened_descriptor(self):
        self.allocate();manager,c=self.objects();m=self.method(c,'open','(Ljava/lang/String;)Ljava/io/InputStream;');name=self.make_string('EAMCore.ini')
        while True:
            self.arm.call('ds10_stats',jni.CTX,jni.OUT)
            if self.base.words(jni.OUT,7)[4]==128:break
            self.assertTrue(self.find('java/lang/String'))
        self.assertEqual(self.env(34,manager,m,name),0);self.assertTrue(self.exception());self.assertEqual(self.io.active(),0)
    def afd(self,name='bundled-game.zip'):
        manager,c=self.objects();m=self.method(c,'openFd','(Ljava/lang/String;)Landroid/content/res/AssetFileDescriptor;');s=self.make_string(name)
        result=self.env(34,manager,m,s)
        for ref in (s,manager,c):self.delete(ref)
        return result
    def afd_method(self,name,signature):return self.method(self.find('android/content/res/AssetFileDescriptor'),name,signature)
    def integer_fd(self,afd):
        obj=self.env(34,afd,self.afd_method('getFileDescriptor','()Ljava/io/FileDescriptor;'))
        m=self.method(self.find('java/io/FileDescriptor'),'getInt$','()I');return obj,self.env(49,obj,m),m
    def test_compressed_openfd_is_ioexception_without_a_fake_descriptor(self):
        self.assertEqual(self.afd('EAMCore.ini'),0);self.assertTrue(self.exception());self.assertEqual(self.open_calls,[(USER,'EAMCore.ini',4)])
    def test_stored_asset_descriptor_reports_real_length_and_zero_window_offset(self):
        self.allocate();a=self.afd();self.assertTrue(a)
        self.assertEqual(self.env(52,a,self.afd_method('getLength','()J')),len(self.io.data))
        self.assertEqual(self.env(52,a,self.afd_method('getStartOffset','()J')),0)
        obj,fd,_=self.integer_fd(a);self.assertEqual(fd,1024);self.delete(a);self.assertEqual(self.io.active(),1)
        self.delete(obj);self.assertEqual(self.io.active(),0)
    def test_explicit_asset_close_invalidates_file_descriptor_and_is_idempotent(self):
        self.allocate();a=self.afd();obj,fd,m=self.integer_fd(a);close=self.afd_method('close','()V')
        self.env(61,a,close);self.assertEqual(self.io.active(),0);self.assertEqual(self.env(49,obj,m),0xffffffff)
        self.env(61,a,close);self.assertFalse(self.exception())
    def test_dup_keeps_payload_alive_and_shares_file_position_after_afd_close(self):
        self.allocate();a=self.afd();obj,fd,_=self.integer_fd(a);clone=self.arm.call('ds_io_fcntl',fd,0,0)
        self.assertNotEqual(clone,fd);self.env(61,a,self.afd_method('close','()V'));self.assertEqual(self.io.active(),1)
        self.assertEqual(self.arm.call('ds_io_read',clone,jni.OUT,4),4);self.assertEqual(bytes(self.arm.uc.mem_read(jni.OUT,4)),self.io.data[:4])
        self.assertEqual(self.arm.call('ds_io_seek',clone,0,1),4);self.arm.call('ds_io_close',clone);self.assertEqual(self.io.active(),0)
    def test_external_close_and_fd_reuse_do_not_close_an_unrelated_file(self):
        self.allocate(2);a=self.afd();obj,fd,m=self.integer_fd(a);self.arm.call('ds_io_close',fd)
        b=self.open('EAMCore.ini');self.assertEqual(self.env(49,obj,m),0xffffffff)
        self.env(61,a,self.afd_method('close','()V'));self.assertEqual(self.io.active(),1);self.delete(b);self.assertEqual(self.io.active(),0)
    def test_descriptor_cleanup_consumes_original_but_preserves_dup(self):
        self.allocate();a=self.afd();obj,fd,_=self.integer_fd(a);clone=self.arm.call('ds_io_dup',fd)
        self.arm.call('ds10_cleanup',jni.CTX);self.assertEqual(self.io.active(),1)
        self.assertEqual(self.arm.call('ds_io_read',clone,jni.OUT,3),3);self.arm.call('ds_io_close',clone)
    def test_fcntl_duplicate_minimum_and_capacity_errors(self):
        self.allocate();s=self.open('EAMCore.ini');original=1024
        clone=self.arm.call('ds_io_fcntl',original,0,1030);self.assertEqual(clone,1030)
        self.assertEqual(self.arm.call('ds_io_fcntl',original,0,1032),0xffffffff)
        self.assertEqual(self.arm.call('ds_io_fcntl',original,0,0xffffffff),0xffffffff)
        self.assertEqual(self.arm.call('ds_io_fcntl',original,3),0xffffffff)
        self.delete(s);self.arm.call('ds_io_close',clone)

if __name__=='__main__':
    started=time.monotonic();names=[n for n in ApkAssets.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(ApkAssets(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (jni.cpp.PORTING/'analysis/apk-assets-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
