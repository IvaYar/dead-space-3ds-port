"""ARM unit checks for the pthread ABI; native concurrency is tested in Azahar."""
import ctypes
import json
import struct
import time
import unittest
from test_arm_loader import ARMCore,PORTING,FILE_ADDR,INFO_ADDR,IMAGE_ADDR
from unicorn.arm_const import UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC
CTX=0x06000000; TABLE=CTX+0x1000; OUT=CTX+0x3000; OBJECT=CTX+0x5000

class ThreadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor=(PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.fixture=(PORTING/'3ds/build-stage7/fixture-stage7.so').read_bytes()
        cls.arm=ARMCore(cls.donor,PORTING/'3ds/build-stage7/core-test.elf')
        cls.arm.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000); cls.arm.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        cls.arm.uc.mem_map(CTX,0x10000)
    def setUp(self):
        self.arm.uc.mem_write(OBJECT,b'\0'*4096)
        self.arm.call('ds_io_init',CTX,CTX+0x100)
        self.assertEqual(self.arm.call('ds_runtime_init',1048576),0)
        self.assertEqual(self.arm.call('ds7_init'),0)
        n=self.arm.call('ds6_bindings',TABLE,192); n+=self.arm.call('ds7_bindings',TABLE+n*8,192-n)
        self.assertEqual(n,148); self.bindings={}
        for i in range(n):
            name,fn=struct.unpack('<II',self.arm.uc.mem_read(TABLE+i*8,8)); self.bindings[self.text(name)]=fn
    def tearDown(self):
        self.arm.call('ds7_test_select_tls',0)
        self.assertEqual(self.arm.call('ds7_test_heap_depth'),0)
        self.assertEqual(self.arm.call('ds7_shutdown',0,0),0)
        self.assertEqual(self.arm.call('ds_runtime_cleanup'),0)
        self.arm.call('ds_io_shutdown',CTX)
    def text(self,p):
        data=bytearray()
        while (b:=bytes(self.arm.uc.mem_read(p+len(data),1)))!=b'\0': data+=b
        return data.decode()
    def word(self,p): return struct.unpack('<I',self.arm.uc.mem_read(p,4))[0]
    def write(self,p,v): self.arm.uc.mem_write(p,struct.pack('<I',v&0xffffffff))
    def call(self,name,*args):
        self.arm.exports['_call']=self.bindings[name]
        return ctypes.c_int32(self.arm.call('_call',*(v&0xffffffff for v in args))).value
    def error(self): return self.word(self.arm.call('ds_io_errno'))
    def test_fixture_has_47_resolved_imports(self):
        self.arm.set_file(self.fixture); self.assertEqual(self.arm.prepare()[0],0)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,TABLE,148,OUT),0)
        self.assertEqual(struct.unpack('<5I',self.arm.uc.mem_read(OUT,20))[:4],(47,47,0,0))
    def test_attributes_layout_validation_and_stack_query(self):
        self.assertEqual(self.call('pthread_attr_init',OUT),0)
        self.assertEqual(struct.unpack('<6I',self.arm.uc.mem_read(OUT,24)),(0,0,262144,0,0,0))
        self.assertEqual(self.call('pthread_attr_setstacksize',OUT,65536),0)
        self.assertEqual(self.call('pthread_attr_getstack',OUT,OUT+32,OUT+36),0)
        self.assertEqual((self.word(OUT+32),self.word(OUT+36)),(0,65536))
        self.assertEqual(self.call('pthread_attr_setstacksize',OUT,8193),22)
        self.assertEqual(self.call('pthread_attr_setdetachstate',OUT,2),22)
        self.assertEqual(self.call('pthread_attr_setdetachstate',OUT,1),0)
        self.assertEqual(self.call('pthread_attr_destroy',OUT),0)
    def test_normal_static_mutex_busy_and_destroy(self):
        self.assertEqual(self.call('pthread_mutex_lock',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_trylock',OBJECT),16)
        self.assertEqual(self.call('pthread_mutex_destroy',OBJECT),16)
        self.assertEqual(self.call('pthread_mutex_unlock',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_destroy',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_lock',OBJECT),22)
    def test_recursive_and_errorcheck_static_initializers(self):
        self.write(OBJECT,0x4000)
        self.assertEqual(self.call('pthread_mutex_lock',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_lock',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_unlock',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_destroy',OBJECT),16)
        self.assertEqual(self.call('pthread_mutex_unlock',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_destroy',OBJECT),0)
        self.write(OBJECT,0x8000)
        self.assertEqual(self.call('pthread_mutex_lock',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_lock',OBJECT),35)
        self.assertEqual(self.call('pthread_mutex_unlock',OBJECT),0)
        self.assertEqual(self.call('pthread_mutex_destroy',OBJECT),0)
    def test_mutex_attributes_and_process_shared_rejection(self):
        self.assertEqual(self.call('pthread_mutexattr_init',OUT),0)
        self.assertEqual(self.call('pthread_mutexattr_settype',OUT,3),22)
        self.assertEqual(self.call('pthread_mutexattr_setpshared',OUT,1),95)
        self.assertEqual(self.call('pthread_mutexattr_settype',OUT,2),0)
        self.assertEqual(self.call('pthread_mutex_init',OBJECT,OUT),0)
        self.assertEqual(self.call('pthread_mutex_destroy',OBJECT),0)
        self.assertEqual(self.call('pthread_mutexattr_destroy',OUT),0)
    def test_condition_timeout_reacquires_mutex(self):
        self.assertEqual(self.call('pthread_mutex_lock',OBJECT),0)
        self.write(OUT,0); self.write(OUT+4,0)
        self.assertEqual(self.call('pthread_cond_timedwait',OBJECT+4,OBJECT,OUT),110)
        self.assertEqual(self.call('pthread_mutex_trylock',OBJECT),16)
        self.assertEqual(self.call('pthread_mutex_unlock',OBJECT),0)
        self.assertEqual(self.call('pthread_cond_signal',OBJECT+4),0)
        self.assertEqual(self.call('pthread_cond_broadcast',OBJECT+4),0)
        self.assertEqual(self.call('pthread_cond_destroy',OBJECT+4),0)
        self.assertEqual(self.call('pthread_mutex_destroy',OBJECT),0)
    def test_condition_rejects_non_owner(self):
        self.assertEqual(self.call('pthread_mutex_init',OBJECT,0),0)
        self.assertEqual(self.call('pthread_cond_wait',OBJECT+4,OBJECT),1)
        self.assertEqual(self.call('pthread_cond_destroy',OBJECT+4),0)
        self.assertEqual(self.call('pthread_mutex_destroy',OBJECT),0)
    def test_semaphore_counts_error_domains_and_overflow(self):
        self.assertEqual(self.call('sem_init',OBJECT,0,0),0)
        self.assertEqual(self.call('sem_trywait',OBJECT),-1); self.assertEqual(self.error(),11)
        self.assertEqual(self.call('sem_timedwait',OBJECT,OUT),-1); self.assertEqual(self.error(),110)
        self.assertEqual(self.call('sem_post',OBJECT),0)
        self.assertEqual(self.call('sem_getvalue',OBJECT,OUT),0); self.assertEqual(self.word(OUT),1)
        self.assertEqual(self.call('sem_wait',OBJECT),0); self.assertEqual(self.call('sem_destroy',OBJECT),0)
        self.assertEqual(self.call('sem_init',OBJECT,0,0x7fffffff),0)
        self.assertEqual(self.call('sem_post',OBJECT),-1); self.assertEqual(self.error(),75)
        self.assertEqual(self.call('sem_destroy',OBJECT),0)
    def test_semaphore_shared_is_not_silently_accepted(self):
        self.assertEqual(self.call('sem_init',OBJECT,1,0),-1); self.assertEqual(self.error(),95)
    def test_deleted_key_and_reused_slot_have_distinct_generations(self):
        self.assertEqual(self.call('pthread_key_create',OUT,0),0); old=self.word(OUT)
        self.assertEqual(self.call('pthread_setspecific',old,0x1234),0)
        self.assertEqual(self.call('pthread_getspecific',old),0x1234)
        self.assertEqual(self.call('pthread_key_delete',old),0)
        self.assertEqual(self.call('pthread_key_create',OUT,0),0); new=self.word(OUT)
        self.assertNotEqual(old,new); self.assertEqual(self.call('pthread_getspecific',new),0)
        self.assertEqual(self.call('pthread_setspecific',old,1),22)
        self.assertEqual(self.call('pthread_key_delete',new),0)
    def test_tls_errno_provider_isolated_and_allocator_hooks_balanced(self):
        a=self.arm.call('ds_io_errno'); self.write(a,31337)
        self.arm.call('ds7_test_select_tls',1); b=self.arm.call('ds_io_errno'); self.assertNotEqual(a,b); self.write(b,101)
        self.arm.call('ds7_test_select_tls',0); self.assertEqual(self.word(self.arm.call('ds_io_errno')),31337)
        p=self.call('calloc',8,8); self.assertGreater(p,0)
        p=self.call('realloc',p,200); self.call('free',p)
        self.assertEqual(self.arm.call('ds7_test_heap_depth'),0)
    def test_thread_spawn_failure_rolls_back_record(self):
        self.assertEqual(self.call('pthread_create',OUT,0,0x100000,0),11)
        self.arm.call('ds7_stats',OUT)
        self.assertEqual(struct.unpack('<2I',self.arm.uc.mem_read(OUT,8)),(0,0))
    def test_sched_policy_and_stale_identifiers(self):
        self_id=self.call('pthread_self'); self.assertNotEqual(self_id,0)
        self.assertEqual(self.call('pthread_getschedparam',self_id,OUT,OUT+4),0)
        self.assertEqual((self.word(OUT),self.word(OUT+4)),(0,0))
        self.assertEqual(self.call('pthread_setschedparam',self_id,1,OUT+4),95)
        self.assertEqual(self.call('pthread_join',self_id,OUT),35)
        self.assertEqual(self.call('pthread_join',0x12345,OUT),3)
    def test_donor_preflight_145_implemented_243_missing_unchanged(self):
        self.arm.set_file(self.donor); result,info=self.arm.prepare(); self.assertEqual(result,0)
        before=bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size))
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,TABLE,148,OUT),9)
        self.assertEqual(struct.unpack('<5I',self.arm.uc.mem_read(OUT,20)),(392,145,243,4,0))
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size)),before)

if __name__=='__main__':
    start=time.monotonic(); result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ThreadTests))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'elapsed_seconds':round(time.monotonic()-start,3),
            'hardware_tested':False,'backend':'Single-thread boundary model; actual contention/threads tested separately in Azahar','game_engine_started':False}
    (PORTING/'analysis/stage7-thread-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
