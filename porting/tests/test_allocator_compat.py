"""Execute the actual donor allocator to catch duplicate sbrk/mmap ownership."""
import hashlib,json,struct,time,unittest
import test_emulator_runtime as old
from test_arm_loader import IMAGE_ADDR, symbols
class Allocator(old.MemoryTests):
    @classmethod
    def setUpClass(cls):old.cpp.CppTests.setUpClass()
    def setUp(self):
        super().setUp();self.assertEqual(self.arm.prepare()[0],0)
        self.assertEqual(self.call('ds29_allocator_init',IMAGE_ADDR,0x600000),0)
        self.caller=IMAGE_ADDR+0x25343c
    def grow(self,n,caller=None):return self.call('ds29_sbrk',n,self.caller if caller is None else caller)
    def test_only_verified_growth_call_returns_new_break(self):
        self.assertEqual(self.grow(4096),old.ARENA+4096)
        self.assertEqual(self.grow(4096,self.caller-4),old.ARENA+4096)
        self.assertEqual(self.call('ds9_sbrk',4096),old.ARENA+8192)
        self.assertEqual(self.grow(0),old.ARENA+12288)
    def test_shrink_and_failure_keep_original_contract(self):
        self.grow(8192);self.assertEqual(self.grow(-4096),old.ARENA+8192)
        self.assertEqual(self.grow(0x10000),0xffffffff);self.assertEqual(self.error(),12)
        self.assertEqual(self.grow(0),old.ARENA+4096)
    def test_reset_restores_old_break_and_does_not_reclaim_live_bytes(self):
        self.grow(4096);self.call('ds29_allocator_reset')
        self.assertEqual(self.grow(4096),old.ARENA+4096);self.assertEqual(self.stats()[0],8192)
    def test_wrong_donor_instruction_is_rejected_without_mutating_image(self):
        self.call('ds29_allocator_reset');p=IMAGE_ADDR+0x253478
        self.arm.uc.mem_write(p,b'\0'*4);before=bytes(self.arm.uc.mem_read(IMAGE_ADDR,0x600000))
        self.assertEqual(self.call('ds29_allocator_init',IMAGE_ADDR,0x600000),22)
        self.assertEqual(self.grow(4096),old.ARENA)
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR,0x600000)),before)
    def test_invalid_image_ranges_are_refused(self):
        for p,n in ((0,0x600000),(IMAGE_ADDR+1,0x600000),(IMAGE_ADDR,0x253480),(0xffff0000,0x600000)):
            self.assertEqual(self.call('ds29_allocator_init',p,n),22)
    def allocator(self,compat):
        if not compat:self.call('ds29_allocator_reset')
        # Route the genuine PLT through a two-instruction thunk passing LR as
        # caller; malloc internals and all metadata writes remain donor ARM.
        thunk=old.cpp.CODE
        self.base.write(thunk,0xe1a0100e,0xe51ff004,self.arm.exports['ds29_sbrk'])
        _,sections=symbols(self.arm.data);rel=sections['.rel.plt'];sym=sections['.dynsym'];strings=sections['.dynstr']
        for off in range(rel[4],rel[4]+rel[5],8):
            target,entry=struct.unpack_from('<II',self.arm.data,off)
            name=struct.unpack_from('<I',self.arm.data,sym[4]+(entry>>8)*16)[0]+strings[4]
            name=self.arm.data[name:self.arm.data.index(0,name)].decode()
            if name in ('sbrk','mmap'):
                self.base.write(IMAGE_ADDR+target,thunk if name=='sbrk' else self.arm.exports['ds9_mmap'])
        state=old.cpp.OBJECT;sentinel=state+0x448
        self.base.write(state+0x460,sentinel,sentinel);self.base.write(sentinel+24,sentinel,sentinel)
        self.base.write(state+0x4d4,4096,4096,4096)
        self.arm.exports['donor_allocate']=IMAGE_ADDR+0x2533ec
        return self.call('donor_allocate',state,64)
    def test_actual_donor_unadapted_leaks_break_then_maps_second_block(self):
        p=self.allocator(False);self.assertEqual(p,old.MAP+32)
        self.assertEqual(self.stats()[:4],(4096,4096,1,1))
    def test_actual_donor_adapted_uses_single_break_block_and_no_mmap(self):
        p=self.allocator(True);self.assertEqual(p,old.ARENA+32)
        self.assertEqual(self.stats()[:4],(4096,4096,0,0))
        self.assertGreater(self.base.words(p+4)[0]&~7,64)
if __name__=='__main__':
    started=time.monotonic();names=[n for n in Allocator.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Allocator(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((old.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (old.cpp.PORTING/'analysis/allocator-compat-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
