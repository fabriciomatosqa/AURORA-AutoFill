"""Native Win32 Ctrl+Shift+Space registration and message dispatch regression tests."""
import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import Mock, patch

from app.win_global_search import (
    MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, QUICK_SEARCH_ID, VK_SPACE,
    WM_HOTKEY, WindowsQuickSearchHotkey,
)


class WinQuickSearchTests(unittest.TestCase):
    def setUp(self):
        self.api = type("FakeUser32", (), {})()
        self.api.RegisterHotKey = Mock(return_value=True)
        self.api.UnregisterHotKey = Mock(return_value=True)
        self.hotkey = WindowsQuickSearchHotkey(api=self.api)

    def test_native_registration_is_exact_modifiers_and_suppresses_repeats(self):
        with patch("app.win_global_search.sys.platform", "win32"):
            ok, warning = self.hotkey.register(1240)
            self.assertTrue(ok, warning)
            self.assertEqual(warning, "")
            self.api.RegisterHotKey.assert_called_once_with(
                1240, QUICK_SEARCH_ID,
                MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_SPACE)
            self.assertTrue(self.hotkey.active)
            # Idempotent: no two overlapping registrations.
            self.assertTrue(self.hotkey.register(1240)[0])
            self.api.RegisterHotKey.assert_called_once()
            self.hotkey.unregister()
            self.api.UnregisterHotKey.assert_called_once_with(
                1240, QUICK_SEARCH_ID)
            self.assertFalse(self.hotkey.active)
            self.hotkey.unregister()
            self.api.UnregisterHotKey.assert_called_once()

    def test_conflict_disables_non_suppressing_fallback(self):
        self.api.RegisterHotKey.return_value = False
        with patch("app.win_global_search.sys.platform", "win32"):
            success, warning = self.hotkey.register(1240)
        self.assertFalse(success)
        self.assertFalse(self.hotkey.active)
        self.assertIn("outro aplicativo", warning)
        self.api.UnregisterHotKey.assert_not_called()

    def test_other_platform_never_reserves_keys(self):
        with patch("app.win_global_search.sys.platform", "linux"):
            self.assertFalse(self.hotkey.register(1240)[0])
        self.api.RegisterHotKey.assert_not_called()

    def test_wm_hotkey_matches_only_our_window_and_key(self):
        def msg(hwnd, event, identity, lparam):
            native = wintypes.MSG()
            native.hWnd = hwnd
            native.message = event
            native.wParam = identity
            native.lParam = lparam
            return native

        combo = ((VK_SPACE << 16) | MOD_CONTROL | MOD_SHIFT)
        with patch("app.win_global_search.sys.platform", "win32"):
            self.assertTrue(self.hotkey.register(1240)[0])
            correct = msg(1240, WM_HOTKEY, QUICK_SEARCH_ID, combo)
            self.assertTrue(self.hotkey.matches(ctypes.addressof(correct)))
            for altered in (
                msg(1241, WM_HOTKEY, QUICK_SEARCH_ID, combo),
                msg(1240, WM_HOTKEY, QUICK_SEARCH_ID + 1, combo),
                msg(1240, 0x0100, QUICK_SEARCH_ID, combo),
                msg(1240, WM_HOTKEY, QUICK_SEARCH_ID, (0x41 << 16) | MOD_CONTROL | MOD_SHIFT),
                msg(1240, WM_HOTKEY, QUICK_SEARCH_ID, (VK_SPACE << 16) | MOD_CONTROL),
            ):
                self.assertFalse(self.hotkey.matches(ctypes.addressof(altered)))
            self.hotkey.unregister()
            self.assertFalse(self.hotkey.matches(ctypes.addressof(correct)))


if __name__ == "__main__":
    unittest.main()
