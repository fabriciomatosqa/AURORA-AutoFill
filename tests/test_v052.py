"""Regressões da v0.5.2: sincronização de teclado, colagem Unicode e banner."""
import ctypes
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.hotkeys import GlobalHotkeyListener, _send_windows_paste

APP_KEEPALIVE = None

def qt_app():
    global APP_KEEPALIVE
    from PySide6.QtWidgets import QApplication
    APP_KEEPALIVE = QApplication.instance() or QApplication([])
    return APP_KEEPALIVE


class ReleaseSynchronisationTests(unittest.TestCase):
    def test_shortcut_fires_only_after_last_key_released(self):
        received = []
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/oi'])
        keys = [SimpleNamespace(char=x, name='', vk=ord(x)) for x in '/oi']
        for k in keys:
            listener._on_press(k)
        self.assertEqual(received, [])
        self.assertEqual(listener._pending, '/oi')
        listener._on_release(keys[0])
        self.assertEqual(received, [])
        listener._on_release(keys[-1])
        self.assertEqual([c.shortcut for c in received], ['/oi'])
        listener._on_release(keys[-1])
        self.assertEqual([c.shortcut for c in received], ['/oi'])

    def test_disabled_cancels_pending_shortcut(self):
        listener = GlobalHotkeyListener(lambda _: self.fail('não pode expandir'))
        listener.update_shortcuts(['/oi'])
        for x in '/oi':
            listener._on_press(SimpleNamespace(char=x, name='', vk=ord(x)))
        listener.set_enabled(False)
        listener._on_release(SimpleNamespace(char='i', name='', vk=ord('i')))
        self.assertIsNone(listener._pending)


class ClipboardPasteTests(unittest.TestCase):
    def test_windows_paste_selects_shortcut_before_ctrl_v(self):
        sent = []
        class Stub:
            def __call__(self, count, records, size):
                sent.extend((records[i].u.ki.wVk, records[i].u.ki.dwFlags)
                            for i in range(count))
                return count
        api = SimpleNamespace(SendInput=Stub(), GetAsyncKeyState=lambda vk: 0)
        with patch.object(ctypes, 'windll', SimpleNamespace(user32=api), create=True), \
             patch('time.sleep', return_value=None):
            _send_windows_paste(3, 2)
        self.assertEqual(sent[:8], [(0x10, 0)] + [(0x25, 1), (0x25, 3)] * 3 + [(0x10, 2)])
        self.assertEqual(sent[8:12], [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)])
        self.assertEqual(sent[12:], [(0x25, 1), (0x25, 3)] * 2)
        # Não emite evento Unicode 0x0004 usado pela estratégia antiga.
        self.assertFalse(any(flag & 0x0004 for _, flag in sent))

    def test_plain_text_uses_clipboard_and_preserves_previous_content(self):
        from engine_fixture import EngineFixture
        with EngineFixture() as engine:
            engine.clipboard.setText('Minha cópia original')
            engine.type('/ola')
            engine.until(75)
            mime = engine.clipboard.mimeData()
            self.assertTrue(mime.text().startswith('Olá!'))
            self.assertFalse(mime.hasHtml())
            self.assertTrue(engine.host._clipboard_pending)
            engine.drain()
            engine.replace.assert_called_once_with(len('/ola'))
            engine.host._play_confirmation.assert_called_once()
            self.assertEqual(engine.clipboard.text(), 'Minha cópia original')
            self.assertFalse(engine.host._clipboard_pending)


class BannerTests(unittest.TestCase):
    def test_source_crop_keeps_aspect_ratio(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        try:
            from PySide6.QtWidgets import QApplication
            from app.ui import AuroraBanner
        except ImportError:
            self.skipTest('PySide6 indisponível')
        qt_app()
        for w, h in [(1060, 168), (1920, 168), (1300, 168), (800, 250)]:
            crop = AuroraBanner.source_crop(2048, 768, w, h)
            self.assertAlmostEqual(crop.width() / crop.height(), w / h, places=5)
            self.assertGreater(crop.width(), 0)
            self.assertGreater(crop.height(), 0)

    def test_synthetic_sound_is_valid_wave(self):
        import wave
        path = Path(__file__).resolve().parents[1] / 'assets' / 'command_click.wav'
        with wave.open(str(path), 'rb') as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getframerate(), 44100)
            self.assertLess(wav.getnframes() / wav.getframerate(), 0.10)


if __name__ == '__main__':
    unittest.main()
