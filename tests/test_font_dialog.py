"""Font launcher and native menu hit areas must preserve editable selections."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from app.font_dialog import FontDialog
from app.inline_images import AuroraImageEditor
from app.paragraph_panel import ParagraphPanel
from app.rich_clipboard import interoperable_html, rich_text_rtf


class FontDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_full_font_settings_survive_html_and_clipboard_without_changing_other_text(self):
        editor = AuroraImageEditor();editor.setPlainText('um dois três')
        cursor = editor.document().find('dois');editor.setTextCursor(cursor)
        dialog = FontDialog(cursor.charFormat(),editor.currentFont(),sample=cursor.selectedText())
        try:
            dialog.font_family.setCurrentText('Arial')
            dialog.font_size.setValue(18)
            dialog.font_style.setCurrentIndex(dialog.font_style.findData('bolditalic'))
            dialog.underline.setChecked(True);dialog.strike.setChecked(True)
            dialog.position.setCurrentIndex(dialog.position.findData('sub'))
            dialog._set_color(False,QBrush(QColor('#1234ab')))
            dialog._set_color(True,QBrush(QColor('#ffee33')))
            cursor.mergeCharFormat(dialog.value())
            for html in (editor.toHtml(),interoperable_html(editor.toHtml())):
                document = QTextDocument();document.setHtml(html)
                self.assertEqual(document.toPlainText(),'um dois três')
                fmt = document.find('dois').charFormat()
                self.assertEqual(fmt.fontPointSize(),18)
                self.assertEqual(fmt.fontWeight(),QFont.Bold)
                self.assertTrue(fmt.fontItalic());self.assertTrue(fmt.fontUnderline());self.assertTrue(fmt.fontStrikeOut())
                self.assertEqual(fmt.verticalAlignment(),QTextCharFormat.AlignSubScript)
                self.assertEqual(fmt.foreground().color().name(),'#1234ab')
                self.assertEqual(fmt.background().color().name(),'#ffee33')
                self.assertFalse(document.find('três').charFormat().fontItalic())
            rtf = rich_text_rtf(editor.toHtml()).decode('ascii')
            for flag in (r'\fs36',r'\b',r'\i',r'\ul',r'\strike',r'\sub'):
                self.assertIn(flag,rtf)
            editor.undo()
            self.assertFalse(editor.document().find('dois').charFormat().fontItalic())
        finally:
            dialog.deleteLater();editor.deleteLater();self.app.processEvents()

    def test_cancel_is_read_only_and_automatic_color_removes_old_colors(self):
        editor = AuroraImageEditor();editor.setHtml('<p><span style="color:#ff0000;background-color:#00ff00">Teste</span></p>')
        editor.selectAll();before=editor.toHtml()
        dialog = FontDialog(editor.textCursor().charFormat(),editor.currentFont())
        try:
            dialog.font_size.setValue(24);dialog.reject()
            self.assertEqual(editor.toHtml(),before)
            dialog._set_color(False,QBrush(Qt.NoBrush))
            dialog._set_color(True,QBrush(Qt.NoBrush))
            editor.textCursor().mergeCharFormat(dialog.value())
            fragment=interoperable_html(editor.toHtml())
            self.assertNotIn('#ff0000',fragment);self.assertNotIn('#00ff00',fragment)
            rtf=rich_text_rtf(editor.toHtml()).decode('ascii')
            self.assertNotIn(r'\red255\green0\blue0',rtf)
            self.assertNotIn(r'\red0\green255\blue0',rtf)
        finally:
            dialog.deleteLater();editor.deleteLater();self.app.processEvents()

    def test_font_footer_opens_dialog_and_applies_only_saved_selection(self):
        from app.ui import AutoFillWindow
        with tempfile.TemporaryDirectory() as temporary:
            with patch('app.ui.application_db_path',return_value=Path(temporary)/'test.db'), \
                 patch('app.ui.GlobalHotkeyListener.start',return_value=(False,'Teste')), \
                 patch('app.ui.AutoFillWindow._initial_release_check'):
                window=AutoFillWindow();window._new_snippet();window.show()
                window.body_input.setPlainText('um dois três')
                cursor=window.body_input.document().find('dois');window.body_input.setTextCursor(cursor)
                dialog=FontDialog(cursor.charFormat(),window.body_input.currentFont())
                dialog.font_size.setValue(18)
                try:
                    self.app.processEvents()
                    with patch('app.ui.FontDialog',return_value=dialog) as constructor, \
                         patch.object(dialog,'exec',return_value=QDialog.Accepted):
                        QTest.mouseClick(window.font_settings_button,Qt.LeftButton)
                    constructor.assert_called_once()
                    self.assertEqual(window.body_input.document().find('dois').charFormat().fontPointSize(),18)
                    self.assertNotEqual(window.body_input.document().find('três').charFormat().fontPointSize(),18)
                    before=window.body_input.toHtml();dialog.font_size.setValue(30)
                    with patch('app.ui.FontDialog',return_value=dialog),patch.object(dialog,'exec',return_value=QDialog.Rejected):
                        QTest.mouseClick(window.font_settings_button,Qt.LeftButton)
                    self.assertEqual(window.body_input.toHtml(),before)
                finally:
                    dialog.deleteLater();window.dirty=False;window._quitting=True
                    window.close();window.deleteLater();self.app.processEvents()

    def test_paragraph_main_and_menu_hit_areas_remain_separate(self):
        editor=AuroraImageEditor();editor.setPlainText('Item')
        panel=ParagraphPanel(editor);panel.show();self.app.processEvents()
        button=panel.buttons['bullet'];opened=[]
        button.menu().aboutToShow.connect(lambda:opened.append(True))
        try:
            QTimer.singleShot(30,button.menu().close)
            QTest.mouseClick(button,Qt.LeftButton,pos=QPoint(button.width()-5,button.height()//2))
            self.assertEqual(opened,[True])
            self.assertIsNone(editor.document().begin().textList())
            QTest.mouseClick(button,Qt.LeftButton,pos=button.rect().center())
            self.assertIsNotNone(editor.document().begin().textList())
            self.assertEqual(editor.toPlainText(),'Item')
        finally:
            button.menu().close();panel.close();panel.deleteLater();editor.deleteLater();self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
