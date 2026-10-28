"""Garantias visuais do seletor Unicode sem dependência de Segoe UI Emoji."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from app.emoji_art import emoji_icon, emoji_artwork
from app.emoji_picker import CATEGORIES, DEFAULT_RECENT


class EmojiArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_visible_emoji_and_category_icons_have_local_fluent_3d_artwork(self):
        codes = {symbol for _, symbol, _ in CATEGORIES}
        codes.add("🕘")
        codes.update(DEFAULT_RECENT)
        codes.update(emoji for _, _, rows in CATEGORIES for emoji, _, _ in rows)
        self.assertGreaterEqual(len(codes), 300)
        self.assertEqual(codes - emoji_artwork().keys(), set())
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

    def test_fluent_atlas_has_pinned_sources_and_gradient_artwork(self):
        import hashlib
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]/'assets/emoji'
        data = json.loads((root/'fluent-3d.json').read_text(encoding='utf-8'))
        self.assertEqual(data['provider'],'Microsoft Fluent Emoji')
        self.assertEqual(data['style'],'3D')
        self.assertEqual(hashlib.sha256((root/data['atlas']).read_bytes()).hexdigest(),data['atlas_sha256'])
        image = emoji_icon('😀').pixmap(QSize(48,48)).toImage()
        colors = {image.pixelColor(x,y).rgb() for x in range(image.width()) for y in range(image.height())
                  if image.pixelColor(x,y).alpha()>200}
        self.assertGreater(len(colors),500)


if __name__ == "__main__":
    unittest.main()
