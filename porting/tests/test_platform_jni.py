"""Platform profile, scoped JNI references and fixed-display event contracts."""
import hashlib,json,struct,time,unittest
import test_jni10 as jni
from test_jni10 import CTX,TEXT,OUT
class PlatformTests(jni.Jni10Tests):
    def obj(self,name):
        cls=self.find(name);m=self.method(cls,'<init>','()V');return cls,self.env(30,cls,m,0)
    def value(self,handle):
        p=self.env(169,handle,0);self.assertTrue(p);text=self.base.text(p);self.env(170,handle,p);return text
    def stats(self):self.arm.call('ds10_stats',CTX,OUT);return self.base.words(OUT,7)
    def test_system_properties_and_unavailable_capabilities(self):
        cls,obj=self.obj('com/ea/blast/SystemAndroidDelegate')
        for name,expected in {'GetManufacturer':'Nintendo','GetDeviceModel':'New Nintendo 3DS','GetTotalRAM':'67108864','GetAccelerometerCount':'0',
                              'GetGyroscopeCount':'0','GetVirtualKeyboardCount':'0','GetLanguage':'en','GetPlatformStdName':'Android','GetApiLevel':'10'}.items():
            m=self.method(cls,name,'()Ljava/lang/String;');s=self.env(34,obj,m);self.assertEqual(self.value(s),expected);self.delete(s)
        self.assertFalse(self.exception())
    def test_new_object_identity_and_constructor_validation(self):
        cls,a=self.obj('com/ea/blast/SystemAndroidDelegate');m=self.method(cls,'<init>','()V');b=self.env(28,cls,m)
        self.assertNotEqual(a,b);self.assertEqual(self.env(24,a,b),0)
        self.assertEqual(self.env(30,self.find('com/ea/EAIO/EAIO'),m,0),0);self.assertTrue(self.exception())
    def test_frames_release_new_references_and_preserve_outer(self):
        outer=self.find('com/ea/EAIO/EAIO');self.assertEqual(self.env(19,4),0)
        child=self.find('java/io/InputStream');array=self.env(176,64);self.assertEqual(self.env(20,0),0)
        self.assertEqual(self.env(24,outer,outer),1)
        self.assertEqual(self.env(21,child),0);self.clear();self.assertEqual(self.env(171,array),0);self.assertTrue(self.exception())
    def test_nested_escape_and_global_string_lifetime(self):
        self.env(19,8);outer=self.env(176,7);self.env(19,8)
        string=self.make_string('retained');global_=self.env(21,string);escape=self.env(20,string)
        self.assertEqual(self.value(escape),'retained');self.assertEqual(self.env(24,escape,global_),1)
        array=self.env(20,outer);self.assertEqual(self.env(171,array),7)
        self.assertEqual(self.value(global_),'retained');self.delete(global_,True);self.delete(array)
    def test_pop_outer_result_creates_independent_reference(self):
        original=self.make_string('outer');self.env(19,4);escaped=self.env(20,original)
        self.assertNotEqual(escaped,original);self.assertEqual(self.env(24,original,escaped),1)
        self.delete(escaped);self.assertEqual(self.value(original),'outer')
    def test_frame_capacity_depth_underflow_and_reinit(self):
        self.assertEqual(self.env(19,-1),0xffffffff);self.clear()
        for _ in range(16):self.assertEqual(self.env(19,0),0)
        self.assertEqual(self.env(19,0),0xffffffff);self.clear();self.assertEqual(self.arm.call('ds10_init',CTX,0,0),16)
        for _ in range(16):self.assertEqual(self.env(20,0),0)
        self.assertEqual(self.env(20,0),0);self.assertTrue(self.exception());self.clear()
        self.assertEqual(self.env(26,129),0xffffffff)
    def test_frame_repeated_string_allocation_does_not_exhaust_pool(self):
        for _ in range(40):
            self.env(19,4);s=self.make_string('short lived');self.assertTrue(s);self.env(20,0)
        self.assertFalse(self.exception());self.assertEqual(self.stats()[4],0)
    def test_pop_pinned_array_and_string_waits_for_release(self):
        self.env(19,8);a=self.env(176,4);copy=self.env(184,a,0)
        self.assertEqual(self.env(20,0),0);self.assertTrue(self.exception());self.clear()
        self.env(192,a,copy,2);s=self.make_string('pin');chars=self.env(169,s,0)
        self.env(20,0);self.assertTrue(self.exception());self.clear();self.env(170,s,chars)
        self.env(20,0);self.assertFalse(self.exception());self.assertEqual(self.stats()[4],0)
    def test_native_entry_reference_frames_remain_bounded(self):
        for _ in range(150):
            self.env(19,16);self.find('com/eamobile/Query');self.make_string('native argument');self.env(20,0)
        self.assertEqual(self.stats()[4],0);self.assertFalse(self.exception())
    def test_query_boolean_quirk_is_narrow_and_opt_in(self):
        cls=self.find('com/eamobile/Query');m=self.method(cls,'isContentReady','()Z',True)
        self.arm.call('ds11_test_content_ready',1);self.assertEqual(self.env(119,cls,m,0),1)
        self.assertEqual(self.env(116,cls,m,0),0);self.assertTrue(self.exception());self.clear()
        self.arm.call('ds10_query_compat',CTX,1);self.assertEqual(self.env(116,cls,m,0),1);self.assertFalse(self.exception())
        self.arm.call('ds11_test_content_ready',0);self.assertEqual(self.env(116,cls,m,0),0)
        v=self.method(cls,'getVersion','()Ljava/lang/String;',True);self.env(119,cls,v,0);self.assertTrue(self.exception())
    def test_package_version_matches_inspected_apk(self):
        cls=self.find('com/eamobile/Query');m=self.method(cls,'getVersion','()Ljava/lang/String;',True);s=self.env(116,cls,m,0)
        expected=json.loads((jni.cpp.PORTING/'analysis/android-abi/candidate-sd-package.json').read_text())['versionName']
        self.assertEqual(self.value(s),expected)
    def test_display_int_float_and_orientation_state(self):
        cls,o=self.obj('com/ea/blast/DisplayAndroidDelegate')
        for name,n in [('GetDefaultWidth',240),('GetDefaultHeight',400)]:self.assertEqual(self.env(51,o,self.method(cls,name,'()I'),0),n)
        for name in ('GetDpiX','GetDpiY'):self.assertEqual(self.env(57,o,self.method(cls,name,'()F'),0),struct.unpack('<I',struct.pack('<f',96.0))[0])
        setter=self.method(cls,'SetStdOrientation','(I)V');getter=self.method(cls,'GetStdOrientation','()I')
        self.env(63,o,setter,self.values(2));self.assertEqual(self.env(51,o,getter,0),2)
        self.env(63,o,setter,self.values(4));self.assertTrue(self.exception());self.clear();self.assertEqual(self.env(51,o,getter,0),2)
    def test_power_policy_changes_backend_and_restores(self):
        cls,o=self.obj('com/ea/blast/PowerManagerAndroid');m=self.method(cls,'ApplyKeepAwake','(Z)V')
        self.env(63,o,m,self.values(1));self.assertEqual(self.arm.call('ds11_test_keep_awake'),1)
        self.env(63,o,m,self.values(0));self.assertEqual(self.arm.call('ds11_test_keep_awake'),0)
        self.env(63,o,m,self.values(2));self.assertTrue(self.exception());self.assertEqual(self.arm.call('ds11_test_keep_awake'),0)
        self.clear();self.env(63,o,m,self.values(1));self.delete(o);self.delete(cls)
        self.assertEqual(self.arm.call('ds10_init',CTX,0,0),16)
        self.arm.call('ds10_cleanup',CTX);self.assertEqual(self.arm.call('ds11_test_keep_awake'),0)
        self.assertEqual(self.arm.call('ds10_init',CTX,0,0),0)
    def test_orientation_requires_real_capability_before_enable(self):
        cls,o=self.obj('com/ea/blast/DeviceOrientationHandlerAndroidDelegate');m=self.method(cls,'SetEnabled','(Z)V')
        self.arm.call('ds11_orientation_backend',CTX,self.arm.exports['ds11_test_orientation'],1)
        self.env(63,o,m,self.values(1));self.assertTrue(self.exception());self.arm.call('ds11_pump_events',CTX)
        self.assertEqual(self.arm.call('ds11_test_orientation_calls'),0)
    def test_orientation_queue_model_delivers_once_and_cancels(self):
        cls,o=self.obj('com/ea/blast/DeviceOrientationHandlerAndroidDelegate');m=self.method(cls,'SetEnabled','(Z)V')
        self.arm.call('ds11_test_accelerometer',CTX,1);self.arm.call('ds11_orientation_backend',CTX,self.arm.exports['ds11_test_orientation'],1)
        self.env(63,o,m,self.values(1));self.assertEqual(self.arm.call('ds11_test_orientation_calls'),0)
        self.arm.call('ds11_pump_events',CTX);self.assertEqual(self.arm.call('ds11_test_orientation_calls'),1)
        self.env(63,o,m,self.values(1));self.arm.call('ds11_pump_events',CTX);self.assertEqual(self.arm.call('ds11_test_orientation_calls'),1)
        self.env(63,o,m,self.values(0));self.env(63,o,m,self.values(1));self.env(63,o,m,self.values(0));self.arm.call('ds11_pump_events',CTX)
        self.assertEqual(self.arm.call('ds11_test_orientation_calls'),1)
    def test_platform_softfp_fixture_and_cleanup(self):
        blob=(jni.BUILD/'fixture-platform.so').read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',jni.cpp.FILE_ADDR,jni.cpp.INFO_ADDR,jni.cpp.IMAGE_ADDR,0,0,OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_platform',CTX,OUT),0)
        a=self.base.words(OUT,3);self.assertEqual(a[0],0);self.assertEqual(a[2],29);self.assertGreater(a[1],150)
        self.assertEqual(self.stats()[4],0)
if __name__=='__main__':
    start=time.monotonic();names=[n for n in PlatformTests.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(PlatformTests(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'elapsed_seconds':round(time.monotonic()-start,3),
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'hardware_tested':False}
    (jni.cpp.PORTING/'analysis/platform-jni-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
