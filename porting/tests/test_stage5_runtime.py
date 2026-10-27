"""Execute actual newlib ARM code and Android ABI bridges under Unicorn."""
import ctypes
import json
import math
import random
import struct
import time
import unittest
from test_arm_loader import ARMCore, PORTING, FILE_ADDR, INFO_ADDR, IMAGE_ADDR, symbols
from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC

CTX=0x06000000
OPS=CTX+0x100
BINDINGS=CTX+0x1000
OUT=CTX+0x3000
TEXT=CTX+0x4000


class RuntimeTests(unittest.TestCase):
    results={}

    @classmethod
    def setUpClass(cls):
        cls.donor=(PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.fixture=(PORTING/'3ds/build-stage5/fixture-stage5.so').read_bytes()
        cls.arm=ARMCore(cls.donor,PORTING/'3ds/build-stage5/core-test.elf')
        cls.arm.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000)
        cls.arm.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        cls.arm.uc.mem_map(CTX,0x10000)
        cls.exports,_=symbols(cls.fixture)

    def setUp(self):
        self.arm.call('ds_runtime_cleanup')
        self.assertEqual(self.arm.call('ds_runtime_init',1048576),0)
        self.arm.uc.mem_write(OPS,b'\0'*16)
        self.arm.call('ds_io_init',CTX,OPS)

    def tearDown(self):
        self.arm.call('ds_runtime_cleanup'); self.arm.call('ds_io_shutdown',CTX)

    def word(self,address): return struct.unpack('<I',self.arm.uc.mem_read(address,4))[0]
    def store(self,address,value): self.arm.uc.mem_write(address,struct.pack('<I',value))
    def stats(self):
        self.arm.call('ds_runtime_stats',OUT+0x800)
        return struct.unpack('<9I',self.arm.uc.mem_read(OUT+0x800,36))
    def string(self,address,text): self.arm.uc.mem_write(address,text+b'\0')
    def cstring(self,address):
        data=bytes(self.arm.uc.mem_read(address,256)); return data[:data.index(0)]
    def call_binding(self,name,*args):
        self.assertEqual(self.arm.call('ds_runtime_bindings',BINDINGS,64),48)
        for i in range(48):
            ptr,fn=struct.unpack('<II',self.arm.uc.mem_read(BINDINGS+i*8,8))
            if self.cstring(ptr)==name.encode():
                self.arm.exports['__call']=fn
                return self.arm.call('__call',*args)
        self.fail(name)

    def test_all_53_bindings_are_unique_and_fixture_imports_bind(self):
        self.assertEqual(self.arm.call('ds_platform_bindings',BINDINGS,64),53)
        names=[]
        for i in range(53):
            ptr,fn=struct.unpack('<II',self.arm.uc.mem_read(BINDINGS+i*8,8))
            names.append(self.cstring(ptr)); self.assertNotEqual(fn,0)
        self.assertEqual(len(set(names)),53)
        self.arm.set_file(self.fixture); self.assertEqual(self.arm.prepare()[0],0)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,BINDINGS,53,OUT),0)
        self.assertEqual(struct.unpack('<5I',self.arm.uc.mem_read(OUT,20))[:4],(49,49,0,0))

    def test_small_binding_buffer_is_untouched(self):
        self.arm.uc.mem_write(BINDINGS,b'Z'*512)
        self.assertEqual(self.arm.call('ds_platform_bindings',BINDINGS,52),0)
        self.assertEqual(bytes(self.arm.uc.mem_read(BINDINGS,512)),b'Z'*512)

    def test_malloc_alignment_calloc_zero_and_free(self):
        for n in (0,1,7,8,9,1000,65537):
            p=self.arm.call('ds_rt_calloc',1,n); self.assertNotEqual(p,0); self.assertEqual(p&7,0)
            self.assertEqual(bytes(self.arm.uc.mem_read(p,n)),b'\0'*n)
            self.arm.call('ds_rt_free',p)
        self.assertEqual(self.stats()[4:6],(0,0))

    def test_calloc_integer_overflow_is_rejected(self):
        self.assertEqual(self.arm.call('ds_rt_calloc',0x80000000,2),0)
        self.assertEqual(self.word(CTX+48),12); self.assertEqual(self.stats()[4:6],(0,0))

    def test_realloc_failure_preserves_pointer_data_and_stats(self):
        p=self.arm.call('ds_rt_malloc',17); self.arm.uc.mem_write(p,b'Z'*17)
        self.assertEqual(self.arm.call('ds_rt_realloc',p,0xffffffff),0)
        self.assertEqual(bytes(self.arm.uc.mem_read(p,17)),b'Z'*17)
        self.assertEqual(self.stats()[4:6],(1,17)); self.assertEqual(self.word(CTX+48),12)
        self.arm.call('ds_rt_free',p)

    def test_limit_is_cumulative_and_recovers_after_free(self):
        self.assertEqual(self.arm.call('ds_runtime_init',64),0)
        p=self.arm.call('ds_rt_malloc',48)
        self.assertEqual(self.arm.call('ds_rt_malloc',17),0)
        self.arm.call('ds_rt_free',p)
        q=self.arm.call('ds_rt_malloc',64); self.assertNotEqual(q,0)
        self.arm.call('ds_rt_free',q)

    def test_init_refuses_to_discard_outstanding_allocations(self):
        p=self.arm.call('ds_rt_malloc',12)
        self.assertEqual(ctypes.c_int32(self.arm.call('ds_runtime_init',10)).value,-1)
        self.assertEqual(self.stats()[4:6],(1,12)); self.arm.call('ds_rt_free',p)

    def test_realloc_null_and_zero(self):
        p=self.arm.call('ds_rt_realloc',0,64); self.assertNotEqual(p,0)
        self.assertEqual(self.arm.call('ds_rt_realloc',p,0),0); self.assertEqual(self.stats()[4:6],(0,0))
        self.arm.call('ds_rt_free',0); self.assertEqual(self.stats()[8],0)

    def test_cleanup_releases_and_counts_unclosed_blocks(self):
        for n in (8,16,24): self.assertNotEqual(self.arm.call('ds_rt_malloc',n),0)
        self.assertEqual(self.arm.call('ds_runtime_cleanup'),3); self.assertEqual(self.stats()[4:6],(0,0))

    def test_invalid_and_double_free_do_not_reach_allocator(self):
        p=self.arm.call('ds_rt_malloc',12); self.arm.call('ds_rt_free',p+1)
        self.assertEqual(self.stats()[4:6],(1,12)); self.assertEqual(self.stats()[8],1)
        self.arm.call('ds_rt_free',p); self.arm.call('ds_rt_free',p)
        self.assertEqual(self.stats()[4:6],(0,0)); self.assertEqual(self.stats()[8],2)

    def test_resize_many_blocks_preserves_data_and_links(self):
        rng=random.Random(7421); active={}
        for _ in range(200):
            if not active or rng.randrange(3)==0:
                n=rng.randrange(1,8193); p=self.arm.call('ds_rt_malloc',n); self.assertNotEqual(p,0)
                value=rng.randrange(256); self.arm.uc.mem_write(p,bytes([value])*n); active[p]=(n,value)
            else:
                p=rng.choice(list(active)); n,value=active.pop(p)
                self.assertEqual(bytes(self.arm.uc.mem_read(p,n)),bytes([value])*n)
                if rng.randrange(2):
                    size=rng.randrange(1,16385); q=self.arm.call('ds_rt_realloc',p,size); self.assertNotEqual(q,0)
                    self.assertEqual(bytes(self.arm.uc.mem_read(q,min(n,size))),bytes([value])*min(n,size))
                    self.arm.uc.mem_write(q,bytes([value])*size); active[q]=(size,value)
                else: self.arm.call('ds_rt_free',p)
            self.assertEqual(self.stats()[4:6],(len(active),sum(n for n,v in active.values())))
        for p in active: self.arm.call('ds_rt_free',p)
        self.assertEqual(self.stats()[4:6],(0,0))

    def test_string_unsigned_comparison_padding_and_missing_search(self):
        self.string(TEXT,b'\xff'); self.string(TEXT+32,b'\x01')
        result=self.call_binding('strcmp',TEXT,TEXT+32); self.assertGreater(ctypes.c_int32(result).value,0)
        self.assertEqual(self.call_binding('strchr',TEXT,0),TEXT+1)
        self.assertEqual(self.call_binding('strstr',TEXT,TEXT+32),0)
        self.arm.uc.mem_write(TEXT+64,b'Z'*16); self.string(TEXT,b'abc')
        self.assertEqual(self.call_binding('strncpy',TEXT+64,TEXT,8),TEXT+64)
        self.assertEqual(bytes(self.arm.uc.mem_read(TEXT+64,9)),b'abc\0\0\0\0\0Z')

    def fixture_probe(self,name):
        self.arm.set_file(self.fixture); self.assertEqual(self.arm.prepare()[0],0)
        self.assertEqual(self.arm.call('ds_platform_bindings',BINDINGS,64),53)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,BINDINGS,53,OUT+0x100),0)
        self.arm.exports['__probe']=IMAGE_ADDR+self.exports[name]
        return self.arm.call('__probe',OUT),struct.unpack('<8I',self.arm.uc.mem_read(OUT,32))

    def test_softfp_memory_probe_and_constructor_not_called(self):
        result,out=self.fixture_probe('probe_memory')
        self.assertEqual(result,0); self.assertEqual(out[:4],(0,42,12,12))
        self.assertEqual(self.stats()[4:6],(0,0)); self.assertEqual(self.stats()[7:9],(2,0))
        self.results['memory_string_probe']='MATCH'; self.results['constructor_marker']=42

    def test_all_30_math_functions_through_softfp_module(self):
        result,out=self.fixture_probe('probe_math')
        self.assertEqual(result,0); self.assertEqual(out[:4],(0,35,33,34))
        self.results['softfp_math_checks']=35; self.results['math_errno']=[33,34]

    def test_real_math_wrapper_returns_double_in_integer_registers(self):
        words=struct.unpack('<2I',struct.pack('<d',2.25))
        lo=self.arm.call('ds_rt_sqrt',*words); hi=self.arm.uc.reg_read(UC_ARM_REG_R1)
        self.assertEqual(struct.unpack('<d',struct.pack('<II',lo,hi))[0],1.5)

    def test_successful_math_preserves_both_errno_domains(self):
        host_errno=self.arm.call('__errno'); self.store(host_errno,22); self.store(CTX+48,30)
        self.arm.call('ds_rt_sqrt',*struct.unpack('<2I',struct.pack('<d',2.25)))
        self.assertEqual(self.word(host_errno),22); self.assertEqual(self.word(CTX+48),30)

    def test_nan_and_infinity_are_not_confused(self):
        for value,expected in ((math.nan,0),(math.inf,1),(-math.inf,1),(1.0,0)):
            self.assertEqual(self.arm.call('ds_rt_isinf',*struct.unpack('<2I',struct.pack('<d',value))),expected)

    def test_donor_preflight_53_resolved_335_missing_image_unchanged(self):
        self.arm.set_file(self.donor); result,info=self.arm.prepare(); self.assertEqual(result,0)
        before=bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size))
        self.assertEqual(self.arm.call('ds_platform_bindings',BINDINGS,64),53)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,BINDINGS,53,OUT),9)
        self.assertEqual(struct.unpack('<5I',self.arm.uc.mem_read(OUT,20)),(392,53,335,4,0))
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size)),before)
        self.results['donor_preflight']={'resolved':53,'missing':335,'weak_zero':4,'patched_sites':0,'image_unchanged':True}


if __name__=='__main__':
    started=time.monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeTests))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
            'elapsed_seconds':round(time.monotonic()-started,3),'hardware_tested':False,
            'actual_newlib_allocator_and_libm':True,'test_only_heap_size':2097152,'test_only_single_thread_lock_stubs':True,
            'game_engine_started':False,**RuntimeTests.results}
    (PORTING/'analysis/stage5-runtime-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
