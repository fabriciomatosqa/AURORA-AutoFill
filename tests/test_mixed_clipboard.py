"""Real Qt documents/MIME plus explicitly simulated external editing contracts."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QImage, QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from app.clipboard_content import clone_mime, expansion_mime, image_mime, prepare_mixed_content
from app.inline_images import AuroraImageEditor, image_sources, plain_text_fallback, validate_inline_html
from app.inline_images import decode_embedded_image, read_image_file, MAX_DIMENSION
from app.core import SnippetStore
from app.expansion import utf16_length
from engine_fixture import EngineFixture


class MixedClipboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def mixed(self, count=2):
        editor = AuroraImageEditor()
        editor.insertHtml("<p><b>Antes 😀 {{data}}</b></p>")
        for index in range(count):
            editor.insertPlainText("\n")
            image = QImage(24 + index, 12, QImage.Format_ARGB32)
            image.fill(Qt.cyan if index == 0 else Qt.red)
            self.assertTrue(editor.insert_image(image))
            editor.insertPlainText(f"\nDepois {index + 1}")
        return editor

    def prepared(self, editor):
        return prepare_mixed_content(editor.toHtml(), "<copiado>", datetime(2026, 10, 20, 12, 30))

    def test_mixed_order_format_variables_and_source_are_preserved(self):
        editor = self.mixed()
        saved = editor.toHtml()
        mixed = self.prepared(editor)
        self.assertEqual(mixed.document_text, "Antes 😀 20/10/2026\n\ufffc\nDepois 1\n\ufffc\nDepois 2")
        self.assertEqual(mixed.image_count, 2)
        self.assertFalse(mixed.image_only)
        self.assertIn("font-weight:700", mixed.html)
        self.assertNotIn("[Imagem", mixed.text)
        self.assertEqual(mixed.text, "Antes 😀 20/10/2026\n\nDepois 1\n\nDepois 2")
        self.assertNotIn("[Imagem]", mixed.text)
        self.assertEqual(editor.toHtml(), saved)
        self.assertEqual(image_sources(mixed.html), image_sources(saved))

    def test_mixed_mime_does_not_offer_first_image_as_entire_document(self):
        mixed = self.prepared(self.mixed())
        payload = expansion_mime(mixed.text, mixed.html)
        self.assertTrue(payload.hasHtml() and payload.hasText())
        self.assertFalse(payload.hasImage())
        self.assertFalse(payload.hasFormat("image/png"))

    def test_isolated_image_has_real_bitmap_png_html_and_explicit_text_fallback(self):
        editor = self.mixed(1)
        source = image_sources(editor.toHtml())[0]
        mixed = prepare_mixed_content(f'<p><img src="{source}"/></p>', "", datetime.now())
        self.assertTrue(mixed.image_only)
        payload = expansion_mime(mixed.text, mixed.html, image_only=True)
        self.assertTrue(payload.hasImage() and payload.hasHtml() and payload.hasText())
        self.assertEqual(payload.imageData().width(), 24)
        self.assertTrue(bytes(payload.data("image/png")).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(payload.text(), "")

    def test_rich_editor_preserves_mixed_html_even_when_bitmap_flavor_is_present(self):
        mixed = self.prepared(self.mixed())
        payload = expansion_mime(mixed.text, mixed.html)
        payload.setImageData(QImage(3, 3, QImage.Format_RGB32))
        destination = AuroraImageEditor()
        destination.insertFromMimeData(payload)
        self.assertEqual(destination.toPlainText(), mixed.document_text)
        self.assertEqual(len(image_sources(destination.toHtml())), 2)
        for source in image_sources(destination.toHtml()):
            resource = destination.document().resource(QTextDocument.ImageResource, QUrl(source))
            self.assertIsInstance(resource, QImage)
            self.assertFalse(resource.isNull())

    def test_plain_destination_gets_editable_text_without_fake_image_markers(self):
        mixed = self.prepared(self.mixed())
        destination = QPlainTextEdit()
        destination.insertFromMimeData(expansion_mime(mixed.text, mixed.html))
        self.assertEqual(destination.toPlainText(), mixed.text)

    def test_cloned_mime_preserves_bitmap_html_png_and_other_formats(self):
        source = image_sources(self.mixed(1).toHtml())[0]
        original = image_mime(source)
        original.setText("Original 😀")
        original.setHtml("<b>Original</b>")
        original.setData("application/x-test", b"\x00\xff")
        cloned = clone_mime(original)
        self.assertTrue(cloned.hasImage())
        self.assertEqual(cloned.imageData(), original.imageData())
        for fmt in ("text/plain", "text/html", "image/png", "application/x-test"):
            self.assertEqual(bytes(cloned.data(fmt)), bytes(original.data(fmt)))

    def test_unquoted_missing_duplicate_and_external_image_sources_are_rejected(self):
        for html in ('<img src=https://example.com/a.png>', '<img src=file:///tmp/a.png>',
                     '<img>', '<img src="x" src="y">', '<img src="data:image/png;base64,AAAA">'):
            with self.subTest(html=html), self.assertRaises(ValueError):
                validate_inline_html(html)

    def test_combined_paste_limit_is_checked_before_changing_editor(self):
        incoming = self.prepared(self.mixed(1))
        destination = self.mixed(1)
        previous = destination.toHtml()
        rejected = []
        destination.imageRejected.connect(rejected.append)
        # Each document is below this limit; the combined document exceeds it.
        with patch("app.inline_images.MAX_TOTAL_IMAGE_PIXELS", 400):
            destination.insertFromMimeData(expansion_mime(incoming.text, incoming.html))
        self.assertTrue(rejected)
        self.assertEqual(len(image_sources(destination.toHtml())), 1)
        self.assertIn("data:image/png", previous)

    def test_image_metadata_pixel_budget_is_checked_before_decode(self):
        source = image_sources(self.mixed(1).toHtml())[0]
        from app.inline_images import decode_embedded_image
        with patch("app.inline_images.MAX_IMAGE_PIXELS", 20):
            with self.assertRaises(ValueError):
                decode_embedded_image(source)

    def test_count_bytes_total_and_pixel_limits_reject_before_expansion(self):
        source = image_sources(self.mixed(1).toHtml())[0]
        html = f'<img src="{source}">'
        with self.assertRaises(ValueError):
            validate_inline_html(html * 13)
        for limit in ("MAX_IMAGE_BYTES", "MAX_TOTAL_IMAGE_BYTES", "MAX_TOTAL_IMAGE_PIXELS"):
            with self.subTest(limit=limit), patch("app.inline_images." + limit, 1):
                with self.assertRaises(ValueError):
                    validate_inline_html(html)

    def test_large_input_is_resized_and_file_metadata_is_checked(self):
        image = QImage(2000, 1000, QImage.Format_RGB32)
        image.fill(Qt.cyan)
        editor = AuroraImageEditor()
        self.assertTrue(editor.insert_image(image))
        decoded = decode_embedded_image(image_sources(editor.toHtml())[0])
        self.assertEqual(decoded.width(), MAX_DIMENSION)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "large.png"
            image.save(str(path), "PNG")
            with patch("app.inline_images.MAX_IMAGE_PIXELS", 100):
                with self.assertRaises(ValueError):
                    read_image_file(str(path))

    def test_loaded_html_cannot_fetch_local_or_remote_images(self):
        editor = AuroraImageEditor()
        rejected = []
        editor.imageRejected.connect(rejected.append)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private.png"
            image = QImage(12, 12, QImage.Format_RGB32)
            image.fill(Qt.red)
            image.save(str(path), "PNG")
            for source in (QUrl.fromLocalFile(str(path)).toString(), "https://example.com/a.png"):
                editor.setHtml(f'<p>Preservado<img src="{source}"></p>')
                resource = editor.document().resource(QTextDocument.ImageResource, QUrl(source))
                self.assertTrue(resource is None or resource.isNull())
                self.assertIn("Preservado", editor.toPlainText())
            self.assertEqual(len(rejected), 2)

    def test_multiple_images_survive_close_reopen_and_json(self):
        editor = self.mixed()
        html = editor.toHtml()
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "test.db"
            store = SnippetStore(db)
            folder = store.create_folder("Mixed")
            store.save(folder, "Mixed", "/mixed", plain_text_fallback(editor.toPlainText()), rich_content=html)
            store.close()
            store = SnippetStore(db)
            other = SnippetStore(Path(temp) / "import.db")
            try:
                self.assertEqual(store.snippets()[0].rich_content, html)
                export = Path(temp) / "export.json"
                store.export_json(export)
                self.assertEqual(other.import_json(export), (1, 0))
                self.assertEqual(other.snippets()[0].rich_content, html)
            finally:
                store.close()
                other.close()

    def test_multiple_images_survive_full_backup_restore_without_schema_changes(self):
        from app.backups import create_backup, restore_backup
        editor = self.mixed()
        html = editor.toHtml()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "profile" / "test.db"
            store = SnippetStore(db)
            folder = store.create_folder("Mixed")
            identifier = store.save(folder, "Mixed", "/mixed", plain_text_fallback(editor.toPlainText()), rich_content=html)
            try:
                columns = list(store.connection.execute("PRAGMA table_info(snippets)"))
                archive = root / "mixed.aurora-backup.zip"
                with patch("app.backups.application_db_path", return_value=db), \
                     patch("app.backups.preferences_path", return_value=root / "missing.json"):
                    create_backup(store, destination=archive)
                    store.save(folder, "Mixed", "/mixed", "Temporário", identifier)
                    restore_backup(store, archive)
                self.assertEqual(store.snippets()[0].rich_content, html)
                self.assertEqual(len(image_sources(store.snippets()[0].rich_content)), 2)
                self.assertEqual(list(store.connection.execute("PRAGMA table_info(snippets)")), columns)
            finally:
                store.close()

    def test_mixed_cursor_offsets_include_images_and_dynamic_clipboard_is_escaped(self):
        editor = self.mixed(1)
        editor.insertPlainText(" {{clipboard}} {{cursor}}Fim")
        mixed = self.prepared(editor)
        self.assertTrue(mixed.document_cursor_prefix.endswith("<copiado> "))
        self.assertIn("&lt;copiado&gt;", mixed.html)
        self.assertNotIn("{{cursor}}", mixed.html)
        self.assertEqual(mixed.left_moves, 3)

    def test_simulated_plain_expansion_verifies_range_and_restores_image_clipboard(self):
        editor = self.mixed()
        with EngineFixture() as engine:
            engine.save("/mixed", plain_text_fallback(editor.toPlainText()), editor.toHtml())
            original = image_mime(image_sources(editor.toHtml())[0])
            engine.clipboard.setMimeData(original)
            engine.type("/mixed")
            engine.drain()
            self.assertNotIn("/mixed", engine.field.text)
            self.assertNotIn("[Imagem", engine.field.text)
            self.assertIn("Depois 2", engine.field.text)
            engine.replace.assert_not_called()
            engine.selection.assert_called_once()
            self.assertTrue(engine.clipboard.mimeData().hasImage())
            self.assertEqual(engine.clipboard.mimeData().imageData(), original.imageData())

    def test_simulated_mixed_unreadable_target_is_cancelled_without_editing(self):
        editor = self.mixed(1)
        with EngineFixture() as engine:
            engine.readable = False
            engine.save("/mixed", "[Imagem]", editor.toHtml())
            engine.type("/mixed")
            engine.drain()
            self.assertEqual(engine.field.text, "/mixed")
            engine.replace.assert_not_called()
            self.assertEqual(engine.clipboard.text(), "original")
            self.assertIsNone(engine.host._active_candidate)
            self.assertIsNone(engine.host._expansion_operation)

    def test_invalid_image_cancels_and_releases_operation_state(self):
        with EngineFixture() as engine:
            engine.save("/mixed", "[Imagem]", '<p><img src="https://example.com/a.png"></p>')
            engine.type("/mixed")
            engine.drain()
            self.assertEqual(engine.field.text, "/mixed")
            self.assertIsNone(engine.host._active_candidate)
            self.assertIsNone(engine.host._expansion_operation)
            self.assertEqual(engine.clipboard.text(), "original")
            engine.replace.assert_not_called()

    def test_simulated_focus_change_after_selection_never_pastes_to_other_field(self):
        editor = self.mixed(1)
        with EngineFixture() as engine:
            engine.save("/mixed", "[Imagem]", editor.toHtml())
            select = engine.select
            def change_focus(*args):
                result = select(*args)
                engine.field_id = 2
                return result
            with patch("app.ui.select_text_range", side_effect=change_focus):
                engine.type("/mixed")
                engine.drain()
            self.assertEqual(engine.fields[1].text, "/mixed")
            self.assertEqual(engine.fields[2].text, "OTHER")
            self.assertEqual(engine.clipboard.text(), "original")

    def test_simulated_new_copy_during_image_lease_is_never_overwritten(self):
        editor = self.mixed(1)
        with EngineFixture() as engine:
            engine.save("/mixed", "[Imagem]", editor.toHtml())
            engine.type("/mixed")
            engine.until(100)
            engine.clipboard.setText("NEW COPY")
            engine.drain()
            self.assertEqual(engine.clipboard.text(), "NEW COPY")

    def test_non_windows_clipboard_change_during_backup_cancels(self):
        with EngineFixture() as engine:
            original_clone = engine.host._clone_clipboard_mime
            def changed():
                result = original_clone()
                engine.clipboard.setText("NEW COPY")
                engine.host._clipboard_changed()
                return result
            with patch("app.ui.windows_clipboard_sequence", return_value=None), \
                 patch.object(engine.host, "_clone_clipboard_mime", side_effect=changed):
                engine.type("/ola")
                engine.drain()
            self.assertEqual(engine.clipboard.text(), "NEW COPY")
            self.assertEqual(engine.field.text, "/ola")
            engine.replace.assert_not_called()

    def test_real_qt_test_area_replaces_shortcut_and_keeps_mixed_cursor(self):
        source = self.mixed()
        source.insertPlainText(" {{cursor}}Fim")
        with EngineFixture() as engine:
            engine.save("/mixed", plain_text_fallback(source.toPlainText()), source.toHtml())
            destination = AuroraImageEditor()
            destination.setPlainText("Vizinho 😀 /mixed")
            cursor = destination.textCursor()
            cursor.movePosition(QTextCursor.End)
            destination.setTextCursor(cursor)
            engine.host.test_box = destination
            engine.host.isActiveWindow = lambda: True
            engine.host.focusWidget = lambda: destination
            engine.type("/mixed")
            engine.drain()
            result = destination.toPlainText()
            self.assertNotIn("/mixed", result, engine.status.showMessage.call_args_list)
            self.assertTrue(result.startswith("Vizinho 😀 Antes 😀"))
            self.assertEqual(result.count("\ufffc"), 2)
            self.assertEqual(len(image_sources(destination.toHtml())), 2)
            self.assertTrue(result.endswith(" Fim"))
            self.assertEqual(destination.textCursor().position(), utf16_length(result[:-3]))
            engine.host._play_confirmation.assert_called_once()
            self.assertEqual(engine.clipboard.text(), "original")
            self.assertEqual(engine.store.snippets()[0].rich_content, source.toHtml())

    def test_copy_menu_copies_selected_image_and_text_without_images(self):
        from app.ui import AutoFillWindow
        editor = self.mixed()
        messages = SimpleNamespace(showMessage=lambda *args: None)
        host = SimpleNamespace(body_input=editor, _expansion_operation=None,
                               _clipboard_lease=object(), _clipboard_pending=True,
                               _clipboard_source_text=lambda: "", statusBar=lambda: messages)
        from engine_fixture import Clipboard
        clipboard = Clipboard()
        with patch("app.ui.QApplication.clipboard", return_value=clipboard):
            AutoFillWindow._copy_content_part(host, 1)
            self.assertTrue(clipboard.mimeData().hasImage())
            self.assertEqual(clipboard.mimeData().imageData().width(), 25)
            self.assertIsNone(host._clipboard_lease)
            AutoFillWindow._copy_content_part(host, None)
            self.assertFalse(clipboard.mimeData().hasImage())
            self.assertNotIn("\ufffc", clipboard.text())
            self.assertNotIn("[Imagem", clipboard.text())
            self.assertIn("Depois 2", clipboard.text())


if __name__ == "__main__":
    unittest.main()
