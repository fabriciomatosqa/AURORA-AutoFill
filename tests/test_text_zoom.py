"""Regressões do controle de zoom visual do AURORA AutoFill."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TextZoomTests(unittest.TestCase):
    def test_editor_zoom_is_visual_only_and_persists(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import QSettings
            from PySide6.QtWidgets import QApplication
            from app.ui import AutoFillWindow
        except ImportError:
            self.skipTest("PySide6 indisponível")

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix="aurora-zoom-") as temp:
            database = Path(temp) / "snippets.sqlite3"
            settings_file = Path(temp) / "zoom.ini"

            def mock_settings(*args):
                return QSettings(str(settings_file), QSettings.IniFormat)

            with patch("app.ui.application_db_path", return_value=database), \
                 patch("app.ui.GlobalHotkeyListener.start", return_value=(False, "Teste")), \
                 patch("app.ui.QSettings", side_effect=mock_settings):
                win = AutoFillWindow()
                try:
                    win._load_editor(win.store.snippets()[0])
                    original_content = win.body_input.toPlainText()
                    original_html = win.body_input.toHtml()
                    default_size = win.body_input.font().pointSizeF()
                    win.text_zoom_slider.setValue(120)
                    self.assertEqual(win.text_zoom_slider.value(), 120)
                    self.assertEqual(win.text_zoom_value.text(), "120%")
                    self.assertGreater(win.body_input.font().pointSizeF(), default_size)
                    self.assertEqual(win.body_input.toPlainText(), original_content)
                    self.assertEqual(win.body_input.toHtml(), original_html)
                    self.assertFalse(win.dirty)
                    win.text_zoom_slider.setValue(80)
                    self.assertEqual(win.text_zoom_value.text(), "80%")
                    self.assertLess(win.body_input.font().pointSizeF(), default_size)
                    win.text_zoom_slider.setValue(110)
                    win.settings.sync()
                finally:
                    win._quitting = True
                    win.close()

                second = AutoFillWindow()
                try:
                    self.assertEqual(second.text_zoom_slider.value(), 110)
                    self.assertEqual(second.text_zoom_value.text(), "110%")
                    second.text_zoom_reset.click()
                    self.assertEqual(second.text_zoom_slider.value(), 100)
                finally:
                    second._quitting = True
                    second.close()
        app.processEvents()

    def test_invalid_saved_zoom_falls_back_to_100(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import QSettings
            from PySide6.QtWidgets import QApplication
            from app.ui import AutoFillWindow
        except ImportError:
            self.skipTest("PySide6 indisponível")
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix="aurora-zoom-invalid-") as temp:
            settings_file = Path(temp) / "prefs.ini"
            settings = QSettings(str(settings_file), QSettings.IniFormat)
            settings.setValue("editor/text_zoom", "inválido")
            settings.sync()
            with patch("app.ui.application_db_path", return_value=Path(temp) / "db.sqlite3"), \
                 patch("app.ui.GlobalHotkeyListener.start", return_value=(False, "Teste")), \
                 patch("app.ui.QSettings", side_effect=lambda *args: QSettings(str(settings_file), QSettings.IniFormat)):
                win = AutoFillWindow()
                try:
                    self.assertEqual(win.text_zoom_slider.value(), 100)
                finally:
                    win._quitting = True
                    win.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
