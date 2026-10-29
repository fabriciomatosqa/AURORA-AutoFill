"""Teste offscreen de seleção global, formulário e visualização mensal."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox

from app.core import SnippetStore
from app.productivity_widgets import FieldsDialog, QuickSearchDialog, UsageStatisticsDialog


class ProductivityWidgetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SnippetStore(Path(self.tmp.name) / "test.sqlite3")
        folder = self.store.create_folder("Exemplo")
        self.item = self.store.save(folder, "Chamado inicial", "/chamado",
                                    "Prezado(a) {{campo:Nome}}")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_form_and_search(self):
        dialog = FieldsDialog("Olá {{campo:Nome}} {{escolha:Status|Aberto|Concluído}}")
        try:
            self.assertEqual(len(dialog.fields), 2)
            self.assertIsInstance(dialog.controls["status"], QComboBox)
            dialog.controls["nome"].setText("Ana")
            self.assertEqual(dialog.values()["nome"], "Ana")
        finally:
            dialog.close()
        picker = QuickSearchDialog(self.store)
        try:
            picker.search.setText("chamado")
            self.assertEqual(picker.matches.count(), 1)
            picker.choose()
            self.assertEqual(picker.selected_snippet.id, self.item)
        finally:
            picker.close()

    def test_statistics_and_clear_no_data(self):
        stats = UsageStatisticsDialog(self.store)
        try:
            self.assertIn("Total: 0", stats.summary.text())
            self.store.register_expansion(self.item)
            stats.refresh()
            self.assertIn("Total: 1", stats.summary.text())
            self.assertEqual(stats.months_layout.count(), 13)
        finally:
            stats.close()


if __name__ == "__main__":
    unittest.main()
