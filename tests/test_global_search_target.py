"""End-to-end contracts for selecting a global command and restoring its target."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.expansion import FocusContext
from app.productivity_features import ProductivityMixin


class DummyHost:
    def __init__(self):
        self.store = object()
        self._quitting = False
        self._quick_picker_open = False
        self._status = Mock()
        self._launch_smart_snippet = Mock()

    def statusBar(self):
        return self._status

    def winId(self):
        return 9900


class QuickSearchTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_context_from_hotkey_survives_modal_search(self):
        origin = FocusContext(120, 34)
        snippet = SimpleNamespace(id=7, content="Texto", rich_content="")
        dlg = SimpleNamespace(Accepted=1, exec=lambda: 1,
                              selected_snippet=snippet)
        host = DummyHost()
        with patch("app.productivity_features.QuickSearchDialog",
                   return_value=dlg), patch(
                   "app.productivity_features.capture_focus") as capture:
            ProductivityMixin._open_global_search(host, origin)
        capture.assert_not_called()
        host._launch_smart_snippet.assert_called_once_with(
            snippet, origin, from_shortcut=None)
        self.assertFalse(host._quick_picker_open)

    def test_settings_button_without_context_captures_current_focus(self):
        origin = FocusContext(120, 34)
        snippet = SimpleNamespace(id=8, content="Outro texto", rich_content="")
        dlg = SimpleNamespace(Accepted=1, exec=lambda: 1,
                              selected_snippet=snippet)
        host = DummyHost()
        with patch("app.productivity_features.QuickSearchDialog",
                   return_value=dlg), patch(
                   "app.productivity_features.capture_focus",
                   return_value=origin) as capture:
            ProductivityMixin._open_global_search(host)
        capture.assert_called_once_with()
        host._launch_smart_snippet.assert_called_once_with(
            snippet, origin, from_shortcut=None)

    def test_selected_plain_command_is_sent_to_verified_previous_editor(self):
        origin = FocusContext(120, 34)
        host = DummyHost()
        snippet = SimpleNamespace(id=9, content="Texto do AURORA", rich_content="")
        calls = []
        with patch("app.productivity_features.sys.platform", "win32"), patch(
                "app.productivity_features.QTimer.singleShot",
                side_effect=lambda delay, cb: calls.append(cb)):
            ProductivityMixin._launch_smart_snippet(
                host, snippet, origin, from_shortcut=None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(QApplication.clipboard().text(), "Texto do AURORA")
        with patch("app.productivity_features.restore_target",
                   return_value=True) as restore, patch(
                   "app.productivity_features.paste_clipboard") as paste:
            calls[0]()
        restore.assert_called_once_with(origin)
        paste.assert_called_once_with()

    def test_changed_editor_is_not_pasted_and_content_remains_copyable(self):
        origin = FocusContext(120, 34)
        host = DummyHost()
        QApplication.clipboard().setText("Texto seguro")
        with patch("app.productivity_features.restore_target",
                   return_value=False), patch(
                   "app.productivity_features.paste_clipboard") as paste:
            ProductivityMixin._safe_paste_selected(
                host, origin, "Texto seguro", None, None)
        paste.assert_not_called()
        self.assertEqual(QApplication.clipboard().text(), "Texto seguro")

    def test_no_external_target_uses_clipboard_not_unfocused_injection(self):
        host = DummyHost()
        snippet = SimpleNamespace(id=10, content="Somente copiar", rich_content="")
        with patch("app.productivity_features.sys.platform", "win32"), patch(
                "app.productivity_features.QTimer.singleShot") as schedule:
            ProductivityMixin._launch_smart_snippet(
                host, snippet, FocusContext(), from_shortcut=None)
        schedule.assert_not_called()
        self.assertEqual(QApplication.clipboard().text(), "Somente copiar")


if __name__ == "__main__":
    unittest.main()
