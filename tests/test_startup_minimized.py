"""Start minimized via Windows Run command and keep a normal manual launch."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import preferences


class FakeKey:
    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = 1
    KEY_READ = 2
    KEY_SET_VALUE = 4
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def CreateKeyEx(self, hive, key, reserved, access):
        return FakeKey(self)

    def OpenKey(self, hive, key, reserved, access):
        if preferences.RUN_NAME not in self.values:
            raise FileNotFoundError("Run entry not found")
        return FakeKey(self)

    def SetValueEx(self, key, name, reserved, kind, data):
        self.values[name] = data

    def QueryValueEx(self, key, name):
        return self.values[name], self.REG_SZ

    def DeleteValue(self, key, name):
        self.values.pop(name)


class MinimizedStartupTests(unittest.TestCase):
    def test_setting_roundtrip_and_normalization(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "settings.json"
            self.assertFalse(preferences.load_preferences(file)["start_minimized"])
            original = dict(preferences.DEFAULTS)
            original["start_minimized"] = True
            preferences.save_preferences(original, file)
            self.assertTrue(preferences.load_preferences(file)["start_minimized"])
            file.write_text('{"start_minimized": "yes"}', encoding="utf-8")
            self.assertFalse(preferences.load_preferences(file)["start_minimized"])

    def test_run_registry_only_adds_minimized_when_requested(self):
        fake = FakeWinreg()
        with patch.dict(sys.modules, {"winreg": fake}), \
             patch("app.preferences.windows_startup_supported", return_value=True):
            preferences.set_windows_startup(True, minimized=False)
            regular = fake.values[preferences.RUN_NAME]
            self.assertTrue(regular.startswith('"'))
            self.assertFalse(regular.endswith("--minimized"))
            self.assertTrue(preferences.windows_startup_enabled())

            preferences.set_windows_startup(True, minimized=True)
            command = fake.values[preferences.RUN_NAME]
            self.assertEqual(command, regular + " --minimized")
            self.assertTrue(preferences.windows_startup_enabled())
            preferences.set_windows_startup(False)
            self.assertNotIn(preferences.RUN_NAME, fake.values)
            self.assertFalse(preferences.windows_startup_enabled())

    def test_startup_behavior_needs_explicit_flag_and_tray(self):
        from main import should_start_in_tray
        with patch("main.sys.platform", "win32"):
            self.assertTrue(should_start_in_tray(["--minimized"], tray_available=True))
            self.assertFalse(should_start_in_tray([], tray_available=True))
            self.assertFalse(should_start_in_tray(["--minimized"], tray_available=False))
        with patch("main.sys.platform", "linux"):
            self.assertFalse(should_start_in_tray(["--minimized"], tray_available=True))



if __name__ == "__main__":
    unittest.main()
