"""Security checks in a disposable Git index, never the real repository index."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

P = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication_guard', P/'tools/check_staged_private_files.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class StagedPrivacy(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='ds_publication_guard_')
        self.repo = Path(self.directory.name)
        self.git('init', '-q')

    def tearDown(self):
        # TemporaryDirectory is this test's own verified temp path, not project data.
        assert self.repo.resolve().parent == Path(tempfile.gettempdir()).resolve()
        assert self.repo.name.startswith('ds_publication_guard_') and not self.repo.is_junction()
        self.directory.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)

    def stage(self, name, data):
        path = self.repo/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.git('add', '-f', '--', name)
        return path

    def test_own_code_and_numerical_result_allowed(self):
        self.stage('porting/tools/example.py', b'print("test")\n')
        self.stage('porting/analysis/test/result.json', b'{"passed": true, "sha256": "abc"}\n')
        self.assertTrue(guard.check(self.repo)['passed'])

    def test_force_added_private_path_rejected(self):
        self.stage('.gitignore', b'.local/\n')
        self.stage('.local/resource-store/data.txt', b'private\n')
        self.assertFalse(guard.check(self.repo)['passed'])

    def test_text_license_allowed(self):
        self.stage('vendor/library/LICENSE', b'BSD 2-Clause License\nCopyright example\n')
        self.assertTrue(guard.check(self.repo)['passed'])

    def test_license_name_does_not_bypass_content_checks(self):
        for name, data in [('LICENSE', b'\x7fELFsynthetic'),
                           ('COPYING', b'MZsynthetic'),
                           ('NOTICE', b'PK\x03\x04synthetic')]:
            with self.subTest(name=name):
                reasons = guard.inspect_blob('vendor/library/'+name, data)
                self.assertTrue(any('content' in reason for reason in reasons))

    def test_staged_bytes_checked_after_worktree_replacement(self):
        path = self.stage('innocent.txt', b'\x7fELFsynthetic fixture, no real game data')
        path.write_bytes(b'safe-looking worktree\n')
        result = guard.check(self.repo)
        self.assertFalse(result['passed'])
        self.assertTrue(any('ELF' in reason for reason in result['rejected'][0]['reasons']))

    def test_renamed_zip_rejected(self):
        self.stage('backup.log', b'PK\x03\x04synthetic archive header')
        self.assertFalse(guard.check(self.repo)['passed'])

    def test_renamed_stack_dump_rejected(self):
        self.stage('summary.json', b'{"workers": [{"wait_stack": [1, 2]}]}')
        self.assertFalse(guard.check(self.repo)['passed'])

    def test_game_resource_extension_rejected(self):
        self.stage('model.m3g', b'synthetic data')
        self.assertFalse(guard.check(self.repo)['passed'])

    def test_asset_mutation_case_path_rejected(self):
        self.stage('porting/analysis/run/assets/published/data/achievements.sb', b'test')
        self.assertFalse(guard.check(self.repo)['passed'])

    def test_nested_object_snapshot_name_rejected(self):
        self.stage('porting/analysis/run/threads-after_pause.json', b'{}')
        self.assertFalse(guard.check(self.repo)['passed'])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StagedPrivacy))
    raise SystemExit(0 if result.wasSuccessful() else 1)
