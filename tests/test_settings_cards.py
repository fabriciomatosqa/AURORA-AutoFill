"""Responsive settings grid: widths, state persistence and connected actions."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from app.preferences import DEFAULTS
from app.settings_panel import SettingsPage


class SettingsCardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def create_page(self, supported=True):
        page = SettingsPage(
            dict(DEFAULTS), startup_supported=supported,
            startup_enabled=False)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.close)
        return page

    @staticmethod
    def visible_columns(page):
        return [layout for i, layout in enumerate(page.column_layouts)
                if page.column_hosts[i].isVisible()]

    @staticmethod
    def placed_names(page):
        return [
            name for layout in page.column_layouts
            for i in range(layout.count())
            for name, widget in page.cards.items()
            if layout.itemAt(i).widget() is widget
        ]

    def test_breakpoints_are_based_on_content_width_not_fullscreen_state(self):
        choose = SettingsPage.columns_for_width
        self.assertEqual(choose(480), 1)
        self.assertEqual(choose(760), 2)    # non-maximized screenshot
        self.assertEqual(choose(1100), 3)   # intermediate window
        self.assertEqual(choose(1660), 4)   # ~1920 desktop minus sidebar
        self.assertEqual(choose(5000), 4)

    def test_window_resizes_between_one_two_three_four_columns(self):
        page = self.create_page()
        page.resize(760, 850)
        page.show()
        self.app.processEvents()
        self.assertEqual(page._current_columns, 2)
        self.assertEqual(len(self.visible_columns(page)), 2)
        self.assertEqual(len(self.placed_names(page)), 6)
        self.assertEqual(set(self.placed_names(page)), set(page.CARD_ORDER))

        page.volume.setValue(42)
        page.prereleases.setChecked(False)
        page.theme.setCurrentIndex(page.theme.findData("light"))
        for width, expected in ((1100, 3), (1660, 4), (520, 1),
                                (760, 2), (1660, 4)):
            page.resize(width, 850)
            self.app.processEvents()
            self.assertEqual(page._current_columns, expected, width)
            self.assertEqual(len(self.visible_columns(page)), expected)
            self.assertEqual(len(self.placed_names(page)), 6)
            self.assertEqual(set(self.placed_names(page)), set(page.CARD_ORDER))
            self.assertEqual(len({id(card) for card in page.cards.values()}), 6)
            self.assertEqual(page.volume.value(), 42)
            self.assertFalse(page.prereleases.isChecked())
            self.assertEqual(page.theme.currentData(), "light")
        self.assertLessEqual(page.theme.width(), 260)
        self.assertLessEqual(page.check_button.width(), 270)

    def test_narrow_layout_has_no_horizontal_scroll_and_all_controls_fit(self):
        page = self.create_page(supported=False)
        page.resize(520, 730)
        page.show()
        self.app.processEvents()
        self.assertEqual(page._current_columns, 1)
        self.assertEqual(page.scroller.horizontalScrollBarPolicy(),
                         Qt.ScrollBarAlwaysOff)
        self.assertEqual(page.scroller.horizontalScrollBar().maximum(), 0)
        self.assertFalse(page.startup.isEnabled())
        self.assertTrue(page.scroller.verticalScrollBar().maximum() > 0)
        self.assertIn("outros aplicativos", page.suggestions.accessibleName())
        self.assertIn("Reproduzir som", page.sound.accessibleName())
        self.assertIn("nova versão", page.updates.accessibleName())

    def test_buttons_and_dependencies_keep_working_after_reflow(self):
        page = self.create_page()
        events = []
        for name, signal in (
            ("search", page.global_search_requested),
            ("stats", page.statistics_requested),
            ("backup", page.backup_requested),
            ("restore", page.restore_requested),
            ("open", page.open_backups_requested),
            ("check", page.check_requested),
            ("sound", page.sound_toggled),
            ("startup", page.startup_toggled),
            ("updates", page.updates_toggled),
            ("preview", page.play_requested),
            ("suggestions", page.suggestions_toggled),
        ):
            signal.connect(lambda *args, n=name: events.append(n))
        for width in (530, 760, 1100, 1660):
            page.resize(width, 820)
            page.show()
            self.app.processEvents()

        for object_name in (
            "globalSearchSettingsButton", "statisticsSettingsButton",
            "settingsBackupCreateButton", "settingsBackupRestoreButton",
            "settingsBackupOpenButton", "settingsCheckUpdatesButton",
        ):
            button = page.findChild(QPushButton, object_name)
            self.assertIsNotNone(button, object_name)
            button.click()

        page.sound.setChecked(False)
        self.assertFalse(page.volume.isEnabled())
        page.sound.setChecked(True)
        self.assertTrue(page.volume.isEnabled())
        page.sample_button.click()
        page.startup.setChecked(True)
        self.assertTrue(page.start_minimized.isEnabled())
        page.updates.setChecked(False)
        page.suggestions.setChecked(True)
        self.assertTrue({
            "search", "stats", "backup", "restore", "open", "check",
            "sound", "startup", "updates", "preview", "suggestions",
        } <= set(events))


if __name__ == "__main__":
    unittest.main()
