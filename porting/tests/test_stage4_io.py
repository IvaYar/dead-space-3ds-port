"""Execute compiled ARM I/O bridge and softfp module with modeled host files."""
import ctypes
import io
import json
import struct
import time
import unittest
import zlib
from test_arm_loader import ARMCore, PORTING, FILE_ADDR, INFO_ADDR, IMAGE_ADDR
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC

CTX=0x06000000
OPS=CTX+0x100
PATH=CTX+0x2000
MISSING=PATH+0x800
OUT=CTX+0x4000
BUFFER=CTX+0x6000
HOOK=CTX+0x1000


class IOTests(unittest.TestCase):
    results={}

    @classmethod
    def setUpClass(cls):
        cls.donor=(PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        cls.asset=(PORTING/'analysis/candidate-sd/assets/published/data/achievements.sb').read_bytes()
        cls.fixture=(PORTING/'3ds/build-stage4/fixture-stage4.so').read_bytes()
        cls.arm=ARMCore(cls.donor, PORTING/'3ds/build-stage4/core-test.elf')
        cls.arm.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000)
        cls.arm.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        cls.arm.uc.mem_map(CTX,0x10000)
        cls.size=cls.arm.call('ds_io_context_size')
        assert cls.size < 0x100

    def setUp(self):
        self.files={}; self.calls=[]; self.next_handle=0x50000000
        self.read_error=0; self.close_error=0; self.last_position=0
        self.data=self.asset
        self.arm.uc.mem_write(OPS, struct.pack('<4I',*(HOOK+i*4 for i in range(4))))
        self.hook=self.arm.uc.hook_add(UC_HOOK_CODE,self.host_call,begin=HOOK,end=HOOK+15)
        self.arm.call('ds_io_init',CTX,OPS)

    def tearDown(self):
        self.arm.call('ds_io_shutdown',CTX)
        self.arm.uc.hook_del(self.hook)
        self.assertFalse(self.files,'Host file leaked')

    def word(self,addr): return struct.unpack('<I',self.arm.uc.mem_read(addr,4))[0]
    def write_word(self,addr,value): self.arm.uc.mem_write(addr,struct.pack('<I',value&0xffffffff))
    def signed(self,value): return ctypes.c_int32(value).value
    def string(self,addr,text): self.arm.uc.mem_write(addr,text.encode()+b'\0')
    def cstring(self,addr):
        out=bytearray()
        while (b:=bytes(self.arm.uc.mem_read(addr+len(out),1)))!=b'\0': out+=b
        return out.decode()
    def error(self): return self.word(CTX+48)
    def active(self): return self.word(CTX+self.size-4)
    def call(self,name,*args): return self.signed(self.arm.call(name,*(a&0xffffffff for a in args)))
    def open(self,path='appbundle:/published/data/achievements.sb',flags=0):
        self.string(PATH,path); return self.call('ds_io_open',PATH,flags)

    def host_call(self,uc,address,size,user):
        a,b,c,d=(uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3))
        which=(address-HOOK)//4
        self.calls.append(which)
        result=0
        if which==0:
            path=self.cstring(a)
            if path!='sdmc:/3ds/deadspace/assets/published/data/achievements.sb': self.write_word(b,2)
            else:
                result=self.next_handle; self.next_handle+=4
                self.files[result]=io.BytesIO(self.data)
        elif which==1:
            if self.read_error: self.write_word(d,self.read_error); result=-1
            else:
                data=self.files[a].read(c); uc.mem_write(b,data); result=len(data)
        elif which==2:
            file=self.files[a]; off=self.signed(b)
            base=(0,file.tell(),len(file.getvalue()))[c]; target=base+off
            if target<0: self.write_word(d,22); result=-1
            elif target>0x7fffffff: self.write_word(d,75); result=-1
            else: file.seek(target); result=target
        elif which==3:
            file=self.files.pop(a); self.last_position=file.tell(); file.close()
            if self.close_error: self.write_word(b,self.close_error); result=-1
        uc.reg_write(UC_ARM_REG_R0,result&0xffffffff)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))

    def test_four_path_prefixes(self):
        for path in ('appbundle:/published/data/achievements.sb','published/data/achievements.sb',
                     '/sdcard/Android/data/com.ea.deadspace/files/published/data/achievements.sb',
                     'sdmc:/3ds/deadspace/assets/published/data/achievements.sb'):
            with self.subTest(path=path):
                self.string(PATH,path)
                self.assertEqual(self.call('ds_io_map_path',PATH,OUT,512),0)
                self.assertEqual(self.cstring(OUT),'sdmc:/3ds/deadspace/assets/published/data/achievements.sb')

    def test_invalid_paths_do_not_reach_host(self):
        for path in ('sdmc:/elsewhere','published/../x','published/a/../../x','published/./x',
                     'published//x','published/a/','published/a:foo','published/a\\b','published/\nx',
                     'published/.','published/..','published/'):
            with self.subTest(path=path): self.assertEqual(self.open(path),-1)
        self.assertEqual(self.calls,[])

    def test_small_output_keeps_canary(self):
        self.string(PATH,'published/file'); self.arm.uc.mem_write(OUT,b'Z'*64)
        self.assertEqual(self.call('ds_io_map_path',PATH,OUT,5),36)
        self.assertEqual(bytes(self.arm.uc.mem_read(OUT,64)),b'Z'*64)

    def test_null_and_oversized_paths(self):
        self.assertEqual(self.call('ds_io_map_path',0,OUT,512),14)
        self.assertEqual(self.open('published/'+'x'*600),-1); self.assertEqual(self.error(),36)

    def test_write_and_unknown_flags_rejected_before_host(self):
        for flags in (1,2,0x40,0x200,0x400,0x242):
            self.assertEqual(self.open(flags=flags),-1); self.assertEqual(self.error(),30)
        self.assertEqual(self.open(flags=0x800),-1); self.assertEqual(self.error(),22)
        self.assertFalse(self.calls)

    def test_largefile_flag_uses_private_host_handle(self):
        fd=self.open(flags=0x20000)
        self.assertEqual(fd,1024); self.assertEqual(self.active(),1)
        self.assertNotIn(fd,self.files)

    def test_descriptor_capacity_and_cleanup(self):
        self.assertEqual([self.open() for _ in range(8)],list(range(1024,1032)))
        self.assertEqual(self.open(),-1); self.assertEqual(self.error(),24)
        self.assertEqual(self.calls.count(0),8)
        self.assertEqual(self.call('ds_io_shutdown',CTX),0)
        self.assertEqual(self.active(),0); self.assertFalse(self.files)

    def test_read_seek_eof_and_zero_count(self):
        fd=self.open()
        self.assertEqual(self.call('ds_io_read',fd,BUFFER,7),7)
        self.assertEqual(bytes(self.arm.uc.mem_read(BUFFER,7)),self.asset[:7])
        self.assertEqual(self.call('ds_io_seek',fd,-2,2),len(self.asset)-2)
        self.assertEqual(self.call('ds_io_read',fd,BUFFER,7),2)
        self.assertEqual(self.call('ds_io_read',fd,BUFFER,7),0)
        before=len(self.calls)
        self.assertEqual(self.call('ds_io_read',fd,0,0),0)
        self.assertEqual(len(self.calls),before)

    def test_invalid_descriptors_and_closed_file(self):
        for fd in (-1,0,1024,1032,0x7fffffff):
            self.assertEqual(self.call('ds_io_read',fd,BUFFER,1),-1); self.assertEqual(self.error(),9)
        fd=self.open(); self.assertEqual(self.call('ds_io_close',fd),0)
        self.assertEqual(self.call('ds_io_close',fd),-1); self.assertEqual(self.error(),9)

    def test_invalid_read_buffer_and_count(self):
        fd=self.open(); self.assertEqual(self.call('ds_io_read',fd,0,1),-1); self.assertEqual(self.error(),14)
        self.assertEqual(self.call('ds_io_read',fd,BUFFER,0xffffffff),-1); self.assertEqual(self.error(),22)
        self.assertNotIn(1,self.calls)

    def test_seek_errors_preserve_position(self):
        fd=self.open(); self.assertEqual(self.call('ds_io_seek',fd,3,0),3)
        self.assertEqual(self.call('ds_io_seek',fd,-10,1),-1); self.assertEqual(self.error(),22)
        self.assertEqual(self.call('ds_io_seek',fd,0x7fffffff,1),-1); self.assertEqual(self.error(),75)
        self.assertEqual(self.call('ds_io_seek',fd,0,1),3)
        before=len(self.calls)
        self.assertEqual(self.call('ds_io_seek',fd,0,3),-1)
        self.assertEqual(len(self.calls),before)

    def test_host_read_error_is_android_errno(self):
        fd=self.open(); self.read_error=5
        self.assertEqual(self.call('ds_io_read',fd,BUFFER,1),-1); self.assertEqual(self.error(),5)

    def test_close_failure_consumes_handle(self):
        fd=self.open(); self.close_error=5
        self.assertEqual(self.call('ds_io_close',fd),-1); self.assertEqual(self.error(),5)
        self.assertEqual(self.active(),0); self.assertFalse(self.files)

    def test_errno_pointer_and_success_preserves_error(self):
        self.assertEqual(self.arm.call('ds_io_errno'),CTX+48)
        self.write_word(CTX+48,30)
        fd=self.open(); self.assertEqual(self.error(),30)
        self.assertEqual(self.call('ds_io_close',fd),0); self.assertEqual(self.error(),30)

    def bind_fixture(self):
        self.arm.set_file(self.fixture); result,info=self.arm.prepare(); self.assertEqual(result,0)
        count=self.arm.call('ds_io_bindings',OUT+0x100,5); self.assertEqual(count,5)
        result=self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,OUT+0x100,count,OUT+0x200)
        self.assertEqual(result,0)
        values=struct.unpack('<5I',self.arm.uc.mem_read(OUT+0x200,20)); self.assertEqual(values[:4],(5,5,0,0))
        self.string(OUT+0x400,'probe_io')
        self.assertEqual(self.arm.call('ds_elf_find_export',FILE_ADDR,INFO_ADDR,OUT+0x400,OUT+0x500,OUT+0x504),0)
        self.arm.exports['__probe']=IMAGE_ADDR+self.word(OUT+0x500)-info.load_min
        return info

    def fixture_probe(self):
        self.bind_fixture(); self.string(PATH,'appbundle:/published/data/achievements.sb')
        self.string(MISSING,'appbundle:/published/data/.stage4-missing-7f49b20a')
        result=self.arm.call('__probe',PATH,MISSING,len(self.asset),zlib.crc32(self.asset),OUT)
        return result,struct.unpack('<12I',self.arm.uc.mem_read(OUT,48))

    def test_softfp_module_reads_real_asset_and_checks_errors(self):
        result,output=self.fixture_probe()
        self.assertEqual(result,0)
        self.assertEqual(output,(0,len(self.asset),zlib.crc32(self.asset),len(self.asset),0,len(self.asset)-1,1,0,9,2,30,42))
        self.assertEqual(self.active(),0)
        self.results['asset_bytes']=len(self.asset); self.results['asset_crc32']=f'{zlib.crc32(self.asset):08x}'
        self.results['android_errno_checks']=[9,2,30]; self.results['constructor_marker']=42

    def test_wrong_resource_fails_and_closes(self):
        self.data=bytes([self.asset[0]^1])+self.asset[1:]
        result,output=self.fixture_probe()
        self.assertEqual(result,4); self.assertNotEqual(output[2],zlib.crc32(self.asset))
        self.assertEqual(self.active(),0)

    def test_truncated_resource_fails_and_closes(self):
        self.data=self.asset[:100]
        result,_=self.fixture_probe(); self.assertEqual(result,4); self.assertEqual(self.active(),0)

    def test_missing_resource_reports_enoent(self):
        self.bind_fixture(); self.string(PATH,'published/missing'); self.string(MISSING,'published/another')
        result=self.arm.call('__probe',PATH,MISSING,len(self.asset),zlib.crc32(self.asset),OUT)
        self.assertEqual(result,1); self.assertEqual(self.word(OUT+8*4),2); self.assertEqual(self.active(),0)

    def test_donor_incomplete_bindings_leave_whole_image_unchanged(self):
        self.arm.set_file(self.donor); result,info=self.arm.prepare(); self.assertEqual(result,0)
        before=bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size))
        count=self.arm.call('ds_io_bindings',OUT+0x100,5)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,OUT+0x100,count,OUT+0x200),9)
        values=struct.unpack('<5I',self.arm.uc.mem_read(OUT+0x200,20))
        self.assertEqual(values,(392,5,383,4,0))
        self.assertEqual(bytes(self.arm.uc.mem_read(IMAGE_ADDR,info.image_size)),before)
        self.results['donor_preflight']={'imports':392,'resolved':5,'missing':383,'weak_zero':4,'patched_sites':0,'image_unchanged':True}


if __name__=='__main__':
    started=time.monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IOTests))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
            'elapsed_seconds':round(time.monotonic()-started,3),'hardware_tested':False,
            'host_files_modeled':True,'game_engine_started':False,**IOTests.results}
    (PORTING/'analysis/stage4-io-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
