"""Shared ARM brk/mmap ownership; legacy disjoint allocator stays a separate mode."""
import hashlib,json,time,unittest
import test_emulator_runtime as old
class Shared(old.MemoryTests):
    @classmethod
    def setUpClass(cls):old.cpp.CppTests.setUpClass()
    def setUp(self):
        super().setUp();self.assertEqual(self.call('ds9_memory_init_shared',old.ARENA,0x20000),0)
    def test_brk_grows_from_bottom_and_maps_from_top(self):
        self.assertEqual(self.call('ds9_sbrk',4096),old.ARENA)
        self.assertEqual(self.map(4096),old.ARENA+0x1f000)
        self.assertEqual(self.map(8192),old.ARENA+0x1d000)
        self.assertEqual(self.stats()[:4],(4096,4096,3,3))
    def test_map_cannot_overwrite_partial_break_page(self):
        self.call('ds9_sbrk',1);self.assertEqual(self.map(0x20000),0xffffffff)
        self.assertEqual(self.map(0x1f000),old.ARENA+4096);self.assertEqual(self.map(1),0xffffffff)
    def test_break_cannot_cross_live_mapping_even_with_free_bytes_above_it(self):
        a=self.map(8192);self.call('ds9_munmap',a+4096,4096)
        self.assertEqual(self.call('ds9_sbrk',0x1e000),old.ARENA)
        self.assertEqual(self.call('ds9_sbrk',1),0xffffffff);self.assertEqual(self.error(),12)
        self.assertEqual(self.call('ds9_sbrk',0),old.ARENA+0x1e000)
        self.call('ds9_munmap',a,4096);self.assertEqual(self.call('ds9_sbrk',8192),old.ARENA+0x1e000)
    def test_map_can_use_freed_break_pages(self):
        self.call('ds9_sbrk',0x20000);self.assertEqual(self.map(1),0xffffffff)
        self.call('ds9_sbrk',-8192);self.assertEqual(self.map(8192),old.ARENA+0x1e000)
    def test_break_can_use_freed_map_pages(self):
        a=self.map(0x20000);self.assertEqual(a,old.ARENA);self.assertEqual(self.call('ds9_sbrk',1),0xffffffff)
        self.call('ds9_munmap',a,8192);self.assertEqual(self.call('ds9_sbrk',8192),a)
    def test_munmap_rejects_break_region_and_preserves_map(self):
        self.call('ds9_sbrk',4097);a=self.map(4096)
        for address in (old.ARENA,old.ARENA+4096):self.assertEqual(self.call('ds9_munmap',address,4096),0xffffffff)
        self.assertEqual(self.stats()[2],1);self.assertEqual(self.call('ds9_munmap',a,4096),0)
    def test_partial_map_free_and_top_down_hole_reuse(self):
        a=self.map(12288);self.arm.uc.mem_write(a,b'A');self.arm.uc.mem_write(a+8192,b'B')
        self.call('ds9_munmap',a+4096,4096);self.assertEqual(self.map(4096),a+4096)
        self.assertEqual(bytes(self.arm.uc.mem_read(a,1)),b'A');self.assertEqual(bytes(self.arm.uc.mem_read(a+8192,1)),b'B')
    def test_reused_pages_are_zeroed_without_touching_break(self):
        self.call('ds9_sbrk',4096);self.arm.uc.mem_write(old.ARENA,b'H'*4096)
        a=self.map(4096);self.arm.uc.mem_write(a,b'M'*4096);self.call('ds9_munmap',a,4096)
        self.assertEqual(self.map(4096),a);self.assertEqual(bytes(self.arm.uc.mem_read(a,4096)),b'\0'*4096)
        self.assertEqual(bytes(self.arm.uc.mem_read(old.ARENA,4096)),b'H'*4096)
    def test_invalid_shared_ranges_are_atomic(self):
        for address,size in ((0,4096),(old.ARENA+1,4096),(old.ARENA,0),(old.ARENA,4097),(0xfffff000,8192),(old.ARENA,129*1024*1024)):
            self.assertEqual(self.call('ds9_memory_init_shared',address,size),22)
        self.assertEqual(self.call('ds9_sbrk',0),old.ARENA)
    def test_shared_and_legacy_reinit_refuse_live_owners(self):
        self.call('ds9_sbrk',1)
        self.assertEqual(self.call('ds9_memory_init_shared',old.ARENA,0x20000),16)
        self.assertEqual(self.call('ds9_memory_init',old.ARENA,0x10000,old.MAP,0x10000),16)
        self.call('ds9_sbrk',-1);a=self.map(4096)
        self.assertEqual(self.call('ds9_memory_init_shared',old.ARENA,0x20000),16);self.call('ds9_munmap',a,4096)
        self.assertEqual(self.call('ds9_memory_init',old.ARENA,0x10000,old.MAP,0x10000),0);self.assertEqual(self.map(4096),old.MAP)
    def test_no_overcommit_and_failed_request_preserves_data(self):
        self.call('ds9_sbrk',0x10000);self.arm.uc.mem_write(old.ARENA,b'H')
        a=self.map(0x10000);self.arm.uc.mem_write(a,b'M');before=self.stats()[:4]
        self.assertEqual(self.map(1),0xffffffff);self.assertEqual(self.call('ds9_sbrk',1),0xffffffff)
        self.assertEqual(self.stats()[:4],before);self.assertEqual(bytes(self.arm.uc.mem_read(old.ARENA,1)),b'H');self.assertEqual(bytes(self.arm.uc.mem_read(a,1)),b'M')
    def test_unsupported_mapping_protections_remain_refused(self):
        for kw in ({'prot':7},{'flags':0x32},{'fd':1},{'offset':4096}):self.assertEqual(self.map(4096,**kw),0xffffffff)
        self.assertEqual(self.stats()[2],0)
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Shared.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Shared(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((old.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (old.cpp.PORTING/'analysis/shared-memory-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
