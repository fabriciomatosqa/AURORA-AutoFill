"""Regressão da barra Fonte compacta, enumeração Windows e seletor de cores."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FontCatalogTests(unittest.TestCase):
    def test_qt_and_windows_installed_families_are_combined(self):
        from app.font_catalog import installed_font_families
        with patch("app.font_catalog.QFontDatabase.families", return_value=["Segoe UI", "Arial"]), \
             patch("app.font_catalog._windows_installed_families", return_value=["Consolas", "Arial", "Verdana"]):
            self.assertEqual(installed_font_families(), ["Arial", "Consolas", "Segoe UI", "Verdana"])

    def test_windows_registry_includes_user_and_system_fonts(self):
        import types
        from app.font_catalog import _windows_installed_families
        class Registry:
            def __init__(self, label):
                self.label = label
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
        def open_key(hive, _path):
            return Registry(hive)
        def enum_value(registry, index):
            groups = {
                "machine": [("Arial (TrueType)", "arial.ttf", 1),
                            ("Segoe UI (TrueType)", "segoeui.ttf", 1)],
                "user": [("Minha Fonte (OpenType)", "personal.otf", 1)]
            }
            try:
                return groups[registry.label][index]
            except IndexError:
                raise OSError("Fim")
        fake = types.SimpleNamespace(
            HKEY_LOCAL_MACHINE="machine", HKEY_CURRENT_USER="user",
            OpenKey=open_key, EnumValue=enum_value)
        with patch("app.font_catalog.sys.platform", "win32"), \
             patch.dict(sys.modules, {"winreg": fake}):
            self.assertEqual(
                _windows_installed_families(), ["Arial", "Minha Fonte", "Segoe UI"])


class FontUiTests(unittest.TestCase):
    def test_catalog_is_searchable_with_arrow_even_if_qt_lists_one_family(self):
        from PySide6.QtWidgets import QApplication
        from app.font_catalog import AuroraFontCombo
        app = QApplication.instance() or QApplication([])
        type(self)._app = app
        with patch("app.font_catalog.installed_font_families",
                   return_value=["Segoe UI", "Arial", "Consolas"]):
            combo = AuroraFontCombo()
            self.assertTrue(combo.isEditable())
            self.assertEqual(combo.count(), 3)
            self.assertIsNotNone(combo.completer())
            self.assertIn("Pesquisar", combo.lineEdit().placeholderText())
            self.assertGreater(combo.view().model().rowCount(), 1)
            combo.resize(214, 29)
            combo.show()
            combo.grab()  # exercita paintEvent, incluindo seta Aurora
            combo.hide()
            combo.deleteLater()

    def test_color_dialog_preserves_full_picker_and_aurora_theme(self):
        from PySide6.QtWidgets import QApplication, QColorDialog, QDialogButtonBox
        from PySide6.QtGui import QColor
        from app.color_dialog import AuroraColorDialog
        app = QApplication.instance() or QApplication([])
        type(self)._app = app
        picker = AuroraColorDialog(QColor("#22bb99"), title="Cor do texto")
        self.assertTrue(picker.testOption(QColorDialog.DontUseNativeDialog))
        self.assertIn("AURORA", picker.windowTitle())
        self.assertIn("#0c1d31", picker.styleSheet())
        self.assertIn("#55d6c0", picker.styleSheet())
        buttons = picker.findChild(QDialogButtonBox)
        self.assertIsNotNone(buttons)
        self.assertEqual(buttons.button(QDialogButtonBox.Ok).text(), "Aplicar cor")
        self.assertEqual(buttons.button(QDialogButtonBox.Cancel).text(), "Cancelar")
        self.assertEqual(picker.currentColor().name(), "#22bb99")
        picker.close()
        picker.deleteLater()


if __name__ == "__main__":
    unittest.main()
