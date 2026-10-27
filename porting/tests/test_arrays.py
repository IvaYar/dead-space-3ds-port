"""GL client descriptors and real buffer stores, executed as ARM code."""
import hashlib,json,struct,time,unittest
import test_gles_state as gl
from test_arm_loader import FILE_ADDR,INFO_ADDR,IMAGE_ADDR
DATA=0x16000400;RESULT=0x16000600
class ArrayTests(gl.GlesTests):
    def names(self,n=1):
        self.call('glGenBuffers',n,gl.OUT);return self.base.words(gl.OUT,n)
    def stats(self):self.arm.call('ds14_test_stats',gl.OUT);return self.base.words(gl.OUT,4)
    def upload(self,data=b'abcdefghijklmnopqrstuvwx'):
        name=self.names()[0];self.call('glBindBuffer',0x8892,name);self.arm.uc.mem_write(DATA,data)
        self.call('glBufferData',0x8892,len(data),DATA,0x88e4);return name
    def read(self,slot=0,index=0,size=16):
        self.arm.uc.mem_write(RESULT,b'Z'*32);code=self.arm.call('ds14_test_read',slot,index,RESULT,size)
        return code,bytes(self.arm.uc.mem_read(RESULT,32))
    def test_generated_names_reserved_until_bound(self):
        a,b=self.names(2);self.assertNotEqual(a,b);self.assertEqual(self.call('glIsBuffer',a),0)
        self.call('glBindBuffer',0x8892,a);self.assertEqual(self.call('glIsBuffer',a),1);self.assertEqual(self.call('glIsBuffer',0),0)
    def test_arbitrary_bind_creates_and_target_bindings_are_independent(self):
        self.call('glBindBuffer',0x8892,0xffffffff);self.call('glBindBuffer',0x8893,123)
        self.assertEqual(self.query(0x8894,1),(0xffffffff,));self.assertEqual(self.query(0x8895,1),(123,))
        a=self.names()[0];self.assertNotEqual(a,123)
    def test_pool_exhaustion_is_atomic_and_recovers_after_delete(self):
        names=self.names(32);self.arm.uc.mem_write(RESULT,b'Z'*8);self.call('glGenBuffers',1,RESULT)
        self.assertEqual(self.call('glGetError'),0x505);self.assertEqual(bytes(self.arm.uc.mem_read(RESULT,8)),b'Z'*8)
        self.base.write(gl.OUT,names[0]);self.call('glDeleteBuffers',1,gl.OUT);self.assertNotEqual(self.names()[0],0)
    def test_upload_and_subdata_copy_real_bytes(self):
        self.upload();self.call('glVertexPointer',3,0x1406,0,0)
        self.assertEqual(self.read(index=1)[1][:12],b'mnopqrstuvwx')
        self.arm.uc.mem_write(DATA,b'1234');self.call('glBufferSubData',0x8892,12,4,DATA)
        self.assertEqual(self.read(index=1)[1][:12],b'1234qrstuvwx')
    def test_descriptor_captures_buffer_at_pointer_call_not_current_binding(self):
        a=self.upload();self.call('glVertexPointer',3,0x1406,0,0);b=self.upload(b'Z'*24)
        self.assertNotEqual(a,b);self.assertEqual(self.query(0x8896,1),(a,));self.assertEqual(self.read()[1][:12],b'abcdefghijkl')
    def test_invalid_subdata_keeps_original_bytes(self):
        self.upload();self.call('glVertexPointer',3,0x1406,0,0)
        for offset,size in ((-1,1),(23,2),(0,-1),(0x7fffffff,4)):
            self.call('glBufferSubData',0x8892,offset,size,DATA);self.assertEqual(self.call('glGetError'),0x501)
        self.assertEqual(self.read()[1][:12],b'abcdefghijkl')
    def test_reallocation_oom_preserves_existing_store(self):
        self.assertEqual(self.arm.call('ds_runtime_init',16),0);self.upload(b'abcdefghijkl')
        self.call('glVertexPointer',3,0x1406,0,0);self.call('glBufferData',0x8892,16,DATA,0x88e4)
        self.assertEqual(self.call('glGetError'),0x505);self.assertEqual(self.read()[1][:12],b'abcdefghijkl');self.assertEqual(self.stats()[1],12)
    def test_buffer_data_null_and_zero_size(self):
        name=self.names()[0];self.call('glBindBuffer',0x8892,name);self.call('glBufferData',0x8892,12,0,0x88e8)
        self.call('glVertexPointer',3,0x1406,0,0);self.assertEqual(self.read()[1][:12],b'\0'*12)
        self.call('glBufferData',0x8892,0,0,0x88e4);self.assertEqual(self.stats()[1],0);self.assertEqual(self.read()[0],0xffffffff)
    def test_delete_detaches_all_current_context_bindings(self):
        name=self.upload();self.call('glBindBuffer',0x8893,name);self.call('glVertexPointer',3,0x1406,0,4)
        self.base.write(gl.OUT,name,name,0,999);self.call('glDeleteBuffers',4,gl.OUT)
        self.assertEqual(self.stats(),(0,0,0,0));self.assertEqual(self.query(0x8896,1),(0,));self.assertEqual(self.call('glIsBuffer',name),0)
        self.call('glGetPointerv',0x808e,gl.OUT);self.assertEqual(self.base.words(gl.OUT)[0],4)
    def test_client_texture_arrays_are_selected_independently(self):
        self.call('glEnableClientState',0x8078);self.call('glTexCoordPointer',2,0x1406,8,DATA)
        self.call('glClientActiveTexture',0x84c1);self.assertEqual(self.call('glIsEnabled',0x8078),0);self.assertEqual(self.query(0x8088,1),(4,))
        self.call('glClientActiveTexture',0x84c0);self.assertEqual(self.call('glIsEnabled',0x8078),1);self.assertEqual(self.query(0x8088,1),(2,))
    def test_pointer_validation_is_atomic(self):
        self.call('glVertexPointer',3,0x1406,12,DATA)
        for n,t,stride,err in ((1,0x1406,0,0x501),(3,0x1401,0,0x500),(3,0x1406,-1,0x501)):
            self.call('glVertexPointer',n,t,stride,DATA+8);self.assertEqual(self.call('glGetError'),err)
        self.call('glGetPointerv',0x808e,gl.OUT);self.assertEqual(self.base.words(gl.OUT)[0],DATA)
        self.call('glColorPointer',3,0x1401,0,DATA);self.assertEqual(self.call('glGetError'),0x501)
    def test_client_reads_require_registered_live_range(self):
        self.arm.uc.mem_write(DATA,b'abcdefghijklmnopqrstuvwx');self.call('glVertexPointer',3,0x1406,0,DATA)
        self.assertEqual(self.read()[0],0xffffffff);self.assertEqual(self.arm.call('ds14_test_range',DATA,24),0)
        self.assertEqual(self.read(index=1)[1][:12],b'mnopqrstuvwx');self.assertEqual(self.read(index=2)[0],0xffffffff)
    def test_staging_checks_index_stride_and_output_capacity(self):
        self.upload();self.call('glVertexPointer',3,0x1406,0,0)
        for index,size in ((1,11),(2,16),(0xffffffff,16)):
            status,out=self.read(index=index,size=size);self.assertEqual(status,0xffffffff);self.assertEqual(out,b'Z'*32)
        self.call('glVertexPointer',3,0x1406,0x7fffffff,0);self.assertEqual(self.read(index=0xffffffff)[0],0xffffffff)
    def test_client_registration_update_removal_and_capacity(self):
        self.call('glVertexPointer',3,0x1406,0,DATA)
        self.assertEqual(self.arm.call('ds14_test_range',DATA,24),0);self.assertEqual(self.arm.call('ds14_test_range',DATA,12),0)
        self.assertEqual(self.read(index=1)[0],0xffffffff);self.assertEqual(self.arm.call('ds14_test_unrange',DATA),0)
        self.assertEqual(self.read()[0],0xffffffff)
        for i in range(8):self.assertEqual(self.arm.call('ds14_test_range',DATA+i*32,24),0)
        self.assertEqual(self.arm.call('ds14_test_range',DATA+256,24),0xffffffff)
        self.assertEqual(self.arm.call('ds14_test_range',0xfffffff0,32),0xffffffff)
    def test_bad_buffer_arguments_do_not_create_storage(self):
        self.arm.uc.mem_write(RESULT,b'Z'*16);self.call('glGenBuffers',-1,RESULT);self.assertEqual(self.call('glGetError'),0x501)
        self.assertEqual(bytes(self.arm.uc.mem_read(RESULT,16)),b'Z'*16)
        self.call('glDeleteBuffers',-1,DATA);self.assertEqual(self.call('glGetError'),0x501)
        self.call('glGenBuffers',0,0);self.assertEqual(self.call('glGetError'),0)
        self.call('glBufferData',0x8892,12,DATA,0x88e4);self.assertEqual(self.call('glGetError'),0x502)
        self.call('glBindBuffer',0x1234,1);self.assertEqual(self.call('glGetError'),0x500)
        self.call('glBindBuffer',0x8892,1);self.call('glBufferData',0x8892,-1,DATA,0x88e4);self.assertEqual(self.call('glGetError'),0x501)
        self.call('glBufferData',0x8892,4,DATA,0x88e0);self.assertEqual(self.call('glGetError'),0x500);self.assertEqual(self.stats()[1],0)
    def test_buffer_parameters_and_softfp_fixture(self):
        blob=(gl.jni.BUILD/'fixture-arrays.so').read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,gl.TABLE,67,gl.OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_arrays',gl.OUT),0);name,size,ptr=self.base.words(gl.OUT,3)
        self.assertTrue(name);self.assertEqual((size,ptr),(24,4));self.assertEqual(self.stats()[1],0)
    def test_cleanup_reclaims_all_live_stores(self):
        self.upload();self.upload();self.assertEqual(self.stats()[1],48);self.arm.call('ds13_close',gl.CTX)
        self.arm.call('ds_runtime_stats',gl.OUT);self.assertEqual(self.base.words(gl.OUT,9)[4:6],(0,0))
        self.assertEqual(self.arm.call('ds13_context_size')<4096,True)
if __name__=='__main__':
    started=time.monotonic();names=[n for n in ArrayTests.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(ArrayTests(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,'game_rendered':False,
        'core_sha256':hashlib.sha256((gl.jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256((gl.jni.BUILD/'fixture-arrays.so').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (gl.jni.cpp.PORTING/'analysis/arrays-tests.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
