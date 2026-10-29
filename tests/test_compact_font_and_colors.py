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

    def test_color_picker_translates_qt_labels_and_offers_reset(self):
        from PySide6.QtWidgets import (
            QApplication, QAbstractButton, QColorDialog, QLabel)
        from PySide6.QtGui import QColor
        from app.color_dialog import AuroraColorDialog
        app = QApplication.instance() or QApplication([])
        type(self)._app = app
        for title, label in (("Cor do texto", "Cor automática"),
                             ("Cor do realce", "Remover realce")):
            picker = AuroraColorDialog(QColor("#0000ff"), title=title)
            try:
                self.assertTrue(picker.testOption(QColorDialog.DontUseNativeDialog))
                self.assertEqual(picker.reset_button.text(), label)
                texts = [x.text().replace("&", "").strip()
                         for x in [*picker.findChildren(QLabel),
                                   *picker.findChildren(QAbstractButton)]]
                self.assertIn("Cores básicas", texts)
                self.assertIn("Cores personalizadas", texts)
                self.assertIn("Capturar cor da tela", texts)
                self.assertNotIn("Basic colors", texts)
                self.assertNotIn("Pick Screen Color", texts)
                self.assertIn("Aplicar cor", texts)
                self.assertIn("Cancelar", texts)
                picker.reset_button.click()
                self.assertTrue(picker.reset_requested)
                self.assertEqual(picker.result(), picker.Accepted)
            finally:
                picker.close()
                picker.deleteLater()
        border = AuroraColorDialog(QColor("red"), title="Cor da borda")
        self.assertIsNone(border.reset_button)
        border.close()
        border.deleteLater()

    def test_picker_can_distinguish_cancel_apply_and_automatic(self):
        from PySide6.QtWidgets import QApplication, QDialog
        from PySide6.QtGui import QColor
        from app.color_dialog import AuroraColorDialog
        app = QApplication.instance() or QApplication([])
        type(self)._app = app

        class Reset(AuroraColorDialog):
            def exec(self):
                self.reset_button.click()
                return self.result()

        class Apply(AuroraColorDialog):
            def exec(self):
                self.setCurrentColor(QColor("#99bb11"))
                self.accept()
                return self.result()

        class Cancel(AuroraColorDialog):
            def exec(self):
                self.reject()
                return self.result()

        accepted, color = Reset.get_choice(QColor("yellow"))
        self.assertTrue(accepted)
        self.assertFalse(color.isValid())
        accepted, color = Apply.get_choice(QColor("yellow"))
        self.assertTrue(accepted)
        self.assertEqual(color.name(), "#99bb11")
        accepted, color = Cancel.get_choice(QColor("yellow"))
        self.assertFalse(accepted)
        self.assertFalse(color.isValid())

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
