import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.expansion import EditSnapshot, FocusContext, utf16_length
from app.windows_context import (ContextUnavailable, MAX_TEXT_UNITS,
                                 capture_edit, select_text_range)
from app.accessibility_context import SELECTION_SUBMITTED


class WindowsContextTests(unittest.TestCase):
    def read(self, text='/ola', selection=(4, 4), class_name='RichEditD2DPT', fail=False, length=None):
        context = FocusContext(101, 1)
        def name(_hwnd, buffer, _size):
            buffer.value = class_name
            return len(class_name)
        def send(_hwnd, message, wparam, lparam, _flags, _timeout, result):
            if fail:
                return 0
            if message == 0x0E:
                value = utf16_length(text) if length is None else length
            elif message == 0xB0:
                value = selection[0] | (selection[1] << 16)
            else:
                buffer = ctypes.create_unicode_buffer(text)
                ctypes.memmove(lparam, buffer, ctypes.sizeof(buffer))
                value = utf16_length(text)
            result._obj.value = value
            return 1
        api = SimpleNamespace(GetClassNameW=name, SendMessageTimeoutW=send)
        with patch('app.windows_context.sys.platform', 'win32'), \
             patch('app.windows_context._api', return_value=api), \
             patch('app.windows_context.capture_focus', return_value=context):
            return capture_edit(context)

    def test_uia_ack_is_pending_not_a_confirmation(self):
        snapshot = EditSnapshot(FocusContext(101, 1), '/ola', 4, 4,
                                ('process', 'field', 'document'))
        with patch('app.windows_context.capture_focus', return_value=snapshot.context), \\
             patch('app.windows_context.select_accessible',
                   return_value=SELECTION_SUBMITTED) as action:
            self.assertIs(select_text_range(snapshot, 0, 4), SELECTION_SUBMITTED)
            action.assert_called_once_with(snapshot, 0, 4)

    def test_known_edit_returns_text_and_selection(self):
        snapshot = self.read()
        self.assertEqual(snapshot.shortcut_range('/ola'), (0, 4))
        self.assertEqual(snapshot.replace(0, 4, 'OK'), 'OK')

    def test_unknown_control_is_not_queried_with_edit_messages(self):
        self.assertIsNone(self.read(class_name='UnknownCustomControl', fail=True))

    def test_accessibility_is_opt_in_and_rechecks_focus(self):
        context = FocusContext(101, 1)
        def name(_hwnd, buffer, _size):
            buffer.value = 'Chrome_RenderWidgetHostHWND'
            return 27
        api = SimpleNamespace(GetClassNameW=name)
        expected = EditSnapshot(context, '/ola', 4, 4, ('7', 'field', 'doc'))
        with patch('app.windows_context.sys.platform', 'win32'), \
             patch('app.windows_context._api', return_value=api), \
             patch('app.windows_context.capture_accessible', return_value=expected) as accessible, \
             patch('app.windows_context.capture_focus', return_value=context):
            self.assertEqual(capture_edit(context), expected)
            accessible.assert_called_once_with(context)
            self.assertEqual(capture_edit(context, accessibility=True), expected)
            with patch('app.windows_context.capture_focus', side_effect=[context, FocusContext(102, 2)]):
                with self.assertRaises(ContextUnavailable):
                    capture_edit(context, accessibility=True)

    def test_unresponsive_known_control_cancels_instead_of_unsafe_fallback(self):
        with self.assertRaises(ContextUnavailable):
            self.read(fail=True)

    def test_large_control_refuses_truncated_selection(self):
        with self.assertRaises(ContextUnavailable):
            self.read(length=MAX_TEXT_UNITS + 1)

    def test_utf16_range_preserves_emoji_before_shortcut(self):
        snapshot = self.read('😀/ola', (6, 6))
        self.assertEqual(snapshot.shortcut_range('/ola'), (2, 6))
        self.assertEqual(snapshot.replace(2, 6, 'OK'), '😀OK')

    def test_existing_selection_and_wrong_suffix_are_rejected(self):
        self.assertIsNone(self.read(selection=(0, 4)).shortcut_range('/ola'))
        self.assertIsNone(self.read(text='/olx').shortcut_range('/ola'))

    def test_richedit_crlf_export_does_not_shift_native_caret_offsets(self):
        snapshot = self.read('A\r\n/ola', (6, 6))
        self.assertEqual(snapshot.text, 'A\r/ola')
        self.assertEqual(snapshot.shortcut_range('/ola'), (2, 6))
        self.assertEqual(snapshot.replace(2, 6, 'OK'), 'A\rOK')
        standard = self.read('A\r\n/ola', (7, 7), class_name='Edit')
        self.assertEqual(standard.shortcut_range('/ola'), (3, 7))
