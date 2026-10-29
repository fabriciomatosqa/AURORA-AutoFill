"""End-to-end contracts for selecting a global command and restoring its target."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.expansion import FocusContext
from app.productivity_features import ProductivityMixin


class DummyHost(ProductivityMixin):
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

    def tearDown(self):
        # Release Qt's native MIME object while the application still exists.
        QApplication.clipboard().clear()

    def test_context_from_hotkey_survives_modal_search(self):
        origin = FocusContext(120, 34)
        snippet = SimpleNamespace(id=7, content="Texto", rich_content="")
        dlg = SimpleNamespace(exec=lambda: 1,
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
        dlg = SimpleNamespace(exec=lambda: 1,
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

    def test_real_dialog_acceptance_without_instance_enum_alias(self):
        import tempfile
        from pathlib import Path
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QWidget
        from app.core import SnippetStore
        from app.productivity_widgets import QuickSearchDialog
        class Host(QWidget, ProductivityMixin):
            pass
        class StrictDialog(QuickSearchDialog):
            def __getattribute__(self, name):
                if name == 'Accepted':
                    raise AttributeError('Enums are only available on the Qt class')
                return super().__getattribute__(name)
            def __init__(self, *args):
                super().__init__(*args)
                QTimer.singleShot(0,self.choose)
        with tempfile.TemporaryDirectory() as temporary:
            store=SnippetStore(Path(temporary)/'test.db')
            folder=store.create_folder('Teste')
            store.save(folder,'Modal','/modal','Texto escolhido')
            host=Host();host.store=store;host._launch_smart_snippet=Mock()
            try:
                with patch('app.productivity_features.QuickSearchDialog',StrictDialog):
                    host._open_global_search(FocusContext(120,34))
                self.assertEqual(host._launch_smart_snippet.call_args.args[0].content,'Texto escolhido')
            finally:
                host.deleteLater();store.close();self.app.processEvents()

    def test_selected_plain_command_is_sent_to_verified_previous_editor(self):
        origin = FocusContext(120, 34)
        host = DummyHost()
        snippet = SimpleNamespace(id=9, content="Texto do AURORA", rich_content="")
        host._insert_search_result = Mock()
        with patch("app.productivity_features.sys.platform", "win32"):
            ProductivityMixin._launch_smart_snippet(
                host, snippet, origin, from_shortcut=None)
        host._insert_search_result.assert_called_once_with(snippet, origin)

    def test_picker_uses_normal_engine_without_erasing_prefix_or_selection(self):
        from engine_fixture import EngineFixture
        for selected in (False, True):
            with self.subTest(selected=selected), EngineFixture() as e:
                e.save('/pick','Resposta 😀')
                e.field.insert('Antes /pick|trocar|depois')
                e.field.anchor = len('Antes /pick|')
                e.field.caret = e.field.anchor + (6 if selected else 0)
                candidate = e.listener.choose_insertion('/pick',e.context())
                self.assertIsNotNone(candidate)
                e.host._expand_global(candidate);e.drain()
                self.assertEqual(e.field.text, 'Antes /pick|Resposta 😀'+('' if selected else 'trocar')+'|depois')
                self.assertFalse(any(vk in (8,46,37,67) for vk,_,_ in e.sent))
                self.assertEqual(e.clipboard.text(),'original')

    def test_picker_request_is_invalidated_by_new_input_or_focus(self):
        from engine_fixture import EngineFixture
        for changed in ('input','focus','pause'):
            with self.subTest(changed=changed), EngineFixture() as e:
                e.save('/pick','Resposta')
                candidate=e.listener.choose_insertion('/pick',e.context())
                if changed=='input':e.type('X')
                elif changed=='focus':e.field_id=2
                else:e.host._hotkeys_enabled=False
                e.host._expand_global(candidate);e.drain()
                self.assertEqual(e.api_calls,0)

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
