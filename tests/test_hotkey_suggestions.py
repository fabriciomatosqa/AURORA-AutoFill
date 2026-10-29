"""Reconhecimento de sugestões e atalho de pesquisa sem abrir hook real."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.hotkeys import GlobalHotkeyListener, ShortcutMatcher


class GlobalProductivityKeysTests(unittest.TestCase):
    def test_transient_suggestions_only_after_slash_and_two_chars(self):
        matcher = ShortcutMatcher(["/contato", "/contrato", "/teste"])
        self.assertEqual(matcher.current_prefix(), "")
        for char in "/co":
            matcher.feed(char)
        self.assertEqual(matcher.current_prefix(), "/co")
        matcher.feed("n")
        self.assertEqual(matcher.current_prefix(), "/con")
        matcher.feed(None, "tab")
        self.assertEqual(matcher.current_prefix(), "")

    def test_ctrl_shift_space_calls_search_without_triggering_snippet(self):
        results = []
        prefixes = []
        listener = GlobalHotkeyListener(
            lambda candidate: results.append(candidate),
            on_quick_search=lambda: results.append("quick_search"),
            on_prefix=prefixes.append)
        with patch("app.hotkeys.windows_modifiers", return_value=None):
            listener._press(SimpleNamespace(name="ctrl_l", char=None))
            listener._press(SimpleNamespace(name="shift_l", char=None))
            listener._press(SimpleNamespace(name="space", char=" "))
        self.assertEqual(results, ["quick_search"])
        self.assertEqual(prefixes[-1], "")

    def test_other_shortcuts_are_not_intercepted(self):
        calls = []
        listener = GlobalHotkeyListener(lambda _: None, on_quick_search=lambda: calls.append("open"))
        with patch("app.hotkeys.windows_modifiers", return_value=None):
            listener._press(SimpleNamespace(name="ctrl_l", char=None))
            listener._press(SimpleNamespace(name="space", char=" "))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
