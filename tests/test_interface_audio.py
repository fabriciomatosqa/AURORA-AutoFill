"""Regression coverage for dark settings surfaces and replaced sound assets."""
from array import array
import os
from pathlib import Path
import tempfile
import unittest
import wave

from app.audio import adjusted_sound


class AudioAssetTests(unittest.TestCase):
    def test_replaced_audio_invalidates_cache_even_with_same_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sound.wav"
            def write_sample(value):
                with wave.open(str(source), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(44100)
                    output.writeframes(array("h", [value] * 32).tobytes())
                os.utime(source, (1_600_000_000, 1_600_000_000))
            write_sample(1000)
            first = adjusted_sound(source, 30, root / "cache")
            write_sample(2000)
            second = adjusted_sound(source, 30, root / "cache")
            self.assertNotEqual(first, second)
            with wave.open(str(second), "rb") as output:
                self.assertEqual(array("h", output.readframes(32))[0], 600)

    def test_supplied_drop_is_short_portable_pcm_without_clipping(self):
        source = Path(__file__).resolve().parents[1] / "assets" / "command_click.wav"
        with wave.open(str(source), "rb") as sound:
            self.assertEqual((sound.getnchannels(), sound.getsampwidth()), (1, 2))
            self.assertLessEqual(sound.getnframes() / sound.getframerate(), 0.6)
            samples = array("h", sound.readframes(sound.getnframes()))
        self.assertGreater(max(abs(value) for value in samples), 100)
        self.assertLess(max(abs(value) for value in samples), 32767)


class SettingsSurfaceTests(unittest.TestCase):
    def test_settings_body_stays_blue_under_dark_native_palette(self):
        try:
            from PySide6.QtGui import QColor, QPalette
            from PySide6.QtWidgets import QApplication, QWidget
            from app.settings_panel import SettingsPage
        except ImportError:
            self.skipTest("PySide6 ausente")
        app = QApplication.instance() or QApplication([])
        palette = app.palette()
        dark = QPalette(palette)
        dark.setColor(QPalette.Window, QColor("#1e1e1e"))
        app.setPalette(dark)
        page = SettingsPage({"sound_enabled": True, "sound_volume": 65,
                             "check_updates": True}, startup_supported=True,
                            startup_enabled=False)
        try:
            page.resize(920, 740)
            page.show()
            app.processEvents()
            body = page.findChild(QWidget, "settingsContent")
            image = body.grab().toImage()
            self.assertEqual(image.pixelColor(2, image.height() - 2).name(), "#091426")
            page.sound.setChecked(False)
            self.assertFalse(page.volume.isEnabled())
            self.assertFalse(page.sample_button.isEnabled())
            page.sound.setChecked(True)
            self.assertTrue(page.sample_button.isEnabled())
        finally:
            page.close()
            page.deleteLater()
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            app.setPalette(palette)


if __name__ == "__main__":
    unittest.main()
