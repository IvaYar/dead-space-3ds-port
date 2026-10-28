"""Read-only font derivative selection through ARM descriptor/stat path mapping."""
import hashlib,json,time,unittest,io
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_PC,UC_ARM_REG_LR
import test_jni10 as jni
SOURCE='sdmc:/3ds/deadspace/assets/published/fonts/Ascender_Uni.ttf'
TARGET='sdmc:/3ds/deadspace/test-output/font-subset/Ascender_Uni.ttf'
class FontProfile(jni.Jni10Tests):
    def setUp(self):
        super().setUp();self.arm.call('ds6_init',0)
        self.assertEqual(self.arm.call('ds_io_read_override',self.arm.exports['ds28_font_path']),0)
        self.open_paths=[];self.arm.uc.hook_del(self.io.hook)
        def backend(uc,address,size,user):
            if address==jni.old_io.HOOK:
                path=self.io.cstring(uc.reg_read(UC_ARM_REG_R0));self.open_paths.append(path)
                if path==TARGET:
                    self.io.calls.append(0);handle=self.io.next_handle;self.io.next_handle+=4;self.io.files[handle]=io.BytesIO(b'font-probe')
                    uc.reg_write(UC_ARM_REG_R0,handle);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
            self.io.host_call(uc,address,size,user)
        self.io.hook=self.arm.uc.hook_add(UC_HOOK_CODE,backend,begin=jni.old_io.HOOK,end=jni.old_io.HOOK+15)
    def tearDown(self):self.arm.call('ds6_cleanup');super().tearDown()
    def mapped(self,p,writable=0):
        result=self.arm.call('ds6_map_path',self.text(jni.TEXT,p),jni.OUT,writable)
        return result,self.io.cstring(jni.OUT)
    def test_external_and_bundle_aliases_select_the_same_derived_font(self):
        for p in ('published/fonts/Ascender_Uni.ttf','appbundle:/published/fonts/Ascender_Uni.ttf',
                  '/sdcard/Android/data/com.ea.deadspace/files/ea/deadspace/published/fonts/Ascender_Uni.ttf'):
            self.assertEqual(self.mapped(p),(0,TARGET))
    def test_other_fonts_and_same_suffix_are_not_overridden(self):
        for p in ('fonts/RussellSquare.ttf','fonts/Ascender_Uni.ttf.bak','other/Ascender_Uni.ttf'):
            self.assertEqual(self.mapped('published/'+p),(0,'sdmc:/3ds/deadspace/assets/published/'+p))
    def test_appdata_font_name_stays_in_private_namespace(self):
        self.assertEqual(self.mapped('appdata:/fonts/Ascender_Uni.ttf'),(0,'sdmc:/3ds/deadspace/test-output/fonts/Ascender_Uni.ttf'))
    def test_write_requests_remain_readonly(self):
        self.assertEqual(self.mapped('published/fonts/Ascender_Uni.ttf',1)[0],0xffffffff)
        self.assertEqual(self.io.open('published/fonts/Ascender_Uni.ttf',1),-1)
        self.assertEqual(self.io.calls,[])
    def test_descriptor_open_uses_the_derived_path_and_real_close(self):
        fd=self.io.open('published/fonts/Ascender_Uni.ttf');self.assertGreaterEqual(fd,1024)
        self.assertEqual(self.open_paths,[TARGET]);self.assertEqual(self.arm.call('ds_io_read',fd,jni.OUT,10),10)
        self.assertEqual(bytes(self.arm.uc.mem_read(jni.OUT,10)),b'font-probe');self.assertEqual(self.arm.call('ds_io_close',fd),0)
    def test_override_cannot_change_while_any_descriptor_is_live(self):
        fd=self.io.open();self.assertEqual(self.arm.call('ds_io_read_override',0),0xffffffff)
        self.assertEqual(self.mapped('published/fonts/Ascender_Uni.ttf'),(0,TARGET))
        self.arm.call('ds_io_close',fd);self.assertEqual(self.arm.call('ds_io_read_override',0),0)
        self.assertEqual(self.mapped('published/fonts/Ascender_Uni.ttf'),(0,SOURCE))
    def test_small_output_capacity_refuses_without_rewriting_original(self):
        self.text(jni.TEXT,SOURCE);self.assertEqual(self.arm.call('ds28_font_path',jni.TEXT,8),36)
        self.assertEqual(self.io.cstring(jni.TEXT),SOURCE)
    def test_path_traversal_is_rejected_before_override(self):
        self.assertEqual(self.mapped('published/fonts/../fonts/Ascender_Uni.ttf')[0],0xffffffff)
if __name__=='__main__':
    started=time.monotonic();names=[n for n in FontProfile.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(FontProfile(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (jni.cpp.PORTING/'analysis/font-profile-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
