"""Nova marca: a imagem transparente é a mesma em todos os pacotes."""
import io
from pathlib import Path
import unittest

from app.branding import brand_webp_bytes


ASSETS = Path(__file__).resolve().parents[1] / "assets"


class AuroraLogoTests(unittest.TestCase):
    def test_source_is_integral_and_has_real_transparency(self):
        from PIL import Image
        raw = brand_webp_bytes(ASSETS)
        self.assertEqual(raw[:4], b"RIFF")
        self.assertEqual(raw[8:12], b"WEBP")
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        self.assertEqual(image.size, (256, 256))
        self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
        self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_generated_icon_files_use_the_same_logo(self):
        from PIL import Image, ImageChops
        source = Image.open(io.BytesIO(brand_webp_bytes(ASSETS))).convert("RGBA")
        with Image.open(ASSETS / "aurora_icon_256.png") as icon:
            self.assertEqual(icon.size, (256, 256))
            self.assertEqual(icon.mode, "RGBA")
            self.assertIsNone(ImageChops.difference(icon, source).getbbox())
        with Image.open(ASSETS / "aurora_icon.png") as icon:
            self.assertEqual(icon.size, (512, 512))
            self.assertEqual(icon.getchannel("A").getextrema(), (0, 255))
        with Image.open(ASSETS / "aurora_icon.ico") as icon:
            self.assertEqual(icon.size, (256, 256))
            self.assertTrue(icon.info.get("sizes"))


if __name__ == "__main__":
    unittest.main()
