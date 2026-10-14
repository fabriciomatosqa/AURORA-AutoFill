"""Regressões do fluxo de expansão; não injeta teclas em aplicativos reais."""
import ctypes
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.hotkeys import GlobalHotkeyListener, ShortcutMatcher, _send_windows_paste


def key(char=None, name=""):
    return SimpleNamespace(char=char, name=name, vk=ord(char) if char else None)


class RecognitionTests(unittest.TestCase):
    def test_longer_shortcut_is_not_preempted(self):
        matcher = ShortcutMatcher(['/oi', '/oie'])
        self.assertEqual([matcher.feed(c) for c in '/oie'], [None, None, None, '/oie'])

    def test_ambiguous_shortcut_requires_space(self):
        matcher = ShortcutMatcher(['/oi', '/oie'])
        self.assertEqual([matcher.feed(c) for c in '/oi '], [None, None, None, '/oi '])

    def test_space_key_release_confirms_shortcut(self):
        received = []
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/oi', '/oie'])
        for c in '/oi':
            listener._on_press(key(c))
            listener._on_release(key(c))
        space = key(name='space')
        listener._on_press(space)
        self.assertEqual(received, [])
        listener._on_release(space)
        self.assertEqual(received, ['/oi '])

    def test_waits_for_shift_release(self):
        received = []
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/OI'])
        shift = key(name='shift')
        listener._on_press(shift)
        for c in '/OI':
            listener._on_press(key(c))
            listener._on_release(key(c))
        self.assertEqual(received, [])
        listener._on_release(shift)
        self.assertEqual(received, ['/OI'])

    def test_ctrl_combination_does_not_match(self):
        received = []
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/oi'])
        listener._on_press(key(name='ctrl_l'))
        for c in '/oi':
            listener._on_press(key(c))
            listener._on_release(key(c))
        listener._on_release(key(name='ctrl_l'))
        self.assertEqual(received, [])


class InjectionTests(unittest.TestCase):
    def test_failed_paste_does_not_send_delete_or_backspace(self):
        sent = []
        class Stub:
            def __call__(self, count, records, size):
                values = [(records[i].u.ki.wVk, records[i].u.ki.dwFlags) for i in range(count)]
                sent.extend(values)
                return 0 if any(vk == 0x56 for vk, _ in values) else count
        api = SimpleNamespace(SendInput=Stub(), GetAsyncKeyState=lambda _: 0)
        with patch.object(ctypes, 'windll', SimpleNamespace(user32=api), create=True):
            with self.assertRaises(OSError):
                _send_windows_paste(3)
        self.assertFalse(any(vk in (8, 0x2E) for vk, _ in sent))
        self.assertEqual(sent[-2:], [(0x10, 2), (0x11, 2)])

    def test_pressed_modifier_aborts_before_selection(self):
        from unittest.mock import Mock
        send = Mock()
        api = SimpleNamespace(SendInput=send, GetAsyncKeyState=lambda _: 0x8000)
        with patch.object(ctypes, 'windll', SimpleNamespace(user32=api), create=True):
            with self.assertRaises(OSError):
                _send_windows_paste(3)
        send.assert_not_called()


class ClipboardAndUnicodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
            from app.ui import AutoFillWindow
        except ImportError:
            raise unittest.SkipTest('PySide6 indisponível')
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.ui import AutoFillWindow
        from PySide6.QtCore import QMimeData
        # Isola o clipboard dos testes de cópias feitas no desktop durante a suíte.
        class Clipboard:
            def __init__(self):
                self.mime = QMimeData()
            def mimeData(self):
                return self.mime
            def text(self):
                return self.mime.text()
            def setMimeData(self, mime):
                self.mime = mime
            def setText(self, text):
                self.mime = QMimeData()
                self.mime.setText(text)
            def clear(self):
                self.mime = QMimeData()
        self.clipboard = Clipboard()
        clipboard_patch = patch('app.ui.QApplication.clipboard', return_value=self.clipboard)
        sequence_patch = patch('app.ui.windows_clipboard_sequence', return_value=1)
        clipboard_patch.start()
        sequence_patch.start()
        self.addCleanup(clipboard_patch.stop)
        self.addCleanup(sequence_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        with patch('app.ui.application_db_path', return_value=Path(self.temp.name) / 'test.db'), \
             patch('app.ui.GlobalHotkeyListener.start', return_value=(False, 'Teste')):
            self.win = AutoFillWindow()
        self.clipboard.setText('original')

    def tearDown(self):
        self.win._quitting = True
        self.win.close()
        self.clipboard.clear()
        self.app.processEvents()
        self.temp.cleanup()

    def expand(self, shortcut='/ola', replacement=None):
        with patch('app.ui.type_backspace_and_paste') as paste, \
             patch('app.ui.QTimer.singleShot') as timer, \
             patch.object(self.win, '_play_confirmation'):
            self.win._perform_expansion(shortcut)
            if replacement:
                replacement()
            if timer.called:
                timer.call_args.args[1]()
            return paste

    def test_new_copy_with_same_text_is_preserved(self):
        from PySide6.QtCore import QMimeData
        def copy_again():
            mime = QMimeData()
            mime.setText(self.clipboard.text())
            mime.setHtml('<b>Nova cópia</b>')
            self.clipboard.setMimeData(mime)
        self.expand(replacement=copy_again)
        self.assertEqual(self.clipboard.mimeData().html(), '<b>Nova cópia</b>')

    def test_new_copy_with_different_text_is_preserved(self):
        self.expand(replacement=lambda: self.clipboard.setText('nova cópia'))
        self.assertEqual(self.clipboard.text(), 'nova cópia')

    def test_changed_windows_sequence_prevents_restoration(self):
        # Mesmo texto e token não bastam se o Windows registrou outra cópia.
        with patch('app.ui.windows_clipboard_sequence', side_effect=[10, 11]):
            self.expand()
        self.assertTrue(self.clipboard.text().startswith('Olá!'))
        self.assertFalse(self.win._clipboard_pending)

    def test_failed_injection_restores_clipboard(self):
        with patch('app.ui.type_backspace_and_paste', side_effect=OSError('falha')), \
             patch('app.ui.QTimer.singleShot') as timer:
            self.win._perform_expansion('/ola')
            timer.call_args.args[1]()
        self.assertEqual(self.clipboard.text(), 'original')
        self.assertFalse(self.win._clipboard_pending)

    def test_nul_is_rejected_before_injection(self):
        folder = self.win.store.folders()[0][0]
        self.win.store.save(folder, 'Inválido', '/nul', 'a\x00b')
        self.expand('/nul').assert_not_called()
        self.assertEqual(self.clipboard.text(), 'original')

    def test_invalid_surrogate_is_rejected_before_injection(self):
        from app.core import RenderResult
        with patch('app.ui.render_snippet', return_value=RenderResult('a\ud800b')):
            self.expand().assert_not_called()
        self.assertEqual(self.clipboard.text(), 'original')

    def test_accents_emojis_and_newlines_reach_clipboard_intact(self):
        text = 'Ação 😀\r\nsegunda linha\n👨‍👩‍👧‍👦'
        folder = self.win.store.folders()[0][0]
        self.win.store.save(folder, 'Texto', '/texto', text)
        with patch('app.ui.type_backspace_and_paste') as paste, \
             patch('app.ui.QTimer.singleShot') as timer, \
             patch.object(self.win, '_play_confirmation'):
            paste.side_effect = lambda *args: self.assertEqual(self.clipboard.text().replace('\r\n', '\n'), text.replace('\r\n', '\n'))
            self.win._perform_expansion('/texto')
            paste.assert_called_once()
            timer.call_args.args[1]()

    def test_unicode_cursor_counts_visual_characters(self):
        from app.ui import cursor_steps
        self.assertEqual(cursor_steps('é😀e\u0301👨‍👩‍👧‍👦\r\n'), 5)
        folder = self.win.store.folders()[0][0]
        self.win.store.save(folder, 'Unicode', '/unicode', 'Olá {{cursor}}😀e\u0301\r\nfim')
        self.expand('/unicode').assert_called_once_with(8, 6)

    def test_confirming_space_is_selected_with_shortcut(self):
        self.expand('/ola ').assert_called_once_with(5, 0)

    def test_changed_foreground_aborts_before_clipboard_write(self):
        self.win._expansion_target = 123
        with patch('app.ui.foreground_window', return_value=456):
            self.expand().assert_not_called()
        self.assertEqual(self.clipboard.text(), 'original')


if __name__ == '__main__':
    unittest.main()
