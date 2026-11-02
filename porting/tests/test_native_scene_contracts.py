"""Run real ARM pager/FBO mutation contracts against isolated optimized sources."""
import argparse
import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / 'tools'))
import build_stage1 as base
from azahar_resource_store import sha
import test_texture_pages as pages
import test_framebuffers as fb
import test_first_frame as draw
import test_jni10 as jni


class SceneAudio(jni.Jni10Tests):
    def test_short_elements_units_and_typed_regions(self):
        a=self.env(178,8);self.assertTrue(a);self.assertEqual(self.env(171,a),8)
        self.arm.uc.mem_write(jni.OUT,b'abcdefghijklmnop')
        self.env(210,a,0,8,jni.OUT);self.assertFalse(self.exception())
        p=self.env(186,a,0);self.assertEqual(bytes(self.arm.uc.mem_read(p,16)),b'abcdefghijklmnop')
        self.arm.uc.mem_write(p,b'AB');self.env(194,a,p,0)
        self.env(210,a,7,2,jni.OUT);self.assertTrue(self.exception());self.clear()
        self.env(208,a,0,1,jni.OUT);self.assertTrue(self.exception());self.clear()
        b=self.env(176,16);self.env(210,b,0,1,jni.OUT);self.assertTrue(self.exception());self.clear()
        p=self.env(186,a,0);self.assertEqual(bytes(self.arm.uc.mem_read(p,16)),b'ABcdefghijklmnop');self.env(194,a,p,2)

    def test_pcm_sink_validates_bounds_and_play_state(self):
        cls=self.find('android/media/AudioTrack');track=self.arm.call('scene_audio_track',jni.CTX)
        play=self.method(cls,'play','()V');stop=self.method(cls,'stop','()V');write=self.method(cls,'write','([SII)I')
        a=self.env(178,8);self.env(63,track,play,0)
        self.assertEqual(self.env(51,track,write,self.values(a,0,8)),8)
        self.assertEqual(self.env(51,track,write,self.values(a,0,9)),0xfffffffe);self.assertTrue(self.exception());self.clear()
        self.env(63,track,stop,0);self.assertEqual(self.env(51,track,write,self.values(a,0,8)),0xfffffffd)

    def test_vm_detach_entry_is_callable(self):
        self.assertEqual(self.env(219,jni.OUT),0);vm=self.base.words(jni.OUT)[0]
        table=self.base.words(vm)[0];detach=self.base.words(table+5*4)[0];self.assertTrue(detach)
        self.arm.exports['_detach']=detach;self.assertEqual(self.arm.call('_detach',vm),0)


class CleanPages(pages.Pages):
    def test_allocator_pressure_spills_an_extra_page_without_losing_pixels(self):
        from unicorn import UC_HOOK_CODE
        from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_PC,UC_ARM_REG_LR
        a,b=[self.image(i) for i in [10,20]];failed=[]
        def refuse_once(uc,address,size,user):
            if not failed and uc.reg_read(UC_ARM_REG_R0)==32:
                failed.append(True);uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        address=self.arm.exports['malloc'];hook=self.arm.uc.hook_add(UC_HOOK_CODE,refuse_once,begin=address,end=address)
        try:c=self.image(30)
        finally:self.arm.uc.hook_del(hook)
        self.assertTrue(failed);self.assertEqual(self.call('glGetError'),0)
        for t,v in [(a,10),(b,20),(c,30)]:self.assertEqual(self.pixel(t),bytes([v,v+1,v+2,v+3]))

    def test_repeated_read_only_evictions_reuse_exact_backing(self):
        names = [self.image(i) for i in [10, 20, 30]]
        for t in names:
            self.pixel(t)
        saves = self.stats()[2]
        for _ in range(3):
            for t, v in zip(names, [10, 20, 30]):
                self.assertEqual(self.pixel(t), bytes([v, v + 1, v + 2, v + 3]))
        self.assertEqual(self.stats()[2], saves)
        self.assertGreater(self.stats()[3], 6)

    def test_FBO_draw_after_clean_reload_invalidates_old_page(self):
        a, b, c = [self.image(i) for i in [10, 20, 30]]
        self.pixel(a)
        self.fbo(); self.attach(a)
        self.call('glViewport', 0, 0, 2, 2)
        self.rgba(0, 0, 1, 1); self.quad_at()
        self.call('glBindFramebufferOES', fb.FB, 0)
        self.pixel(b); self.pixel(c)
        self.assertEqual(self.pixel(a), bytes([0, 0, 255, 255]))

    def test_replacement_drops_retained_snapshot(self):
        a, b, c = [self.image(i) for i in [10, 20, 30]]
        self.pixel(a)
        self.call('glBindTexture', fb.T, a)
        self.call('glTexImage2D', fb.T, 0, 0x1908, 2, 2, 0, 0x1908, 0x1401, 0)
        self.pixel(b); self.pixel(c)
        self.assertEqual(self.pixel(a), b'\0' * 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--attempt', required=True)
    ap.add_argument('--scene-build', default='scene14')
    args = ap.parse_args(); assert args.attempt.isalnum()
    d = P.parent / ('.local/native-scene-contracts-' + args.attempt)
    assert not d.exists(), 'Preserve previous fixture evidence'
    d.mkdir()
    candidate = P / ('3ds/build-native-game-v0.1.7-' + args.scene_build)
    tree = ast.parse((P / 'tools/build_emulator_runtime.py').read_text())
    names = next(ast.literal_eval(n.value) for n in ast.walk(tree)
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets))
    sources = [candidate / n if n in ['ds15_textures.c', 'ds26_framebuffer.c','ds10_jni.c','ds22_draw.c'] else P / '3ds/source' / n for n in names]
    models = ['runtime_heap.c', 'runtime_os.c', 'stage6_stat_fixture.c', 'ds7_platform_model.c',
              'jni10_callbacks.c', 'ds11_platform_model.c', 'sensor_jni_model.c', 'arrays_model.c',
              'textures_model.c', 'pipeline_model.c']
    command = [str(base.GCC), *base.FLAGS, '-DDS7_SEMAPHORE_COUNT=64', '-I' + str(P / '3ds/include'), '-I'+str(candidate),
               '-ffreestanding', '-fno-builtin', '-fno-unwind-tables', '-nostdlib',
               *map(str, sources), *[str(P / 'tests' / n) for n in models],
               '-Wl,-Ttext=0x00100000', '-Wl,-e,ds_elf_inspect',
               '-Wl,--start-group', '-lm', '-lc', '-lnosys', '-lgcc', '-Wl,--end-group', '-o', str(d / 'core-test.elf')]
    subprocess.run(command, check=True)
    shutil.copyfile(P / '3ds/build-emulator/fixture-stage8.so', d / 'fixture-stage8.so')
    pages.gl.jni.cpp.BUILD = d
    tests = [n for n in pages.Pages.__dict__ if n.startswith('test_')]
    tests += [n for n in CleanPages.__dict__ if n.startswith('test_')]
    suite=unittest.TestSuite(CleanPages(n) for n in tests)
    audio_tests=[n for n in SceneAudio.__dict__ if n.startswith('test_')]
    suite.addTests(SceneAudio(n) for n in audio_tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    proof = {'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
             'errors': len(result.errors), 'failures': len(result.failures),
             'checks': tests+audio_tests, 'hardware_tested': False,
             'optimized_source_sha256': {n: sha(candidate / n) for n in ['ds15_textures.c', 'ds26_framebuffer.c']},
             'ELF_sha256': sha(d / 'core-test.elf')}
    (d / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
