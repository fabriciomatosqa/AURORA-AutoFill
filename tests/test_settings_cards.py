"""Settings layout: grouped desktop / full-width compact, with persistent controls."""
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
    def group_positions(page):
        grid = page.groups_grid
        return {
            key: (grid.getItemPosition(grid.indexOf(panel))[:2])
            for key, panel in page.groups.items()
        }

    def test_breakpoints_use_available_content_width(self):
        choose = SettingsPage.columns_for_width
        self.assertEqual(choose(480), 1)
        self.assertEqual(choose(760), 1)     # compact screenshot
        self.assertEqual(choose(980), 1)     # no squashed desktop columns
        self.assertEqual(choose(1100), 2)    # two comfortable groups
        self.assertEqual(choose(1660), 2)    # maximized window
        self.assertEqual(choose(5000), 2)    # never four tiny cards

    def test_resizing_keeps_groups_controls_and_preferences(self):
        page = self.create_page()
        page.resize(760, 850)
        page.show()
        self.app.processEvents()
        self.assertEqual(page._current_columns, 1)
        self.assertEqual(self.group_positions(page),
                         {"general": (0, 0), "tools": (1, 0)})
        self.assertEqual(set(page.cards), set(page.CARD_ORDER))
        self.assertEqual(len(page.cards), 8)

        page.volume.setValue(42)
        page.prereleases.setChecked(False)
        page.theme.setCurrentIndex(page.theme.findData("light"))
        for width, expected in ((1100, 2), (1660, 2), (520, 1),
                                (760, 1), (1660, 2), (980, 1)):
            page.resize(width, 850)
            self.app.processEvents()
            self.assertEqual(page._current_columns, expected, width)
            expected_positions = ({"general": (0, 0), "tools": (0, 1)}
                                  if expected == 2 else
                                  {"general": (0, 0), "tools": (1, 0)})
            self.assertEqual(self.group_positions(page), expected_positions)
            self.assertEqual(set(page.cards), set(page.CARD_ORDER))
            self.assertEqual(len({id(card) for card in page.cards.values()}), 8)
            self.assertEqual(page.volume.value(), 42)
            self.assertFalse(page.prereleases.isChecked())
            self.assertEqual(page.theme.currentData(), "light")

    def test_compact_groups_fill_width_and_never_scroll_horizontally(self):
        page = self.create_page(supported=False)
        page.resize(520, 730)
        page.show()
        self.app.processEvents()
        self.assertEqual(page._current_columns, 1)
        self.assertEqual(page.groups["general"].width(),
                         page.groups["tools"].width())
        self.assertGreater(page.groups["general"].width(),
                           page.groups_host.width() - 8)
        self.assertEqual(page.scroller.horizontalScrollBarPolicy(),
                         Qt.ScrollBarAlwaysOff)
        self.assertEqual(page.scroller.horizontalScrollBar().maximum(), 0)
        self.assertFalse(page.startup.isEnabled())
        self.assertGreater(page.scroller.verticalScrollBar().maximum(), 0)
        self.assertIn("outros aplicativos", page.suggestions.accessibleName())
        self.assertIn("Reproduzir som", page.sound.accessibleName())
        self.assertIn("nova versão", page.updates.accessibleName())

    def test_backup_buttons_wrap_when_group_is_narrow(self):
        page = self.create_page()
        page.resize(1660, 850)
        page.show()
        self.app.processEvents()
        self.assertTrue(page._backup_horizontal)
        for col, button in enumerate(page.backup_buttons):
            self.assertIs(page.backup_buttons_grid.itemAtPosition(0, col).widget(),
                          button)
        page.resize(520, 850)
        self.app.processEvents()
        self.assertFalse(page._backup_horizontal)
        for row, button in enumerate(page.backup_buttons):
            self.assertIs(page.backup_buttons_grid.itemAtPosition(row, 0).widget(),
                          button)

    def test_actions_and_dependencies_survive_multiple_resizes(self):
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
        for width in (530, 760, 1100, 1660, 980):
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
