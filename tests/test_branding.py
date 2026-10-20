"""A marca precisa ser a mesma na janela, app, instalador e Linux."""
import io
import unittest
from pathlib import Path

from app.branding import brand_webp_bytes


class BrandingTests(unittest.TestCase):
    def test_transparent_logo_is_intact(self):
        data = brand_webp_bytes()
        self.assertEqual(data[:4], b"RIFF")
        self.assertEqual(data[8:12], b"WEBP")
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        self.assertEqual(img.size, (256, 256))
        alpha = img.getchannel("A")
        self.assertEqual(alpha.getextrema(), (0, 255))

    def test_generated_variants_are_valid(self):
        from PIL import Image
        root = Path(__file__).resolve().parents[1] / "assets"
        sizes = [("aurora_icon.png", (512, 512)),
                 ("aurora_icon_256.png", (256, 256))]
        for name, size in sizes:
            with Image.open(root / name) as img:
                self.assertEqual(img.size, size)
                self.assertEqual(img.mode, "RGBA")
                self.assertEqual(img.getchannel("A").getextrema(), (0, 255))
        with Image.open(root / "aurora_icon.ico") as ico:
            self.assertEqual(ico.size, (256, 256))


if __name__ == "__main__":
    unittest.main()
