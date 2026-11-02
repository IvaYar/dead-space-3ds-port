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


class CleanPages(pages.Pages):
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
    args = ap.parse_args(); assert args.attempt.isalnum()
    d = P.parent / ('.local/native-loading-pages-tests-' + args.attempt)
    assert not d.exists(), 'Preserve previous fixture evidence'
    d.mkdir()
    candidate = P / '3ds/build-native-game-v0.1.7-loadclean'
    tree = ast.parse((P / 'tools/build_emulator_runtime.py').read_text())
    names = next(ast.literal_eval(n.value) for n in ast.walk(tree)
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets))
    sources = [candidate / n if n in ['ds15_textures.c', 'ds26_framebuffer.c'] else P / '3ds/source' / n for n in names]
    models = ['runtime_heap.c', 'runtime_os.c', 'stage6_stat_fixture.c', 'ds7_platform_model.c',
              'jni10_callbacks.c', 'ds11_platform_model.c', 'sensor_jni_model.c', 'arrays_model.c',
              'textures_model.c', 'pipeline_model.c']
    command = [str(base.GCC), *base.FLAGS, '-DDS7_SEMAPHORE_COUNT=64', '-I' + str(P / '3ds/include'),
               '-ffreestanding', '-fno-builtin', '-fno-unwind-tables', '-nostdlib',
               *map(str, sources), *[str(P / 'tests' / n) for n in models],
               '-Wl,-Ttext=0x00100000', '-Wl,-e,ds_elf_inspect',
               '-Wl,--start-group', '-lm', '-lc', '-lnosys', '-lgcc', '-Wl,--end-group', '-o', str(d / 'core-test.elf')]
    subprocess.run(command, check=True)
    shutil.copyfile(P / '3ds/build-emulator/fixture-stage8.so', d / 'fixture-stage8.so')
    pages.gl.jni.cpp.BUILD = d
    tests = [n for n in pages.Pages.__dict__ if n.startswith('test_')]
    tests += [n for n in CleanPages.__dict__ if n.startswith('test_')]
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(CleanPages(n) for n in tests))
    proof = {'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
             'errors': len(result.errors), 'failures': len(result.failures),
             'checks': tests, 'hardware_tested': False,
             'optimized_source_sha256': {n: sha(candidate / n) for n in ['ds15_textures.c', 'ds26_framebuffer.c']},
             'ELF_sha256': sha(d / 'core-test.elf')}
    (d / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
