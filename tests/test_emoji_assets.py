"""Garantias visuais do seletor Unicode sem dependência de Segoe UI Emoji."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from app.emoji_art import emoji_icon, emoji_svgs
from app.emoji_picker import CATEGORIES, DEFAULT_RECENT


class EmojiArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_visible_emoji_and_category_icons_have_local_vectors(self):
        codes = {symbol for _, symbol, _ in CATEGORIES}
        codes.add("🕘")
        codes.update(DEFAULT_RECENT)
        codes.update(emoji for _, _, rows in CATEGORIES for emoji, _, _ in rows)
        self.assertGreaterEqual(len(codes), 300)
        self.assertEqual(codes - emoji_svgs().keys(), set())
        for emoji in codes:
            with self.subTest(emoji=emoji):
                self.assertFalse(emoji_icon(emoji).isNull())

    def test_smiley_draws_a_visibly_yellow_colored_icon(self):
        image = emoji_icon("🙂").pixmap(QSize(32, 32)).toImage()
        self.assertFalse(image.isNull())
        yellow = visible = 0
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                if color.alpha() > 100:
                    visible += 1
                    if color.red() > 170 and color.green() > 110 and color.blue() < 150:
                        yellow += 1
        self.assertGreater(visible, 150)
        self.assertGreater(yellow, 100)


if __name__ == "__main__":
    unittest.main()
