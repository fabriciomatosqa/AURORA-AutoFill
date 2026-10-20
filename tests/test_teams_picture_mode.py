"""Alternativa Teams com bitmap real, sem fingir aceitação do anexo."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.clipboard_content import message_as_image_mime, render_message_as_bitmap
from app.inline_images import AuroraImageEditor
from app.preferences import normalize_preferences, load_preferences, save_preferences
from engine_fixture import EngineFixture


class TeamsPictureModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def illustrated_editor():
        editor = AuroraImageEditor()
        editor.insertPlainText("Cadastro de colaborador: 20/10/2026\n")
        bitmap = QImage(70, 45, QImage.Format_ARGB32)
        bitmap.fill(Qt.cyan)
        assert editor.insert_image(bitmap)
        editor.insertPlainText("\nConfira os dados antes de enviar.")
        return editor

    def test_one_png_contains_full_text_and_illustration(self):
        editor = self.illustrated_editor()
        result = render_message_as_bitmap(editor.toHtml())
        self.assertFalse(result.isNull())
        self.assertEqual(result.width(), 760)
        self.assertGreater(result.height(), 75)
        # A figura azul do modelo deve estar de fato desenhada no bitmap.
        cyan = any(result.pixelColor(x, y).red() < 30 and
                   result.pixelColor(x, y).green() > 220 and
                   result.pixelColor(x, y).blue() > 220
                   for x in range(0, result.width(), 4)
                   for y in range(0, result.height(), 4))
        self.assertTrue(cyan)
        payload = message_as_image_mime(editor.toHtml())
        self.assertTrue(payload.hasImage())
        self.assertTrue(bytes(payload.data("image/png")).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertFalse(payload.hasText())
        self.assertFalse(payload.hasHtml())

    def test_bitmap_mode_is_opt_in_and_preferences_roundtrip(self):
        defaults = normalize_preferences({})
        self.assertFalse(defaults["images_as_single_picture"])
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / "settings.json"
            save_preferences({"images_as_single_picture": True}, settings)
            self.assertTrue(load_preferences(settings)["images_as_single_picture"])
            self.assertFalse(normalize_preferences({"images_as_single_picture": "yes"})[
                "images_as_single_picture"])

    def test_oversize_message_fails_without_truncating_text(self):
        with self.assertRaisesRegex(ValueError, "muito longo"):
            render_message_as_bitmap("<p>Linha de cadastro</p>" * 900)

    def test_opted_in_shortcut_offers_native_bitmap_and_preserves_clipboard(self):
        editor = self.illustrated_editor()
        with EngineFixture() as e:
            e.host.preferences = {"images_as_single_picture": True}
            e.save("/cadastro", editor.toPlainText(), editor.toHtml())
            e.type("/cadastro")
            e.until(75)
            payload = e.clipboard.mimeData()
            self.assertTrue(payload.hasImage())
            self.assertFalse(payload.hasText())
            self.assertEqual(e.host._play_confirmation.call_count, 1)
            e.drain()
            self.assertEqual(e.clipboard.text(), "original")
            self.assertEqual(e.host._play_confirmation.call_count, 1)

    def test_default_mode_keeps_mixed_text_and_html_not_bitmap(self):
        editor = self.illustrated_editor()
        with EngineFixture() as e:
            e.host.preferences = {"images_as_single_picture": False}
            e.save("/cadastro", editor.toPlainText(), editor.toHtml())
            e.type("/cadastro")
            e.until(75)
            payload = e.clipboard.mimeData()
            self.assertTrue(payload.hasHtml())
            self.assertTrue(payload.hasText())
            self.assertFalse(payload.hasImage())
            e.drain()
            self.assertEqual(e.host._play_confirmation.call_count, 1)

    def test_browser_without_confirmation_plays_once_when_paste_is_sent(self):
        with EngineFixture() as e:
            e.readable = False
            e.save("/ola", "Bom dia")
            e.type("/ola")
            e.until(75)
            e.host._play_confirmation.assert_called_once()
            e.drain()
            e.host._play_confirmation.assert_called_once()
            self.assertEqual(e.clipboard.text(), "original")


if __name__ == "__main__":
    unittest.main()
