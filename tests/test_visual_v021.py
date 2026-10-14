"""Static release checks; not a substitute for testing PySide6 on Windows."""
from pathlib import Path
import ast
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VisualPackageChecks(unittest.TestCase):
    def test_assets_are_complete_pngs(self):
        for name in ('aurora_icon.png',):
            data = (ROOT / 'assets' / name).read_bytes()
            self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))
            width, height = struct.unpack('>II', data[16:24])
            self.assertGreaterEqual(width, 160)
            self.assertGreaterEqual(height, 160)
            self.assertTrue(data.endswith(b'IEND\xaeB`\x82'))

    def test_banner_full_resolution(self):
        data = (ROOT / 'assets' / 'aurora_banner.jpg').read_bytes()
        self.assertTrue(data.startswith(b'\xff\xd8\xff'))
        self.assertGreater(len(data), 100000)

    def test_responsive_editor_contract_is_present(self):
        # Parse Python to detect syntax errors and keep a regression assertion
        # for the main resize fix, even on CI systems without Qt installed.
        source = (ROOT / 'app' / 'ui.py').read_text(encoding='utf-8')
        ast.parse(source)
        self.assertIn('setMinimumSize(1060, min_height)', source)
        self.assertIn('self.editor_scroll = QScrollArea()', source)
        self.assertIn('self.editor_scroll.setWidgetResizable(True)', source)
        self.assertIn('self.editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)', source)
        self.assertIn('sidebar.setMinimumWidth(265)', source)
        self.assertIn('aurora_banner.jpg', source)
        self.assertIn('aurora_icon.png', source)


if __name__ == '__main__':
    unittest.main()