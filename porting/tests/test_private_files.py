"""Run private descriptor policy, flags and shared-pool ownership as ARM code."""
import hashlib,io,json,struct,time,unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_LR
import test_jni10 as jni
TABLE=0x06008c00;PATH=0x06008400;DATA=0x06008600;RESULT=0x06009000;HOOK=0x06007000
ROOT='sdmc:/3ds/deadspace/test-output/';CREAT=0x40;EXCL=0x80;TRUNC=0x200;APPEND=0x400
class PrivateFiles(jni.Jni10Tests):
    def setUp(self):
        super().setUp();self.arm.call('ds6_init',0);self.store={};self.paths={};self.flags={};self.host_calls=[];self.write_error=0;self.partial=None
        self.arm.uc.mem_write(TABLE,struct.pack('<4I',*(HOOK+i*4 for i in range(4))))
        self.hook=self.arm.uc.hook_add(UC_HOOK_CODE,self.backend,begin=HOOK,end=HOOK+15)
        self.assertEqual(self.arm.call('ds24_init',TABLE),0)
    def tearDown(self):
        self.arm.call('ds24_shutdown');self.arm.uc.hook_del(self.hook);self.arm.call('ds6_cleanup');super().tearDown()
    def backend(self,uc,address,size,user):
        a,b,c,d=[uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        which=(address-HOOK)//4;self.host_calls.append((which,a,b,c));result=0
        if which==0:
            path=self.io.cstring(a)
            if b&EXCL and path in self.store:self.io.write_word(d,17)
            elif path not in self.store and not b&CREAT:self.io.write_word(d,2)
            else:
                if b&TRUNC or path not in self.store:self.store[path]=b''
                result=self.io.next_handle;self.io.next_handle+=4;self.io.files[result]=io.BytesIO(self.store[path]);self.paths[result]=path;self.flags[result]=b
        elif which==1:
            data=self.io.files[a].read(c);uc.mem_write(b,data);result=len(data)
        elif which==2:
            if self.write_error:self.io.write_word(d,self.write_error);result=-1
            else:
                f=self.io.files[a]
                if self.flags[a]&APPEND:f.seek(0,2)
                n=c if self.partial is None else min(c,self.partial);result=f.write(bytes(uc.mem_read(b,n)));self.store[self.paths[a]]=f.getvalue()
        else:
            self.io.files.pop(a).close()
        uc.reg_write(UC_ARM_REG_R0,result&0xffffffff);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def open(self,name='save',flags=2|CREAT,mode=0o600):
        self.io.string(PATH,name if ':' in name else 'appdata:/'+name)
        return self.arm.call('ds24_open',PATH,flags,mode)
    def write(self,fd,data):self.arm.uc.mem_write(DATA,data);return self.arm.call('ds24_write',fd,DATA,len(data))
    def read(self,fd,n):
        count=self.arm.call('ds24_read',fd,DATA,n)
        return count,bytes(self.arm.uc.mem_read(DATA,count)) if count<0x80000000 else b''
    def err(self):return self.io.word(self.arm.call('ds_io_errno'))
    def close(self,fd):return self.arm.call('ds_io_close',fd)
    def test_create_write_seek_reopen_persists_exact_bytes(self):
        fd=self.open();self.assertEqual(self.write(fd,b'A\0BCD'),5);self.assertEqual(self.arm.call('ds_io_seek',fd,0,0),0)
        self.assertEqual(self.read(fd,8),(5,b'A\0BCD'));self.close(fd);fd=self.open(flags=0);self.assertEqual(self.read(fd,8),(5,b'A\0BCD'))
    def test_access_modes_reject_wrong_direction_without_backend_calls(self):
        fd=self.open(flags=1|CREAT);before=len(self.host_calls);self.assertEqual(self.read(fd,1)[0],0xffffffff);self.assertEqual(self.err(),9);self.assertEqual(len(self.host_calls),before)
        self.close(fd);fd=self.open(flags=0);self.assertEqual(self.write(fd,b'X'),0xffffffff);self.assertEqual(self.err(),9)
    def test_append_writes_at_end_after_seek_and_does_not_truncate(self):
        self.store[ROOT+'save']=b'ABC';fd=self.open(flags=2|APPEND);self.arm.call('ds_io_seek',fd,0,0);self.write(fd,b'D')
        self.assertEqual(self.store[ROOT+'save'],b'ABCD')
    def test_truncate_and_create_exclusive_have_real_error_semantics(self):
        self.store[ROOT+'save']=b'old';self.assertEqual(self.open(flags=1|CREAT|EXCL),0xffffffff);self.assertEqual(self.err(),17)
        self.assertEqual(self.store[ROOT+'save'],b'old');fd=self.open(flags=1|TRUNC);self.close(fd);self.assertEqual(self.store[ROOT+'save'],b'')
    def test_open_without_create_returns_missing_instead_of_creating_file(self):
        self.assertEqual(self.open(flags=0),0xffffffff);self.assertEqual(self.err(),2);self.assertEqual(self.store,{})
    def test_invalid_flags_and_modes_never_touch_host(self):
        for flags,mode in ((3,0),(2|0x800,0),(EXCL,0),(TRUNC,0),(2|CREAT,0xffffffff)):
            before=len(self.host_calls);self.assertEqual(self.open(flags=flags,mode=mode),0xffffffff);self.assertEqual(self.err(),22);self.assertEqual(len(self.host_calls),before)
    def test_asset_open_read_delegates_and_write_open_remains_readonly(self):
        fd=self.open('appbundle:/published/data/achievements.sb',0);self.assertEqual(fd,1024);self.assertEqual(self.read(fd,4),(4,self.io.asset[:4]));self.close(fd)
        self.assertEqual(self.open('appbundle:/published/data/achievements.sb',1|TRUNC),0xffffffff);self.assertEqual(self.err(),30);self.assertFalse(self.host_calls)
    def test_path_traversal_and_foreign_mount_are_rejected(self):
        for path in ('appdata:/../escape','appdata:////escape','appdata:/a/../escape','appdata:/a\\b','sdmc:/other/file'):
            self.assertEqual(self.open(path),0xffffffff)
        self.assertFalse(self.host_calls)
    def test_generated_double_separator_maps_to_same_private_file(self):
        fd=self.open('appdata://save');self.write(fd,b'DS');self.close(fd);fd=self.open('appdata:/save',0);self.assertEqual(self.read(fd,2),(2,b'DS'))
    def test_descriptor_exhaustion_precedes_truncate_side_effects(self):
        self.store[ROOT+'existing']=b'preserve';fds=[self.open(str(i)) for i in range(8)];self.assertNotIn(0xffffffff,fds)
        before=len(self.host_calls);self.assertEqual(self.open('existing',2|TRUNC),0xffffffff);self.assertEqual(self.err(),24)
        self.assertEqual(self.store[ROOT+'existing'],b'preserve');self.assertEqual(len(self.host_calls),before)
    def test_legacy_close_clears_shadow_before_descriptor_reuse(self):
        fd=self.open(flags=1|CREAT);self.close(fd);other=self.open('appbundle:/published/data/achievements.sb',0);self.assertEqual(other,fd)
        self.assertEqual(self.read(other,4),(4,self.io.asset[:4]));self.assertEqual(self.write(other,b'!'),0xffffffff);self.assertEqual(self.err(),9)
    def test_zero_length_and_invalid_transfer_arguments(self):
        fd=self.open();self.assertEqual(self.arm.call('ds24_write',fd,0,0),0);self.assertEqual(self.arm.call('ds24_read',fd,0,0),0)
        for fn in ('ds24_read','ds24_write'):
            self.assertEqual(self.arm.call(fn,fd,0,1),0xffffffff);self.assertEqual(self.err(),14)
            self.assertEqual(self.arm.call(fn,fd,DATA,0x80000000),0xffffffff);self.assertEqual(self.err(),22)
    def test_partial_write_and_backend_error_are_preserved(self):
        fd=self.open();self.partial=2;self.assertEqual(self.write(fd,b'ABCDE'),2);self.assertEqual(self.store[ROOT+'save'],b'AB')
        self.write_error=5;self.assertEqual(self.write(fd,b'XYZ'),0xffffffff);self.assertEqual(self.err(),5);self.assertEqual(self.store[ROOT+'save'],b'AB')
    def test_shutdown_closes_only_owned_descriptors(self):
        a=self.open();b=self.open('appbundle:/published/data/achievements.sb',0)
        self.assertEqual(self.arm.call('ds24_shutdown'),1);self.assertEqual(self.arm.call('ds_io_free_slots'),7);self.assertEqual(self.read(b,1),(1,self.io.asset[:1]));self.close(b)
        self.assertEqual(self.arm.call('ds24_write',a,DATA,1),0xffffffff)
    def test_namespace_is_bounded_and_cannot_change_under_live_descriptors(self):
        self.io.string(PATH,'night');self.assertEqual(self.arm.call('ds6_appdata_namespace',PATH),0);fd=self.open();self.assertIn(ROOT+'night/save',self.store)
        self.io.string(PATH,'next');self.assertEqual(self.arm.call('ds6_appdata_namespace',PATH),0xffffffff);self.assertEqual(self.err(),16);self.close(fd)
        for name in ('../escape','a/b','x'*33,'a:b'):
            self.io.string(PATH,name);self.assertEqual(self.arm.call('ds6_appdata_namespace',PATH),0xffffffff)
    def test_duplicate_initialization_does_not_drop_open_handles(self):
        fd=self.open();self.assertEqual(self.arm.call('ds24_init',TABLE),0xffffffff);self.write(fd,b'kept');self.assertEqual(self.store[ROOT+'save'],b'kept')
    def test_largefile_flag_does_not_change_access_mode(self):
        fd=self.open(flags=2|CREAT|0x20000);self.assertEqual(self.write(fd,b'ok'),2);self.arm.call('ds_io_seek',fd,0,0);self.assertEqual(self.read(fd,2),(2,b'ok'))
    def test_horizon_fs_errno_descriptions_are_translated_without_masking_unknown_errors(self):
        for raw,want in ((0xc82044be,17),(0xc8804478,2),(0xc8804470,2),(0xc8804471,2),(0xc82044b4,17),(0xc82044b9,17),
                         (0xc8204499,5),(0xc82004be,5),(17,17),(2,2)):
            self.assertEqual(self.arm.call('ds6_host_error',raw),want)
    def test_duplicate_private_descriptor_retains_access_and_shared_offset(self):
        fd=self.open();self.write(fd,b'ABCDE');self.arm.call('ds_io_seek',fd,0,0);dup=self.arm.call('ds_io_dup',fd)
        self.assertEqual(self.read(fd,2),(2,b'AB'));self.assertEqual(self.read(dup,2),(2,b'CD'));self.close(fd)
        self.assertEqual(self.write(dup,b'!'),1);self.assertEqual(self.store[ROOT+'save'],b'ABCD!');self.close(dup)

if __name__=='__main__':
    start=time.monotonic();names=[n for n in PrivateFiles.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(PrivateFiles(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-start,3)}
    (jni.cpp.PORTING/'analysis/private-files-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
