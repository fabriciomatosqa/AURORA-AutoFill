"""Appearance regression tests, isolated profiles and no real keyboard/network."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QColor, QPalette, QTextCursor
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from app import preferences
from app.themes import ThemeController, current_theme, resolved_theme
from app.ui import AutoFillWindow, AuroraBanner, AuroraMenu
from app.color_dialog import AuroraColorDialog
from app.update_notice import UpdateNotice

ROOT = Path(__file__).resolve().parents[1]


class PreferenceTests(unittest.TestCase):
    def test_new_existing_legacy_and_invalid_preferences(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / "settings.json"
            self.assertEqual(preferences.load_preferences(settings)["theme"], "system")
            self.assertEqual(preferences.load_preferences(settings, existing_profile=True)["theme"], "dark")
            settings.write_text('{"sound_volume": 37}')
            self.assertEqual(preferences.load_preferences(settings)["theme"], "dark")
            for invalid in (None, [], {}, "other", 3):
                self.assertEqual(preferences.normalize_preferences({"theme": invalid})["theme"], "dark")
            for mode in ("light", "dark", "system"):
                preferences.save_preferences({"theme": mode}, settings)
                self.assertEqual(preferences.load_preferences(settings)["theme"], mode)

    def test_main_light_palette_contrast(self):
        def luminance(color):
            rgb = QColor(color).getRgbF()[:3]
            values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
            return sum(v * weight for v, weight in zip(values, (.2126, .7152, .0722)))
        for foreground, background in (("#16324f", "#ffffff"), ("#4f6b86", "#f4f8fc"),
                                       ("#ffffff", "#00798a"), ("#00788a", "#f4f8fc"),
                                       ("#09283b", "#8ce4d5")):
            values = sorted((luminance(foreground), luminance(background)))
            self.assertGreaterEqual((values[1] + .05) / (values[0] + .05), 4.5)

    def test_first_choice_is_saved_before_second_launch_and_old_backups_stay_dark(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / "settings.json"
            preferences.load_preferences(settings, existing_profile=False, initialize=True)
            self.assertEqual(preferences.load_preferences(settings, existing_profile=True)["theme"], "system")
            settings.write_text('{"sound_volume": 37}')
            preferences.load_preferences(settings, initialize=True)
            self.assertEqual(json.loads(settings.read_text())["theme"], "dark")
            self.assertEqual(preferences.load_preferences(settings)["sound_volume"], 37)


class AppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-theme-")
        root = Path(self.temp.name)
        self.settings = root / "settings.json"
        self.patches = [
            patch("app.ui.application_db_path", return_value=root / "snippets.sqlite3"),
            patch("app.preferences.preferences_path", return_value=self.settings),
            patch("app.ui.GlobalHotkeyListener.start", return_value=(False, "Teste")),
            patch("app.ui.AutoFillWindow._initial_release_check"),
        ]
        for item in self.patches:
            item.start()
        self.win = AutoFillWindow()
        self.win.show()
        self.app.processEvents()

    def tearDown(self):
        self.win.dirty = False
        self.win._quitting = True
        self.win.close()
        self.win.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()
        self.app.setProperty("auroraTheme", "dark")

    def choose(self, value):
        box = self.win.settings_page.theme
        box.setCurrentIndex(box.findData(value))
        self.app.processEvents()

    def test_picker_palette_banner_and_persistence(self):
        for mode in ("light", "dark", "system"):
            self.choose(mode)
            expected = resolved_theme(mode, self.app.styleHints().colorScheme())
            self.assertEqual(current_theme(), expected)
            self.assertEqual(preferences.load_preferences(self.settings)["theme"], mode)
            self.assertEqual(self.win.banner._image.cacheKey(),
                             (self.win.banner._day if expected == "light" else self.win.banner._night).cacheKey())
            self.assertFalse(self.win.banner_brand.isHidden())
            color = self.app.palette().color(QPalette.Text)
            self.assertEqual(color.name(), "#16324f" if expected == "light" else "#f5faff")
            self.assertEqual(self.win.banner.height(), 168)

    def test_failed_save_keeps_previous_theme_and_picker(self):
        self.choose("dark")
        with patch("app.features.save_preferences", side_effect=OSError("Disk full")), patch("app.features.QMessageBox.warning"):
            self.choose("light")
        self.assertEqual(current_theme(), "dark")
        self.assertEqual(self.win.settings_page.theme.currentData(), "dark")
        self.assertEqual(preferences.load_preferences(self.settings)["theme"], "dark")

    def test_native_scheme_signal_fallback_and_forced_mode(self):
        self.choose("system")
        # Exercise the native Qt signal connection; real desktop event delivery
        # is additionally checked manually on the user's Windows/Linux desktop.
        self.app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
        self.assertEqual(current_theme(), "light")
        self.app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        self.assertEqual(current_theme(), "dark")
        self.app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Unknown)
        self.assertEqual(current_theme(), "dark")
        self.choose("light")
        self.app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        self.assertEqual(current_theme(), "light")

    def test_switch_does_not_edit_rich_content_selection_or_database(self):
        folder = self.win.store.create_folder("Pessoal")
        html = '<p><span style="font-family:serif; font-size:17pt; color:#bc173d; background-color:#ffee33; font-weight:700">Colorido</span></p><p>Segundo parágrafo</p>'
        ident = self.win.store.save(folder, "Cores", "/cores", "Colorido\nSegundo parágrafo", rich_content=html)
        self.win._refresh_all()
        self.win._load_editor(self.win._get_snippet(ident))
        cursor = self.win.body_input.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(5, QTextCursor.KeepAnchor)
        self.win.body_input.setTextCursor(cursor)
        editor_before = self.win.body_input.toHtml()
        preview_before = self.win.preview.toHtml()
        doc = self.win.body_input.document()
        doc.setModified(False)
        for mode in ("light", "dark", "system"):
            self.choose(mode)
            self.assertEqual(self.win.store.snippet_by_shortcut("/cores").rich_content, html)
            self.assertEqual(self.win.body_input.toHtml(), editor_before)
            self.assertEqual(self.win.preview.toHtml(), preview_before)
            self.assertEqual(self.win.body_input.textCursor().selectedText(), "lor")
            self.assertFalse(doc.isModified())

    def test_popups_icons_and_dialogs_follow_appearance(self):
        menu = AuroraMenu(self.win)
        color = AuroraColorDialog(QColor("#bc173d"), self.win)
        notice = UpdateNotice()
        self.choose("light")
        for widget in (menu, color, self.win.settings_page):
            self.assertNotIn("#091426", widget.styleSheet())
            self.assertNotIn("#112f41", widget.styleSheet())
        self.assertIn("#ffffff", color.styleSheet())
        panel = notice.findChild(QPushButton, "updateAccept").parentWidget()
        self.assertIn("#ffffff", panel.styleSheet())
        self.choose("dark")
        self.assertIn("#0c1d31", color.styleSheet())
        self.assertEqual(color.currentColor().name(), "#bc173d")
        menu.deleteLater()
        color.deleteLater()
        notice.deleteLater()

    def test_banner_geometry_and_shared_overlay_at_multiple_sizes(self):
        banner = self.win.banner
        # Day and night show the same landscape. Different source dimensions
        # would change the crop/scale and move the mountains on a theme switch.
        self.assertEqual(banner._night.size(), banner._day.size())
        self.assertEqual((banner._night.width(), banner._night.height()), (2048, 768))
        for width in (1060, 1320, 1920, 2560):
            self.win.resize(width, 900)
            self.app.processEvents()
            brand_geometry = None
            landscape_crop = None
            for mode in ("light", "dark"):
                self.choose(mode)
                source = banner._image
                self.assertFalse(source.isNull())
                crop = banner.source_crop(source.width(), source.height(), banner.panorama_width(), banner.height())
                self.assertLessEqual(crop.right(), source.width())
                self.assertLessEqual(crop.bottom(), source.height())
                if landscape_crop is None:
                    landscape_crop = crop
                else:
                    self.assertEqual(crop, landscape_crop)
                self.assertTrue(self.win.banner_brand.isVisible())
                if brand_geometry is None:
                    brand_geometry = self.win.banner_brand.geometry()
                else:
                    self.assertEqual(self.win.banner_brand.geometry(), brand_geometry)
                caption = self.win.banner_brand.findChild(QLabel, "topCaption")
                self.assertEqual(caption.palette().color(QPalette.WindowText).name(), "#d2eafa")
                self.assertFalse(banner.grab().isNull())
