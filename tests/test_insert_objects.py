"""Regressões: tabelas editáveis no grupo Parágrafo, sem terceira coluna."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QWidgetAction

from app.clipboard_content import expansion_mime
from app.formatting import has_rich_formatting
from app.inline_images import AuroraImageEditor
from app.insert_objects import build_table_menu, insert_table
from app.paragraph_panel import ParagraphPanel


class TableInParagraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    @staticmethod
    def dispose(widget):
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_table_stays_editable_and_preserves_rich_html(self):
        editor = AuroraImageEditor()
        try:
            table = insert_table(editor, 3, 4)
            self.assertEqual((table.rows(), table.columns()), (3, 4))
            self.assertIsNotNone(editor.textCursor().currentTable())
            editor.textCursor().insertText("Cliente")
            html = editor.toHtml()
            self.assertIn("<table", html.lower())
            self.assertIn("Cliente", html)
            self.assertTrue(has_rich_formatting(html))
            payload = expansion_mime(editor.toPlainText(), html)
            self.assertTrue(payload.hasHtml())
            self.assertIn("<table", payload.html().lower())
            restored = AuroraImageEditor()
            try:
                restored.setHtml(html)
                self.assertIn("<table", restored.toHtml().lower())
                self.assertIn("Cliente", restored.toPlainText())
            finally:
                self.dispose(restored)
        finally:
            self.dispose(editor)

    def test_limits_prevent_oversized_tables(self):
        editor = AuroraImageEditor()
        try:
            for dimensions in ((0, 2), (13, 2), (2, 9), (12, 8)):
                with self.subTest(dimensions=dimensions):
                    with self.assertRaises(ValueError):
                        insert_table(editor, *dimensions)
            self.assertNotIn("<table", editor.toHtml().lower())
        finally:
            self.dispose(editor)

    def test_menu_keeps_grid_and_custom_dimensions(self):
        editor = AuroraImageEditor()
        panel = ParagraphPanel(editor)
        try:
            self.assertEqual(panel.table_button.accessibleName(), "Inserir tabela")
            self.assertEqual(panel.controls.width(), 300)
            self.assertEqual(panel.width(), 300)
            menu = panel.table_button.menu()
            self.assertIsNotNone(menu)
            action = next(a for a in menu.actions() if isinstance(a, QWidgetAction))
            holder = action.defaultWidget()
            self.assertEqual(holder.layout().count(), 30)
            self.assertIn("Definir linhas e colunas", menu.actions()[-1].text())
            # Na terceira linha, penúltima posição, imediatamente antes de emoji.
            bottom_row = panel.controls.layout().itemAt(2).layout()
            self.assertIs(bottom_row.itemAt(3).widget(), panel.table_button)
            self.assertIs(bottom_row.itemAt(4).widget(), panel.emoji_button)
            self.assertEqual(
                [bottom_row.itemAt(i).widget().width() for i in range(5)],
                [58, 58, 58, 58, 52])
            panel._insert_table(2, 3)
            self.assertIn("<table", editor.toHtml().lower())
        finally:
            self.dispose(panel)
            self.dispose(editor)

    def test_ribbon_contains_only_fonte_and_paragrafo(self):
        from app.ui import AutoFillWindow
        with tempfile.TemporaryDirectory(prefix="aurora-table-only-") as directory:
            with patch("app.ui.application_db_path",
                       return_value=Path(directory) / "snippets.sqlite3"), \
                 patch("app.ui.GlobalHotkeyListener.start",
                       return_value=(False, "Teste")), \
                 patch("app.ui.AutoFillWindow._initial_release_check"):
                win = AutoFillWindow()
                try:
                    win._new_snippet()
                    self.assertFalse(hasattr(win, "insert_objects_panel"))
                    self.assertTrue(hasattr(win.paragraph_panel, "table_button"))
                    self.assertEqual(win.paragraph_panel.footer.label.text(), "Parágrafo")
                    self.assertEqual(win.paragraph_panel.height(), 115)
                    self.assertEqual(win.paragraph_panel.width(), 300)
                    widgets = [
                        win.font_toolbar.layout().itemAt(i).widget()
                        for i in range(win.font_toolbar.layout().count())
                        if win.font_toolbar.layout().itemAt(i).widget()
                    ]
                    self.assertLess(widgets.index(win.font_group),
                                    widgets.index(win.paragraph_panel))
                    self.assertEqual(len(
                        [w for w in widgets if w.objectName() == "fontDivider"]), 1)
                finally:
                    win.dirty = False
                    win._quitting = True
                    win.close()
                    win.deleteLater()
                    self.app.clipboard().clear()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
