"""Real text and native images in their original order; no whole-message PNG."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.clipboard_content import (
    ordered_clipboard_parts, clipboard_part_mime, expansion_mime,
    prepare_mixed_content,
)
from app.inline_images import AuroraImageEditor
from app.preferences import normalize_preferences, load_preferences, save_preferences
from app.ui import AutoFillWindow
from engine_fixture import EngineFixture, Clipboard


class SeparateContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def illustrated_editor():
        editor = AuroraImageEditor()
        editor.insertPlainText("Texto inicial: {{data}}\n")
        for color in (Qt.cyan, Qt.red):
            bitmap = QImage(70, 45, QImage.Format_ARGB32)
            bitmap.fill(color)
            assert editor.insert_image(bitmap)
            editor.insertPlainText("\nTexto posterior\n")
        return editor

    def test_split_preserves_order_and_variable_values(self):
        editor = self.illustrated_editor()
        now = datetime(2026, 10, 21, 10, 30)
        parts = ordered_clipboard_parts(editor.toHtml(), "", now)
        self.assertEqual([p.kind for p in parts],
                         ["text", "image", "text", "image", "text"])
        self.assertIn("21/10/2026", parts[0].text)
        self.assertIn("Texto posterior", parts[2].text)
        self.assertIn("Texto posterior", parts[4].text)
        self.assertEqual(len({parts[1].source, parts[3].source}), 2)

        for part in parts:
            mime = clipboard_part_mime(part)
            if part.kind == "text":
                self.assertTrue(mime.hasText())
                self.assertFalse(mime.hasImage())
                self.assertFalse(mime.hasHtml())
                self.assertNotIn("[Imagem", mime.text())
            else:
                self.assertTrue(mime.hasImage())
                self.assertFalse(mime.hasText())
                self.assertFalse(mime.hasHtml())
                self.assertTrue(bytes(mime.data("image/png")).startswith(
                    bytes([137, 80, 78, 71, 13, 10, 26, 10])))

    def test_text_only_fallback_has_no_image_placeholder(self):
        editor = self.illustrated_editor()
        mixed = prepare_mixed_content(editor.toHtml(), "", datetime(2026, 10, 21))
        self.assertNotIn("[Imagem", mixed.text)
        self.assertIn("Texto inicial", mixed.text)
        self.assertIn("Texto posterior", mixed.text)
        combined = expansion_mime(mixed.text, mixed.html)
        self.assertTrue(combined.hasHtml())
        self.assertTrue(combined.hasText())
        self.assertFalse(combined.hasImage())

    def test_removed_mode_ignored_even_if_enabled_in_old_settings(self):
        self.assertNotIn("images_as_single_picture", normalize_preferences({}))
        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / "settings.json"
            save_preferences({"images_as_single_picture": True}, settings)
            prefs = load_preferences(settings)
            self.assertNotIn("images_as_single_picture", prefs)
            self.assertNotIn("images_as_single_picture", settings.read_text())
        editor = self.illustrated_editor()
        with EngineFixture() as e:
            e.host.preferences = {"images_as_single_picture": True}
            e.save("/mix", editor.toPlainText(), editor.toHtml())
            e.type("/mix")
            e.until(75)
            payload = e.clipboard.mimeData()
            self.assertTrue(payload.hasText() and payload.hasHtml())
            self.assertFalse(payload.hasImage())
            e.drain()

    def test_menu_sequence_copy_keeps_text_then_native_image_then_text(self):
        editor = AuroraImageEditor()
        editor.insertPlainText("Início\n")
        picture = QImage(80, 50, QImage.Format_ARGB32)
        picture.fill(Qt.cyan)
        assert editor.insert_image(picture)
        editor.insertPlainText("\nFim")
        host = SimpleNamespace(
            body_input=editor, _expansion_operation=None,
            _clipboard_lease=None, _clipboard_pending=False,
            _clipboard_source_text=lambda: "",
            statusBar=lambda: SimpleNamespace(showMessage=lambda *args: None),
        )
        clipboard = Clipboard()
        with patch("app.ui.QApplication.clipboard", return_value=clipboard):
            AutoFillWindow._copy_content_part(host, ("next", None))
            self.assertTrue(clipboard.mimeData().hasText())
            self.assertFalse(clipboard.mimeData().hasImage())
            self.assertIn("Início", clipboard.text())
            AutoFillWindow._copy_content_part(host, ("next", None))
            self.assertTrue(clipboard.mimeData().hasImage())
            self.assertFalse(clipboard.mimeData().hasText())
            self.assertEqual(clipboard.mimeData().imageData().width(), 80)
            AutoFillWindow._copy_content_part(host, ("next", None))
            self.assertTrue(clipboard.mimeData().hasText())
            self.assertIn("Fim", clipboard.text())
            self.assertFalse(clipboard.mimeData().hasImage())

    def test_invalid_image_and_unsupported_part_fail_cleanly(self):
        with self.assertRaises(ValueError):
            ordered_clipboard_parts('<img src="https://example.com/photo.png">')
        with self.assertRaises(ValueError):
            clipboard_part_mime(SimpleNamespace(kind="video"))


if __name__ == "__main__":
    unittest.main()
