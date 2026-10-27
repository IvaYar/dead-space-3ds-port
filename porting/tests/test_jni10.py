"""Compiled ARM JNI reference, array and InputStream contracts; no Java success stubs."""
import ctypes,hashlib,json,struct,time,unittest
import test_stage8_cpp as cpp
import test_stage4_io as old_io
BUILD=cpp.PORTING/'3ds/build-emulator';cpp.BUILD=BUILD
CTX=0x0600a000;TEXT=0x06008000;OUT=0x06009000
class Jni10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cpp.CppTests.setUpClass()
    def setUp(self):
        self.base=cpp.CppTests();self.base.setUp();self.arm=self.base.arm
        self.io=old_io.IOTests();self.io.arm=self.arm;self.io.asset=(cpp.PORTING/'analysis/candidate-sd/assets/published/data/achievements.sb').read_bytes()
        self.io.size=self.arm.call('ds_io_context_size');self.io.setUp()
        self.assertLess(self.arm.call('ds10_context_size'),0x2000)
        self.assertEqual(self.arm.call('ds10_init',CTX,0,self.arm.exports['ds10_test_startup']),0)
    def tearDown(self):
        self.arm.call('ds10_cleanup',CTX);self.io.tearDown();self.base.tearDown()
    def text(self,p,s):self.arm.uc.mem_write(p,s.encode()+b'\0');return p
    def env(self,slot,*args,context=CTX):
        table=self.base.words(context)[0];fn=self.base.words(table+slot*4)[0];self.assertNotEqual(fn,0)
        self.arm.exports['_jni']=fn
        return self.arm.call('_jni',context,*(a&0xffffffff for a in args))
    def find(self,name):return self.env(6,self.text(TEXT,name))
    def method(self,clazz,name,sig,static=False):return self.env(113 if static else 33,clazz,self.text(TEXT+256,name),self.text(TEXT+512,sig))
    def exception(self):return self.env(228)
    def clear(self):self.env(17)
    def delete(self,handle,global_=False):self.env(22 if global_ else 23,handle)
    def make_string(self,name):return self.env(167,self.text(TEXT,name))
    def objects(self):
        cls=self.find('com/ea/blast/MainActivity');get=self.method(cls,'GetInstance','()Lcom/ea/blast/MainActivity;',True)
        activity=self.env(114,cls,get);assets=self.method(cls,'getAssets','()Landroid/content/res/AssetManager;')
        manager=self.env(34,activity,assets);mc=self.find('android/content/res/AssetManager')
        return manager,mc
    def open(self,path='data/achievements.sb'):
        manager,cls=self.objects();method=self.method(cls,'open','(Ljava/lang/String;)Ljava/io/InputStream;')
        name=self.make_string(path);stream=self.env(34,manager,method,name);self.delete(name);self.delete(manager);self.delete(cls)
        return stream
    def stream_methods(self):
        cls=self.find('java/io/InputStream')
        return (self.method(cls,'read','([BII)I'),self.method(cls,'skip','(J)J'),self.method(cls,'close','()V'))
    def values(self,*values):
        for i,v in enumerate(values):self.arm.uc.mem_write(OUT+i*8,struct.pack('<Q',v&0xffffffffffffffff))
        return OUT
    def test_exact_method_signature_and_static_kind(self):
        cls=self.find('com/ea/blast/MainActivity');self.assertTrue(cls)
        self.assertTrue(self.method(cls,'GetInstance','()Lcom/ea/blast/MainActivity;',True))
        self.assertEqual(self.method(cls,'GetInstance','()Ljava/lang/Object;',True),0);self.assertTrue(self.exception());self.clear()
        self.assertEqual(self.method(cls,'GetInstance','()Lcom/ea/blast/MainActivity;'),0);self.assertTrue(self.exception())
    def test_unknown_class_and_method_report_pending_exception(self):
        self.assertEqual(self.find('not/Implemented'),0);self.assertTrue(self.env(15));self.clear();self.assertEqual(self.env(15),0)
        cls=self.find('com/ea/EAIO/EAIO');self.assertEqual(self.method(cls,'missing','()V'),0);self.assertTrue(self.exception())
    def test_local_global_reference_identity_and_lifetime(self):
        a=self.find('com/ea/EAIO/EAIO');b=self.env(21,a);self.assertNotEqual(a,b);self.assertEqual(self.env(24,a,b),1)
        self.delete(a);self.assertTrue(self.method(b,'Startup','(Landroid/content/res/AssetManager;)V',True))
        self.delete(b,True);self.assertEqual(self.env(21,b),0);self.assertTrue(self.exception())
    def test_reference_kind_cannot_be_deleted_by_wrong_family(self):
        a=self.find('java/io/InputStream');g=self.env(21,a);self.delete(g);self.assertTrue(self.exception());self.clear()
        self.assertEqual(self.env(24,a,g),1);self.delete(g,True);self.delete(a)
    def test_same_instance_across_independent_local_references(self):
        cls=self.find('com/ea/blast/MainActivity');m=self.method(cls,'GetInstance','()Lcom/ea/blast/MainActivity;',True)
        a=self.env(114,cls,m);b=self.env(116,cls,m,0);self.assertNotEqual(a,b);self.assertEqual(self.env(24,a,b),1)
        c=self.env(31,a);self.assertEqual(self.env(24,c,cls),1)
    def test_invalid_receiver_and_method_id_do_not_dispatch(self):
        cls=self.find('com/ea/blast/MainActivity');m=self.method(cls,'GetInstance','()Lcom/ea/blast/MainActivity;',True)
        self.assertEqual(self.env(114,self.find('java/io/InputStream'),m),0);self.assertTrue(self.exception());self.clear()
        self.assertEqual(self.env(114,cls,0x12345678),0);self.assertTrue(self.exception())
    def test_stale_handles_do_not_survive_context_reset(self):
        a=self.find('java/io/InputStream');self.assertEqual(self.arm.call('ds10_init',CTX,0,0),16)
        self.arm.call('ds10_cleanup',CTX);self.assertEqual(self.arm.call('ds10_init',CTX,0,0),0)
        b=self.find('java/io/InputStream');self.assertNotEqual(a,b);self.assertEqual(self.env(21,a),0)
    def test_foreign_context_handle_is_rejected(self):
        a=self.find('java/io/InputStream');other=CTX+0x2000
        self.assertEqual(self.arm.call('ds10_init',other,0,0),0)
        self.assertEqual(self.env(21,a,context=other),0);self.arm.call('ds10_cleanup',other)
    def test_reference_capacity_fails_instead_of_reusing_live_token(self):
        refs=[self.find('java/io/InputStream') for _ in range(128)];self.assertEqual(len(set(refs)),128);self.assertNotIn(0,refs)
        self.assertEqual(self.find('java/io/InputStream'),0);self.assertTrue(self.exception())
    def test_byte_arrays_zero_length_zero_fill_and_capacity(self):
        zero=self.env(176,0);self.assertTrue(zero);self.assertEqual(self.env(171,zero),0);self.delete(zero)
        refs=[self.env(176,4) for _ in range(8)];self.assertNotIn(0,refs);self.assertEqual(self.env(176,4),0);self.clear()
        self.env(200,refs[0],0,4,OUT);self.assertEqual(bytes(self.arm.uc.mem_read(OUT,4)),b'\0'*4)
    def test_invalid_array_sizes_and_regions_leave_output_unchanged(self):
        self.assertEqual(self.env(176,-1),0);self.clear();self.assertEqual(self.env(176,0x7fffffff),0);self.clear()
        array=self.env(176,4);self.arm.uc.mem_write(OUT,b'Z'*16)
        for start,length in ((-1,1),(3,2),(0,-1),(0x7fffffff,1)):
            self.env(200,array,start,length,OUT);self.assertTrue(self.exception());self.clear()
        self.assertEqual(bytes(self.arm.uc.mem_read(OUT,16)),b'Z'*16)
    def test_array_global_reference_keeps_storage_alive(self):
        a=self.env(176,4);g=self.env(21,a);self.delete(a);self.assertEqual(self.env(171,g),4)
        self.delete(g,True);self.assertEqual(self.env(171,g),0);self.assertTrue(self.exception())
    def test_copy_commit_abort_and_release_semantics(self):
        a=self.env(176,4);self.arm.uc.mem_write(OUT,b'abcd');self.env(208,a,0,4,OUT)
        copy=self.env(184,a,OUT+16);self.assertEqual(bytes(self.arm.uc.mem_read(OUT+16,1)),b'\1')
        self.arm.uc.mem_write(copy,b'1234');self.env(192,a,copy,1)
        self.env(200,a,0,4,OUT);self.assertEqual(bytes(self.arm.uc.mem_read(OUT,4)),b'1234')
        self.arm.uc.mem_write(copy,b'5678');self.env(192,a,copy,2)
        self.env(200,a,0,4,OUT);self.assertEqual(bytes(self.arm.uc.mem_read(OUT,4)),b'1234')
        copy=self.env(184,a,0);self.arm.uc.mem_write(copy,b'ABCD');self.env(192,a,copy,0)
        self.env(200,a,0,4,OUT);self.assertEqual(bytes(self.arm.uc.mem_read(OUT,4)),b'ABCD')
    def test_invalid_release_and_pinned_deletion_refuse_safely(self):
        a=self.env(176,4);copy=self.env(184,a,0);self.delete(a);self.assertTrue(self.exception());self.clear()
        self.env(192,a,copy,7);self.assertTrue(self.exception());self.clear();self.env(192,a,copy,2);self.delete(a)
    def test_reference_array_and_file_cleanup_reclaims_all_resources(self):
        a=self.env(176,128);self.env(184,a,0);self.open()
        self.assertGreater(self.arm.call('ds10_cleanup',CTX),0);self.assertFalse(self.io.files)
        self.arm.call('ds_runtime_stats',OUT);self.assertEqual(self.base.words(OUT,9)[4],0)
    def test_stream_read_eof_zero_length_and_closed_error(self):
        stream=self.open();read,skip,close=self.stream_methods();a=self.env(176,8)
        self.assertEqual(self.env(49,stream,read,a,2,4),4)
        self.env(200,a,0,8,OUT);self.assertEqual(bytes(self.arm.uc.mem_read(OUT,8)),b'\0\0'+self.io.asset[:4]+b'\0\0')
        self.env(63,stream,close,0);self.env(63,stream,close,0)
        self.assertEqual(self.env(49,stream,read,a,0,1),0xffffffff);self.assertTrue(self.exception())
    def test_stream_global_alias_keeps_descriptor_until_last_reference(self):
        s=self.open();g=self.env(21,s);self.delete(s);self.assertEqual(len(self.io.files),1)
        self.delete(g,True);self.assertFalse(self.io.files)
    def test_path_traversal_and_missing_file_are_exceptions(self):
        before=len(self.io.calls);self.assertEqual(self.open('../outside'),0);self.assertEqual(len(self.io.calls),before);self.assertTrue(self.exception())
        self.clear();self.assertEqual(self.open('missing.sb'),0);self.assertTrue(self.exception());self.assertFalse(self.io.files)
    def test_declared_unsupported_method_cannot_fake_success(self):
        manager,cls=self.objects();method=self.method(cls,'openFd','(Ljava/lang/String;)Landroid/content/res/AssetFileDescriptor;')
        self.assertTrue(method);s=self.make_string('data/achievements.sb')
        self.assertEqual(self.env(36,manager,method,self.values(s)),0);self.assertTrue(self.exception());self.assertFalse(self.io.calls)
    def test_actual_softfp_jni_probe_reads_crc_and_long_skip(self):
        blob=(BUILD/'fixture-jni10.so').read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',cpp.FILE_ADDR,cpp.INFO_ADDR,cpp.IMAGE_ADDR,0,0,OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_jni10',CTX,OUT),0)
        result=self.base.words(OUT,4);self.assertEqual(result[0],0);self.assertGreater(result[1],190);self.assertEqual(result[2:],(3568,0x4a8d9499))
        self.assertFalse(self.io.files);self.assertEqual(self.arm.call('ds10_test_callback_errors'),0)
if __name__=='__main__':
    start=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Jni10Tests))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'elapsed_seconds':round(time.monotonic()-start,3),
        'core_sha256':hashlib.sha256((BUILD/'core-test.elf').read_bytes()).hexdigest(),'hardware_tested':False}
    (cpp.PORTING/'analysis/jni10-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
