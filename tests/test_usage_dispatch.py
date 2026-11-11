"""Métricas de uso: contar envios confirmados pelo AURORA uma única vez.

Não contabilizar apenas preparação/copiar e não contar novamente quando um
editor remoto confirma a colagem de forma assíncrona.
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.core import SnippetStore
from app.ui import AutoFillWindow
from app.productivity_features import ProductivityMixin


class UsageDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SnippetStore(Path(self.tmp.name) / "snippets.sqlite3")
        folder = self.store.create_folder("Uso")
        self.item = self.store.save(folder, "Chamado", "/chamado", "Olá!")
        self.status = Mock()
        self.window = SimpleNamespace(store=self.store,
                                      _play_confirmation=Mock(),
                                      _confirm_expansion=Mock(),
                                      _finish_expansion=Mock(),
                                      statusBar=lambda: self.status)
        self.window._record_snippet_usage = lambda snippet_id: (
            AutoFillWindow._record_snippet_usage(self.window, snippet_id))
        self.window._record_expansion_usage = lambda operation: (
            AutoFillWindow._record_expansion_usage(self.window, operation))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    @staticmethod
    def operation():
        return SimpleNamespace(
            candidate=SimpleNamespace(shortcut="/chamado", selected_shortcut=""),
            usage_recorded=False, usage_error=False, image_count=0,
            before=SimpleNamespace(identity=()), feedback_played=True,
            stage="prepared", images_confirmed=False,
        )

    def test_dispatch_counted_before_remote_confirmation_and_not_twice(self):
        operation = self.operation()
        self.assertEqual(self.store.usage_report()["total"], 0)
        with patch("app.ui.QTimer.singleShot"):
            AutoFillWindow._expansion_sent(self.window, operation)
            AutoFillWindow._expansion_sent(self.window, operation)
        self.assertEqual(self.store.usage_report()["total"], 1)
        self.assertTrue(operation.usage_recorded)
        AutoFillWindow._expansion_succeeded(self.window, operation)
        self.assertEqual(self.store.usage_report()["total"], 1)
        self.assertEqual(operation.stage, "confirmed")

    def test_another_dispatched_operation_is_counted_separately(self):
        for _ in range(3):
            op = self.operation()
            with patch("app.ui.QTimer.singleShot"):
                AutoFillWindow._expansion_sent(self.window, op)
        self.assertEqual(self.store.usage_report()["total"], 3)

    def test_sqlite_failure_is_not_silent_in_status(self):
        op = self.operation()
        with patch.object(self.store, "register_expansion",
                          side_effect=sqlite3.OperationalError("database is locked")):
            with patch("app.ui.QTimer.singleShot"):
                AutoFillWindow._expansion_sent(self.window, op)
            self.assertTrue(op.usage_error)
            self.assertFalse(op.usage_recorded)
            AutoFillWindow._expansion_succeeded(self.window, op)
        self.assertEqual(self.store.usage_report()["total"], 0)
        self.assertIn("estatística", self.status.showMessage.call_args.args[0])

    def test_smart_template_paste_counts_after_dispatch_only(self):
        text = "Texto do formulário"
        context = SimpleNamespace(window=1, control=1)
        snippet = self.store.snippet_by_shortcut("/chamado")
        copied = SimpleNamespace(text=lambda: text)
        with patch("app.productivity_features.QApplication.clipboard",
                   return_value=copied), \
             patch("app.productivity_features.restore_target", return_value=True), \
             patch("app.clipboard_content.materialize_clipboard"), \
             patch("app.productivity_features.paste_clipboard") as paste:
            ProductivityMixin._safe_paste_selected(
                self.window, context, text, snippet, shortcut=None)
        paste.assert_called_once()
        self.assertEqual(self.store.usage_report()["total"], 1)

    def test_manual_clipboard_fallback_does_not_count_as_sent(self):
        text = "Texto do formulário"
        context = SimpleNamespace(window=1, control=1)
        snippet = self.store.snippet_by_shortcut("/chamado")
        with patch("app.productivity_features.QApplication.clipboard",
                   return_value=SimpleNamespace(text=lambda: text)), \
             patch("app.productivity_features.restore_target", return_value=False):
            ProductivityMixin._safe_paste_selected(
                self.window, context, text, snippet, shortcut=None)
        self.assertEqual(self.store.usage_report()["total"], 0)


if __name__ == "__main__":
    unittest.main()
