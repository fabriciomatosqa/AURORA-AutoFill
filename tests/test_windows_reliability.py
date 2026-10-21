"""Regressões do fluxo de expansão; não injeta teclas em aplicativos reais."""
import ctypes
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.hotkeys import GlobalHotkeyListener, ShortcutMatcher, _send_windows_paste
from engine_fixture import EngineTestCase


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
        self.assertEqual([c.shortcut for c in received], ['/oi '])

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
        self.assertEqual([c.shortcut for c in received], ['/OI'])

    def test_typo_backspace_correction_expands_immediately(self):
        matcher = ShortcutMatcher(['/bomdia'])
        for ch in '/bomdiq':
            self.assertIsNone(matcher.feed(ch))
        self.assertIsNone(matcher.feed(None, 'backspace'))
        self.assertEqual(matcher.feed('a'), '/bomdia')

    def test_long_prefix_and_correction_are_not_premature(self):
        matcher = ShortcutMatcher(['/bom', '/bomdia'])
        for ch in '/bomdiq':
            self.assertIsNone(matcher.feed(ch))
        self.assertIsNone(matcher.feed(None, 'backspace'))
        self.assertEqual(matcher.feed('a'), '/bomdia')
        matcher.clear()
        for ch in '/bom':
            self.assertIsNone(matcher.feed(ch))
        self.assertEqual(matcher.feed(' ', 'space'), '/bom ')

    def test_lookup_with_thousands_of_shortcuts_and_mixed_case(self):
        matcher = ShortcutMatcher([f'/comando{i}' for i in range(5000)] + ['/bomdia'])
        for ch in '/BOMDI':
            self.assertIsNone(matcher.feed(ch))
        self.assertEqual(matcher.feed('A'), '/BOMDIA')

    def test_one_character_shortcut_without_overlap_fires_on_keyup(self):
        received = []
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/1'])
        for character in '/1':
            listener._on_press(key(character))
            listener._on_release(key(character))
        self.assertEqual([c.shortcut for c in received], ['/1'])

    def test_one_character_prefix_fires_after_quiet_period(self):
        from app.expansion import FocusContext
        received, timers = [], []
        class ManualTimer:
            def __init__(self, delay, callback):
                self.delay, self.callback = delay, callback
                self.cancelled = False
                timers.append(self)
            def start(self):
                pass
            def cancel(self):
                self.cancelled = True
            def fire(self):
                self.callback()
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/1', '/10', '/11'])
        with patch('app.hotkeys.Timer', ManualTimer), \
             patch('app.hotkeys.capture_focus', return_value=FocusContext(101, 1)):
            for character in '/1':
                listener._on_press(key(character))
                listener._on_release(key(character))
            self.assertEqual(received, [])
            self.assertEqual(len(timers), 1)
            self.assertLessEqual(timers[0].delay, 0.25)
            timers[0].fire()
            self.assertEqual([c.shortcut for c in received], ['/1'])
            timers[0].fire()  # callback duplicado não executa novamente
            self.assertEqual(len(received), 1)

    def test_typing_longer_shortcut_cancels_short_prefix(self):
        from app.expansion import FocusContext
        received, timers = [], []
        class ManualTimer:
            def __init__(self, delay, callback):
                self.callback, self.cancelled = callback, False
                timers.append(self)
            def start(self):
                pass
            def cancel(self):
                self.cancelled = True
            def fire(self):
                self.callback()
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/1', '/10'])
        with patch('app.hotkeys.Timer', ManualTimer), \
             patch('app.hotkeys.capture_focus', return_value=FocusContext(101, 1)):
            for character in '/10':
                listener._on_press(key(character))
                listener._on_release(key(character))
            self.assertTrue(timers[0].cancelled)
            self.assertEqual([c.shortcut for c in received], ['/10'])
            timers[0].fire()  # timer antigo não pode colar /1
            self.assertEqual([c.shortcut for c in received], ['/10'])

    def test_short_prefix_backspace_and_new_input_are_safe(self):
        from app.expansion import FocusContext
        received, timers = [], []
        class ManualTimer:
            def __init__(self, delay, callback):
                self.callback, self.cancelled = callback, False
                timers.append(self)
            def start(self):
                pass
            def cancel(self):
                self.cancelled = True
            def fire(self):
                self.callback()
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/1', '/10'])
        with patch('app.hotkeys.Timer', ManualTimer), \
             patch('app.hotkeys.capture_focus', return_value=FocusContext(101, 1)):
            for character in '/1x':
                listener._on_press(key(character))
                listener._on_release(key(character))
            self.assertTrue(timers[0].cancelled)
            timers[0].fire()
            self.assertEqual(received, [])
            backspace = key(name='backspace')
            listener._on_press(backspace)
            listener._on_release(backspace)
            self.assertEqual(len(timers), 2)
            timers[-1].fire()
            self.assertEqual([c.shortcut for c in received], ['/1'])

    def test_pending_shortcut_is_invalidated_on_focus_or_pause(self):
        from app.expansion import FocusContext
        received, timers = [], []
        class ManualTimer:
            def __init__(self, delay, callback):
                self.callback, self.cancelled = callback, False
                timers.append(self)
            def start(self):
                pass
            def cancel(self):
                self.cancelled = True
            def fire(self):
                self.callback()
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(['/1', '/10'])
        with patch('app.hotkeys.Timer', ManualTimer), \
             patch('app.hotkeys.capture_focus', return_value=FocusContext(101, 1)):
            for character in '/1':
                listener._on_press(key(character))
                listener._on_release(key(character))
            listener.invalidate()
            self.assertTrue(timers[0].cancelled)
            timers[0].fire()
            self.assertEqual(received, [])
            for character in '/1':
                listener._on_press(key(character))
                listener._on_release(key(character))
            listener.set_enabled(False)
            self.assertTrue(timers[1].cancelled)
            timers[1].fire()
            self.assertEqual(received, [])

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


