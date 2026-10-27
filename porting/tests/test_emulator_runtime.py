"""Regression, arena edge cases and actual softfp mmap ABI on the experiment core."""
import ctypes,hashlib,json,struct,time,unittest
import test_stage8_regression as old
import test_stage8_cpp as cpp
BUILD=cpp.PORTING/'3ds/build-emulator'
old.BUILD=old.previous.BUILD=old.previous.old.BUILD=cpp.BUILD=BUILD
ARENA=0x12000000;MAP=ARENA+0x10000
class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.base=cpp.CppTests();self.base.setUp();self.arm=self.base.arm
        self.arm.uc.mem_map(ARENA,0x20000)
        self.assertEqual(self.arm.call('ds9_memory_init',ARENA,0x10000,MAP,0x10000),0)
    def tearDown(self):self.base.tearDown()
    def call(self,name,*args):return self.arm.call(name,*(v&0xffffffff for v in args))
    def error(self):return self.base.words(self.arm.call('ds_io_errno'))[0]
    def stats(self):self.arm.call('ds9_memory_stats',cpp.OUT);return self.base.words(cpp.OUT,8)
    def map(self,size,prot=3,flags=0x22,fd=-1,offset=0,hint=0):return self.call('ds9_mmap',hint,size,prot,flags,fd,offset)
    def test_sbrk_query_growth_shrink_and_old_pointer(self):
        self.assertEqual(self.call('ds9_sbrk',0),ARENA)
        self.assertEqual(self.call('ds9_sbrk',8192),ARENA)
        self.assertEqual(self.call('ds9_sbrk',-4096),ARENA+8192)
        self.assertEqual(self.call('ds9_sbrk',0),ARENA+4096)
        self.assertEqual(self.stats()[:2],(4096,8192))
    def test_sbrk_underflow_and_overflow_preserve_break(self):
        self.call('ds9_sbrk',256)
        for value in (-257,-0x80000000,0x7fffffff,0x10000):
            self.assertEqual(self.call('ds9_sbrk',value),0xffffffff);self.assertEqual(self.error(),12)
            self.assertEqual(self.call('ds9_sbrk',0),ARENA+256)
    def test_sbrk_exact_capacity_and_zero_query_work(self):
        self.assertEqual(self.call('ds9_sbrk',0x10000),ARENA)
        self.assertEqual(self.call('ds9_sbrk',0),ARENA+0x10000)
        self.assertEqual(self.call('ds9_sbrk',1),0xffffffff)
        self.assertEqual(self.call('ds9_sbrk',-0x10000),ARENA+0x10000)
    def test_init_rejects_overlap_unaligned_zero_and_wrapping_ranges(self):
        for args in ((ARENA+1,0x10000,MAP,0x10000),(ARENA,0,MAP,4096),(ARENA,0x10000,ARENA+4096,4096),
                     (ARENA,0x10000,0xfffff000,8192),(ARENA,4096,MAP,128*1024*1024)):
            self.assertEqual(self.call('ds9_memory_init',*args),22)
    def test_init_refuses_live_break_or_mapping(self):
        self.call('ds9_sbrk',1);self.assertEqual(self.call('ds9_memory_init',ARENA,0x10000,MAP,0x10000),16)
        self.call('ds9_sbrk',-1);self.map(1);self.assertEqual(self.call('ds9_memory_init',ARENA,0x10000,MAP,0x10000),16)
        self.call('ds9_munmap',MAP,4096);self.assertEqual(self.call('ds9_memory_init',ARENA,0x10000,MAP,0x10000),0)
    def test_mmap_rounds_to_pages_and_ignores_nonfixed_hint(self):
        self.assertEqual(self.map(1,hint=0x76543210),MAP)
        self.assertEqual(self.map(4097),MAP+4096)
        self.assertEqual(self.stats()[2],3)
    def test_mmap_real_zero_fill_on_first_and_reused_allocation(self):
        self.arm.uc.mem_write(MAP,b'\xaa'*8192);self.assertEqual(self.map(4097),MAP)
        self.assertEqual(bytes(self.arm.uc.mem_read(MAP,8192)),b'\0'*8192)
        self.arm.uc.mem_write(MAP,b'\xbb'*8192);self.call('ds9_munmap',MAP,8192)
        self.assertEqual(self.map(8192),MAP);self.assertEqual(bytes(self.arm.uc.mem_read(MAP,8192)),b'\0'*8192)
    def test_mmap_capacity_and_recovery(self):
        self.assertEqual(self.map(0x10000),MAP);self.assertEqual(self.map(1),0xffffffff);self.assertEqual(self.error(),12)
        self.assertEqual(self.call('ds9_munmap',MAP+4096,4096),0);self.assertEqual(self.map(4096),MAP+4096)
    def test_partial_munmap_preserves_neighbors(self):
        self.map(3*4096);self.arm.uc.mem_write(MAP,b'A');self.arm.uc.mem_write(MAP+8192,b'B')
        self.assertEqual(self.call('ds9_munmap',MAP+4096,4096),0);self.assertEqual(self.map(4096),MAP+4096)
        self.assertEqual(bytes(self.arm.uc.mem_read(MAP,1)),b'A');self.assertEqual(bytes(self.arm.uc.mem_read(MAP+8192,1)),b'B')
    def test_munmap_holes_do_not_underflow_accounting(self):
        self.map(8192);self.call('ds9_munmap',MAP,8192);self.call('ds9_munmap',MAP,12288)
        self.assertEqual(self.stats()[2],0)
    def test_munmap_invalid_range_does_not_release_valid_pages(self):
        self.map(8192)
        for args in ((MAP+1,4096),(MAP-4096,4096),(MAP+0x10000,4096),(MAP,0),(MAP,0xffffffff)):
            self.assertEqual(self.call('ds9_munmap',*args),0xffffffff);self.assertEqual(self.error(),22)
        self.assertEqual(self.stats()[2],2)
    def test_unsupported_mmap_modes_refuse_instead_of_fake_protection(self):
        for kwargs in ({'prot':1},{'prot':0},{'prot':7},{'flags':0x32},{'flags':0x21},{'flags':2},{'fd':3}):
            self.assertEqual(self.map(4096,**kwargs),0xffffffff);self.assertEqual(self.error(),95)
        self.assertEqual(self.stats()[2],0)
    def test_mmap_invalid_size_and_offset(self):
        for size,offset in ((0,0),(0xffffffff,0),(4096,1),(4096,4096)):
            self.assertEqual(self.map(size,offset=offset),0xffffffff);self.assertEqual(self.error(),22)
    def test_real_softfp_module_six_argument_mmap_and_partial_unmap(self):
        blob=(BUILD/'fixture-memory.so').read_bytes();self.base.prepare(blob)
        n=self.arm.call('ds9_memory_bindings',cpp.TABLE+156*8,3);self.assertEqual(n,3)
        self.assertEqual(self.arm.call('ds_elf_resolve',cpp.FILE_ADDR,cpp.INFO_ADDR,cpp.IMAGE_ADDR,cpp.TABLE,159,cpp.OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_memory',cpp.OUT,ARENA),0)
        self.assertEqual(self.base.words(cpp.OUT,2),(0,9));self.assertEqual(self.stats()[0],0);self.assertEqual(self.stats()[2],0)
if __name__=='__main__':
    start=time.monotonic();suite=unittest.TestSuite()
    for case in (old.previous.old.LoaderRegression,old.previous.old.IORegression,old.previous.old.RuntimeRegression,
                 old.previous.LibcRegression,old.ThreadRegression,cpp.CppTests,MemoryTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tested_core':'emulator runtime','tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
        'elapsed_seconds':round(time.monotonic()-start,3),'hardware_tested':False,
        'core_sha256':hashlib.sha256((BUILD/'core-test.elf').read_bytes()).hexdigest()}
    (cpp.PORTING/'analysis/emulator-runtime-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
