"""Pesquisa global e automação respeitam o foco anterior."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from app.productivity_features import restore_target, same_windows_focus
from app.expansion import FocusContext


class ProductivitySafetyTests(unittest.TestCase):
    def test_non_windows_never_injects_to_arbitrary_context(self):
        with patch("app.productivity_features.sys.platform", "linux"):
            self.assertFalse(restore_target(FocusContext()))
            self.assertFalse(same_windows_focus(FocusContext()))

    def test_windows_missing_window_prevents_injection(self):
        with patch("app.productivity_features.sys.platform", "win32"):
            self.assertFalse(restore_target(FocusContext()))
            self.assertFalse(same_windows_focus(FocusContext()))


if __name__ == "__main__":
    unittest.main()
