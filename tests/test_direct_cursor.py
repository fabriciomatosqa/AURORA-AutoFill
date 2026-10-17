import ctypes
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.accessibility_context import capture_accessible, AccessibilityUnavailable
from app.expansion import EditSnapshot, FocusContext, prefix_offset, utf16_length
from app.windows_context import FocusMonitor
from engine_fixture import EngineFixture


class DirectCursorTests(unittest.TestCase):
    def test_prefix_offset_maps_native_newlines_and_utf16(self):
        self.assertEqual(prefix_offset('😀\r\nAB', '😀\nA'), 5)
        self.assertEqual(prefix_offset('😀\rAB', '😀\r\nA'), 4)
        self.assertEqual(prefix_offset('AB', ''), 0)
        with self.assertRaises(ValueError):
            prefix_offset('AB', 'AC')

    def test_webview_literal_and_long_cursor_paste_use_direct_selection(self):
        for content in ('Resposta simples', 'Olá 😀\n{{cursor}}' + 'e\u0301\n' * 2000):
            with self.subTest(cursor='{{cursor}}' in content), EngineFixture() as e:
                e.save('/teams', content)
                e.paste_delay = 1000  # asynchronous WebView paste
                def snapshot(context, **_):
                    current = e.snapshot(context)
                    return EditSnapshot(context, current.text, current.start, current.end,
                                        ('renderer-pid', 'editor', 'document'))
                with patch('app.ui.capture_edit', side_effect=snapshot):
                    e.type('/teams')
                    e.drain()
                e.selection.assert_called_once()
                e.replace.assert_not_called()
                e.move.assert_not_called()
                self.assertEqual(e.api_calls, 1)
                self.assertFalse(any(vk == 37 for vk, _, _ in e.sent))
                self.assertEqual(e.field.text, content.replace('{{cursor}}', ''))
                e.host._play_confirmation.assert_called_once()
                if '{{cursor}}' in content:
                    self.assertEqual(e.field.caret, utf16_length('Olá 😀\n'))

    def test_duplicate_focus_event_keeps_operation_but_real_change_invalidates(self):
        monitor = FocusMonitor.__new__(FocusMonitor)
        monitor._changed = Mock()
        monitor._last_focus = FocusContext(101, 1)
        with patch('app.windows_context.capture_focus', return_value=FocusContext(101, 1)):
            monitor._handle_event(0x8005, 1)
            monitor._changed.assert_not_called()
        with patch('app.windows_context.capture_focus', return_value=FocusContext(102, 2)):
            monitor._handle_event(3, 102)
        with patch('app.windows_context.capture_focus', return_value=FocusContext(101, 1)):
            monitor._handle_event(3, 101)
        self.assertEqual(monitor._changed.call_count, 2)

    def test_embedded_renderer_pid_is_allowed_only_with_matching_window_scope(self):
        context = FocusContext(101, 1)
        def pid(_window, pointer):
            pointer._obj.value = 77
            return 1
        response = dict(status='ok', text='/teams', start=6, end=6,
                        identity=['88', 'field', 'doc'], window='101', control='1')
        api = SimpleNamespace(GetWindowThreadProcessId=Mock(side_effect=pid))
        with patch.object(ctypes, 'windll', SimpleNamespace(user32=api), create=True), \
             patch('app.accessibility_context._client.request', return_value=response):
            self.assertEqual(capture_accessible(context).identity[0], '88')
            response['window'] = '999'
            with self.assertRaises(AccessibilityUnavailable):
                capture_accessible(context)
