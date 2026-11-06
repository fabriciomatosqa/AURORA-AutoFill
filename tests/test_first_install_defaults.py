"""First-install defaults must not override old users or re-register startup."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QObject, QCoreApplication, QEvent

from app.features import AuroraFeaturesMixin
from app.preferences import load_preferences


class Profile(QObject, AuroraFeaturesMixin):
    def __init__(self, *, fresh_database: bool):
        super().__init__()
        self.store = SimpleNamespace(_fresh_database=fresh_database)


class FirstInstallDefaultsTests(unittest.TestCase):
    @staticmethod
    def initialize(profile: Profile, target: Path, *, windows: bool):
        with patch("app.features.preferences_path", return_value=target), \
             patch("app.preferences.preferences_path", return_value=target), \
             patch("app.features.windows_startup_supported", return_value=windows), \
             patch("app.features.set_windows_startup") as registry:
            profile._initialize_features()
            values = load_preferences(target)
        return values, registry

    @staticmethod
    def dispose(profile):
        profile._update_watch.stop()
        profile.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_fresh_windows_profile_starts_minimized_with_suggestions(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "settings.json"
            profile = Profile(fresh_database=True)
            try:
                values, startup = self.initialize(profile, target, windows=True)
                startup.assert_called_once_with(True, minimized=True)
                self.assertTrue(values["start_minimized"])
                self.assertTrue(values["suggest_shortcuts"])
                self.assertTrue(profile.preferences["suggest_shortcuts"])
                self.assertTrue(target.exists())
            finally:
                self.dispose(profile)

    def test_existing_profile_does_not_change_disabled_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "settings.json"
            target.write_text(json.dumps({
                "start_minimized": False,
                "suggest_shortcuts": False,
                "theme": "dark",
            }), encoding="utf-8")
            before = target.read_bytes()
            profile = Profile(fresh_database=False)
            try:
                values, startup = self.initialize(profile, target, windows=True)
                startup.assert_not_called()
                self.assertFalse(values["start_minimized"])
                self.assertFalse(values["suggest_shortcuts"])
                self.assertEqual(before, target.read_bytes())
            finally:
                self.dispose(profile)

    def test_settings_file_takes_precedence_even_with_fresh_db(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "settings.json"
            target.write_text('{"suggest_shortcuts": false, "start_minimized": false}',
                              encoding="utf-8")
            profile = Profile(fresh_database=True)
            try:
                values, startup = self.initialize(profile, target, windows=True)
                startup.assert_not_called()
                self.assertFalse(values["start_minimized"])
                self.assertFalse(values["suggest_shortcuts"])
            finally:
                self.dispose(profile)

    def test_existing_database_with_missing_settings_is_not_onboarded_again(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "settings.json"
            profile = Profile(fresh_database=False)
            try:
                values, startup = self.initialize(profile, target, windows=True)
                startup.assert_not_called()
                self.assertFalse(values["start_minimized"])
                self.assertFalse(values["suggest_shortcuts"])
            finally:
                self.dispose(profile)

    def test_linux_first_install_enables_suggestions_without_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "settings.json"
            profile = Profile(fresh_database=True)
            try:
                values, startup = self.initialize(profile, target, windows=False)
                startup.assert_not_called()
                self.assertTrue(values["suggest_shortcuts"])
            finally:
                self.dispose(profile)


if __name__ == "__main__":
    unittest.main()
