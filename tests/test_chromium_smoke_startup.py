"""The native smoke waits for Chrome to finish writing DevToolsActivePort."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock


class ChromiumStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/'packaging/smoke_web_expansion.py'
        spec=importlib.util.spec_from_file_location('aurora_chromium_smoke',path)
        cls.smoke=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.smoke)

    def test_missing_locked_and_partial_files_are_retried_until_complete(self):
        path=Mock()
        path.read_text.side_effect=[FileNotFoundError(),PermissionError(),'',
            '49213\n','49213\n/devtools/browser/fixture-id\n']
        self.assertEqual([self.smoke.read_devtools_port(path) for _ in range(5)],
                         [None,None,None,None,49213])

    def test_invalid_ports_and_unfinished_endpoints_are_not_ready(self):
        for content in ('0\n/devtools/browser/fixture','65536\n/devtools/browser/fixture',
                        'incomplete\n/devtools/browser/fixture','49213\n/devtools/',
                        '49213\n/devtools/browser/','49213\n'):
            with self.subTest(content=content):
                path=Mock();path.read_text.return_value=content
                self.assertIsNone(self.smoke.read_devtools_port(path))


if __name__=='__main__':
    unittest.main()
