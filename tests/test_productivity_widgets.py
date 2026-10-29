"""Teste offscreen de seleção global, formulário e visualização mensal."""
import os
import tempfile
import unittest
from pathlib import Path
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QLabel
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QCoreApplication, QEvent

from app.core import SnippetStore
from app.productivity_widgets import FieldsDialog, QuickSearchDialog, UsageStatisticsDialog
from app.settings_panel import SettingsPage
from app.preferences import DEFAULTS


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
        # Recycled calendar cells and popup controls use deleteLater().
        # Drain Qt's deferred deletes before destroying QApplication at exit.
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
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
            dialog.deleteLater()
        picker = QuickSearchDialog(self.store)
        try:
            picker.search.setText("chamado")
            self.assertEqual(picker.matches.count(), 1)
            picker.choose()
            self.assertEqual(picker.selected_snippet.id, self.item)
        finally:
            picker.close()
            picker.deleteLater()

    def test_statistics_calendar_daily_totals_and_month_navigation(self):
        self.store.register_expansion(self.item, date(2026, 10, 29))
        self.store.register_expansion(self.item, date(2026, 10, 29))
        self.store.register_expansion(self.item, date(2026, 9, 30))
        stats = UsageStatisticsDialog(self.store, today=date(2026, 10, 29))
        try:
            self.assertIn("Hoje: 2", stats.summary.text())
            self.assertIn("Este mês: 2", stats.summary.text())
            self.assertIn("Este ano: 3", stats.summary.text())
            self.assertIn("Total: 3", stats.summary.text())
            self.assertEqual(stats.month_label.text(), "Outubro 2026")
            self.assertEqual(len(stats.day_buttons), 31)
            self.assertIn("2 usos", stats.day_buttons[29].text())
            QTest.mouseClick(stats.day_buttons[29], Qt.LeftButton)
            self.assertIn("29/10/2026 — 2 usos", stats.day_details.text())
            self.assertIn("Chamado inicial (2)", stats.day_details.text())
            self.assertIn("0 usos", stats.day_buttons[28].text())
            QTest.mouseClick(stats.previous_button, Qt.LeftButton)
            self.assertEqual(stats.month_label.text(), "Setembro 2026")
            self.assertEqual(len(stats.day_buttons), 30)
            self.assertIn("1 uso", stats.day_buttons[30].text())
            QTest.mouseClick(stats.day_buttons[30], Qt.LeftButton)
            self.assertIn("30/09/2026 — 1 uso", stats.day_details.text())
            QTest.mouseClick(stats.next_button, Qt.LeftButton)
            self.assertEqual(stats.month_label.text(), "Outubro 2026")
            self.assertIn("Total: 3", stats.summary.text())
            self.store.reset_usage()
            stats.refresh()
            self.assertIn("Total: 0", stats.summary.text())
            self.assertIn("0 usos", stats.day_buttons[29].text())
        finally:
            stats.close()
            stats.deleteLater()

    def test_settings_productivity_buttons_emit_and_explain_usage(self):
        page = SettingsPage(dict(DEFAULTS), startup_supported=False,
                            startup_enabled=False)
        try:
            search_button = page.findChild(
                QPushButton,
                "globalSearchSettingsButton")
            stats_button = page.findChild(
                __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton,
                "statisticsSettingsButton")
            self.assertIsNotNone(search_button)
            self.assertIsNotNone(stats_button)
            received = []
            page.global_search_requested.connect(lambda: received.append("search"))
            page.statistics_requested.connect(lambda: received.append("statistics"))
            search_button.click()
            stats_button.click()
            self.assertEqual(received, ["search", "statistics"])
            self.assertTrue(any(
                "Ctrl + Shift + Espaço" in label.text()
                for label in page.findChildren(
                    QLabel)))
        finally:
            page.close()
            page.deleteLater()


if __name__ == "__main__":
    unittest.main()
