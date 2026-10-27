"""Computer-only ARM execution audit. Unknown imports STOP, never return success.

This is not a port release. Import traps enable finding the first actual blocker
without claiming that those imports have been implemented. Never shipped in CIA.
"""
import argparse,collections,ctypes,errno,hashlib,json,struct,sys,time,zlib
from pathlib import Path
PORTING=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PORTING/'tests'))
from test_arm_loader import ARMCore,Info,symbols,FILE_ADDR,INFO_ADDR,IMAGE_ADDR,STACK_ADDR,STOP_ADDR
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_INVALID,UcError
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC
CTX=0x06000000; TABLE=CTX+0x1000; OUT=CTX+0x5000; PLAN=CTX+0x6000; TRAPS=0x05e00000
REGS=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)

class Experiment:
    def __init__(self,core_path,limit=4*1024*1024,sensors=False,graphics=False,arena_break_mib=20,arena_map_mib=20,instructions=50_000_000):
        self.instruction_limit=instructions
        self.sensors=sensors or graphics;self.graphics=graphics
        self.blob=(PORTING/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
        assert hashlib.sha1(self.blob).hexdigest()=='3c4a1b844eddbf3b9f0d2d946433bc429cc64b2e'
        self.arm=ARMCore(self.blob,core_path);self.uc=self.arm.uc
        self.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000);self.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        self.uc.mem_map(CTX,0x10000);self.uc.mem_map(TRAPS,0x10000)
        self.uc.mem_map(STACK_ADDR+65536,1024*1024-65536)
        self.stop=None; self.phase='setup';self.calls=collections.Counter();self.traps={};self.completed=[]
        self.audit_handlers={};self.cpu_start=time.process_time_ns()
        self.report={'mode':'computer-only execution audit','emulator':'Unicorn ARM11 MPCore','hardware_tested':False,
            'donor_sha256':hashlib.sha256(self.blob).hexdigest(),'gameplay':False,'unknown_import_policy':'stop before execution; no success stubs',
            'core_sha256':hashlib.sha256(core_path.read_bytes()).hexdigest(),'phases':self.completed}
        self.host_files={};self.host_serial=0x51000000
        self.arm.call('ds6_test_host_stat_layout',OUT);self.stat_layout=self.words(OUT,18)
        ops=[]
        for i in range(4):
            address=TRAPS+0xd000+i*8;ops.append(address)
            self.audit_handlers[address]=(f'file backend {i}',lambda i=i:self.host_file_call(i))
        self.write(CTX+0x100,*ops);self.arm.call('ds_io_init',CTX,CTX+0x100)
        assert self.arm.call('ds_runtime_init',limit)==0
        self.report['runtime_allocation_limit']=limit
        assert self.arm.call('ds6_init',0)==0
        assert self.arm.call('ds7_init')==0 and self.arm.call('ds8_init')==0
        if 'ds11_test_content_ready' in self.arm.exports:
            receipt=PORTING/'analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace/assets-verified.txt'
            expected='DS_ASSETS_V1 dd42272365d0abd8ad9c89450bb7f869ee4ac0ad548525758e6a1e7df4d3c1eb 1728 414822611\n'
            ready=receipt.exists() and receipt.read_bytes()==expected.encode('ascii')
            self.arm.call('ds11_test_content_ready',int(ready));self.report['verified_asset_cache_available']=ready
        if 'ds9_memory_init' in self.arm.exports:
            assert 1<=arena_break_mib<=32 and 1<=arena_map_mib<=80
            brk_bytes=arena_break_mib*1024*1024;map_bytes=arena_map_mib*1024*1024
            self.uc.mem_map(0x12000000,brk_bytes+map_bytes)
            assert self.arm.call('ds9_memory_init',0x12000000,brk_bytes,0x12000000+brk_bytes,map_bytes)==0
            self.report['arena_capacity_bytes']={'break':brk_bytes,'anonymous_mappings':map_bytes}
            refusal=TRAPS+0xbc00
            def arena_refused():
                op,requested,error=(self.uc.reg_read(r) for r in REGS[:3])
                self.snapshot('arena_refusal_guard',self.string(op))
                self.stop.update(bytes_requested=requested,android_errno=error,
                    policy='diagnostic stop at first arena refusal; donor recovery not attempted')
                return 0
            self.audit_handlers[refusal]=('arena refusal guard',arena_refused)
            self.arm.call('ds9_memory_observer',refusal)
        count=self.arm.call('ds6_bindings',TABLE,512)
        count+=self.arm.call('ds7_bindings',TABLE+count*8,512-count)
        count+=self.arm.call('ds8_bindings',TABLE+count*8,512-count)
        if 'ds9_memory_bindings' in self.arm.exports:count+=self.arm.call('ds9_memory_bindings',TABLE+count*8,512-count)
        count+=self.arm.call('ds17_bindings',TABLE+count*8,512-count)
        self.bindings={}
        for i in range(count):
            name,address=self.words(TABLE+i*8,2);self.bindings[self.string(name)]=address
        assert self.arm.prepare()[0]==0
        self.info=Info.from_buffer_copy(self.uc.mem_read(INFO_ADDR,ctypes.sizeof(Info)))
        # Preserve evidence that the production binding guard still rejects the donor.
        before=bytes(self.uc.mem_read(IMAGE_ADDR,self.info.image_size))
        result=self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,TABLE,count,OUT)
        preflight=self.words(OUT,5)
        assert result==9 and preflight[2]>0 and before==bytes(self.uc.mem_read(IMAGE_ADDR,self.info.image_size))
        self.report['production_preflight']={'resolved':preflight[1],'missing':preflight[2],'weak_zero':preflight[3],'image_unchanged':True}
        self.host_dirs={};self.dir_serial=0x52520000
        ops=[]
        for i in range(3):
            address=TRAPS+0xa800+i*8;ops.append(address)
            self.audit_handlers[address]=(f'directory backend {i}',lambda i=i:self.host_directory_call(i))
        self.write(CTX+0x180,*ops);assert self.arm.call('ds20_init',CTX+0x180)==0
        added=self.arm.call('ds20_bindings',TABLE+count*8,512-count)
        for i in range(added):
            name,address=self.words(TABLE+(count+i)*8,2);self.bindings[self.string(name)]=address
        count+=added
        self.report['filesystem_opt_in_bindings']=added
        if self.graphics:
            self.uc.mem_map(0x1a000000,1024*1024)
            assert self.arm.call('ds13_init',CTX+0xd000,0x1a000000,400,240,400*240*3,0)==0
            assert self.arm.call('ds13_current',CTX+0xd000)==0
            observer=TRAPS+0xb000
            def gl_unsupported():
                op=self.string(self.uc.reg_read(UC_ARM_REG_R0));value=self.uc.reg_read(UC_ARM_REG_R1)
                self.snapshot('unimplemented_gl_state',op);self.stop['enum']=f'{value:08x}';return 0
            self.audit_handlers[observer]=('GLES observer',gl_unsupported)
            self.arm.call('ds13_observer',CTX+0xd000,observer,0)
            added=self.arm.call('ds13_bindings',TABLE+count*8,512-count)
            for i in range(added):
                name,fn=self.words(TABLE+(count+i)*8,2);self.bindings[self.string(name)]=fn
            count+=added
            self.report['graphics_context']={'surface':[400,240],'format':'RGB8 rows','bindings':added,'renderer':'bounded unlit CPU triangles, matrices and nonmip texture sampling; guarded CPU profile stops before donor workers'}
        # Host process CPU time is an emulator service, NOT a 3DS clock implementation.
        if 'ds9_memory_init' in self.arm.exports:
            address=TRAPS+0xe000
            self.audit_handlers[address]=('clock',lambda:(time.process_time_ns()-self.cpu_start)//1000)
            self.bindings['clock']=address
            name_addr=CTX+0xf000;self.uc.mem_write(name_addr,b'clock\0')
            self.write(TABLE+count*8,name_addr,address);count+=1
            self.report['emulator_services']={'clock':'host process CPU microseconds; excluded from production supported count'}
        self.dyn=[]
        for i in range(1,self.info.symcount):
            row=struct.unpack_from('<IIIBBH',self.blob,self.info.symoff+i*16)
            if row[5] or not row[0]:continue
            name=self.string(FILE_ADDR+self.info.stroff+row[0]);self.dyn.append((name,row[3]&15,row[3]>>4))
            if name in self.bindings or row[3]>>4==2:continue
            if row[3]&15==1:
                # Objects cannot safely be replaced by a function trap.
                # The stack canary is real writable storage, not a callable stub.
                if name!='__stack_chk_guard':raise RuntimeError('Unknown data import: '+name)
                address=TRAPS+0xf000;self.write(address,0x9b1d73a5)
                self.report['audit_stack_canary_storage']=hex(address)
            else:
                address=TRAPS+len(self.traps)*8;self.traps[address]=name
                self.write(address,0xe7f000f0,0xe12fff1e)
            self.write(TABLE+count*8,FILE_ADDR+self.info.stroff+row[0],address);count+=1
        self.report['stop_trap_imports']=list(self.traps.values())
        result=self.arm.call('ds_init_bind_plan',FILE_ADDR,len(self.blob),IMAGE_ADDR,IMAGE_ADDR,TABLE,count,PLAN,OUT)
        assert result==0,('plan',result,self.words(OUT,5))
        self.report['constructor_entries']=self.words(PLAN)[0]
        self.uc.hook_add(UC_HOOK_CODE,self.on_trap,begin=TRAPS,end=TRAPS+0xffff)
        self.uc.hook_add(UC_HOOK_MEM_INVALID,self.on_memory)
        # A single-thread CPU model must not masquerade as working native threads.
        for name in ('ds7_spawn','ds7_cv_wait','ds7_bad_main_exit','abort','_open_r','_write_r','_stat_r','_mkdir_r','ds6_native_clock','ds6_native_sleep'):
            if name in self.arm.exports:
                pc=self.arm.exports[name];self.uc.hook_add(UC_HOOK_CODE,self.boundary(name),begin=pc,end=pc)
        for name,pc in self.bindings.items():
            if name not in ('__dso_handle','__sF','_ctype_','_tolower_tab_','_toupper_tab_','__page_size','tzname'):
                self.uc.hook_add(UC_HOOK_CODE,self.count_call(name),begin=pc,end=pc)
    def words(self,p,n=1):return struct.unpack('<'+'I'*n,self.uc.mem_read(p,n*4))
    def host_file_call(self,operation):
        a,b,c,d=(self.uc.reg_read(r) for r in REGS)
        if operation==0:
            name=self.string(a);prefix='sdmc:/3ds/deadspace/assets/published/'
            if not name.startswith(prefix):self.write(b,2);return 0
            root=(PORTING/'analysis/candidate-sd/assets/published').resolve();path=(root/name[len(prefix):]).resolve()
            if not path.is_relative_to(root) or not path.is_file():self.write(b,2);return 0
            handle=self.host_serial;self.host_serial+=4;self.host_files[handle]=path.open('rb');return handle
        file=self.host_files.get(a)
        if file is None:self.write(d if operation in (1,2) else b,9);return -1
        try:
            if operation==1:
                data=file.read(c)
                if data:self.uc.mem_write(b,data)
                return len(data)
            if operation==2:
                file.seek(ctypes.c_int32(b).value,c);return file.tell()
            file.close();del self.host_files[a];return 0
        except (OSError,ValueError):self.write(d if operation in (1,2) else b,5);return -1
    def write(self,p,*values):self.uc.mem_write(p,struct.pack('<'+'I'*len(values),*(v&0xffffffff for v in values)))
    def host_directory_call(self,operation):
        a,b,c=(self.uc.reg_read(r) for r in REGS[:3]);error_ptr=b if operation in (0,2) else c
        try:
            if operation==0:
                path=self.host_metadata_path(self.string(a))
                if not path.is_dir():raise FileNotFoundError(errno.ENOENT,'not a directory')
                entries=list(path.iterdir());handle=self.dir_serial;self.dir_serial+=4
                self.host_dirs[handle]=iter(entries);return handle
            if a not in self.host_dirs:raise OSError(errno.EBADF,'stale directory')
            if operation==2:del self.host_dirs[a];return 0
            file=next(self.host_dirs[a],None)
            if file is None:return 0
            name=file.name.encode('utf-8')
            if len(name)>255:raise OSError(errno.ENAMETOOLONG,'directory name')
            data=struct.pack('<QI',file.stat().st_ino,4 if file.is_dir() else 8)+name+b'\0'
            self.uc.mem_write(b,data);return 1
        except OSError as exc:self.write(error_ptr,exc.errno or errno.EIO);return 0 if operation==0 else -1
    def string(self,p,max_bytes=4096):
        out=bytearray()
        for i in range(max_bytes):
            b=bytes(self.uc.mem_read(p+i,1))
            if b==b'\0':return out.decode('utf-8',errors='replace')
            out+=b
        raise ValueError('Unterminated string')
    def snapshot(self,kind,name,address=None):
        self.stop={'kind':kind,'name':name,'phase':self.phase,'pc':f'{self.uc.reg_read(UC_ARM_REG_PC):08x}',
            'lr':f'{self.uc.reg_read(UC_ARM_REG_LR):08x}','args':[f'{self.uc.reg_read(r):08x}' for r in REGS]}
        if address is not None:self.stop['address']=f'{address:08x}'
        if name=='JNIEnv slot 6':
            self.stop['class_requested']=self.string(self.uc.reg_read(UC_ARM_REG_R1))
        self.uc.emu_stop()
    def on_trap(self,uc,address,size,data):
        if address in self.audit_handlers:
            name,function=self.audit_handlers[address];self.calls['emulator:'+name]+=1
            value=function()
            if self.stop:return
            self.uc.reg_write(UC_ARM_REG_R0,value&0xffffffff)
            self.uc.reg_write(UC_ARM_REG_PC,self.uc.reg_read(UC_ARM_REG_LR));return
        kind='unimplemented_jni' if 0x8000<=address-TRAPS<0xa000 else 'unimplemented_import'
        self.snapshot(kind,self.traps.get(address,'unknown trap address'))
    def on_memory(self,uc,access,address,size,value,data):self.snapshot('invalid_memory',str(access),address);return False
    def boundary(self,name):
        def callback(uc,address,size,data):
            if name=='_mkdir_r':
                reent,path_ptr,mode=(uc.reg_read(r) for r in REGS[:3]);error=0
                try:
                    path=self.host_metadata_path(self.string(path_ptr),True);path.mkdir(mode=mode)
                except OSError as exc:error=exc.errno or errno.EIO
                if error:self.write(reent+self.stat_layout[1],error)
                self.calls['emulator:native_mkdir']+=1
                uc.reg_write(UC_ARM_REG_R0,0xffffffff if error else 0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
            if name=='_stat_r':
                reent,path_ptr,out=(uc.reg_read(r) for r in REGS[:3]);error=0
                try:
                    file=self.host_metadata_path(self.string(path_ptr))
                    s=file.stat();values=(s.st_mode,s.st_size,4096,(s.st_size+511)//512,1,int(s.st_atime),int(s.st_mtime),int(s.st_ctime))
                    packed=bytearray(self.stat_layout[0])
                    for i,v in enumerate(values):
                        offset,width=self.stat_layout[2+i*2:4+i*2];packed[offset:offset+width]=v.to_bytes(width,'little',signed=v<0)
                    uc.mem_write(out,bytes(packed))
                except OSError as exc:error=exc.errno or errno.EIO
                except OverflowError:error=75
                if error:self.write(reent+self.stat_layout[1],error)
                self.calls['emulator:native_stat']+=1
                self.report['emulator_services']['native_stat']='host read-only asset metadata packed using linked newlib layout; Bionic conversion in ARM'
                uc.reg_write(UC_ARM_REG_R0,0xffffffff if error else 0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
            if name=='ds6_native_clock' and 'ds9_memory_init' in self.arm.exports:
                clock_id,out=(uc.reg_read(r) for r in REGS[:2])
                if clock_id not in (0,1):self.snapshot('unimplemented_native_clock',str(clock_id));return
                ns=time.time_ns() if clock_id==0 else time.monotonic_ns()
                self.write(out,ns//1_000_000_000,ns%1_000_000_000)
                self.calls['emulator:native_clock']+=1
                self.report['emulator_services']['native_clock']='host realtime/monotonic; Android conversion runs in ARM code'
                uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
            self.snapshot('unimplemented_native_boundary',name)
        return callback
    def host_metadata_path(self,path,writable=False):
        prefixes=(('sdmc:/3ds/deadspace/test-output/',PORTING/'analysis/unicorn-userdata',True),
                  ('sdmc:/3ds/deadspace/assets/',PORTING/'analysis/candidate-sd/assets',False))
        if path=='sdmc:/3ds/deadspace/':
            if writable:raise PermissionError(errno.EROFS,'read-only virtual mount')
            return PORTING/'analysis/candidate-sd'
        for prefix,root,allowed in prefixes:
            if path.startswith(prefix):
                if writable and not allowed:raise PermissionError(errno.EROFS,'read-only assets')
                if allowed:root.mkdir(exist_ok=True)
                root=root.resolve();file=(root/path[len(prefix):]).resolve()
                if not file.is_relative_to(root):raise PermissionError(errno.EACCES,'outside profile root')
                return file
        raise FileNotFoundError(errno.ENOENT,'outside filesystem profile')
    def count_call(self,name):
        def callback(uc,address,size,data):
            self.calls[name]+=1
            if name in ('open','stat','fopen','access','mkdir','opendir'):
                self.report.setdefault('file_operations',[]).append({'api':name,'path':self.string(uc.reg_read(UC_ARM_REG_R0))})
            if name.startswith('gl') and self.graphics:
                counts={'glTexImage2D':9,'glTexSubImage2D':9,'glGenTextures':2,'glBindTexture':2,'glBlendFunc':2,'glGetIntegerv':2,'glGetFloatv':2,'glGetFixedv':2,'glGetBooleanv':2,'glGetError':0}
                count=counts.get(name,1);args=[uc.reg_read(r) for r in REGS[:min(count,4)]]
                if count>4:args.extend(self.words(uc.reg_read(UC_ARM_REG_SP),count-4))
                event={'api':name,'args':[f'{v:08x}' for v in args]}
                if name=='glTexImage2D' and args[6:8]==[0x1908,0x1401] and 0<args[3]<=512 and 0<args[4]<=512 and args[8]:
                    try:event['source_crc32']=f'{zlib.crc32(bytes(uc.mem_read(args[8],args[3]*args[4]*4))):08x}'
                    except UcError:event['source_crc32']='unreadable'
                self.report.setdefault('graphics_operations',[]).append(event)
            if name in ('sbrk','mmap','munmap'):
                args=[uc.reg_read(r) for r in REGS]
                if name=='mmap':args.extend(self.words(uc.reg_read(UC_ARM_REG_SP),2))
                event={'api':name,'args':[f'{v:08x}' for v in args]}
                self.report.setdefault('arena_operations',[]).append(event)
                pc=uc.reg_read(UC_ARM_REG_LR)&~1;holder=[]
                def returned(uc,address,size,data):
                    event['return']=f'{uc.reg_read(UC_ARM_REG_R0):08x}';uc.hook_del(holder[0])
                holder.append(uc.hook_add(UC_HOOK_CODE,returned,begin=pc,end=pc))
        return callback
    def call(self,label,pc,*args):
        self.phase=label;self.stop=None
        self.uc.reg_write(UC_ARM_REG_SP,STACK_ADDR+1024*1024-4096);self.uc.reg_write(UC_ARM_REG_LR,STOP_ADDR)
        for reg,value in zip(REGS,args):self.uc.reg_write(reg,value)
        for i,value in enumerate(args[4:]):self.write(self.uc.reg_read(UC_ARM_REG_SP)+i*4,value)
        try:self.uc.emu_start(pc,STOP_ADDR,count=self.instruction_limit,timeout=30_000_000)
        except UcError as exc:
            if not self.stop:self.snapshot('emulation_exception',str(exc))
        if self.stop:return False
        if self.uc.reg_read(UC_ARM_REG_PC)!=STOP_ADDR:
            self.snapshot('instruction_or_time_limit',label);return False
        self.completed.append({'name':label,'return_r0':f'{self.uc.reg_read(UC_ARM_REG_R0):08x}'})
        return True
    def run(self):
        # Invoke the production constructor planner/runner; it never skips a failed entry.
        okay=self.call('donor constructors',self.arm.exports['ds_init_run'],PLAN)
        self.report['constructors_completed']=self.words(PLAN+8)[0]
        self.report['constructors_passed']=okay
        if okay and 'ds_jni_init' in self.arm.exports:
            self.report['engine_entry_attempted']=False
            okay=self.bootstrap()
        if not okay:self.report['stop']=self.stop
        self.arm.call('ds_runtime_stats',OUT);values=self.words(OUT,9)
        self.report['heap_stats']=values
        gate_depth=self.arm.call('ds7_test_gate_depth');self.report['paused_gate_depth']=gate_depth
        if 'ds9_memory_stats' in self.arm.exports and not gate_depth:
            self.arm.call('ds9_memory_stats',OUT);self.report['donor_arena_stats']=self.words(OUT,8)
        elif gate_depth:self.report['locked_stats_unavailable']='paused inside critical section; no reentrant sampling'
        if 'ds10_stats' in self.arm.exports and self.report.get('engine_entry_attempted'):
            self.arm.call('ds10_stats',CTX+0xa000,OUT)
            self.report['jni_stats']=dict(zip(('pending_exception','lookups','calls','failures','live_refs','peak_refs','startup_calls'),self.words(OUT,7)))
        self.report['runtime_calls']=dict(self.calls)
        if not gate_depth:
            self.arm.call('ds17_stats',OUT);self.report['jump_stats']=dict(zip(('saves','restores','refusals'),self.words(OUT,3)))
        if self.graphics:
            self.arm.call('ds13_stats',CTX+0xd000,OUT);self.report['graphics_stats']=dict(zip(('queries','clears','pixels','flushes'),self.words(OUT,4)))
            self.arm.call('ds15_test_stats',OUT);self.report['texture_stats']=dict(zip(('names','bytes','uploads','patches'),self.words(OUT,4)))
            self.report['graphics_error']=f'{self.arm.call("ds16_test_error"):08x}'
            self.arm.call('ds18_jni_stats',CTX+0xa000,OUT);self.report['string_stats']=dict(zip(('new16','newUTF','get16','getUTF','regions','errors'),self.words(OUT,6)))
            self.arm.call('ds19_jni_stats',CTX+0xa000,OUT);self.report['asset_stats']=dict(zip(('lists','names','gets','sets','extra_strings','arrays'),self.words(OUT,6)))
            if self.arm.call('ds15_test_image',1,0,OUT)==0:
                w,h,fmt,data=self.words(OUT,4);self.report['first_texture']={'name':1,'level':0,'width':w,'height':h,'format':f'{fmt:04x}',
                    'bytes':w*h*4,'stored_crc32':f'{zlib.crc32(bytes(self.uc.mem_read(data,w*h*4))):08x}'}
        self.report.setdefault('engine_entry_attempted',False)
        for file in self.host_files.values():file.close()
        return self.report
    def native_call(self,label,pc,context,*args):
        # A real VM releases a native method's local references on return.
        table=self.words(context)[0]
        push=self.words(table+19*4)[0];pop=self.words(table+20*4)[0]
        self.arm.exports['_frame_push']=push;self.arm.exports['_frame_pop']=pop
        assert self.arm.call('_frame_push',context,16)==0
        result=self.call(label,pc,context,*args)
        if result:self.arm.call('_frame_pop',context,0)
        return result
    def bootstrap(self):
        context=CTX+0xa000;verified=CTX+0x7000
        result=self.arm.call('ds_bootstrap_verify',FILE_ADDR,len(self.blob),IMAGE_ADDR,self.info.image_size,IMAGE_ADDR,INFO_ADDR,verified)
        if result: self.snapshot('bootstrap_verification_failed',str(result));return False
        on_load,vm_storage,get_chars,release_chars=self.words(verified,4)
        if 'ds10_init' in self.arm.exports:
            observer=TRAPS+0xc000;exports,_=symbols(self.blob)
            def observe():
                op,cls,name,sig=[self.string(self.uc.reg_read(r)) for r in REGS]
                missing=self.words(self.uc.reg_read(UC_ARM_REG_SP))[0]
                request={'operation':op,'class':cls,'name':name,'signature':sig,'missing':missing==1,'status':missing}
                self.report.setdefault('java_requests',[]).append(request)
                if missing==1:
                    self.snapshot('unimplemented_java_adapter',op);self.stop['request']=request
                return 0
            self.audit_handlers[observer]=('JNI observer',observe)
            startup=IMAGE_ADDR+exports['Java_com_ea_EAIO_EAIO_Startup']
            assert self.arm.call('ds10_init',context,observer,startup)==0
            listing=TRAPS+0xb800
            def list_assets():
                _,path_ptr,names,capacity=(self.uc.reg_read(r) for r in REGS)
                try:
                    relative=self.string(path_ptr);root=(PORTING/'analysis/candidate-sd/assets/published').resolve();path=(root/relative).resolve()
                    if not path.is_relative_to(root):return -1
                    entries=list(path.iterdir()) if path.is_dir() else []
                    if any(p.is_symlink() for p in entries):return -1
                    data=[p.name.encode('utf-8') for p in entries]
                    if len(data)>2048 or any(len(n)>255 for n in data):return -1
                    if names:
                        if capacity<len(data):return -1
                        for i,name in enumerate(data):self.uc.mem_write(names+i*256,name+b'\0')
                    return len(data)
                except (OSError,UnicodeError):return -1
            self.audit_handlers[listing]=('asset directory backend',list_assets)
            self.arm.call('ds19_assets_backend',context,listing,0)
            if 'ds10_query_compat' in self.arm.exports:
                self.arm.call('ds10_query_compat',context,1)
                self.report['verified_jni_quirks']=['Selected SD Query.isContentReady()Z uses CallStaticObjectMethodV; opt-in narrow adapter']
            if 'ds11_orientation_backend' in self.arm.exports:
                callback=IMAGE_ADDR+exports['Java_com_ea_blast_DeviceOrientationHandlerAndroidDelegate_NativeOnDeviceOrientationChange']
                self.arm.call('ds11_orientation_backend',context,callback,1)
                self.report['orientation_provider']='fixed display callback registered but disabled: accelerometer backend unavailable'
            if self.sensors:
                callback=IMAGE_ADDR+exports['Java_com_ea_blast_AccelerometerAndroidDelegate_NativeOnAcceleration']
                assert self.arm.call('ds12_test_attach',context,callback)==0
                self.report['sensor_mode']='injected CPU sensor model; native backend tested separately in Azahar'
                self.report['orientation_provider']='fixed display event queue enabled with attached sensor model'
        else:self.arm.call('ds_jni_init',context)
        # Unknown Java calls terminate explicitly, rather than dereferencing NULL
        # or simulating an entire Android VM with permissive success values.
        for slot in range(4,233):
            pointer=context+16+slot*4
            if not self.words(pointer)[0]:
                address=TRAPS+0x8000+slot*8;self.traps[address]=f'JNIEnv slot {slot}'
                self.write(address,0xe7f000f0,0xe12fff1e);self.write(pointer,address)
        if not self.call('JNI_OnLoad',IMAGE_ADDR+on_load,context+8,0):return False
        returned=self.uc.reg_read(UC_ARM_REG_R0)
        stored=self.words(IMAGE_ADDR+vm_storage)[0]
        self.report['jni_bootstrap']={'return':f'{returned:08x}','stored_vm_matches':stored==context+8}
        if returned!=0x10004 or stored!=context+8:
            self.snapshot('jni_bootstrap_failed','JNI_OnLoad result or JavaVM pointer');return False
        exports,_=symbols(self.blob)
        name='Java_com_ea_blast_MainActivity_NativeOnCreate'
        self.report['engine_entry_attempted']=True
        self.report['entry_export']=name
        if not self.native_call('NativeOnCreate',IMAGE_ADDR+exports[name],context,0):return False
        name='Java_com_ea_blast_AndroidRenderer_NativeOnSurfaceCreated'
        if not self.native_call('NativeOnSurfaceCreated',IMAGE_ADDR+exports[name],context,0):return False
        name='Java_com_ea_blast_AndroidRenderer_NativeOnSurfaceChanged'
        if not self.native_call('NativeOnSurfaceChanged',IMAGE_ADDR+exports[name],context,0,400,240):return False
        name='Java_com_ea_blast_AndroidRenderer_NativeOnDrawFrame'
        self.report['frames_returned']=0
        for frame in range(1,121):
            self.report['frame_attempt']=frame
            if not self.native_call(f'NativeOnDrawFrame[{frame}]',IMAGE_ADDR+exports[name],context,0):return False
            self.report['frames_returned']=frame
            if 'ds11_pump_events' in self.arm.exports:
                if not self.call(f'orientation pump[{frame}]',self.arm.exports['ds11_pump_events'],context):return False
            if self.sensors:
                if not self.call(f'accelerometer pump[{frame}]',self.arm.exports['ds12_test_pump'],context,frame*16667,0):return False
        self.snapshot('frame_budget_exhausted','120 lifecycle callbacks; no renderer implemented');return False

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core',type=Path,default=PORTING/'3ds/build-emulator/core-test.elf')
    parser.add_argument('--output',type=Path,default=PORTING/'analysis/engine-first-entry-experiment.json')
    parser.add_argument('--sensors',action='store_true',help='Opt-in sensor model; use a separate output from the guarded baseline')
    parser.add_argument('--graphics',action='store_true',help='Opt-in real GLES context/state and software clear; implies sensors')
    parser.add_argument('--arena-break-mib',type=int,default=20)
    parser.add_argument('--arena-map-mib',type=int,default=20)
    parser.add_argument('--instructions',type=int,default=50_000_000)
    args=parser.parse_args()
    if args.output==PORTING/'analysis/engine-first-entry-experiment.json':
        if args.graphics:args.output=PORTING/'analysis/engine-graphics-entry.json'
        elif args.sensors:args.output=PORTING/'analysis/engine-sensor-entry.json'
    start=time.monotonic();experiment=Experiment(args.core,sensors=args.sensors,graphics=args.graphics,arena_break_mib=args.arena_break_mib,arena_map_mib=args.arena_map_mib,instructions=args.instructions)
    report=experiment.run();report['elapsed_seconds']=round(time.monotonic()-start,3)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('core_sha256','constructors_completed','stop','asset_stats','first_texture','elapsed_seconds') if k in report},indent=2),flush=True)
if __name__=='__main__':main()
