"""Guia dos comandos dinâmicos: conteúdo, acessibilidade e integração no editor."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea

from app.dynamic_help import DYNAMIC_HELP_SECTIONS, DynamicCommandsHelpDialog
from app.date_formats import FORMAT_CODE_GROUPS, format_date_ptbr
from app.ui import AutoFillWindow


class DynamicHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    @staticmethod
    def _dispose(widget):
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_all_five_categories_and_fourteen_tokens_are_explained(self):
        expected = {
            "Data e hora": 6,
            "Área de transferência e cursor": 2,
            "Cálculos": 1,
            "Formulários interativos": 2,
            "Automações": 3,
        }
        self.assertEqual(
            {name: len(entries) for name, _intro, entries in DYNAMIC_HELP_SECTIONS},
            expected)
        for section_name, intro, entries in DYNAMIC_HELP_SECTIONS:
            self.assertTrue(intro, section_name)
            for label, token, explanation in entries:
                with self.subTest(section=section_name, token=token):
                    self.assertTrue(label)
                    self.assertTrue(token.startswith("{{") and token.endswith("}}"))
                    self.assertGreaterEqual(len(explanation), 35)

    def test_guide_is_scrollable_read_only_and_allows_selecting_tokens(self):
        dialog = DynamicCommandsHelpDialog()
        try:
            dialog.show()
            self.app.processEvents()
            self.assertIsInstance(dialog.scroll_area, QScrollArea)
            self.assertEqual(dialog.scroll_area.horizontalScrollBarPolicy(),
                             Qt.ScrollBarAlwaysOff)
            self.assertEqual(len(dialog.sections), 5)
            self.assertEqual(len(dialog.token_labels), 14)
            expected_tokens = [
                code for _name, _intro, entries in DYNAMIC_HELP_SECTIONS
                for _label, code, _description in entries
            ]
            self.assertEqual([label.text() for label in dialog.token_labels],
                             expected_tokens)
            for label in dialog.token_labels:
                self.assertEqual(label.textFormat(), Qt.PlainText)
                self.assertTrue(
                    label.textInteractionFlags() & Qt.TextSelectableByMouse)
            self.assertGreater(dialog.scroll_area.verticalScrollBar().maximum(), 0)
        finally:
            self._dispose(dialog)

    def test_date_reference_is_accessible_from_tab_and_date_section(self):
        from datetime import datetime
        dialog = DynamicCommandsHelpDialog()
        try:
            dialog.show()
            self.app.processEvents()
            self.assertEqual(dialog.tabs.count(), 5)
            self.assertEqual(dialog.tabs.tabText(3), "Data e hora")
            self.assertEqual(dialog.tabs.currentIndex(), 0)
            dialog.tabs.setCurrentIndex(3)
            self.app.processEvents()
            before = dialog.scroll_area.verticalScrollBar().value()
            dialog.date_reference_button.click()
            self.app.processEvents()
            self.assertEqual(dialog.tabs.currentIndex(), 3)
            self.assertGreater(
                dialog.scroll_area.verticalScrollBar().value(), before)
            self.assertGreater(dialog.scroll_area.verticalScrollBar().maximum(), 0)
            self.assertIs(
                dialog.date_codes_content.parent(), dialog.scroll_area.widget())
            expected = {code for _name, rows in FORMAT_CODE_GROUPS
                        for code, _description in rows}
            self.assertEqual(set(dialog.date_code_labels), expected)
            self.assertEqual(set(dialog.date_code_examples), expected)
            sample = datetime(2026, 11, 6, 14, 30, 45, 123456)
            for code in expected:
                with self.subTest(code=code):
                    self.assertEqual(
                        dialog.date_code_examples[code].text(),
                        format_date_ptbr(sample, code) or "(vazio sem fuso)")
            self.assertEqual(dialog.date_code_examples["%a"].text(), "sex")
            self.assertEqual(dialog.date_code_examples["%A"].text(), "sexta-feira")
            self.assertEqual(dialog.date_code_examples["%b"].text(), "nov")
            self.assertEqual(dialog.date_code_examples["%B"].text(), "novembro")
        finally:
            self._dispose(dialog)

    def test_each_command_group_has_its_own_tab_without_duplicate_borders(self):
        dialog = DynamicCommandsHelpDialog()
        try:
            dialog.show()
            self.app.processEvents()
            expected_names = [
                "Área de transferência e cursor",
                "Automações",
                "Cálculos",
                "Data e hora",
                "Formulários",
            ]
            self.assertEqual(
                [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())],
                expected_names)
            self.assertEqual(
                len(dialog.group_pages), len(DYNAMIC_HELP_SECTIONS))
            self.assertEqual(len(dialog.token_labels), 14)
            for i, (name, _description, entries) in enumerate(
                    sorted(DYNAMIC_HELP_SECTIONS, key=lambda x: x[0].casefold())):
                dialog.tabs.setCurrentIndex(i)
                self.app.processEvents()
                self.assertIs(dialog.tabs.currentWidget(), dialog.group_pages[name])
                self.assertIs(dialog.sections[name].parent(),
                              dialog.group_pages[name].widget())
                # Only this group's tokens are inside the active page.
                from PySide6.QtWidgets import QLabel
                labels = dialog.group_pages[name].findChildren(QLabel, "dynamicHelpToken")
                self.assertEqual([label.text() for label in labels],
                                 [code for _title, code, _help in entries])
            # The pane and the selected tab share the same background.
            self.assertIn("border-top-left-radius: 0px",
                          dialog.styleSheet())
            self.assertIn("margin-bottom: -1px",
                          dialog.styleSheet())
            self.assertGreaterEqual(dialog.width(), 600)
        finally:
            self._dispose(dialog)

    def test_help_button_is_at_right_and_does_not_modify_editor_or_menu(self):
        with tempfile.TemporaryDirectory(prefix="aurora-dynamic-help-") as directory:
            with patch("app.ui.application_db_path",
                       return_value=Path(directory) / "snippets.sqlite3"), \
                 patch("app.ui.GlobalHotkeyListener.start",
                       return_value=(False, "Ambiente de teste")), \
                 patch("app.ui.AutoFillWindow._initial_release_check"):
                win = AutoFillWindow()
                try:
                    win._new_snippet()
                    self.assertEqual(win.dynamic_help_button.text(), "?")
                    self.assertEqual(
                        win.dynamic_help_button.accessibleName(),
                        "Ajuda dos comandos dinâmicos")
                    self.assertIs(
                        win.dynamic_tools_row.itemAt(
                            win.dynamic_tools_row.count() - 1).widget(),
                        win.dynamic_help_button)
                    self.assertIsNotNone(
                        win.dynamic_tools_row.itemAt(
                            win.dynamic_tools_row.count() - 2).spacerItem())

                    menu_tokens = {
                        group: [action.data() for action in submenu.actions()]
                        for group, submenu in win.dynamic_token_groups.items()
                    }
                    guide_tokens = {
                        name: [token for _label, token, _desc in entries]
                        for name, _intro, entries in DYNAMIC_HELP_SECTIONS
                    }
                    self.assertEqual(menu_tokens, guide_tokens)

                    before = win.body_input.toPlainText()
                    with patch("app.ui.DynamicCommandsHelpDialog.exec",
                               return_value=QDialog.Accepted) as open_dialog:
                        win.dynamic_help_button.click()
                        open_dialog.assert_called_once_with()
                    self.assertEqual(win.body_input.toPlainText(), before)
                finally:
                    self.app.clipboard().clear()
                    win.dirty = False
                    win._quitting = True
                    win.close()
                    win.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
