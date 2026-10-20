"""Imagens embutidas: inserção, print, clipboard, prévia e backups."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.inline_images import (
    AuroraImageEditor, contains_inline_images, image_sources,
    decode_embedded_image, plain_text_fallback, validate_inline_html,
)
from app.formatting import has_rich_formatting, render_rich_html
from app.core import SnippetStore
from app.backups import create_backup, restore_backup


class InlineImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def image():
        image = QImage(240, 100, QImage.Format_ARGB32)
        image.fill(Qt.cyan)
        return image

    def test_mixed_text_and_inline_image_roundtrip(self):
        editor = AuroraImageEditor()
        editor.setPlainText("Antes do print\n")
        errors = []
        editor.imageRejected.connect(errors.append)
        self.assertTrue(editor.insert_image(self.image()), errors)
        editor.insertPlainText("\nDepois do print")
        html = editor.toHtml()
        sources = image_sources(html)
        self.assertEqual(len(sources), 1)
        self.assertTrue(sources[0].startswith("data:image/png;base64,"))
        self.assertEqual(decode_embedded_image(sources[0]).size(), self.image().size())
        self.assertTrue(has_rich_formatting(html))
        self.assertEqual(plain_text_fallback(editor.toPlainText()).count("[Imagem]"), 1)
        self.assertIn("Antes", plain_text_fallback(editor.toPlainText()))
        self.assertIn("Depois", plain_text_fallback(editor.toPlainText()))
        validate_inline_html(html)

        second = AuroraImageEditor()
        second.setHtml(html)
        self.assertEqual(len(image_sources(second.toHtml())), 1)
        self.assertIn("Depois", second.toPlainText())
        rendered = render_rich_html(second.toHtml(), "", None)
        self.assertIn("data:image/png;base64,", rendered)

    def test_screenshot_paste_uses_image_payload(self):
        editor = AuroraImageEditor()
        clipboard = QMimeData()
        clipboard.setImageData(self.image())
        errors = []
        editor.imageRejected.connect(errors.append)
        editor.insertFromMimeData(clipboard)
        self.assertTrue(contains_inline_images(editor.toHtml()), errors)
        self.assertEqual(plain_text_fallback(editor.toPlainText()), "[Imagem]")

    def test_external_image_paste_is_rejected_without_loading_remote_resource(self):
        editor = AuroraImageEditor()
        rejected = []
        editor.imageRejected.connect(rejected.append)
        clipboard = QMimeData()
        clipboard.setHtml('<p>Olá</p><img src="https://example.org/image.png">')
        clipboard.setText("Olá")
        editor.insertFromMimeData(clipboard)
        self.assertTrue(rejected)
        self.assertFalse(contains_inline_images(editor.toHtml()))
        self.assertIn("Olá", editor.toPlainText())

    def test_data_uri_and_png_reject_corrupted_images(self):
        for value in ("data:image/png;base64,not_base64", "file:///tmp/private.png",
                      "https://example.com/photo.png"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_inline_html(f'<img src="{value}">')

    def test_inline_images_survive_json_and_whole_profile_backup(self):
        editor = AuroraImageEditor()
        editor.insertPlainText("Texto\n")
        errors = []
        editor.imageRejected.connect(errors.append)
        self.assertTrue(editor.insert_image(self.image()), errors)
        editor.insertPlainText("\nFim")
        html = editor.toHtml()
        fallback = plain_text_fallback(editor.toPlainText())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "AuroraAutoFill" / "snippets.sqlite3"
            store = SnippetStore(database)
            folder = store.create_folder("Prints")
            store.save(folder, "Resposta ilustrada", "/print", fallback, rich_content=html)
            backup = root / "images.aurora-backup.zip"
            with patch("app.backups.application_db_path", return_value=database), \
                 patch("app.backups.preferences_path", return_value=database.parent / "settings.json"):
                try:
                    create_backup(store, destination=backup)
                    store.save(folder, "Resposta ilustrada", "/print", "Texto temporário",
                               store.snippets()[0].id)
                    restore_backup(store, backup)
                    restored = store.snippets()[0]
                    self.assertEqual(restored.rich_content, html)
                    self.assertEqual(restored.content, fallback)
                    self.assertIn("data:image/png;base64,", restored.rich_content)
                    exported = root / "exports.json"
                    store.export_json(exported)
                    imported = SnippetStore(root / "copied.sqlite3")
                    try:
                        self.assertEqual(imported.import_json(exported), (1, 0))
                        self.assertEqual(imported.snippets()[0].rich_content, html)
                    finally:
                        imported.close()
                finally:
                    store.close()


if __name__ == "__main__":
    unittest.main()
