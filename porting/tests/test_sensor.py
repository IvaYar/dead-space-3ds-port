"""Actual ARM sampler and separately compiled Android softfp callback tests."""
import hashlib,json,struct,time,unittest
from test_arm_loader import ARMCore,PORTING,segments,symbols
from unicorn.arm_const import UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC
BUILD=PORTING/'3ds/build-sensor';CAL=0x06008000;OUT=0x06009000
class SensorTests(unittest.TestCase):
    def setUp(self):
        self.arm=ARMCore(b'\0',BUILD/'sensor-test.elf');self.arm.uc.mem_map(0x06000000,65536)
        self.arm.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000);self.arm.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        self.call('sensor_test_reset');self.cal();self.assertEqual(self.call('sensor_test_init',CAL),0)
    def call(self,name,*args):return self.arm.call(name,*(v&0xffffffff for v in args))
    def cal(self,axes=(1,2,3),bias=(0,0,0),scale=(512,512,512)):
        self.arm.uc.mem_write(CAL,struct.pack('<3bx6f',*axes,*bias,*scale))
    def poll(self,t):return self.call('sensor_test_poll',t&0xffffffff,t>>32)
    def output(self):return struct.unpack('<3f',self.arm.uc.mem_read(self.call('sensor_test_output'),12))
    def test_gravity_and_zero_are_converted_in_si_units(self):
        self.call('sensor_test_enable',1);self.call('sensor_test_raw',0,512,-512);self.assertEqual(self.poll(0),1)
        for a,b in zip(self.output(),(0,9.80665,-9.80665)):self.assertAlmostEqual(a,b,places=5)
    def test_axis_sign_permutation_bias_and_independent_scales(self):
        self.cal((-2,3,1),(10,20,30),(512,1024,256));self.assertEqual(self.call('sensor_test_init',CAL),0)
        self.call('sensor_test_raw',522,1044,286);self.call('sensor_test_enable',1);self.poll(0)
        for a,b in zip(self.output(),(-9.80665,9.80665,9.80665)):self.assertAlmostEqual(a,b,places=5)
    def test_bad_calibration_does_not_replace_valid_state(self):
        for axes in ((0,2,3),(1,1,3),(1,2,4),(-128,2,3)):
            self.cal(axes);self.assertEqual(self.call('sensor_test_init',CAL),0xffffffff)
        for value in (0,-1,float('nan'),float('inf'),1e-30):
            self.cal(scale=(value,512,512));self.assertEqual(self.call('sensor_test_init',CAL),0xffffffff)
        for value in (32769,float('nan'),float('inf')):
            self.cal(bias=(value,0,0));self.assertEqual(self.call('sensor_test_init',CAL),0xffffffff)
        self.assertEqual(self.call('sensor_test_enable',1),0);self.assertEqual(self.poll(0),1)
    def test_enable_is_idempotent_and_init_refuses_active_state(self):
        self.assertEqual(self.call('sensor_test_enable',1),0);self.assertEqual(self.call('sensor_test_enable',1),0)
        self.assertEqual(self.call('sensor_test_enable_calls'),1);self.assertEqual(self.call('sensor_test_init',CAL),0xffffffff)
        self.assertEqual(self.call('sensor_test_enable',2),0xffffffff)
    def test_enable_failure_preserves_disabled_state(self):
        self.call('sensor_test_backend',1,1);self.assertEqual(self.call('sensor_test_enable',1),0xfffffffe)
        self.assertEqual(self.call('sensor_test_enabled'),0);self.assertEqual(self.poll(0),0);self.assertEqual(self.call('sensor_test_read_calls'),0)
    def test_disable_failure_retains_ownership_and_close_can_retry(self):
        self.call('sensor_test_enable',1);self.call('sensor_test_backend',1,1)
        self.assertEqual(self.call('sensor_test_close'),0xfffffffe);self.assertEqual(self.call('sensor_test_enabled'),1)
        self.call('sensor_test_backend',0,1);self.assertEqual(self.call('sensor_test_close'),0);self.assertEqual(self.call('sensor_test_enabled'),0)
    def test_delivery_rate_limits_reads_and_handles_frequency_change(self):
        self.call('sensor_test_enable',1);self.assertEqual(self.poll(0),1);self.assertEqual(self.poll(49999),0);self.assertEqual(self.poll(50000),1)
        self.assertEqual(self.call('sensor_test_read_calls'),2)
        for hz in (0,201,0xffffffff):self.assertEqual(self.call('sensor_test_rate',hz),0xffffffff)
        self.assertEqual(self.call('sensor_test_rate',100),0);self.assertEqual(self.poll(50001),1)
    def test_read_failure_or_unavailable_sample_preserves_output(self):
        self.call('sensor_test_enable',1);self.call('sensor_test_raw',512,0,0);self.poll(0);before=self.output()
        for status,expected in ((0,0),(-1,0xfffffffe),(2,0xfffffffe)):
            self.call('sensor_test_backend',0,status);self.assertEqual(self.poll(50000),expected);self.assertEqual(self.output(),before)
    def test_clock_rollback_is_rejected_without_read(self):
        self.call('sensor_test_enable',1);self.poll(100000);self.assertEqual(self.poll(99999),0xffffffff);self.assertEqual(self.call('sensor_test_read_calls'),1)
    def test_uint64_boundary_does_not_wrap_deadline(self):
        self.call('sensor_test_enable',1);self.assertEqual(self.poll((1<<64)-50001),1);self.assertEqual(self.poll((1<<64)-1),1)
    def test_raw_int16_extremes_remain_finite(self):
        self.call('sensor_test_raw',-32768,32767,0);self.call('sensor_test_enable',1);self.poll(0)
        self.assertAlmostEqual(self.output()[0],-64*9.80665,places=3)
    def test_android_named_delays_use_gingerbread_microseconds(self):
        self.call('sensor_test_enable',1)
        for delay,interval in ((1,20000),(2,60000),(3,200000),(2500000,2500000)):
            self.assertEqual(self.call('sensor_test_android_delay',delay),0);self.assertEqual(self.poll(0),1)
            self.assertEqual(self.poll(interval-1),0);self.assertEqual(self.poll(interval),1)
            self.call('sensor_test_enable',0);self.call('sensor_test_enable',1)
    def test_android_fastest_and_negative_delay(self):
        self.call('sensor_test_enable',1);self.assertEqual(self.call('sensor_test_android_delay',0),0)
        self.assertEqual(self.poll(0),1);self.assertEqual(self.poll(0),1)
        self.assertEqual(self.call('sensor_test_android_delay',-1),0xffffffff)
        self.assertEqual(self.poll(1),1)
    def test_softfp_callback_receives_handles_and_three_floats(self):
        blob=(BUILD/'fixture-sensor.so').read_bytes();base=0x40000000;self.arm.uc.mem_map(base,65536)
        for p in segments(blob):
            if p[0]==1 and p[4]:self.arm.uc.mem_write(base+p[2],blob[p[1]:p[1]+p[4]])
        exports,_=symbols(blob);self.call('sensor_test_raw',512,-512,256);self.call('sensor_test_enable',1)
        self.assertEqual(self.call('sensor_test_dispatch',0,0,base+exports['probe_acceleration']),1)
        env,obj,x,y,z,count=struct.unpack('<IIfffI',self.arm.uc.mem_read(OUT,24));self.assertEqual((env,obj,count),(0x12345678,0x87654321,1))
        for a,b in zip((x,y,z),(9.80665,-9.80665,4.903325)):self.assertAlmostEqual(a,b,places=5)
if __name__=='__main__':
    start=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SensorTests))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,'game_adapter_enabled':False,
        'elapsed_seconds':round(time.monotonic()-start,3),'core_sha256':hashlib.sha256((BUILD/'sensor-test.elf').read_bytes()).hexdigest(),
        'fixture_sha256':hashlib.sha256((BUILD/'fixture-sensor.so').read_bytes()).hexdigest()}
    (PORTING/'analysis/sensor-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
