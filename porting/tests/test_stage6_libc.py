"""Run Bionic numeric/format/data adapters as ARM code, without host OS calls."""
import ast
import ctypes
import datetime
import json
import re
import struct
import time
import unittest
from test_arm_loader import ARMCore,PORTING,FILE_ADDR,INFO_ADDR,IMAGE_ADDR,symbols
from unicorn.arm_const import UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC,UC_ARM_REG_R1

CTX=0x06000000; OPS=CTX+0x100; TABLE=CTX+0x1000; OUT=CTX+0x3000; TEXT=CTX+0x5000

class LibcTests(unittest.TestCase):
    results={}
    @classmethod
    def setUpClass(cls):
        cls.donor=(PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.fixture=(PORTING/'3ds/build-stage6/fixture-stage6.so').read_bytes()
        cls.arm=ARMCore(cls.donor,PORTING/'3ds/build-stage6/core-test.elf')
        cls.arm.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000); cls.arm.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        cls.arm.uc.mem_map(CTX,0x10000); cls.exports,_=symbols(cls.fixture)
    def setUp(self):
        self.assertEqual(self.arm.call('ds_runtime_init',1048576),0)
        self.arm.uc.mem_write(OPS,b'\0'*16); self.arm.call('ds_io_init',CTX,OPS)
        self.arm.call('ds6_basics_init',0)
        self.assertEqual(self.arm.call('ds6_bindings',TABLE,128),108)
        self.bindings={}
        for i in range(108):
            name,ptr=struct.unpack('<II',self.arm.uc.mem_read(TABLE+i*8,8)); self.bindings[self.cstring(name).decode()]=ptr
    def tearDown(self):
        self.arm.call('ds6_basics_cleanup')
        self.assertEqual(self.arm.call('ds_runtime_cleanup'),0,'Probe leaked a tracked allocation')
        self.arm.call('ds_io_shutdown',CTX)
        self.assertEqual(self.arm.call('ds6_test_unexpected_os_calls'),0)
    def word(self,p): return struct.unpack('<I',self.arm.uc.mem_read(p,4))[0]
    def text(self,p,t): self.arm.uc.mem_write(p,t.encode()+b'\0')
    def cstring(self,p):
        a=bytearray()
        while (b:=bytes(self.arm.uc.mem_read(p+len(a),1)))!=b'\0': a+=b
        return bytes(a)
    def invoke(self,name,*args):
        self.arm.exports['_binding']=self.bindings[name]
        return self.arm.call('_binding',*(x&0xffffffff for x in args))
    def error(self): return self.word(CTX+48)
    def test_all_108_bindings_and_57_fixture_imports(self):
        self.assertEqual(len(self.bindings),108)
        self.arm.set_file(self.fixture); self.assertEqual(self.arm.prepare()[0],0)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,TABLE,108,OUT),0)
        self.assertEqual(struct.unpack('<5I',self.arm.uc.mem_read(OUT,20))[:4],(57,57,0,0))
    def test_original_softfp_module_basics(self):
        self.arm.set_file(self.fixture); self.assertEqual(self.arm.prepare()[0],0)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,TABLE,108,OUT+256),0)
        self.arm.exports['probe']=IMAGE_ADDR+self.exports['probe_basics']
        self.assertEqual(self.arm.call('probe',OUT),0)
        self.assertEqual(struct.unpack('<3I',self.arm.uc.mem_read(OUT,12)),(0,31,42))
        self.results['softfp_basics_checks']=31
    def test_all_257_character_classes_match_aosp(self):
        source=(PORTING/'analysis/android-abi/libc_stdlib_ctype_.c').read_text()
        body=re.search(r'_C_ctype_\[[^]]+\]\s*=\s*\{(.*?)\};',source,re.S)[1]
        body=re.sub(r'/\*.*?\*/','',body,flags=re.S).replace('(char)','')
        flags={'_U':1,'_L':2,'_N':4,'_S':8,'_P':16,'_C':32,'_X':64,'_B':128,'0':0}
        expected=[]
        for token in body.split(','):
            if token.strip():
                value=0
                for part in token.strip().split('|'): value|=flags[part.strip()]
                expected.append(value)
        pointer=self.word(self.bindings['_ctype_'])
        self.assertEqual(bytes(self.arm.uc.mem_read(pointer,257)),bytes(expected))
    def test_all_257_case_mappings_match_aosp(self):
        for suffix,name in (('tolower','_tolower_tab_'),('toupper','_toupper_tab_')):
            source=(PORTING/f'analysis/android-abi/libc_stdlib_{suffix}_.c').read_text()
            body=re.search(r'_C_'+suffix+r'_\[[^]]+\]\s*=\s*\{(.*?)\};',source,re.S)[1]
            body=re.sub(r'/\*.*?\*/','',body,flags=re.S)
            expected=[]
            for token in body.split(','):
                token=token.strip()
                if token:
                    value=-1 if token=='EOF' else ord(ast.literal_eval(token)) if token.startswith("'") else int(token,0)
                    expected.append(value&0xffff)
            self.assertEqual(len(expected),257)
            pointer=self.word(self.bindings[name]); actual=struct.unpack('<257H',self.arm.uc.mem_read(pointer,514))
            self.assertEqual(actual,tuple(expected))
    def test_strtod_double_return_and_end_pointer(self):
        self.text(TEXT,'-1.25x'); lo=self.invoke('strtod',TEXT,OUT); hi=self.arm.uc.reg_read(UC_ARM_REG_R1)
        self.assertEqual(struct.unpack('<d',struct.pack('<II',lo,hi))[0],-1.25); self.assertEqual(self.word(OUT),TEXT+5)
    def test_numeric_range_and_invalid_base(self):
        self.text(TEXT,'1e9999'); self.invoke('strtod',TEXT,OUT); self.assertEqual(self.error(),34)
        self.text(TEXT,'10'); self.invoke('strtol',TEXT,OUT,1); self.assertEqual(self.error(),22)
    def test_native_errno_is_preserved_by_number_parser(self):
        errno=self.arm.call('__errno'); self.arm.uc.mem_write(errno,struct.pack('<I',22))
        self.text(TEXT,'42'); self.assertEqual(self.invoke('strtol',TEXT,OUT,10),42); self.assertEqual(self.word(errno),22)
    def test_environment_pool_overwrite_and_cleanup(self):
        for i in range(16):
            self.text(TEXT,'N'+str(i)); self.text(TEXT+128,'value')
            self.assertEqual(self.invoke('setenv',TEXT,TEXT+128,1),0)
        self.text(TEXT,'EXTRA'); self.assertEqual(ctypes.c_int32(self.invoke('setenv',TEXT,TEXT+128,1)).value,-1)
        self.assertEqual(self.error(),12)
        self.text(TEXT,'N0'); self.text(TEXT+128,'new')
        self.assertEqual(self.invoke('setenv',TEXT,TEXT+128,0),0); self.assertEqual(self.cstring(self.invoke('getenv',TEXT)),b'value')
        self.assertEqual(self.invoke('setenv',TEXT,TEXT+128,1),0); self.assertEqual(self.cstring(self.invoke('getenv',TEXT)),b'new')
    def test_invalid_environment_name(self):
        for name in ('','A=B'):
            self.text(TEXT,name); self.text(TEXT+128,'v')
            self.assertEqual(ctypes.c_int32(self.invoke('setenv',TEXT,TEXT+128,1)).value,-1); self.assertEqual(self.error(),22)
    def test_random_sequence_matches_48_bit_recurrence(self):
        state=0x1234abcd330e
        for _ in range(30):
            state=(state*0x5deece66d+11)&0xffffffffffff
            self.assertEqual(self.invoke('lrand48'),state>>17)
    def test_atomic_return_conventions(self):
        self.arm.uc.mem_write(OUT,struct.pack('<i',5))
        self.assertEqual(self.invoke('__atomic_inc',OUT),5); self.assertEqual(self.word(OUT),6)
        self.assertEqual(self.invoke('__atomic_dec',OUT),6); self.assertEqual(self.word(OUT),5)
        self.assertEqual(self.invoke('__atomic_cmpxchg',7,11,OUT),1); self.assertEqual(self.word(OUT),5)
        self.assertEqual(self.invoke('__atomic_cmpxchg',5,11,OUT),0); self.assertEqual(self.word(OUT),11)
        self.assertEqual(self.invoke('__atomic_swap',3,OUT),11); self.assertEqual(self.word(OUT),3)
    def test_utc_calendar_roundtrips_and_normalization(self):
        for epoch in (0,-1,-2147483648,2147483647,1709164800):
            self.arm.uc.mem_write(OUT,struct.pack('<i',epoch)); p=self.invoke('gmtime',OUT)
            got=struct.unpack('<11i',self.arm.uc.mem_read(p,44)); expected=datetime.datetime(1970,1,1,tzinfo=datetime.timezone.utc)+datetime.timedelta(seconds=epoch)
            self.assertEqual(got[:6],(expected.second,expected.minute,expected.hour,expected.day,expected.month-1,expected.year-1900))
            self.assertEqual(ctypes.c_int32(self.invoke('mktime',p)).value,epoch)
        values=[0,0,0,1,12,123,0,0,0,0,0]; self.arm.uc.mem_write(OUT,struct.pack('<11i',*values))
        self.assertEqual(self.invoke('mktime',OUT),1704067200)
    def test_utc_calendar_overflow_keeps_input(self):
        original=struct.pack('<11i',0,0,0,1,0,200,0,0,0,0,0); self.arm.uc.mem_write(OUT,original)
        self.assertEqual(ctypes.c_int32(self.invoke('mktime',OUT)).value,-1); self.assertEqual(self.error(),75)
        self.assertEqual(bytes(self.arm.uc.mem_read(OUT,44)),original)
    def test_native_stat_serialization_all_fields_and_padding(self):
        self.assertEqual(self.arm.call('ds6_test_stat_pack',OUT,0),0)
        expected=bytearray(104)
        for offset,value in ((12,0x12345678),(16,0o100644),(20,2),(24,19),(28,23),(56,4096),(72,123),(76,456),(80,789),(84,1234),(88,5678),(92,9876)):
            struct.pack_into('<I',expected,offset,value)
        for offset,value in ((0,17),(32,29),(48,123456),(64,242),(96,0x12345678)): struct.pack_into('<Q',expected,offset,value)
        self.assertEqual(bytes(self.arm.uc.mem_read(OUT,104)),bytes(expected))
        self.results['bionic_stat_size']=104; self.results['bionic_file_size']=84
    def test_stat_time_overflow_does_not_write_output(self):
        self.arm.uc.mem_write(OUT,b'Z'*104)
        self.assertEqual(ctypes.c_int32(self.arm.call('ds6_test_stat_pack',OUT,1)).value,-1)
        self.assertEqual(self.error(),75); self.assertEqual(bytes(self.arm.uc.mem_read(OUT,104)),b'Z'*104)
    def test_path_mapping_and_asset_write_refusal(self):
        self.text(TEXT,'appdata:/file.txt'); self.assertEqual(self.arm.call('ds6_map_path',TEXT,OUT,1),0)
        self.assertEqual(self.cstring(OUT),b'sdmc:/3ds/deadspace/test-output/file.txt')
        self.text(TEXT,'appdata:/../bad'); self.assertEqual(ctypes.c_int32(self.arm.call('ds6_map_path',TEXT,OUT,1)).value,-1)
        self.text(TEXT,'appbundle:/published/data/achievements.sb'); self.assertEqual(ctypes.c_int32(self.arm.call('ds6_map_path',TEXT,OUT,1)).value,-1)
        self.assertEqual(self.error(),30)
    def test_adopt_handle_uses_existing_descriptor_pool(self):
        self.assertEqual(self.arm.call('ds_io_adopt_handle',0x45600000),1024)
        self.assertEqual(self.arm.call('ds_io_native_handle',1024),0x45600000)
        self.assertEqual(self.arm.call('ds_io_native_handle',0),0); self.assertEqual(self.error(),9)
        self.arm.call('ds_io_close',1024)
    def test_sysconf_and_invalid_clock_do_not_call_os(self):
        self.assertEqual(self.invoke('sysconf',0x27),4096)
        self.assertEqual(self.invoke('sysconf',0x0b),11)
        self.assertEqual(ctypes.c_int32(self.invoke('clock_gettime',99,OUT)).value,-1); self.assertEqual(self.error(),22)
    def test_donor_preflight_refuses_280_missing_without_changes(self):
        self.arm.set_file(self.donor); result,info=self.arm.prepare(); self.assertEqual(result,0)
        before=bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size))
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,TABLE,108,OUT),9)
        self.assertEqual(struct.unpack('<5I',self.arm.uc.mem_read(OUT,20)),(392,108,280,4,0))
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size)),before)

if __name__=='__main__':
    start=time.monotonic(); result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LibcTests))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'elapsed_seconds':round(time.monotonic()-start,3),
            'hardware_tested':False,'os_calls_allowed':False,'game_engine_started':False,**LibcTests.results}
    (PORTING/'analysis/stage6-libc-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
