"""Validação do salvamento instantâneo e das ferramentas tipográficas do AURORA."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core import SnippetStore
from app.formatting import has_rich_formatting


class StoreIncrementalSaveTests(unittest.TestCase):
    def test_one_character_update_is_atomic_and_preserves_existing_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SnippetStore(Path(tmp) / 'data.sqlite3')
            try:
                folder = store.create_folder("Setor")
                item = store.save(folder, "CAD", "/cad", "Texto", rich_content="<p><b>Texto</b></p>")
                store.update_snippet_fields(item, title="CAD1")
                self.assertEqual(store.snippet_by_shortcut("/cad").title, "CAD1")
                store.update_snippet_fields(item, shortcut="/eu")
                updated = store.snippet_by_shortcut("/eu")
                self.assertIsNotNone(updated)
                self.assertEqual(updated.content, "Texto")
                self.assertEqual(updated.rich_content, "<p><b>Texto</b></p>")
                store.update_snippet_fields(item, content="Texto novo", rich_content="<p>Texto novo</p>")
                self.assertEqual(store.snippet_by_shortcut("/eu").content, "Texto novo")
            finally:
                store.close()

    def test_temporary_conflict_does_not_replace_last_good_shortcut(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SnippetStore(Path(tmp) / 'data.sqlite3')
            try:
                folder = store.create_folder("Setor")
                main = store.save(folder, "Primeiro", "/cad", "Texto")
                store.save(folder, "Segundo", "/x", "Outro")
                with self.assertRaises(ValueError):
                    store.update_snippet_fields(main, shortcut="/")
                with self.assertRaises(ValueError):
                    store.update_snippet_fields(main, shortcut="/xyz")
                self.assertIsNotNone(store.snippet_by_shortcut("/cad"))
                self.assertIsNone(store.snippet_by_shortcut("/xyz"))
                store.update_snippet_fields(main, shortcut="/outro")
                self.assertIsNotNone(store.snippet_by_shortcut("/outro"))
            finally:
                store.close()


class FontHtmlTests(unittest.TestCase):
    def test_default_body_font_is_not_considered_user_formatting(self):
        html = "<html><body style=\" font-family:'Sans'; font-size:10pt;\"><p>Olá</p></body></html>"
        self.assertFalse(has_rich_formatting(html))
        self.assertTrue(has_rich_formatting(
            "<html><body style=\" font-family:'Sans';\"><p>"
            "<span style=\"font-family:'Arial'; font-size:22pt; color:#ff0000;\">Olá</span>"
            "</p></body></html>"))
        self.assertTrue(has_rich_formatting('<p style="background-color:#ffff00">Olá</p>'))
        self.assertTrue(has_rich_formatting('<span style="text-decoration:line-through">Ok</span>'))


class AutosaveAndFontUiTests(unittest.TestCase):
    def _window(self, temp):
        from PySide6.QtWidgets import QApplication
        from app.ui import AutoFillWindow
        app = QApplication.instance() or QApplication([])
        type(self)._application = app
        self._ctx = [
            patch('app.ui.application_db_path', return_value=Path(temp) / 'test.sqlite3'),
            patch('app.ui.GlobalHotkeyListener.start', return_value=(False, 'Modo de teste')),
            patch('app.ui.AutoFillWindow._initial_release_check'),
        ]
        for context in self._ctx:
            context.__enter__()
        self.app = app
        return AutoFillWindow()

    def _cleanup(self, win):
        from PySide6.QtCore import QCoreApplication, QEvent
        win.dirty = False
        win._quitting = True
        win.close()
        win.deleteLater()
        self.app.clipboard().clear()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        for context in reversed(self._ctx):
            context.__exit__(None, None, None)

    def test_autocreates_valid_snippet_and_saves_each_edit_without_button(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        with tempfile.TemporaryDirectory() as temp:
            win = self._window(temp)
            try:
                win._new_snippet()
                win.title_input.setText('Saudação')
                win.shortcut_input.setText('/eu')
                self.assertIsNone(win.current_id)
                win.body_input.setPlainText('Olá')
                original = win.current_id
                self.assertIsInstance(original, int)
                self.assertEqual(win.store.snippet_by_shortcut('/eu').content, 'Olá')
                win.title_input.setText('Saudações')
                self.assertEqual(win.store.snippet_by_shortcut('/eu').title, 'Saudações')
                win.shortcut_input.setText('/')
                self.assertIsNotNone(win.store.snippet_by_shortcut('/eu'))
                self.assertTrue(win.dirty)
                win.shortcut_input.setText('/x')
                self.assertIsNone(win.store.snippet_by_shortcut('/eu'))
                self.assertEqual(win.store.snippet_by_shortcut('/x').id, original)
                self.assertFalse(win.dirty)
                self.assertIn('automaticamente', win.autosave_status.text())
                cursor = win.body_input.textCursor()
                from PySide6.QtGui import QTextCursor
                cursor.movePosition(QTextCursor.End)
                win.body_input.setTextCursor(cursor)
                win.body_input.insertPlainText('!')
                self.assertEqual(win.store.snippet_by_shortcut('/x').content, 'Olá!')
                self.assertEqual(win.body_input.textCursor().position(), len('Olá!'))
            finally:
                self._cleanup(win)

    def test_font_controls_are_saved_with_independent_text_formatting(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtGui import QTextCursor, QFontDatabase, QColor
        from app.formatting import render_rich_html
        with tempfile.TemporaryDirectory() as temp:
            win = self._window(temp)
            try:
                win._new_snippet()
                win.title_input.setText('Fonte')
                win.shortcut_input.setText('/fonte')
                win.body_input.setPlainText('Grande pequeno')
                cursor = win.body_input.textCursor()
                cursor.setPosition(0)
                cursor.setPosition(6, QTextCursor.KeepAnchor)
                win.body_input.setTextCursor(cursor)
                # O Windows CI roda sem sessão gráfica e nem sempre expõe
                # suas fontes instaladas ao Qt; no desktop real expõe todas.
                families = QFontDatabase.families()
                win._apply_font_family(families[0] if families else 'Segoe UI')
                win._apply_font_size(22)
                win._apply_format('bold', True)
                win._apply_format('strike', True)
                with patch('app.ui.AuroraColorDialog.get_color', return_value=QColor('#aa3300')):
                    win._choose_font_color(False)
                self.assertEqual(win.text_color_button.marker_color().name(), '#aa3300')
                with patch('app.ui.AuroraColorDialog.get_color', return_value=QColor('#ffee22')):
                    win._choose_font_color(True)
                self.assertEqual(win.highlight_button.marker_color().name(), '#ffee22')
                with patch('app.ui.AuroraColorDialog.get_color', return_value=QColor()):
                    win._choose_font_color(False)
                self.assertEqual(win.text_color_button.marker_color().name(), '#aa3300')
                saved = win.store.snippet_by_shortcut('/fonte')
                self.assertEqual(saved.content, 'Grande pequeno')
                self.assertTrue(has_rich_formatting(saved.rich_content))
                self.assertIn('22pt', saved.rich_content)
                self.assertIn('aa3300', saved.rich_content.lower())
                self.assertIn('Grande', render_rich_html(saved.rich_content, ''))
                self.assertIn('pequeno', render_rich_html(saved.rich_content, ''))
                self.assertIn('automaticamente', win.autosave_status.text())
                from app.font_catalog import AuroraFontCombo
                self.assertIsInstance(win.font_family, AuroraFontCombo)
                self.assertGreater(win.font_family.count(), 0)
                # Três linhas compactas como no Word: seleção de fonte,
                # estilos e cores. O painel não cresce sem necessidade.
                self.assertLessEqual(win.font_toolbar.sizeHint().height(), 115)
                self.assertGreaterEqual(win.font_toolbar.sizeHint().height(), 80)
                self.assertEqual(win.format_buttons['bold'].height(), 27)
            finally:
                self._cleanup(win)


if __name__ == '__main__':
    unittest.main()
