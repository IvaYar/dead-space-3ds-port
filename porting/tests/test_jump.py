"""Android ARM setjmp: real nonlocal return, core/VFP and rejection paths."""
import hashlib,json,struct,time,unittest
import test_jni10 as jni
from test_arm_loader import FILE_ADDR,INFO_ADDR,IMAGE_ADDR,STOP_ADDR
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_PC,UC_ARM_REG_SP
TABLE=0x06004000;OUT=0x06009000;ENV=0x0600b004
class JumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):jni.cpp.CppTests.setUpClass()
    def setUp(self):
        self.base=jni.cpp.CppTests();self.base.setUp();self.arm=self.base.arm;self.arm.call('ds17_reset_stats')
        self.assertEqual(self.arm.call('ds17_bindings',TABLE,4),4)
    def tearDown(self):self.base.tearDown()
    def fixture(self,thumb=False):
        blob=(jni.BUILD/('fixture-jump-thumb.so' if thumb else 'fixture-jump.so')).read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,TABLE,4,OUT),0);return blob
    def invoke(self,blob,name,*args):return self.base.invoke(blob,name,OUT,*(v&0xffffffff for v in args))
    def stats(self):self.arm.call('ds17_stats',OUT+256);return self.base.words(OUT+256,3)
    def test_arm_deep_return_positive_zero_and_negative(self):
        blob=self.fixture()
        for value in (41,0,-17):
            self.assertEqual(self.invoke(blob,'probe_jump',value),0);self.assertEqual(self.base.words(OUT,2),((value if value else 1)&0xffffffff,17))
        self.assertEqual(self.stats(),(3,3,0))
    def test_thumb_deep_return_and_interworking(self):
        blob=self.fixture(True)
        for value in (29,0,-31):
            self.assertEqual(self.invoke(blob,'probe_jump',value),0);self.assertEqual(self.base.words(OUT,2),((value if value else 1)&0xffffffff,17))
    def test_nested_independent_contexts_arm_and_thumb(self):
        for thumb in (False,True):
            self.assertEqual(self.invoke(self.fixture(thumb),'probe_jump_nested'),0);self.assertEqual(self.base.words(OUT,2),(11,2))
        self.assertEqual(self.stats(),(4,4,0))
    def test_underscore_pair_does_real_jump(self):
        for thumb in (False,True):
            blob=self.fixture(thumb)
            for value in (0,19,-7):
                self.assertEqual(self.invoke(blob,'probe_jump_underscore',value),0);self.assertEqual(self.base.words(OUT,2),((value if value else 1)&0xffffffff,23))
    def test_all_core_vfp_fpscr_and_four_aligned_sp_buffer(self):
        self.assertEqual(self.invoke(self.fixture(),'probe_jump_registers'),0)
        values=self.base.words(OUT,31);self.assertEqual(values[0],37)
        self.assertEqual(values[1:9],tuple(0x11111111*i for i in range(4,12)));self.assertEqual(values[9],values[30])
        self.assertEqual(values[10],0x00400000);self.assertEqual(values[11]&7,4)
        self.assertEqual(values[12:28],tuple(v for i in range(8,16) for v in (0x11110000+i,0xaaaa0000+i)))
        self.assertEqual(values[28:30],(0xdeadbeef,0xdeadbeef))
    def save(self,underscore=False):
        self.arm.uc.mem_write(ENV-4,b'Z'*264);self.assertEqual(self.arm.call('ds17__setjmp' if underscore else 'ds17_setjmp',ENV),0)
        return self.base.words(ENV,64)
    def test_layout_magic_core_offsets_owner_and_reserved_canaries(self):
        words=self.save();self.assertEqual(words[0:2],(0x4278f501,0));self.assertEqual(words[31],0x44533137)
        self.assertEqual(words[29],STOP_ADDR);self.assertTrue(words[28]);self.assertEqual(words[32:],(0x5a5a5a5a,)*32)
        self.assertEqual(bytes(self.arm.uc.mem_read(ENV-4,4)),b'ZZZZ');self.assertEqual(bytes(self.arm.uc.mem_read(ENV+256,4)),b'ZZZZ')
    def test_wrong_magic_kind_and_unowned_buffers_reject(self):
        self.save();self.assertEqual(self.arm.call('ds17_validate',ENV,0),2)
        self.base.write(ENV,0);self.assertEqual(self.arm.call('ds17_validate',ENV,1),2)
        self.save();self.base.write(ENV+31*4,0);self.assertEqual(self.arm.call('ds17_validate',ENV,1),2)
    def test_cross_thread_owner_rejects_and_original_thread_accepts(self):
        self.save();self.arm.call('ds7_test_select_tls',1);self.assertEqual(self.arm.call('ds17_validate',ENV,1),3)
        self.arm.call('ds7_test_select_tls',0);self.assertEqual(self.arm.call('ds17_validate',ENV,1),0)
    def test_nonempty_signal_mask_refuses_and_underscore_ignores_it(self):
        self.save();self.base.write(ENV+4,1);self.assertEqual(self.arm.call('ds17_validate',ENV,1),4)
        self.save(True);self.base.write(ENV+4,1);self.assertEqual(self.arm.call('ds17_validate',ENV,0),0)
    def test_null_unaligned_and_malformed_sp_lr_refuse(self):
        self.assertEqual(self.arm.call('ds17_validate',0,1),1);self.assertEqual(self.arm.call('ds17_validate',ENV+1,1),1)
        for word,value in ((28,0),(28,3),(29,0),(29,2)):
            self.save();self.base.write(ENV+word*4,value);self.assertEqual(self.arm.call('ds17_validate',ENV,1),5)
    def test_invalid_longjmp_takes_fatal_path_before_restoring_registers(self):
        self.save();self.base.write(ENV,0);seen=[]
        def stop(uc,address,size,data):seen.append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_SP)&7));uc.reg_write(UC_ARM_REG_PC,STOP_ADDR);uc.emu_stop()
        def unalign(uc,address,size,data):uc.reg_write(UC_ARM_REG_SP,uc.reg_read(UC_ARM_REG_SP)-4)
        pc=self.arm.exports['ds17_bad_jump'];hook=self.arm.uc.hook_add(UC_HOOK_CODE,stop,begin=pc,end=pc)
        entry=self.arm.exports['ds17_longjmp'];align_hook=self.arm.uc.hook_add(UC_HOOK_CODE,unalign,begin=entry,end=entry)
        try:self.arm.call('ds17_longjmp',ENV,42)
        finally:self.arm.uc.hook_del(hook)
        self.arm.uc.hook_del(align_hook)
        self.assertEqual(seen,[(2,0)]);self.assertEqual(self.stats(),(1,0,1))
    def test_registry_capacity_is_atomic(self):
        self.arm.uc.mem_write(OUT,b'Z'*32);self.assertEqual(self.arm.call('ds17_bindings',OUT,3),0);self.assertEqual(bytes(self.arm.uc.mem_read(OUT,32)),b'Z'*32)
    def test_export_metadata_passes_strict_loader_arm_and_thumb(self):
        for thumb in (False,True):
            self.fixture(thumb)
            for name in ('probe_jump','probe_jump_nested','probe_jump_underscore','probe_jump_registers'):
                self.arm.uc.mem_write(OUT+512,name.encode()+b'\0')
                self.assertEqual(self.arm.call('ds_elf_find_export',FILE_ADDR,INFO_ADDR,OUT+512,OUT,OUT+4),0)
if __name__=='__main__':
    started=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(JumpTests))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),
        'fixtures_sha256':{n:hashlib.sha256((jni.BUILD/n).read_bytes()).hexdigest() for n in ('fixture-jump.so','fixture-jump-thumb.so')},'elapsed_seconds':round(time.monotonic()-started,3)}
    (jni.cpp.PORTING/'analysis/jump-tests.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
