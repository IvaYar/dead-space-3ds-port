"""Exploratory ARM execution of donor worker initialization slices.

Each worker executes its own ARM context and TLS on a separate stack until its
first native sleep. Parent resumes afterwards. CV waits stop explicitly;
this is not a general pthread scheduler and cannot replace native Azahar tests.
"""
import json,time,struct
from run_engine_experiment import Experiment,PORTING,REGS,TRAPS
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_LR,UC_ARM_REG_SP,UC_ARM_REG_R0
class WorkerExperiment(Experiment):
    def __init__(self):
        self.worker=None;self.workers=[];self.active_worker=False;self.main_cpu=None
        super().__init__(PORTING/'3ds/build-emulator/core-test.elf',graphics=True,arena_break_mib=20,arena_map_mib=80,instructions=500_000_000)
        self.selector=self.arm.call('ds7_test_tls_selector_address')
        self.uc.mem_map(0x19000000,0x40000)
        pc=self.arm.exports['ds7_platform_yield'];self.uc.hook_add(UC_HOOK_CODE,self.yield_parent,begin=pc,end=pc)
        for name in ('ds7_cv_wait','ds7_native_join'):
            pc=self.arm.exports[name];self.uc.hook_add(UC_HOOK_CODE,self.unsupported_schedule(name),begin=pc,end=pc)
        self.report['worker_model']='ARM worker initial slices on distinct stacks/TLS; suspend at first sleep; CV waits stop; not a general scheduler'
        self.report['cooperative_workers']=self.workers
    def unsupported_schedule(self,name):
        def callback(uc,address,size,data):self.snapshot('unsupported_worker_schedule',name)
        return callback
    def boundary(self,name):
        fallback=super().boundary(name)
        def callback(uc,address,size,data):
            if name=='ds7_spawn':
                if len(self.workers)==16:self.snapshot('unsupported_worker_schedule','worker capacity');return
                entry,arg,stack=(uc.reg_read(r) for r in REGS[:3]);self.worker={'entry':entry,'argument':arg,'stack_bytes':stack}
                if stack>0x40000:self.snapshot('unsupported_worker_schedule','worker stack capacity');return
                self.worker['tls']=len(self.workers)+1;self.worker['started']=False;self.workers.append(self.worker)
                if len(self.workers)>1:self.uc.mem_map(0x19000000+(len(self.workers)-1)*0x40000,0x40000)
                self.report['cooperative_worker']=self.worker
                uc.reg_write(UC_ARM_REG_R0,0x51510000+len(self.workers)*4);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
            if name=='ds6_native_sleep' and self.active_worker:
                ptr=uc.reg_read(UC_ARM_REG_R0);sec,nsec=self.words(ptr,2)
                if sec>60 or nsec>=1_000_000_000:self.snapshot('unsupported_worker_schedule','invalid worker sleep');return
                self.worker['sleep_ns']=sec*1_000_000_000+nsec
                self.worker['executed_to_sleep']=True;self.active_worker=False
                self.write(self.selector,0);uc.context_restore(self.main_cpu);return
            fallback(uc,address,size,data)
        return callback
    def yield_parent(self,uc,address,size,data):
        if not self.worker or self.worker['started'] or self.active_worker:return
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));self.main_cpu=uc.context_save()
        self.active_worker=True;self.worker['started']=True;self.write(self.selector,self.worker['tls'])
        uc.reg_write(UC_ARM_REG_SP,0x19000000+self.worker['tls']*0x40000-16);uc.reg_write(UC_ARM_REG_LR,TRAPS+0xbf00)
        uc.reg_write(UC_ARM_REG_R0,self.worker['argument']);uc.reg_write(UC_ARM_REG_PC,self.worker['entry'])
if __name__=='__main__':
    start=time.monotonic();e=WorkerExperiment();d=e.run();d['elapsed_seconds']=round(time.monotonic()-start,3)
    (PORTING/'analysis/engine-worker-experiment.json').write_text(json.dumps(d,indent=2)+'\n')
    print(json.dumps({k:d[k] for k in ('stop','cooperative_worker','graphics_stats','texture_stats','elapsed_seconds') if k in d},indent=2))
