"""Package gate tests: temporary fixture trees, no local executable builds."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('aurora_verify_bundle', ROOT / 'packaging/verify_bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class PackagingTests(unittest.TestCase):
    def fixture(self, directory, platform):
        dist = Path(directory) / 'application'
        assets = dist / '_internal/assets'
        assets.mkdir(parents=True)
        for name in bundle.ASSETS:
            shutil.copy2(ROOT / 'assets' / name, assets / name)
        executable = 'AURORA AutoFill.exe' if platform == 'windows' else 'AURORA AutoFill'
        (dist / executable).write_bytes(b'synthetic-test-only')
        plugin = 'qwindows.dll' if platform == 'windows' else 'libqxcb.so'
        plugins = dist / '_internal/PySide6/plugins/platforms'
        plugins.mkdir(parents=True)
        (plugins / plugin).write_bytes(b'synthetic-test-only')
        if platform == 'windows':
            (dist / '_internal/app').mkdir()
            shutil.copy2(ROOT / 'app/accessibility_worker.ps1', dist / '_internal/app/accessibility_worker.ps1')
        return dist

    def test_complete_windows_and_linux_resource_layout(self):
        for platform in ('windows', 'linux'):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                result = bundle.verify_bundle(self.fixture(temporary, platform), platform)
                self.assertEqual(result['local_data_scan'], 'passed')
                self.assertEqual(len(result['resources_sha256']), 7 if platform == 'windows' else 6)

    def test_windows_requires_worker_at_runtime_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            dist = self.fixture(temporary, 'windows')
            (dist / '_internal/app/accessibility_worker.ps1').unlink()
            with self.assertRaisesRegex(ValueError, 'Worker UIA'):
                bundle.verify_bundle(dist, 'windows')

    def test_missing_or_modified_visual_resource_and_qt_plugin_fail(self):
        for target in ('assets/aurora_banner.jpg', 'assets/command_click.wav',
                       'PySide6/plugins/platforms/qwindows.dll'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                dist = self.fixture(temporary, 'windows')
                (dist / '_internal' / target).unlink()
                with self.assertRaises(ValueError):
                    bundle.verify_bundle(dist, 'windows')
        with tempfile.TemporaryDirectory() as temporary:
            dist = self.fixture(temporary, 'windows')
            (dist / '_internal/assets/aurora_banner.jpg').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                bundle.verify_bundle(dist, 'windows')

    def test_personal_data_caches_and_private_keys_reject_bundle(self):
        for name, contents in (('qa/local.json', b'{}'), ('snippets.sqlite3', b'data'),
                               ('debug.log', b'data'), ('.env', b'SECRET=example'),
                               ('__pycache__/module.pyc', b'data'),
                               ('private.pem', b'-----BEGIN PRIVATE KEY-----')):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                dist = self.fixture(temporary, 'linux')
                path = dist / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
                with self.assertRaises(ValueError):
                    bundle.verify_bundle(dist, 'linux')
