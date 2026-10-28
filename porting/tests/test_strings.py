"""JNI UTF-16 and modified UTF-8 contracts executed as ARM code."""
import hashlib,json,struct,time,unittest
import test_jni10 as jni
from test_arm_loader import FILE_ADDR,INFO_ADDR,IMAGE_ADDR
DATA=0x06008400;COPY=0x06008700;REGION=0x06008800
def mutf(units):
    out=bytearray()
    for v in units:
        if 0<v<128:out.append(v)
        elif v<2048:out.extend((0xc0|(v>>6),0x80|(v&63)))
        else:out.extend((0xe0|(v>>12),0x80|((v>>6)&63),0x80|(v&63)))
    return bytes(out)
class StringTests(jni.Jni10Tests):
    def wide(self,units):
        if units:self.arm.uc.mem_write(DATA,struct.pack('<'+'H'*len(units),*units))
        return self.env(163,DATA,len(units))
    def utf(self,data):self.arm.uc.mem_write(DATA,data+b'\0');return self.env(167,DATA)
    def units(self,s,critical=False):
        n=self.env(164,s);p=self.env(224 if critical else 165,s,COPY)
        self.assertTrue(p);self.assertEqual(bytes(self.arm.uc.mem_read(COPY,1)),b'\0')
        out=struct.unpack('<'+'H'*n,self.arm.uc.mem_read(p,n*2));self.env(225 if critical else 166,s,p);return out
    def encoded(self,s):
        n=self.env(168,s);p=self.env(169,s,COPY);self.assertTrue(p);data=bytes(self.arm.uc.mem_read(p,n+1));self.env(170,s,p)
        self.assertEqual(data[-1:],b'\0');return data[:-1]
    def live_heap(self):self.arm.call('ds_runtime_stats',jni.OUT);return self.base.words(jni.OUT,9)[4:6]
    def test_zero_length_newstring_and_nonnull_empty_views(self):
        s=self.env(163,0,0);self.assertTrue(s);self.assertEqual(self.units(s),());self.assertEqual(self.encoded(s),b'')
    def test_embedded_nul_is_code_unit_and_modified_two_byte_sequence(self):
        s=self.wide((65,0,66));self.assertEqual(self.env(164,s),3);self.assertEqual(self.env(168,s),4)
        self.assertEqual(self.encoded(s),b'A\xc0\x80B');self.assertEqual(self.units(s),(65,0,66))
    def test_cyrillic_bmp_and_all_encoding_boundaries(self):
        u=(1,127,128,2047,2048,0x416,0x20ac,0xffff);s=self.wide(u)
        self.assertEqual(self.encoded(s),mutf(u));self.assertEqual(self.units(s),u)
    def test_surrogate_pair_and_lone_surrogates_remain_code_units(self):
        u=(0xd83d,0xde80,0xd800,0xdc00);s=self.wide(u);self.assertEqual(self.env(164,s),4)
        self.assertEqual(self.encoded(s),mutf(u));self.assertEqual(self.units(s),u)
    def test_newstringutf_decodes_canonical_modified_encoding(self):
        u=(0,0x416,0xd83d,0xde80);s=self.utf(mutf(u));self.assertEqual(self.units(s),u);self.assertEqual(self.encoded(s),mutf(u))
    def test_malformed_or_standard_four_byte_utf8_rejects_without_leaks(self):
        for data in (b'\x80',b'\xc0\x81',b'\xc1\xbf',b'\xc2',b'\xe0\x80\x80',b'\xed\x20\x80',b'\xf0\x9f\x9a\x80'):
            self.assertEqual(self.utf(data),0);self.assertTrue(self.exception());self.clear();self.assertEqual(self.live_heap(),(0,0))
    def test_newstring_copies_input_and_borrowed_storage_is_stable(self):
        s=self.wide((1,2,3));p=self.env(165,s,0);self.arm.uc.mem_write(DATA,b'Z'*6)
        self.assertEqual(bytes(self.arm.uc.mem_read(p,6)),b'\1\0\2\0\3\0');self.env(166,s,p)
    def test_encoded_byte_limit_and_utf16_length_bounds(self):
        a=self.wide((65,)*255);self.assertTrue(a);self.delete(a)
        a=self.wide((0x20ac,)*85);self.assertTrue(a);self.delete(a)
        self.assertEqual(self.wide((0x20ac,)*86),0);self.clear()
        for ptr,n in ((DATA,-1),(DATA,256),(0,1),(DATA+1,1),(0xfffffffe,2)):
            self.assertEqual(self.env(163,ptr,n),0);self.assertTrue(self.exception());self.clear()
        self.assertEqual(self.live_heap(),(0,0))
    def test_pool_exhaustion_and_recovery_after_last_reference_deleted(self):
        refs=[self.wide((i,)) for i in range(8)];self.assertNotIn(0,refs);self.assertEqual(self.wide((9,)),0);self.clear()
        self.delete(refs[0]);self.assertTrue(self.wide((10,)))
    def test_allocation_failure_is_atomic_and_recovers(self):
        self.assertEqual(self.arm.call('ds_runtime_init',1),0);self.assertEqual(self.wide(()),0);self.assertTrue(self.exception())
        self.assertEqual(self.live_heap(),(0,0));self.clear();self.assertEqual(self.arm.call('ds_runtime_init',1048576),0);self.assertTrue(self.wide(()))
    def test_reference_capacity_failure_reclaims_allocated_payload(self):
        for _ in range(128):self.assertTrue(self.find('java/io/InputStream'))
        self.assertEqual(self.wide((65,)),0);self.assertTrue(self.exception());self.assertEqual(self.live_heap(),(0,0))
    def test_independent_utf_and_utf16_pin_release_families(self):
        s=self.wide((65,));p=self.env(165,s,0);u=self.env(169,s,0)
        self.env(170,s,p);self.assertTrue(self.exception());self.clear();self.env(166,s,u);self.assertTrue(self.exception());self.clear()
        self.env(170,s,u);self.env(166,s,p);self.delete(s);self.assertEqual(self.live_heap(),(0,0))
    def test_global_alias_keeps_both_representations_alive(self):
        s=self.wide((0,0x416));g=self.env(21,s);self.delete(s);self.assertEqual(self.units(g),(0,0x416));self.delete(g,True);self.assertEqual(self.live_heap(),(0,0))
    def test_nested_local_frames_escape_and_cleanup_string_payloads(self):
        self.env(19,4);a=self.wide((65,0));self.env(19,4);b=self.wide((0x416,));self.assertEqual(self.env(20,b),b)
        self.assertEqual(self.units(b),(0x416,));self.env(20,0);self.assertEqual(self.live_heap(),(0,0))
        self.assertEqual(self.env(164,a),0);self.assertTrue(self.exception())
    def test_frame_pop_reclaims_handles_but_preserves_borrowed_utf16_storage(self):
        self.env(19,4);s=self.wide((65,));p=self.env(165,s,0);self.env(20,0);self.assertFalse(self.exception())
        self.assertEqual(bytes(self.arm.uc.mem_read(p,2)),b'A\0');self.assertGreater(self.live_heap()[0],0)
        self.assertEqual(self.env(164,s),0);self.assertTrue(self.exception());self.clear()
        self.arm.call('ds10_cleanup',jni.CTX);self.assertEqual(self.live_heap(),(0,0))
    def test_pop_with_global_alias_allows_release_through_surviving_reference(self):
        self.env(19,4);s=self.wide((65,0,0x416));g=self.env(21,s);p=self.env(169,s,0)
        self.env(20,0);self.assertFalse(self.exception());self.assertEqual(bytes(self.arm.uc.mem_read(p,6)),b'A\xc0\x80\xd0\x96\0')
        self.env(170,g,p);self.assertFalse(self.exception());self.delete(g,True);self.assertEqual(self.live_heap(),(0,0))
    def test_all_borrow_families_survive_last_reference_deletion_and_pool_pressure(self):
        s=self.wide((0x416,));p=self.env(165,s,0);u=self.env(169,s,0);q=self.env(224,s,0)
        self.delete(s);self.assertFalse(self.exception())
        refs=[self.wide((n,)) for n in range(7)];self.assertNotIn(0,refs)
        self.assertEqual(bytes(self.arm.uc.mem_read(p,2)),b'\x16\x04');self.assertEqual(p,q)
        self.assertEqual(bytes(self.arm.uc.mem_read(u,3)),b'\xd0\x96\0')
        self.assertEqual(self.wide((99,)),0);self.assertTrue(self.exception());self.clear()
        self.arm.call('ds10_cleanup',jni.CTX);self.assertEqual(self.live_heap(),(0,0))
    def test_regions_use_code_units_and_do_not_write_terminators(self):
        u=(65,0,0x416,0xd83d,0xde80);s=self.wide(u);self.arm.uc.mem_write(REGION,b'Z'*32)
        self.env(220,s,1,3,REGION);self.assertEqual(bytes(self.arm.uc.mem_read(REGION,8)),struct.pack('<3H',*u[1:4])+b'ZZ')
        self.arm.uc.mem_write(REGION,b'Z'*32);self.env(221,s,1,3,REGION);want=mutf(u[1:4]);self.assertEqual(bytes(self.arm.uc.mem_read(REGION,len(want)+1)),want+b'Z')
    def test_bad_region_ranges_keep_outputs_unchanged(self):
        s=self.wide((65,66));self.arm.uc.mem_write(REGION,b'Z'*32)
        for slot in (220,221):
            for start,n in ((-1,1),(1,2),(0,-1),(0x7fffffff,1)):
                self.env(slot,s,start,n,REGION);self.assertTrue(self.exception());self.clear()
            self.assertEqual(bytes(self.arm.uc.mem_read(REGION,32)),b'Z'*32);self.env(slot,s,2,0,0);self.assertFalse(self.exception())
    def test_critical_borrow_has_its_own_release_and_lifetime(self):
        s=self.wide((0,0x416));p=self.env(224,s,0);self.env(166,s,p);self.assertTrue(self.exception());self.clear()
        self.env(225,s,p);self.assertFalse(self.exception());self.delete(s);self.assertEqual(self.live_heap(),(0,0))
    def test_stale_and_foreign_string_handles_are_rejected(self):
        s=self.wide((65,));other=jni.CTX+0x2000;self.arm.call('ds10_init',other,0,0)
        self.assertEqual(self.env(164,s,context=other),0);self.arm.call('ds10_cleanup',other)
        self.delete(s);self.assertEqual(self.env(165,s,0),0);self.assertTrue(self.exception())
    def test_cleanup_reclaims_pinned_utf16_utf8_and_critical_views(self):
        s=self.wide((65,0));self.env(165,s,0);self.env(169,s,0);self.env(224,s,0)
        self.arm.call('ds10_cleanup',jni.CTX);self.assertEqual(self.live_heap(),(0,0))
    def test_codec_failures_do_not_partially_write_output(self):
        self.arm.uc.mem_write(DATA,b'\xc2A');self.arm.uc.mem_write(REGION,b'Z'*16)
        self.assertEqual(self.arm.call('ds18_decode',DATA,2,REGION,8),0xffffffff);self.assertEqual(bytes(self.arm.uc.mem_read(REGION,16)),b'Z'*16)
        self.arm.uc.mem_write(DATA,struct.pack('<H',0x20ac));self.assertEqual(self.arm.call('ds18_encode',DATA,1,REGION,2),0xffffffff);self.assertEqual(bytes(self.arm.uc.mem_read(REGION,16)),b'Z'*16)
    def test_original_softfp_string_fixture(self):
        blob=(jni.BUILD/'fixture-strings.so').read_bytes();self.base.prepare(blob)
        self.assertEqual(self.arm.call('ds_elf_resolve',FILE_ADDR,INFO_ADDR,IMAGE_ADDR,0,0,jni.OUT),0)
        self.assertEqual(self.base.invoke(blob,'probe_strings',jni.CTX,jni.OUT),0)
        failure,checks,units,bytes_=self.base.words(jni.OUT,4);self.assertEqual(failure,0);self.assertGreater(checks,30);self.assertEqual((units,bytes_),(7,17));self.assertEqual(self.live_heap(),(0,0))
if __name__=='__main__':
    started=time.monotonic();names=[n for n in StringTests.__dict__ if n.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(StringTests(n) for n in names))
    report={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'hardware_tested':False,
        'core_sha256':hashlib.sha256((jni.BUILD/'core-test.elf').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256((jni.BUILD/'fixture-strings.so').read_bytes()).hexdigest(),'elapsed_seconds':round(time.monotonic()-started,3)}
    (jni.cpp.PORTING/'analysis/strings-tests.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
