"""Regressões: tabelas editáveis no grupo Parágrafo, sem terceira coluna."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtWidgets import QApplication, QDialog, QToolButton, QWidgetAction
from PySide6.QtGui import QMouseEvent
from unittest.mock import Mock
from types import SimpleNamespace

from app.clipboard_content import expansion_mime
from app.formatting import has_rich_formatting
from app.inline_images import AuroraImageEditor
from app.insert_objects import TableDimensionsDialog, build_table_menu, insert_table
from app.paragraph_panel import ParagraphPanel
from app.table_styles import TABLE_STYLES, TableStylePreview, apply_table_style, build_table_styles_menu
from app.ribbon import TableSplitButton


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
            # Tanto o corpo quanto a seta usam o mesmo popup nativo;
            # não há showMenu() reentrante no sinal clicked.
            self.assertEqual(panel.table_button.popupMode(),
                             QToolButton.InstantPopup)
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

    def test_custom_dimensions_dialog_shows_both_inputs_at_once(self):
        dialog = TableDimensionsDialog()
        try:
            self.assertEqual(dialog.windowTitle(), "Inserir tabela")
            self.assertEqual(dialog.rows_input.accessibleName(), "Número de linhas")
            self.assertEqual(dialog.columns_input.accessibleName(), "Número de colunas")
            self.assertEqual(dialog.dimensions(), (3, 3))
            dialog.columns_input.setValue(8)
            dialog.rows_input.setValue(12)
            self.assertEqual(dialog.columns_input.maximum(), 6)
            self.assertEqual(dialog.dimensions(), (12, 6))
            dialog.rows_input.setValue(2)
            self.assertEqual(dialog.columns_input.maximum(), 8)
            dialog.columns_input.setValue(8)
            self.assertEqual(dialog.dimensions(), (2, 8))
        finally:
            self.dispose(dialog)

    def test_menu_custom_action_accepts_or_cancels_once(self):
        editor = AuroraImageEditor()
        panel = ParagraphPanel(editor)
        try:
            action = panel.table_button.menu().actions()[-1]
            with patch("app.insert_objects.TableDimensionsDialog") as dialog_cls:
                dialog = dialog_cls.return_value
                dialog.exec.return_value = QDialog.Accepted
                dialog.dimensions.return_value = (2, 3)
                action.trigger()
                self.assertIn("<table", editor.toHtml().lower())
            before = editor.toHtml()
            with patch("app.insert_objects.TableDimensionsDialog") as dialog_cls:
                dialog_cls.return_value.exec.return_value = QDialog.Rejected
                action.trigger()
            self.assertEqual(editor.toHtml(), before)
        finally:
            self.dispose(panel)
            self.dispose(editor)

    def test_table_split_button_uses_different_click_regions(self):
        editor = AuroraImageEditor()
        panel = ParagraphPanel(editor)
        try:
            button = panel.table_button
            self.assertIsInstance(button, TableSplitButton)
            self.assertFalse(button.icon().isNull())
            self.assertTrue(button.is_styles_arrow(50))
            self.assertFalse(button.is_styles_arrow(10))
            self.assertEqual(button.menu().actions()[-1].text(),
                             "Definir linhas e colunas…")
            self.assertEqual(button.popupMode(), QToolButton.InstantPopup)
            popup = Mock()
            original = button.styles_menu
            button.styles_menu = SimpleNamespace(popup=popup)
            try:
                # Testa a lógica do clique sem disparar eventos nativos de
                # popup, que podem prender um runner Windows sem desktop.
                event = QMouseEvent(
                    QEvent.MouseButtonPress,
                    QPointF(button.width() - 3, 12),
                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                button.mousePressEvent(event)
                self.assertEqual(popup.call_count, 1)
            finally:
                button.styles_menu = original
        finally:
            self.dispose(panel)
            self.dispose(editor)

    def test_table_styles_gallery_has_real_visual_previews(self):
        editor = AuroraImageEditor()
        panel = ParagraphPanel(editor)
        try:
            styles_menu = panel.table_button.styles_menu
            self.assertEqual(styles_menu.objectName(), "auroraTableStylesMenu")
            action = next(item for item in styles_menu.actions()
                          if isinstance(item, QWidgetAction))
            previews = action.defaultWidget().findChildren(TableStylePreview)
            self.assertEqual(len(previews), len(TABLE_STYLES))
            self.assertEqual({spec.group for spec in TABLE_STYLES},
                             {"Tabelas Simples", "Tabelas de Grade", "Tabelas de Lista"})
            action_labels = [a.text() for a in styles_menu.actions()]
            self.assertTrue(any("Limpar formatação" in name for name in action_labels))
            self.assertTrue(any("Modificar Estilo" in name for name in action_labels))
            self.assertTrue(any("Novo Estilo" in name for name in action_labels))
        finally:
            self.dispose(panel)
            self.dispose(editor)

    def test_table_style_is_editable_and_persists_in_html(self):
        editor = AuroraImageEditor()
        try:
            table = insert_table(editor, 3, 4)
            editor.textCursor().insertText("Dado editável")
            blue = next(s for s in TABLE_STYLES if s.key == "grid-blue")
            apply_table_style(table, blue)
            html = editor.toHtml()
            self.assertIn("<table", html.lower())
            self.assertIn("Dado editável", html)
            self.assertIn("#1976b9", html.lower())
            restored = AuroraImageEditor()
            try:
                restored.setHtml(html)
                self.assertIn("Dado editável", restored.toPlainText())
                self.assertIn("<table", restored.toHtml().lower())
            finally:
                self.dispose(restored)
        finally:
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


class CustomTableStylePreferencesTests(unittest.TestCase):
    def test_custom_styles_survive_settings_save_and_invalid_entries_are_ignored(self):
        from app.preferences import load_preferences, save_preferences
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "settings.json"
            preferences = load_preferences(destination)
            preferences['table_styles'] = [
                {'name': 'Azul pessoal', 'accent': '#2878cc', 'variant': 'grid'},
                {'name': 'Azul pessoal', 'accent': '#2878cc', 'variant': 'grid'},
                {'name': 'Inseguro', 'accent': 'url(file:///etc/passwd)', 'variant': 'grid'},
                {'name': 'Listrado', 'accent': '#208b77', 'variant': 'list'},
            ]
            save_preferences(preferences, destination)
            restored = load_preferences(destination)
            self.assertEqual(restored['table_styles'], [
                {'name': 'Azul pessoal', 'accent': '#2878cc', 'variant': 'grid'},
                {'name': 'Listrado', 'accent': '#208b77', 'variant': 'list'}])
            restored['sound_volume'] = 40
            save_preferences(restored, destination)
            self.assertEqual(load_preferences(destination)['table_styles'],
                             restored['table_styles'])


if __name__ == "__main__":
    unittest.main()
