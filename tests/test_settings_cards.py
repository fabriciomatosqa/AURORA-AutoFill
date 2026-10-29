"""Responsive AURORA settings layout and callback regressions."""
import os
import unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton
from app.settings_panel import SettingsPage
from app.preferences import DEFAULTS

class SettingsCardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def create_page(self, supported=True):
        page = SettingsPage(dict(DEFAULTS), startup_supported=supported, startup_enabled=False)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.close)
        return page

    def names(self, page, layout):
        return [name for i in range(layout.count())
                for name, widget in page.cards.items()
                if layout.itemAt(i).widget() is widget]

    def test_responsive_columns_preserve_state(self):
        page = self.create_page()
        page.resize(1200, 900)
        page.show()
        self.app.processEvents()
        self.assertFalse(page._compact_columns)
        self.assertEqual(self.names(page, page.left_column),
                         ["appearance", "productivity", "backups"])
        self.assertEqual(self.names(page, page.right_column),
                         ["audio", "startup", "updates"])
        self.assertLessEqual(page.theme.width(), 260)
        self.assertLessEqual(page.check_button.width(), 270)
        page.volume.setValue(42)
        page.prereleases.setChecked(False)
        page.resize(600, 750)
        self.app.processEvents()
        self.assertTrue(page._compact_columns)
        self.assertEqual(self.names(page, page.left_column),
                         ["appearance", "productivity", "audio",
                          "startup", "backups", "updates"])
        self.assertFalse(page.right_host.isVisible())
        self.assertEqual(page.volume.value(), 42)
        page.resize(1200, 900)
        self.app.processEvents()
        self.assertFalse(page._compact_columns)
        self.assertEqual(page.volume.value(), 42)
        self.assertFalse(page.prereleases.isChecked())

    def test_buttons_and_dependencies_keep_working(self):
        page = self.create_page()
        events = []
        for name, signal in [
            ("search", page.global_search_requested),
            ("stats", page.statistics_requested),
            ("backup", page.backup_requested),
            ("restore", page.restore_requested),
            ("open", page.open_backups_requested),
            ("check", page.check_requested),
            ("sound", page.sound_toggled),
            ("startup", page.startup_toggled),
        ]:
            signal.connect(lambda *args, n=name: events.append(n))
        for obj in ["globalSearchSettingsButton", "statisticsSettingsButton",
                    "settingsBackupCreateButton", "settingsBackupRestoreButton",
                    "settingsBackupOpenButton", "settingsCheckUpdatesButton"]:
            btn = page.findChild(QPushButton, obj)
            self.assertIsNotNone(btn, obj)
            btn.click()
        page.sound.setChecked(False)
        self.assertFalse(page.volume.isEnabled())
        page.sound.setChecked(True)
        self.assertTrue(page.volume.isEnabled())
        page.startup.setChecked(True)
        self.assertTrue(page.start_minimized.isEnabled())
        self.assertTrue(set(["search", "stats", "backup", "restore",
                             "open", "check", "sound", "startup"]) <= set(events))

    def test_no_horizontal_scroll_and_accessibility(self):
        page = self.create_page(supported=False)
        page.resize(530, 730)
        page.show()
        self.app.processEvents()
        self.assertEqual(page.scroller.horizontalScrollBarPolicy(),
                         Qt.ScrollBarAlwaysOff)
        self.assertFalse(page.startup.isEnabled())
        self.assertIn("outros aplicativos", page.suggestions.accessibleName())
        self.assertGreater(page.scroller.verticalScrollBar().maximum(), 0)

if __name__ == "__main__":
    unittest.main()
