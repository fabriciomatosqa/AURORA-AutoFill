"""Geometry and click regressions for the Word-like ribbon controls."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QSize
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.emoji_art import emoji_icon
from app.icons import apply_icon
from app.ribbon import RibbonFooter, RibbonToolButton
from app.themes import ThemeController


class RibbonGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_square_icon_is_centered_even_in_wide_column(self):
        theme = ThemeController('dark')
        try:
            for mode in ('dark', 'light'):
                theme.set_preference(mode)
                for split in (False, True):
                    button = RibbonToolButton(menu=split)
                    button.setFixedSize(72, 27)
                    apply_icon(button, 'align-left')
                    button.setIconSize(QSize(18,18))
                    button.show()
                    self.app.processEvents()
                    visible = button.visual_rect()
                    icon = button.icon_rect()
                    self.assertTrue(button.rect().contains(visible))
                    self.assertTrue(visible.contains(icon))
                    self.assertLessEqual(visible.width(), 41)
                    width = visible.width()-(13 if split else 0)
                    self.assertLessEqual(abs(icon.center().x()-(visible.left()+(width-1)//2)), 1)
                    self.assertLessEqual(abs(icon.center().y()-visible.center().y()), 1)
                    self.assertFalse(button.grab().isNull())
                    button.hide()
                    button.deleteLater()
        finally:
            theme.set_preference('dark')

    def test_word_footer_has_caption_and_operable_launcher(self):
        calls = []
        footer = RibbonFooter('Parágrafo', lambda: calls.append('open'))
        try:
            footer.show()
            self.app.processEvents()
            self.assertEqual(footer.label.text(), 'Parágrafo')
            self.assertIn('opções completas', footer.launcher.toolTip())
            self.assertFalse(footer.launcher.icon().isNull())
            QTest.mouseClick(footer.launcher, Qt.LeftButton)
            self.assertEqual(calls, ['open'])
        finally:
            footer.hide()
            footer.deleteLater()

    def test_fluent_emoji_icon_fits_button_and_renders_color(self):
        button = RibbonToolButton()
        button.setFixedSize(72,27)
        button.setIcon(emoji_icon('🙂'))
        button.setIconSize(QSize(23,23))
        button.show()
        self.app.processEvents()
        try:
            self.assertTrue(button.visual_rect().contains(button.icon_rect()))
            image = button.grab().toImage()
            self.assertFalse(image.isNull())
            yellow = sum(
                image.pixelColor(x,y).red()>170 and
                image.pixelColor(x,y).green()>110 and
                image.pixelColor(x,y).blue()<150
                for y in range(image.height()) for x in range(image.width())
            )
            self.assertGreater(yellow,20)
        finally:
            button.hide()
            button.deleteLater()


if __name__ == '__main__':
    unittest.main()
