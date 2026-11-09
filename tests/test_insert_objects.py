"""Regression tests for the new native table / vector shapes / chart ribbon."""
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QDialog

from app.clipboard_content import expansion_mime
from app.formatting import has_rich_formatting
from app.inline_images import AuroraImageEditor, image_sources
from app.insert_objects import (
    SHAPES, CHART_TYPES, ChartDialog, InsertObjectsPanel,
    insert_table, parse_chart_data, render_chart, render_shape,
)


class InsertObjectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    @classmethod
    def tearDownClass(cls):
        cls.app.processEvents()

    @staticmethod
    def dispose(widget):
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_native_table_is_editable_and_survives_html_clipboard(self):
        editor = AuroraImageEditor()
        try:
            table = insert_table(editor, 3, 4)
            self.assertEqual(table.rows(), 3)
            self.assertEqual(table.columns(), 4)
            self.assertIsNotNone(editor.textCursor().currentTable())
            editor.textCursor().insertText("Cliente")
            html = editor.toHtml()
            self.assertIn("<table", html.lower())
            self.assertIn("Cliente", html)
            self.assertTrue(has_rich_formatting(html))
            payload = expansion_mime(editor.toPlainText(), html)
            self.assertTrue(payload.hasHtml())
            self.assertIn("<table", payload.html().lower())
            self.assertNotIn("Rich Text Format", " ".join(payload.formats()))
            restored = AuroraImageEditor()
            try:
                restored.setHtml(html)
                self.assertIn("Cliente", restored.toPlainText())
                self.assertIn("<table", restored.toHtml().lower())
            finally:
                self.dispose(restored)
        finally:
            self.dispose(editor)

    def test_limits_prevent_oversized_tables(self):
        editor = AuroraImageEditor()
        try:
            for rows, cols in ((0, 2), (13, 2), (2, 9), (12, 8)):
                with self.subTest(rows=rows, cols=cols), self.assertRaises(ValueError):
                    insert_table(editor, rows, cols)
            self.assertNotIn("<table", editor.toHtml().lower())
        finally:
            self.dispose(editor)

    def test_shapes_render_and_insert_through_existing_image_pipeline(self):
        editor = AuroraImageEditor()
        try:
            for label, key in SHAPES:
                with self.subTest(shape=label):
                    image = render_shape(key)
                    self.assertFalse(image.isNull())
                    self.assertEqual((image.width(), image.height()), (420, 240))
            self.assertTrue(editor.insert_image(render_shape("arrow")))
            html = editor.toHtml()
            self.assertEqual(len(image_sources(html)), 1)
            self.assertTrue(has_rich_formatting(html))
        finally:
            self.dispose(editor)
        with self.assertRaises(ValueError):
            render_shape("untrusted")

    def test_chart_values_are_checked_without_code_execution(self):
        self.assertEqual(parse_chart_data("Jan;10\nFev;20,5"),
                         [("Jan", 10), ("Fev", 20.5)])
        for data in ("A;1", "A;1\nB;-2", "A;NaN\nB;2",
                     "A;Inf\nB;3", "A;1\nB;999999999",
                     "A;1+1\nB;2", "A;1\nB;0/0", "A,1\nB,2",
                     "A;0\nB;0", "x" * 25 + ";1\nB;2"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_chart_data(data)

    def test_all_chart_types_produce_real_images(self):
        data = parse_chart_data("Equipe A;12\nEquipe B;23\nEquipe C;9")
        editor = AuroraImageEditor()
        try:
            for kind in CHART_TYPES:
                with self.subTest(kind=kind):
                    picture = render_chart(kind, data, "Resumo mensal")
                    self.assertFalse(picture.isNull())
                    self.assertEqual((picture.width(), picture.height()), (760, 450))
            self.assertTrue(editor.insert_image(render_chart("Colunas", data, "Resumo")))
            self.assertEqual(len(image_sources(editor.toHtml())), 1)
        finally:
            self.dispose(editor)

    def test_chart_dialog_validates_before_accepting(self):
        dialog = ChartDialog()
        try:
            dialog.data_edit.setPlainText("A;12\nB;7")
            dialog.title_edit.setText("Teste")
            dialog._validate()
            self.assertEqual(dialog.result(), QDialog.Accepted)
            self.assertEqual(dialog.values, [("A", 12), ("B", 7)])
        finally:
            self.dispose(dialog)

    def test_panel_has_three_live_controls_in_one_compact_group(self):
        editor = AuroraImageEditor()
        panel = InsertObjectsPanel(editor)
        try:
            self.assertEqual((panel.width(), panel.height()), (300, 115))
            self.assertEqual(panel.controls.height(), 91)
            self.assertEqual(panel.footer.label.text(), "Inserir")
            self.assertEqual([x.accessibleName() for x in (
                panel.table_button, panel.shape_button, panel.chart_button)],
                ["Tabelas", "Formas", "Gráficos"])
            self.assertTrue(panel.table_button.menu().actions())
            self.assertEqual(len(panel.shape_button.menu().actions()), len(SHAPES))
            panel._insert_table(2, 2)
            self.assertIn("<table", editor.toHtml().lower())
        finally:
            self.dispose(panel)
            self.dispose(editor)


class RibbonPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_insert_group_occupies_right_side_and_matches_other_groups(self):
        from app.ui import AutoFillWindow
        with tempfile.TemporaryDirectory(prefix="aurora-insert-objects-") as directory:
            with patch("app.ui.application_db_path",
                       return_value=Path(directory) / "snippets.sqlite3"), \
                 patch("app.ui.GlobalHotkeyListener.start",
                       return_value=(False, "Teste")), \
                 patch("app.ui.AutoFillWindow._initial_release_check"):
                win = AutoFillWindow()
                try:
                    win._new_snippet()
                    self.assertEqual(win.insert_objects_panel.footer.label.text(), "Inserir")
                    self.assertEqual(win.insert_objects_panel.height(),
                                     win.paragraph_panel.height())
                    self.assertEqual(win.insert_objects_panel.width(), 300)
                    layout = win.font_toolbar.layout()
                    widgets = [layout.itemAt(i).widget()
                               for i in range(layout.count())
                               if layout.itemAt(i).widget()]
                    self.assertLess(widgets.index(win.font_group),
                                    widgets.index(win.paragraph_panel))
                    self.assertLess(widgets.index(win.paragraph_panel),
                                    widgets.index(win.insert_objects_panel))
                finally:
                    win.dirty = False
                    win._quitting = True
                    win.close()
                    win.deleteLater()
                    self.app.clipboard().clear()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
