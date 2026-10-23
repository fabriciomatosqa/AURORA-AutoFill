"""Compatibilidade de cores HTML/RTF com Word/Teams sem bitmap e sem perder texto."""
import os
import re
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class OfficeRichClipboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def sample_html(self):
        from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
        document = QTextDocument()
        cursor = QTextCursor(document)
        cursor.insertText("CADASTRO COLABORADOR 22/10/2026")
        cursor.insertBlock()
        cursor.insertBlock()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#b345e2"))
        fmt.setBackground(QColor("#36d119"))
        fmt.setFontPointSize(15)
        fmt.setFontFamilies(["Arial"])
        cursor.insertText("vamos testar essa bagaça", fmt)
        return document.toHtml()

    def test_qt_html_to_interoperable_html_preserves_both_colors(self):
        from PySide6.QtGui import QColor, QTextDocument, QTextFormat
        from app.rich_clipboard import interoperable_html
        fragment = interoperable_html(self.sample_html())
        self.assertIn("#b345e2", fragment)
        self.assertIn("background-color:#36d119", fragment)
        self.assertIn('color="#b345e2"', fragment)
        self.assertIn("font-size:15pt", fragment)
        self.assertIn("vamos testar essa bagaça", fragment)
        document = QTextDocument()
        document.setHtml(fragment)
        self.assertEqual(
            document.toPlainText().replace("\u2028", "\n"),
            "CADASTRO COLABORADOR 22/10/2026\n\nvamos testar essa bagaça")
        cursor = document.find("vamos testar")
        self.assertFalse(cursor.isNull())
        fmt = cursor.charFormat()
        self.assertEqual(fmt.foreground().color().name(), "#b345e2")
        self.assertEqual(fmt.background().color().name(), "#36d119")

    def test_clipboard_html_has_real_paragraphs_and_keeps_empty_lines(self):
        from PySide6.QtGui import QTextDocument
        from app.rich_clipboard import interoperable_html
        source = self.sample_html()
        fragment = interoperable_html(source)
        self.assertEqual(fragment.count('<p style="margin:0">'), 3)
        self.assertIn('<p style="margin:0"><br></p>', fragment)
        self.assertNotIn('</span><br><span', fragment)
        original = QTextDocument()
        original.setHtml(source)
        roundtrip = QTextDocument()
        roundtrip.setHtml(fragment)
        self.assertEqual(roundtrip.toPlainText(), original.toPlainText())

    def test_styled_service_message_keeps_paragraph_breaks_in_all_clipboard_formats(self):
        from app.clipboard_content import expansion_mime
        from PySide6.QtGui import QTextDocument
        from app.rich_clipboard import cf_html_bytes, interoperable_html
        html = ('<p>Prezado(a), bom dia.</p><p><br></p>'
                '<p>Espero que esteja bem.</p><p><br></p>'
                '<p>Informamos que a <b>Sede já realizou a correção necessária</b> '
                'no sistema.</p><p><br></p>'
                '<p>Manteremos o acompanhamento do caso.</p>')
        doc = QTextDocument()
        doc.setHtml(html)
        plain = doc.toPlainText()
        self.assertIn('dia.\n\nEspero', plain)
        self.assertIn('bem.\n\nInformamos', plain)
        fragment = interoperable_html(html)
        self.assertEqual(fragment.count('<p style="margin:0">'), 7)
        self.assertIn("font-weight:bold", fragment)
        with patch("app.clipboard_content.sys.platform", "win32"):
            mime = expansion_mime(plain, html)
            web_mime = expansion_mime(plain, html, web_html_only=True)
        for variant in (mime, web_mime):
            self.assertEqual(variant.text(), plain)
            pasted = QTextDocument()
            pasted.setHtml(variant.html())
            self.assertEqual(pasted.toPlainText(), plain)
            self.assertEqual(variant.html().count('<p style="margin:0">'), 7)
        native = bytes(mime.data('application/x-qt-windows-mime;value="HTML Format"'))
        self.assertIn(b'StartFragment:', native)
        self.assertIn(b'<p style="margin:0">', native)
        self.assertGreaterEqual(bytes(mime.data('application/x-qt-windows-mime;value="Rich Text Format"')).count(b'\\par '), 6)

    def test_soft_line_break_remains_inside_same_paragraph(self):
        from PySide6.QtGui import QTextDocument
        from app.rich_clipboard import interoperable_html
        html = "<p>Linha inicial<br>continuação formatada</p>"
        fragment = interoperable_html(html)
        self.assertEqual(fragment.count('<p style="margin:0">'), 1)
        self.assertIn("<br>", fragment)
        result = QTextDocument()
        result.setHtml(fragment)
        self.assertEqual(result.toPlainText().replace("\u2028", "\n"),
                         "Linha inicial\ncontinuação formatada")

    def test_windows_rtf_contains_color_table_and_highlight(self):
        from app.rich_clipboard import rich_text_rtf
        result = rich_text_rtf(self.sample_html()).decode("ascii")
        self.assertTrue(result.startswith(r"{\rtf1"))
        self.assertIn(r"\red179\green69\blue226;", result)
        self.assertIn(r"\red54\green209\blue25;", result)
        self.assertRegex(result, r"\\cf[1-9]\d*")
        self.assertRegex(result, r"\\highlight[1-9]\d*")
        self.assertIn(r"\fs30", result)
        self.assertIn(r"\f1", result)
        self.assertIn(r"\u231?", rich_text_rtf("<p>ç</p>").decode("ascii"))
        self.assertIn(r"\u", rich_text_rtf("<p>😀</p>").decode("ascii"))

    def test_cf_html_offsets_are_correct_utf8_with_accents(self):
        from app.rich_clipboard import cf_html_bytes
        fragment = '<p>Olá, função 😀 <span style="color:#ff0000">vermelho</span></p>'
        payload = cf_html_bytes(fragment)
        header = payload.split(b"<html>", 1)[0]
        offsets = {key.decode("ascii"): int(value) for key,value in
                   re.findall(rb"(StartHTML|EndHTML|StartFragment|EndFragment):(\d+)",header)}
        self.assertEqual(payload[offsets["StartHTML"]:offsets["StartHTML"]+6], b"<html>")
        self.assertEqual(offsets["EndHTML"], len(payload))
        self.assertEqual(payload[offsets["StartFragment"]:offsets["EndFragment"]],
                         fragment.encode("utf-8"))
        self.assertIn(b"<!--StartFragment-->", payload)
        self.assertIn(b"<!--EndFragment-->", payload)

    def test_windows_payload_has_html_rtf_and_editable_text(self):
        from app.clipboard_content import expansion_mime
        from app.rich_clipboard import cf_html_bytes
        with patch("app.clipboard_content.sys.platform", "win32"):
            mime = expansion_mime(
                "CADASTRO COLABORADOR 22/10/2026\n\nvamos testar essa bagaça",
                self.sample_html())
        html_mime = 'application/x-qt-windows-mime;value="HTML Format"'
        rtf_mime = 'application/x-qt-windows-mime;value="Rich Text Format"'
        self.assertTrue(mime.hasText())
        self.assertTrue(mime.hasHtml())
        self.assertTrue(mime.hasFormat(html_mime))
        self.assertTrue(mime.hasFormat(rtf_mime))
        self.assertFalse(mime.hasImage())
        self.assertFalse(mime.hasFormat("image/png"))
        self.assertEqual(mime.data(html_mime).data().count(b"StartFragment:"), 1)
        self.assertIn(b"\\highlight", bytes(mime.data(rtf_mime)))

    def test_teams_web_html_only_retains_html_and_text_without_office_formats(self):
        from app.clipboard_content import expansion_mime
        with patch("app.clipboard_content.sys.platform", "win32"):
            mime = expansion_mime("CADASTRO\ntexto em destaque", self.sample_html(),
                                  web_html_only=True)
        self.assertTrue(mime.hasText())
        self.assertTrue(mime.hasHtml())
        self.assertIn("#b345e2", mime.html())
        self.assertIn("background-color:#36d119", mime.html())
        self.assertFalse(any("Rich Text Format" in x or "HTML Format" in x
                             for x in mime.formats()))
        self.assertFalse(mime.hasImage())

    def test_plain_snippet_does_not_acquire_rtf_or_html(self):
        from app.clipboard_content import expansion_mime
        with patch("app.clipboard_content.sys.platform", "win32"):
            mime = expansion_mime("Texto simples")
        self.assertFalse(mime.hasHtml())
        self.assertFalse(any("Rich Text Format" in v for v in mime.formats()))
        self.assertEqual(mime.text(), "Texto simples")

    def test_mixed_images_keep_original_html_with_separate_image_resources(self):
        from app.clipboard_content import expansion_mime
        data_uri = ("data:image/png;base64,"
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                    "AAAAC0lEQVR42mP8/x8AAusB9WlD7l8AAAAASUVORK5CYII=")
        html = f"<html><body><p>Texto antes</p><img src='{data_uri}'/><p>Texto depois</p></body></html>"
        with patch("app.clipboard_content.sys.platform", "win32"):
            payload = expansion_mime("Texto antes\nTexto depois", html)
        self.assertIn(data_uri, payload.html())
        self.assertFalse(any("Rich Text Format" in m for m in payload.formats()))
        self.assertEqual(payload.text(), "Texto antes\nTexto depois")
        self.assertFalse(payload.hasImage())

    @unittest.skipUnless(sys.platform == "win32", "Clipboard nativo Windows")
    def test_windows_registers_html_and_rtf_formats_for_office(self):
        from PySide6.QtWidgets import QApplication
        if QApplication.platformName().lower() != "windows":
            self.skipTest("Qt offscreen não publica no clipboard nativo Win32")
        import ctypes
        from app.clipboard_content import expansion_mime
        mime = expansion_mime("Teste", self.sample_html())
        board = QApplication.clipboard()
        old = board.mimeData()
        formats = list(old.formats()) if old else []
        originals = [(f, bytes(old.data(f))) for f in formats] if old else []
        try:
            board.setMimeData(mime)
            import ctypes.wintypes as wt
            user = ctypes.windll.user32
            user.RegisterClipboardFormatW.argtypes = [wt.LPCWSTR]
            user.RegisterClipboardFormatW.restype = wt.UINT
            user.IsClipboardFormatAvailable.argtypes = [wt.UINT]
            user.IsClipboardFormatAvailable.restype = wt.BOOL
            for name in ("HTML Format", "Rich Text Format"):
                format_id = user.RegisterClipboardFormatW(name)
                self.assertTrue(user.IsClipboardFormatAvailable(format_id), name)
        finally:
            from PySide6.QtCore import QMimeData
            restored = QMimeData()
            for fmt, data in originals:
                restored.setData(fmt, data)
            board.setMimeData(restored)


if __name__ == "__main__":
    unittest.main()
