"""A pré-visualização é um espelho visual, não um segundo editor."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.inline_images import AuroraReadOnlyPreview, AuroraImageEditor
from app.ui import AutoFillWindow


class ReadOnlyPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_preview_rejects_keyboard_paste_drop_and_image_insertion(self):
        preview = AuroraReadOnlyPreview()
        try:
            preview.setHtml("<p>Olá <b>mundo</b> 😀</p>")
            original_html = preview.toHtml()
            original_text = preview.toPlainText()
            self.assertTrue(preview.isReadOnly())
            self.assertEqual(preview.textInteractionFlags(), Qt.NoTextInteraction)
            self.assertEqual(preview.focusPolicy(), Qt.NoFocus)
            self.assertFalse(preview.acceptDrops())
            self.assertFalse(preview.isUndoRedoEnabled())
            self.assertEqual(preview.contextMenuPolicy(), Qt.NoContextMenu)
            preview.show()
            self.app.processEvents()
            QTest.keyClicks(preview, "SUBSTITUÍDO")
            QTest.keyClick(preview, Qt.Key_Backspace)
            QTest.keyClick(preview, Qt.Key_Delete)
            QTest.keyClick(preview, Qt.Key_A, Qt.ControlModifier)
            QTest.keyClick(preview, Qt.Key_V, Qt.ControlModifier)
            source = QMimeData()
            source.setHtml("<p>Conteúdo invasor</p>")
            source.setText("Conteúdo invasor")
            preview.insertFromMimeData(source)
            image = QImage(4, 4, QImage.Format_ARGB32)
            image.fill(Qt.red)
            self.assertFalse(preview.insert_image(image))
            self.assertEqual(preview.toPlainText(), original_text)
            self.assertEqual(preview.toHtml(), original_html)
            self.assertFalse(preview.textCursor().hasSelection())
        finally:
            preview.close()
            preview.deleteLater()

    def test_preview_updates_immediately_from_editor_without_autosave_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("app.ui.application_db_path", return_value=Path(tmp) / "test.sqlite3"), \
             patch("app.ui.GlobalHotkeyListener.start", return_value=(False, "Modo de teste")), \
             patch("app.ui.AutoFillWindow._initial_release_check"):
            win = AutoFillWindow()
            try:
                win._new_snippet()
                win.title_input.setText("Pré-visualização")
                win.shortcut_input.setText("/previa")
                win.body_input.setPlainText("Isso é um teste.")
                self.assertEqual(win.preview.toPlainText().strip(), "Isso é um teste.")
                self.assertIsInstance(win.preview, AuroraReadOnlyPreview)
                self.assertIsInstance(win.body_input, AuroraImageEditor)
                self.assertNotIsInstance(win.body_input, AuroraReadOnlyPreview)
                win.body_input.setHtml("<p>Texto <b>em destaque</b> 😀</p>")
                self.app.processEvents()
                self.assertIn("Texto em destaque 😀", win.preview.toPlainText())
                self.assertIn("font-weight", win.preview.toHtml().lower())
                before = win.preview.toPlainText()
                win.preview.insertFromMimeData(self.app.clipboard().mimeData())
                QTest.keyClicks(win.preview, "NÃO DEVE ALTERAR")
                self.app.processEvents()
                self.assertEqual(win.preview.toPlainText(), before)
                self.assertEqual(win.store.snippet_by_shortcut("/previa").content.strip(),
                                 win.body_input.toPlainText().strip())
                win.body_input.setPlainText("Modificado no editor acima 🙂")
                self.app.processEvents()
                self.assertEqual(win.preview.toPlainText().strip(), "Modificado no editor acima 🙂")
                self.assertTrue(win.preview.isReadOnly())
                self.assertEqual(win.preview.textInteractionFlags(), Qt.NoTextInteraction)
            finally:
                win.dirty = False
                win._quitting = True
                win.close()
                win.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
