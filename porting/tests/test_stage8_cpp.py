"""Execute compiled ARM C++ constructors and validate lifecycle refusal paths."""
import ctypes,json,struct,time,unittest
from test_arm_loader import ARMCore,PORTING,FILE_ADDR,INFO_ADDR,IMAGE_ADDR,STOP_ADDR,symbols
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC,UC_ARM_REG_PC
BUILD=PORTING/'3ds/build-stage8'
CTX=0x06000000; TABLE=CTX+0x1000; OUT=CTX+0x3000; OBJECT=CTX+0x5000; PLAN=CTX+0x6000; CODE=CTX+0x8000; MARKS=CTX+0x9000
class CppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor=(PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.fixture=(BUILD/'fixture-stage8.so').read_bytes()
    def setUp(self):
        self.arm=ARMCore(self.donor,BUILD/'core-test.elf')
        self.arm.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000); self.arm.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        self.arm.uc.mem_map(CTX,0x10000)
        self.arm.call('ds_io_init',CTX,CTX+0x100); self.assertEqual(self.arm.call('ds_runtime_init',1048576),0)
        self.assertEqual(self.arm.call('ds7_init'),0); self.assertEqual(self.arm.call('ds8_init'),0)
        n=self.arm.call('ds6_bindings',TABLE,192); n+=self.arm.call('ds7_bindings',TABLE+n*8,192-n)
        n+=self.arm.call('ds8_bindings',TABLE+n*8,192-n); self.assertEqual(n,156)
        self.bindings={}; self.indices={}
        for i in range(n):
            name,fn=struct.unpack('<II',self.arm.uc.mem_read(TABLE+i*8,8)); name=self.text(name)
            self.bindings[name]=fn; self.indices[name]=i
        # Independent six-instruction ARM callback: append R0 to a list.
        self.arm.uc.mem_write(CODE,struct.pack('<7I',0xe59f1010,0xe5912000,0xe2822001,0xe7810102,0xe5812000,0xe12fff1e,MARKS))
    def tearDown(self):
        self.arm.call('ds7_test_select_tls',0)
        self.arm.call('ds8_finalize',0)
        self.assertEqual(self.arm.call('ds7_shutdown',0,0),0)
        self.assertEqual(self.arm.call('ds_runtime_cleanup'),0)
        self.arm.call('ds_io_shutdown',CTX)
    def text(self,p):
        data=bytearray()
        while (b:=bytes(self.arm.uc.mem_read(p+len(data),1)))!=b'\0': data+=b
        return data.decode()
    def words(self,p,n=1): return struct.unpack('<'+'I'*n,self.arm.uc.mem_read(p,n*4))
    def write(self,p,*v): self.arm.uc.mem_write(p,struct.pack('<'+'I'*len(v),*(x&0xffffffff for x in v)))
    def call(self,name,*args):
        self.arm.exports['_call']=self.bindings[name]
        return ctypes.c_int32(self.arm.call('_call',*(a&0xffffffff for a in args))).value
    def stats(self):
        self.arm.call('ds8_stats',OUT); return self.words(OUT,10)
    def prepare(self,blob=None):
        blob=self.fixture if blob is None else blob
        self.arm.set_file(blob); code,info=self.arm.prepare(); self.assertEqual(code,0); return info
    def plan(self,blob=None):
        blob=self.fixture if blob is None else blob
        return self.arm.call('ds_init_bind_plan',FILE_ADDR,len(blob),IMAGE_ADDR,IMAGE_ADDR,TABLE,156,PLAN,OUT)
    def invoke(self,blob,name,*args):
        exports,_=symbols(blob); self.arm.exports['_fixture']=IMAGE_ADDR+exports[name]
        return self.arm.call('_fixture',*args)
    def marks(self): return self.words(MARKS+4,self.words(MARKS)[0])
    def fatal(self,name,*args):
        hit=[]
        def stop(uc,address,size,data): hit.append(address); uc.reg_write(UC_ARM_REG_PC,STOP_ADDR); uc.emu_stop()
        pc=self.arm.exports['ds7_bad_main_exit']; hook=self.arm.uc.hook_add(UC_HOOK_CODE,stop,begin=pc,end=pc)
        try: self.arm.call(name,*args)
        finally: self.arm.uc.hook_del(hook)
        self.assertEqual(hit,[pc])
    def test_guard_four_bytes_bit_zero_only_and_neighbor_untouched(self):
        self.write(OBJECT,0x80000000,0xabcdef01)
        self.assertEqual(self.arm.call('ds8_guard_acquire',OBJECT),1)
        self.arm.call('ds8_guard_release',OBJECT)
        self.assertEqual(self.words(OBJECT,2),(0x80000001,0xabcdef01))
        self.assertEqual(self.arm.call('ds8_guard_acquire',OBJECT),0)
    def test_guard_abort_allows_retry_without_marking_initialized(self):
        self.write(OBJECT,0x80000000)
        self.assertEqual(self.arm.call('ds8_guard_acquire',OBJECT),1); self.arm.call('ds8_guard_abort',OBJECT)
        self.assertEqual(self.words(OBJECT)[0],0x80000000)
        self.assertEqual(self.arm.call('ds8_guard_acquire',OBJECT),1); self.arm.call('ds8_guard_release',OBJECT)
        self.assertEqual(self.stats()[1:5],(1,1,0,0))
    def test_guard_slots_recycle_for_many_distinct_statics(self):
        for i in range(300):
            p=OBJECT+i*4; self.assertEqual(self.arm.call('ds8_guard_acquire',p),1); self.arm.call('ds8_guard_release',p)
        self.assertEqual(self.stats()[4],0)
    def test_recursive_initialization_faults_without_skipping_constructor(self):
        self.arm.call('ds8_guard_acquire',OBJECT); self.fatal('ds8_guard_acquire',OBJECT)
        self.assertEqual(self.words(OBJECT)[0],0); self.assertEqual(self.stats()[9],1)
        self.arm.call('ds8_guard_abort',OBJECT)
    def test_wrong_owner_cannot_publish_completed_guard(self):
        self.arm.call('ds8_guard_acquire',OBJECT); self.arm.call('ds7_test_select_tls',1)
        self.fatal('ds8_guard_release',OBJECT); self.assertEqual(self.words(OBJECT)[0],0)
        self.arm.call('ds7_test_select_tls',0); self.arm.call('ds8_guard_abort',OBJECT)
    def test_unaligned_guard_faults_without_access(self):
        self.fatal('ds8_guard_acquire',OBJECT+1); self.assertEqual(self.words(OBJECT)[0],0)
    def test_runtime_reset_refuses_active_guard(self):
        self.arm.call('ds8_guard_acquire',OBJECT); self.assertEqual(self.arm.call('ds8_init'),16)
        self.arm.call('ds8_guard_abort',OBJECT); self.assertEqual(self.arm.call('ds8_init'),0)
    def test_active_guard_limit_faults_instead_of_skipping_initialization(self):
        for i in range(64): self.assertEqual(self.arm.call('ds8_guard_acquire',OBJECT+i*4),1)
        self.fatal('ds8_guard_acquire',OBJECT+256); self.assertEqual(self.words(OBJECT+256)[0],0)
        for i in range(64): self.arm.call('ds8_guard_abort',OBJECT+i*4)
        self.assertEqual(self.stats()[4],0)
    def test_runtime_reset_refuses_pending_destructors(self):
        self.arm.call('ds8_atexit',CODE,17,OBJECT); self.assertEqual(self.arm.call('ds8_init'),16)
        self.arm.call('ds8_finalize',0); self.assertEqual(self.marks(),(17,)); self.assertEqual(self.arm.call('ds8_init'),0)
    def test_aeabi_and_cxa_argument_orders_and_lifo(self):
        self.assertEqual(self.arm.call('ds8_aeabi_atexit',10,CODE,OBJECT),0)
        self.assertEqual(self.arm.call('ds8_atexit',CODE,20,OBJECT),0)
        self.arm.call('ds8_finalize',0); self.assertEqual(self.marks(),(20,10))
    def test_dso_filter_and_repeat_do_not_double_destroy(self):
        for obj,dso in ((10,OBJECT),(20,OBJECT+4),(30,OBJECT)):
            self.arm.call('ds8_atexit',CODE,obj,dso)
        self.arm.call('ds8_finalize',OBJECT); self.arm.call('ds8_finalize',OBJECT)
        self.assertEqual(self.marks(),(30,10)); self.assertEqual(self.stats()[7],1)
        self.arm.call('ds8_finalize',0); self.assertEqual(self.marks(),(30,10,20))
    def test_registry_capacity_failure_is_reported_and_slots_reusable(self):
        for i in range(256): self.assertEqual(self.arm.call('ds8_atexit',CODE,i,OBJECT),0)
        self.assertEqual(ctypes.c_int32(self.arm.call('ds8_atexit',CODE,999,OBJECT)).value,-1)
        self.assertEqual(self.words(self.arm.call('ds_io_errno'))[0],12)
        self.arm.call('ds8_finalize',0); self.assertEqual(self.marks(),tuple(reversed(range(256))))
        self.assertEqual(self.arm.call('ds8_atexit',CODE,1000,OBJECT),0)
    def test_null_destructor_is_not_registered(self):
        self.assertEqual(ctypes.c_int32(self.arm.call('ds8_atexit',0,1,OBJECT)).value,-1)
        self.assertEqual(self.stats()[7],0); self.assertEqual(self.words(self.arm.call('ds_io_errno'))[0],22)
    def test_compiler_generated_global_constructors_and_destructors(self):
        self.prepare(); self.assertEqual(self.plan(),0); self.assertEqual(self.words(PLAN,3),(2,1,0))
        self.invoke(self.fixture,'probe_snapshot',OUT); self.assertEqual(self.words(OUT,5),(0,0,0,0,0))
        self.assertEqual(self.arm.call('ds_init_run',PLAN),0)
        self.invoke(self.fixture,'probe_snapshot',OUT); self.assertEqual(self.words(OUT,5),(2,912,0,0,0))
        self.arm.call('ds8_finalize',0)
        self.invoke(self.fixture,'probe_snapshot',OUT); self.assertEqual(self.words(OUT,5),(2,912,2,21,0))
        self.assertEqual(self.stats()[5:9],(2,2,0,0))
    def test_constructor_plan_is_single_use(self):
        self.prepare(); self.assertEqual(self.plan(),0); self.assertEqual(self.arm.call('ds_init_run',PLAN),0)
        self.assertEqual(self.arm.call('ds_init_run',PLAN),12)
        self.invoke(self.fixture,'probe_snapshot',OUT); self.assertEqual(self.words(OUT,2),(2,912))
    def test_empty_or_running_plan_cannot_execute(self):
        self.assertEqual(self.arm.call('ds_init_run',PLAN),12)
        self.write(PLAN,1,2,0,CODE); self.assertEqual(self.arm.call('ds_init_run',PLAN),12)
        self.assertEqual(self.marks(),())
    def test_plan_snapshots_constructor_array_before_execution(self):
        info=self.prepare(); self.assertEqual(self.plan(),0)
        self.write(IMAGE_ADDR+info.init_array,IMAGE_ADDR+info.image_size+4)
        self.assertEqual(self.arm.call('ds_init_run',PLAN),0)
        self.invoke(self.fixture,'probe_snapshot',OUT); self.assertEqual(self.words(OUT,2),(2,912))
    def test_last_bad_constructor_prevents_even_dt_init_from_running(self):
        info=self.prepare(); self.write(IMAGE_ADDR+info.init_array,IMAGE_ADDR+info.image_size+4)
        self.assertEqual(self.plan(),11); self.assertEqual(self.words(PLAN,3),(0,0,0))
        self.assertEqual(self.arm.call('ds_init_run',PLAN),12)
        self.invoke(self.fixture,'probe_snapshot',OUT); self.assertEqual(self.words(OUT,5),(0,0,0,0,0))
    def test_constructor_in_writable_data_is_rejected(self):
        info=self.prepare(); self.write(IMAGE_ADDR+info.init_array,IMAGE_ADDR+info.init_array)
        self.assertEqual(self.plan(),11)
    def test_misaligned_arm_constructor_is_rejected(self):
        info=self.prepare(); pointer=self.words(IMAGE_ADDR+info.init_array)[0]
        self.write(IMAGE_ADDR+info.init_array,(pointer&~3)+2); self.assertEqual(self.plan(),11)
    def test_null_and_minus_one_array_sentinels_are_skipped(self):
        for value in (0,0xffffffff):
            info=self.prepare(); self.write(IMAGE_ADDR+info.init_array,value)
            self.assertEqual(self.plan(),0); self.assertEqual(self.words(PLAN,3),(1,1,0))
    def test_unresolved_binding_leaves_image_unchanged_and_plan_empty(self):
        info=self.prepare(); before=bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size))
        self.write(TABLE+self.indices['malloc']*8+4,0)
        self.assertEqual(self.plan(),9); self.assertEqual(self.words(PLAN,3),(0,0,0))
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size)),before)
    def test_legacy_imported_dso_token_and_aeabi_destructor(self):
        blob=(BUILD/'fixture-stage8-legacy.so').read_bytes(); self.prepare(blob); self.assertEqual(self.plan(blob),0)
        self.assertEqual(self.arm.call('ds_init_run',PLAN),0)
        self.assertEqual(self.invoke(blob,'probe_legacy_marker'),1)
        token=self.bindings['__dso_handle']; self.assertEqual(self.invoke(blob,'probe_legacy_token'),token)
        self.assertEqual(self.words(token)[0],token)
        self.arm.call('ds8_finalize',token); self.assertEqual(self.invoke(blob,'probe_legacy_marker'),2)
    def test_donor_cannot_build_constructor_plan_while_imports_are_missing(self):
        info=self.prepare(self.donor); before=bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size))
        self.assertEqual(info.init_count,209); self.assertEqual(self.plan(self.donor),9)
        self.assertEqual(self.words(OUT,4),(392,149,239,4)); self.assertEqual(self.words(PLAN,3),(0,0,0))
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size)),before)
        for name in ('__cxa_begin_cleanup','__cxa_call_unexpected','__cxa_type_match','__gnu_Unwind_Find_exidx','glDrawArrays'):
            self.assertNotIn(name,self.bindings)
if __name__=='__main__':
    start=time.monotonic(); result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CppTests))
    report={'tested_core':'stage8','tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
        'elapsed_seconds':round(time.monotonic()-start,3),'hardware_tested':False,'native_concurrency_tested_separately_in_Azahar':True}
    (PORTING/'analysis/stage8-cpp-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
