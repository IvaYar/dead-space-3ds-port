"""Execute ARM JNI String[] ownership and bounded directory snapshot contracts."""
import hashlib,json,struct,time,unittest
import test_strings as strings
import test_jni10 as jni
from test_arm_loader import FILE_ADDR,INFO_ADDR,IMAGE_ADDR
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_LR
HOOK=0x06007000;PATH=0x06007400;DEST=0x06007800
REGS=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
class AssetTests(strings.StringTests):
    def setUp(self):
        super().setUp();self.entries={'':['z','a','middle']};self.backend_calls=[];self.backend_error=False;self.report_count=None;self.fill_count=None
        self.hook=self.arm.uc.hook_add(UC_HOOK_CODE,self.backend,begin=HOOK,end=HOOK)
        self.arm.call('ds19_assets_backend',jni.CTX,HOOK,0)
    def tearDown(self):
        self.arm.uc.hook_del(self.hook);super().tearDown()
    def backend(self,uc,address,size,user):
        _,p,out,cap=(uc.reg_read(r) for r in REGS);path=self.base.text(p);self.backend_calls.append((path,bool(out),cap))
        names=[n.encode('utf-8') if isinstance(n,str) else n for n in self.entries.get(path,[])]
        result=-1 if self.backend_error else len(names)
        if out:
            for i,name in enumerate(names[:cap]):uc.mem_write(out+i*256,(name+b'\0')[:256])
            if self.fill_count is not None:result=self.fill_count
        elif self.report_count is not None:result=self.report_count
        uc.reg_write(UC_ARM_REG_R0,result&0xffffffff);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def listing(self,path=''):
        manager,clazz=self.objects();m=self.method(clazz,'list','(Ljava/lang/String;)[Ljava/lang/String;');s=self.make_string(path)
        result=self.env(34,manager,m,s);self.delete(s);self.delete(manager);self.delete(clazz);return result
    def array(self,n=3,initial=0):
        c=self.find('java/lang/String');a=self.env(172,n,c,initial);self.delete(c);return a
    def names(self,a):
        result=[]
        for i in range(self.env(171,a)):
            s=self.env(173,a,i);result.append(self.encoded(s));self.delete(s)
        return result
    def stats(self):self.arm.call('ds19_jni_stats',jni.CTX,jni.OUT);return self.base.words(jni.OUT,6)
    def path(self,data):
        self.arm.uc.mem_write(PATH,data+b'\0');self.arm.uc.mem_write(DEST,b'Z'*256)
        result=self.arm.call('ds19_path',PATH,DEST);return result,bytes(self.arm.uc.mem_read(DEST,256))
    def test_listing_sorted_deduplicated_and_temporary_strings_reclaimed(self):
        self.entries['']=['z','a','a'];a=self.listing();self.assertEqual(self.names(a),[b'a',b'z']);self.assertEqual(self.stats()[4:],(2,1))
        self.delete(a);self.assertEqual(self.stats()[4:],(0,0));self.assertEqual(self.live_heap(),(0,0))
    def test_empty_and_missing_directories_are_nonnull_empty_arrays(self):
        for path in ('missing','not-a-directory'):
            a=self.listing(path);self.assertTrue(a);self.assertEqual(self.env(171,a),0);self.delete(a)
        self.assertFalse(self.exception());self.assertEqual(self.live_heap(),(0,0))
    def test_more_elements_than_string_pool_and_reference_table(self):
        self.entries['']=[f'name-{i:03}' for i in range(151)];a=self.listing();self.assertEqual(len(self.names(a)),151)
        self.assertFalse(self.exception());self.delete(a);self.assertEqual(self.live_heap(),(0,0))
    def test_utf8_filenames_convert_to_utf16_and_modified_utf8(self):
        self.entries['']=['\u0416','\U0001f680'];a=self.listing();s=self.env(173,a,1)
        self.assertEqual(self.units(s),(0xd83d,0xde80));self.assertEqual(self.encoded(s),strings.mutf((0xd83d,0xde80)))
        self.delete(a);self.assertEqual(self.units(s),(0xd83d,0xde80));self.delete(s);self.assertEqual(self.live_heap(),(0,0))
    def test_element_identity_and_global_reference_survive_array_deletion(self):
        a=self.listing();s=self.env(173,a,0);t=self.env(173,a,0);self.assertNotEqual(s,t);self.assertEqual(self.env(24,s,t),1)
        g=self.env(21,s);self.delete(a);self.delete(s);self.delete(t);self.assertEqual(self.encoded(g),b'a');self.delete(g,True)
        self.assertEqual(self.live_heap(),(0,0))
    def test_ordinary_string_initialization_retains_payload_without_jni_ref(self):
        s=self.wide((65,0,0x416));a=self.array(3,s);self.delete(s);s=self.env(173,a,2)
        self.assertEqual(self.units(s),(65,0,0x416));self.delete(a);self.assertEqual(self.units(s),(65,0,0x416));self.delete(s)
        self.assertEqual(self.live_heap(),(0,0))
    def test_set_replace_clear_and_self_assignment_preserve_ownership(self):
        a=self.listing();s=self.env(173,a,0);self.env(174,a,0,s);self.env(174,a,1,s);self.delete(s)
        self.assertEqual(self.names(a),[b'a',b'a',b'z']);self.env(174,a,0,0);self.assertEqual(self.env(173,a,0),0)
        self.delete(a);self.assertEqual(self.live_heap(),(0,0))
    def test_wrong_component_and_element_types_refuse_atomically(self):
        wrong=self.find('java/io/InputStream');self.assertEqual(self.env(172,1,wrong,0),0);self.assertTrue(self.exception());self.clear()
        a=self.listing();before=self.names(a);self.env(174,a,0,wrong);self.assertTrue(self.exception());self.clear();self.assertEqual(self.names(a),before)
        self.assertEqual(self.array(1,wrong),0);self.assertTrue(self.exception());self.clear();self.delete(a);self.delete(wrong)
    def test_bounds_sizes_and_null_array_are_exceptions(self):
        for n in (-1,2049,0x7fffffff):self.assertEqual(self.array(n),0);self.assertTrue(self.exception());self.clear()
        a=self.array(0);self.assertTrue(a);self.assertEqual(self.env(171,a),0)
        for handle,index in ((a,0),(a,-1),(0,0)):
            self.assertEqual(self.env(173,handle,index),0);self.assertTrue(self.exception());self.clear()
            self.env(174,handle,index,0);self.assertTrue(self.exception());self.clear()
        self.delete(a)
    def test_object_array_pool_exhaustion_and_recovery(self):
        arrays=[self.array(0) for _ in range(8)];self.assertNotIn(0,arrays);self.assertEqual(self.array(0),0);self.clear()
        self.delete(arrays.pop());arrays.append(self.array(0));self.assertNotIn(0,arrays)
        for a in arrays:self.delete(a)
    def test_array_alias_and_nested_local_frame_escape(self):
        self.env(19,8);a=self.listing();g=self.env(21,a);self.env(20,0);self.assertEqual(self.names(g),[b'a',b'middle',b'z'])
        self.env(19,8);s=self.env(173,g,0);s=self.env(20,s);self.delete(g,True);self.assertEqual(self.encoded(s),b'a');self.delete(s)
        self.assertEqual(self.live_heap(),(0,0))
    def test_pinned_extra_string_refuses_delete_and_frame_pop(self):
        a=self.listing();self.env(19,4);s=self.env(173,a,0);p=self.env(224,s,0);self.delete(a)
        self.delete(s);self.assertTrue(self.exception());self.clear();self.env(20,0);self.assertTrue(self.exception());self.clear()
        self.env(225,s,p);self.env(20,0);self.assertEqual(self.live_heap(),(0,0))
    def test_cleanup_reclaims_live_array_and_pinned_external_string(self):
        a=self.listing();s=self.env(173,a,0);self.env(169,s,0);self.arm.call('ds10_cleanup',jni.CTX);self.assertEqual(self.live_heap(),(0,0))
    def test_backend_missing_refuses_instead_of_reporting_empty_success(self):
        self.arm.call('ds19_assets_backend',jni.CTX,0,0);self.assertEqual(self.listing(),0);self.assertTrue(self.exception())
    def test_backend_error_count_overflow_and_two_pass_race_are_atomic(self):
        for error,count,fill in ((True,None,None),(False,2049,None),(False,None,2),(False,None,-1)):
            self.backend_error,self.report_count,self.fill_count=error,count,fill
            self.assertEqual(self.listing(),0);self.assertTrue(self.exception());self.clear();self.assertEqual(self.live_heap(),(0,0));self.assertEqual(self.stats()[4:],(0,0))
    def test_invalid_backend_filenames_are_not_published(self):
        for name in (b'..',b'a/b',b'a\\b',b'a:b',b'\x80',b'\xed\xa0\x80',b'\xf4\x90\x80\x80',b'X'*256):
            self.entries['']=[name];self.assertEqual(self.listing(),0);self.assertTrue(self.exception());self.clear();self.assertEqual(self.live_heap(),(0,0))
    def test_allocation_failures_rollback_snapshots_arrays_and_strings(self):
        for budget in (32,800,1000,1400):
            self.assertEqual(self.arm.call('ds_runtime_init',budget),0);self.assertEqual(self.listing(),0);self.assertTrue(self.exception());self.clear()
            self.assertEqual(self.live_heap(),(0,0));self.assertEqual(self.stats()[4:],(0,0))
        self.assertEqual(self.arm.call('ds_runtime_init',1048576),0);a=self.listing();self.assertTrue(a);self.delete(a)
    def test_reference_capacity_failure_reclaims_new_array_payload(self):
        c=self.find('java/lang/String')
        for _ in range(127):self.find('java/io/InputStream')
        self.assertEqual(self.env(172,10,c,0),0);self.assertTrue(self.exception());self.assertEqual(self.live_heap(),(0,0));self.assertEqual(self.stats()[5],0)
    def test_paths_canonicalize_virtual_published_aliases(self):
        for path in (b'data/',b'published/data',b'appbundle:/published/data'):
            result,out=self.path(path);self.assertEqual(result,0);self.assertEqual(out[:5],b'data\0')
        for path in (b'',b'published',b'published/',b'appbundle:/published'):
            result,out=self.path(path);self.assertEqual((result,out[0]),(0,0))
    def test_unsafe_and_malformed_paths_do_not_write_output(self):
        for path in (b'/',b'//',b'../x',b'a/../b',b'a//b',b'a\\b',b'a:b',b'\xc0\x80',b'\xed\xa0\x80',b'\xf0\x9f\x9a\x80',b'x'*256):
            result,out=self.path(path);self.assertEqual(result,0xffffffff,path);self.assertEqual(out,b'Z'*256)
    def test_supplementary_path_uses_filesystem_scalar_utf8(self):
        result,out=self.path(strings.mutf((0xd83d,0xde80)));self.assertEqual(result,0);self.assertEqual(out[:5],b'\xf0\x9f\x9a\x80\0')
    def test_traversal_is_rejected_before_directory_backend(self):
        self.assertEqual(self.listing('../outside'),0);self.assertTrue(self.exception());self.assertEqual(self.backend_calls,[])
    def test_open_alias_and_exact_external_cache_prefix(self):
        for path in ('data/achievements.sb','published/data/achievements.sb','appbundle:/published/data/achievements.sb'):
            s=self.open(path);self.assertTrue(s);self.delete(s)
        path='/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/published/data/achievements.sb'
        self.io.string(PATH,path);fd=self.arm.call('ds_io_open',PATH,0);self.assertEqual(fd,1024);self.arm.call('ds_io_close',fd)
    def test_directory_delegate_distinguishes_internal_and_external_roots(self):
        c=self.find('com/ea/blast/GetAppDataDirectoryDelegate');m=self.method(c,'<init>','()V');o=self.env(30,c,m,0)
        for name,want in (('GetAppDataDirectory',b'appdata:/'),('GetExternalStorageDirectory',b'/sdcard/Android/data/com.ea.deadspace/files')):
            m=self.method(c,name,'()Ljava/lang/String;');s=self.env(34,o,m);self.assertEqual(self.encoded(s),want);self.delete(s)
    def test_arena_observer_reports_refusal_and_default_errno_is_preserved(self):
        self.arm.uc.mem_map(0x12000000,0x2000);self.assertEqual(self.arm.call('ds9_memory_init',0x12000000,4096,0x12001000,4096),0)
        events=[]
        def observe(uc,address,size,user):
            p,n,error=(uc.reg_read(r) for r in REGS[:3]);events.append((self.base.text(p),n,error));uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        hook=self.arm.uc.hook_add(UC_HOOK_CODE,observe,begin=HOOK+4,end=HOOK+4);self.arm.call('ds9_memory_observer',HOOK+4)
        self.assertEqual(self.arm.call('ds9_mmap',0,8192,3,0x22,0xffffffff,0),0xffffffff);self.assertEqual(events,[('mmap',8192,12)])
        self.assertEqual(self.base.words(self.arm.call('ds_io_errno'))[0],12);self.arm.call('ds9_memory_observer',0)
        self.assertEqual(self.arm.call('ds9_sbrk',8192),0xffffffff);self.assertEqual(len(events),1);self.arm.uc.hook_del(hook)
    def test_real_softfp_asset_fixture_matches_source_directory_contract(self):
        contract=json.loads((jni.cpp.PORTING/'analysis/asset-directory-contract.json').read_text());self.entries={p:d['names'] for p,d in contract['directories'].items()}
        blob=(jni.BUILD/'fixture-assets.so').read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,0,0,jni.OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_assets',jni.CTX,jni.OUT),0)
        failure,checks,total,crc=self.base.words(jni.OUT,4);self.assertEqual(failure,0);self.assertGreater(checks,350);self.assertEqual(total,176)
        expected=0
        for d in contract['directories'].values():expected^=int(d['names_crc32'],16)
        self.assertEqual(crc,expected);self.assertEqual(self.stats()[4:],(0,0));self.assertEqual(self.live_heap(),(0,0))
if __name__=='__main__':
    start=time.monotonic();names=[n for n in AssetTests.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(AssetTests(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256((jni.BUILD/'fixture-assets.so').read_bytes()).hexdigest(),
        'elapsed_seconds':round(time.monotonic()-start,3)}
    (jni.cpp.PORTING/'analysis/assets-tests.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
