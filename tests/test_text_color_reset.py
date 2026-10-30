"""Resetting only text color or highlight must preserve all other styles."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import QApplication, QTextEdit

from app.text_color_reset import clear_selected_color


class TextColorResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = QTextEdit()
        self.editor.setPlainText("ABCD")
        cursor = self.editor.textCursor()
        cursor.select(QTextCursor.Document)
        style = QTextCharFormat()
        style.setForeground(QColor("#eecc22"))
        style.setBackground(QColor("#2266bb"))
        style.setFontWeight(700)
        style.setFontItalic(True)
        style.setFontUnderline(True)
        cursor.mergeCharFormat(style)
        self.editor.setTextCursor(cursor)

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()

    def select(self, start, end):
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def fmt_at(self, index):
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(index + 1)
        return cursor.charFormat()

    def test_remove_foreground_only_for_selected_range(self):
        self.select(1, 3)  # only BC, never A or D
        clear_selected_color(self.editor, highlight=False)
        self.assertEqual(self.editor.textCursor().selectedText(), "BC")
        for index in (1, 2):
            fmt = self.fmt_at(index)
            self.assertFalse(fmt.hasProperty(QTextFormat.ForegroundBrush))
            self.assertEqual(fmt.background().color().name(), "#2266bb")
            self.assertEqual(fmt.fontWeight(), 700)
            self.assertTrue(fmt.fontItalic())
            self.assertTrue(fmt.fontUnderline())
        for index in (0, 3):
            self.assertEqual(self.fmt_at(index).foreground().color().name(),
                             "#eecc22")
        self.assertEqual(self.editor.toPlainText(), "ABCD")

    def test_remove_highlight_without_changing_font_color(self):
        self.select(0, 4)
        clear_selected_color(self.editor, highlight=True)
        for index in range(4):
            fmt = self.fmt_at(index)
            self.assertFalse(fmt.hasProperty(QTextFormat.BackgroundBrush))
            self.assertEqual(fmt.foreground().color().name(), "#eecc22")
            self.assertTrue(fmt.fontItalic())
            self.assertEqual(fmt.fontWeight(), 700)

    def test_no_selection_restores_automatic_insertion_color(self):
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.editor.setTextCursor(cursor)
        self.assertTrue(self.editor.currentCharFormat().hasProperty(
            QTextFormat.ForegroundBrush))
        clear_selected_color(self.editor, highlight=False)
        self.assertFalse(self.editor.currentCharFormat().hasProperty(
            QTextFormat.ForegroundBrush))
        self.assertTrue(self.editor.currentCharFormat().hasProperty(
            QTextFormat.BackgroundBrush))
        self.assertTrue(self.editor.currentCharFormat().fontItalic())

    def test_color_reset_can_be_undone_in_one_step(self):
        self.select(0, 4)
        clear_selected_color(self.editor, highlight=False)
        self.assertFalse(self.fmt_at(2).hasProperty(QTextFormat.ForegroundBrush))
        self.editor.undo()
        self.assertEqual(self.fmt_at(2).foreground().color().name(), "#eecc22")


if __name__ == "__main__":
    unittest.main()