class ClipboardAndUnicodeTests(EngineTestCase):

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
        self.engine.type('/ola')
        self.engine.until(20)
        self.clipboard.sequence += 1
        self.engine.drain()
        self.assertTrue(self.clipboard.text().startswith('Olá!'))
        self.assertFalse(self.win._clipboard_pending)

    def test_failed_injection_restores_clipboard(self):
        with patch('app.ui.replace_shortcut', side_effect=OSError('falha')):
            self.expand()
        self.assertEqual(self.clipboard.text(), 'original')
        self.assertFalse(self.win._clipboard_pending)

    def test_nul_is_rejected_before_injection(self):
        self.engine.save('/nul', 'a\x00b')
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
        self.engine.listener.update_shortcuts(['/texto'])
        self.expand('/texto').assert_called_once()
        self.assertEqual(self.engine.field.text.replace('\r\n', '\n'), text.replace('\r\n', '\n'))

    def test_unicode_cursor_counts_visual_characters(self):
        from app.ui import cursor_steps
        self.assertEqual(cursor_steps('é😀e\u0301👨‍👩‍👧‍👦\r\n'), 5)
        folder = self.win.store.folders()[0][0]
        self.win.store.save(folder, 'Unicode', '/unicode', 'Olá {{cursor}}😀e\u0301\r\nfim')
        self.engine.listener.update_shortcuts(['/unicode'])
        self.expand('/unicode').assert_called_once_with(8)
        self.engine.position.assert_called_once()
        self.assertEqual(self.engine.position.call_args.args[1], 4)
        self.engine.move.assert_not_called()

    def test_confirming_space_is_selected_with_shortcut(self):
        # O cadastro novo bloqueia /ola + /olax. Este teste valida a
        # compatibilidade com um par legado já salvo por versões anteriores.
        folder = self.win.store.folders()[0][0]
        with self.win.store.connection:
            self.win.store.connection.execute(
                "INSERT INTO snippets(folder_id,title,shortcut,content) VALUES (?,?,?,?)",
                (folder, 'Legado', '/olax', 'Outro'))
        self.engine.listener.update_shortcuts(
            [s.shortcut for s in self.win.store.snippets()])
        self.expand('/ola ').assert_called_once_with(5)

    def test_changed_foreground_aborts_before_clipboard_write(self):
        self.engine.type('/ola')
        self.engine.window_id = 456
        self.engine.drain()
        self.engine.replace.assert_not_called()
        self.assertEqual(self.clipboard.text(), 'original')


if __name__ == '__main__':
    unittest.main()
