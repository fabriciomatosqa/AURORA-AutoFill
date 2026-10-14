"""Smoke tests for the actual PySide6 widgets on a graphical or offscreen runner."""
import os
import tempfile
import unittest
from unittest.mock import patch


class InterfaceSmokeTests(unittest.TestCase):
    def test_visual_controls_credit_and_dropdown(self):
        if os.name != 'nt':
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        try:
            from PySide6.QtWidgets import QApplication
            from app.ui import AutoFillWindow, AuroraFolderCombo, AuroraWordmark
        except ImportError:
            self.skipTest('PySide6 ausente')
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix='aurora-test-') as tmp:
            with patch('app.ui.application_db_path', return_value=os.path.join(tmp, 'test.db')):
                with patch('app.ui.GlobalHotkeyListener.start', return_value=(False, 'Modo de teste')):
                    win = AutoFillWindow()
                    try:
                        self.assertIsInstance(win.filter_folder, AuroraFolderCombo)
                        self.assertIsInstance(win.editor_folder, AuroraFolderCombo)
                        self.assertTrue(win.findChildren(AuroraWordmark))
                        credit = win.statusBar().findChildren(type(win.edit_heading), 'developerCredit')
                        self.assertEqual(len(credit), 1)
                        self.assertIn('Fabricio Matos', credit[0].text())
                        self.assertGreaterEqual(win.filter_folder.count(), 2)
                        self.assertFalse(win.windowIcon().isNull())
                        win.filter_folder.showPopup()
                        app.processEvents()
                        menu = win.filter_folder._folder_menu
                        self.assertIsNotNone(menu)
                        self.assertEqual(len(menu.actions()), win.filter_folder.count())
                        if len(menu.actions()) > 1:
                            menu.actions()[1].trigger()
                            self.assertEqual(win.filter_folder.currentIndex(), 1)
                        menu.hide()
                    finally:
                        win._quitting = True
                        win.close()
        app.processEvents()


if __name__ == '__main__':
    unittest.main()