"""Testes visuais e funcionais para a barra Word do AURORA."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class WordColorButtonTests(unittest.TestCase):
    def test_bottom_marker_is_rendered_and_changes_with_color(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QColor
        from app.color_button import AuroraColorButton
        app = QApplication.instance() or QApplication([])
        type(self)._app = app
        button = AuroraColorButton("A", QColor("#d32f2f"))
        self.assertEqual(button.marker_color().name(), "#d32f2f")
        try:
            button.show()
            app.processEvents()
            center = button.marker_rect().center()
            first = button.grab().toImage().pixelColor(center)
            self.assertEqual(first.name(), "#d32f2f")
            button.set_marker_color("#2196f3")
            app.processEvents()
            second = button.grab().toImage().pixelColor(center)
            self.assertEqual(second.name(), "#2196f3")
            button.set_marker_color("not-a-color")
            self.assertEqual(button.marker_color().name(), "#2196f3")
        finally:
            button.hide()
            button.deleteLater()
            app.processEvents()

    def test_highlighter_has_its_own_indicator(self):
        from PySide6.QtWidgets import QApplication
        from app.color_button import AuroraColorButton
        app = QApplication.instance() or QApplication([])
        type(self)._app = app
        first = AuroraColorButton("A", "#f44336")
        second = AuroraColorButton("✎", "#ffeb3b")
        try:
            first.set_marker_color("#009688")
            self.assertEqual(first.marker_color().name(), "#009688")
            self.assertEqual(second.marker_color().name(), "#ffeb3b")
        finally:
            first.deleteLater()
            second.deleteLater()


class WordToolbarOrderTests(unittest.TestCase):
    def test_toolbar_matches_word_row_order_and_remains_compact(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from PySide6.QtTest import QTest
        from app.ui import AutoFillWindow
        from app.color_button import AuroraColorButton
        from app.themes import ui_color
        app = QApplication.instance() or QApplication([])
        type(self)._app = app
        with tempfile.TemporaryDirectory(prefix="aurora-wordbar-") as tmp:
            with patch('app.ui.application_db_path', return_value=Path(tmp) / 'test.db'), \
                 patch('app.ui.GlobalHotkeyListener.start',
                       return_value=(False, 'Modo de teste')), \
                 patch('app.ui.AutoFillWindow._initial_release_check'):
                win = AutoFillWindow()
                original_theme = win.theme_controller.preference
                try:
                    win._new_snippet()
                    win.resize(1060, 840)
                    win.show()
                    app.processEvents()
                    toolbar = win.font_controls.layout()
                    self.assertEqual(toolbar.count(), 3)
                    row0 = toolbar.itemAt(0).layout()
                    row1 = toolbar.itemAt(1).layout()
                    row2 = toolbar.itemAt(2).layout()
                    self.assertIs(row0.itemAt(0).widget(), win.font_family)
                    self.assertIs(row0.itemAt(1).widget(), win.font_size)
                    expected_modes = ["bold", "italic", "underline", "strike",
                                      "subscript", "superscript"]
                    for index, mode in enumerate(expected_modes):
                        self.assertIs(row1.itemAt(index).widget(), win.format_buttons[mode])
                    self.assertIs(row2.itemAt(0).widget(), win.text_color_button)
                    self.assertIs(row2.itemAt(1).widget(), win.highlight_button)
                    self.assertIsInstance(win.text_color_button, AuroraColorButton)
                    self.assertIsInstance(win.highlight_button, AuroraColorButton)
                    self.assertLessEqual(win.font_toolbar.sizeHint().height(), 115)
                    self.assertEqual(win.text_color_button.marker_rect().height(), 3)
                    self.assertEqual(win.highlight_button.marker_rect().height(), 3)
                    self.assertEqual(row2.count(),5)
                    self.assertEqual([row2.itemAt(i).widget().width() for i in range(5)], [55,55,69,45,45])
                    self.assertEqual(row2.itemAt(4).widget().geometry().right(),win.font_size.geometry().right())
                    self.assertEqual(win.paragraph_panel.height(),win.font_controls.height())
                    # Check rendered relationships: the old trailing stretch
                    # let CSS shrink buttons even when setFixedSize was used.
                    widths = {button.width() for button in win.format_buttons.values()}
                    self.assertEqual(len(widths), 1)
                    self.assertEqual(row1.itemAt(6).widget().geometry().right(),
                                     win.font_size.geometry().right())
                    self.assertEqual(win.shortcut_input.geometry().top(),
                                     win.editor_folder.geometry().top())
                    self.assertEqual(win.shortcut_input.height(), win.editor_folder.height())
                    spin = win.font_size
                    for theme in ('dark', 'light'):
                        win.theme_controller.set_preference(theme)
                        app.processEvents()
                        image = QImage(spin.size(), QImage.Format_ARGB32)
                        spin.render(image)
                        expected = ui_color('#81e9d9')
                        for up in (True, False):
                            rect = spin.step_button_rect(up)
                            self.assertTrue(spin.rect().contains(rect))
                            self.assertFalse(rect.isEmpty())
                            # The two step buttons used to render as empty
                            # squares on Windows. Require visible arrow pixels.
                            pixels = sum(
                                sum(abs(a-b) for a,b in zip(image.pixelColor(x,y).getRgb()[:3],
                                                          expected.getRgb()[:3])) < 60
                                for x in range(rect.left(), rect.right()+1)
                                for y in range(rect.top(), rect.bottom()+1))
                            self.assertGreater(pixels, 3)
                        initial = spin.value()
                        QTest.mouseClick(spin, Qt.LeftButton, pos=spin.step_button_rect(True).center())
                        self.assertEqual(spin.value(), initial + 1)
                        QTest.mouseClick(spin, Qt.LeftButton, pos=spin.step_button_rect(False).center())
                        self.assertEqual(spin.value(), initial)
                finally:
                    win.theme_controller.set_preference(original_theme)
                    win.dirty = False
                    win._quitting = True
                    win.close()
                    win.deleteLater()
                    app.clipboard().clear()
                    app.processEvents()


if __name__ == "__main__":
    unittest.main()
