"""Package gate tests: temporary fixture trees, no local executable builds."""
import importlib.util
from contextlib import closing, contextmanager
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('aurora_verify_bundle', ROOT / 'packaging/verify_bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)
smoke_spec = importlib.util.spec_from_file_location('aurora_smoke_frozen', ROOT / 'packaging/smoke_frozen.py')
smoke = importlib.util.module_from_spec(smoke_spec)
smoke_spec.loader.exec_module(smoke)


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


class FrozenSmokeTests(unittest.TestCase):
    def run_smoke(self, corrupt=False):
        connect = sqlite3.connect
        temporary_directory = tempfile.TemporaryDirectory
        connections = []
        cleaned = []
        launches = []

        class TrackedConnection(sqlite3.Connection):
            closed = False
            def close(self):
                self.closed = True
                return super().close()

        def tracked_connect(path):
            connection = connect(path, factory=TrackedConnection)
            connections.append(connection)
            return connection

        @contextmanager
        def profile(**kwargs):
            with temporary_directory(**kwargs) as path:
                try:
                    yield path
                finally:
                    all_closed = all(connection.closed for connection in connections)
                    # Release fixture handles even when exercising a broken implementation.
                    for connection in connections:
                        if not connection.closed:
                            connection.close()
                    self.assertTrue(all_closed, 'SQLite must close before profile cleanup')
            cleaned.append(True)

        def launch(_args, **kwargs):
            self.assertTrue(all(connection.closed for connection in connections))
            database = Path(kwargs['env']['APPDATA']) / 'AutoFillStudio/snippets.sqlite3'
            database.parent.mkdir(parents=True, exist_ok=True)
            with closing(connect(database)) as connection, connection:
                if not launches:
                    connection.executescript('CREATE TABLE folders(id INTEGER PRIMARY KEY, name TEXT);'
                                             'CREATE TABLE snippets(folder_id INTEGER, title TEXT, '
                                             'shortcut TEXT, content TEXT, rich_content TEXT);')
                elif corrupt:
                    connection.execute('DELETE FROM snippets')
            launches.append(True)
            return Mock(returncode=0)

        with temporary_directory() as path:
            executable = Path(path) / 'synthetic.exe'
            executable.write_bytes(b'not executed')
            with patch.object(smoke.sqlite3, 'connect', side_effect=tracked_connect), \
                 patch.object(smoke.tempfile, 'TemporaryDirectory', side_effect=profile), \
                 patch.object(smoke.subprocess, 'run', side_effect=launch), \
                 patch.object(smoke.sys, 'argv', ['smoke', '--exe', str(executable)]), \
                 patch('builtins.print') as printed:
                if corrupt:
                    with self.assertRaises(SystemExit):
                        smoke.main()
                    printed.assert_not_called()
                else:
                    def success(*_args):
                        self.assertEqual(cleaned, [True], 'Success must follow profile cleanup')
                    printed.side_effect = success
                    smoke.main()
                    printed.assert_called_once()
        self.assertEqual(len(launches), 2)
        self.assertEqual(len(connections), 2)
        self.assertTrue(all(connection.closed for connection in connections))

    def test_connections_close_before_relaunch_and_cleanup(self):
        self.run_smoke()

    def test_preservation_failure_still_closes_connections_without_false_success(self):
        self.run_smoke(corrupt=True)
