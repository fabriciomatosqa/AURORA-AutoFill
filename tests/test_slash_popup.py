"""Regressions for the non-activating slash popup and Win32 navigation."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication, QTextEdit
from PySide6.QtTest import QTest
from PySide6.QtGui import QTextCursor

from app.core import SnippetStore
from app.expansion import ExpansionCandidate, FocusContext, EditSnapshot
from app.hotkeys import GlobalHotkeyListener, INJECTION_TAG, ShortcutMatcher
from app.slash_popup import (POPUP_GAP, ASSETS, SlashCommandPopup,
                             placement_for_caret)
from app.productivity_features import ProductivityMixin


def key(character=None, name=""):
    return SimpleNamespace(char=character, name=name,
                           vk=ord(character) if character else None)


class NativeSuppressed(Exception):
    """Pynput raises a special exception to suppress a hardware event."""


class FakeHook:
    def __init__(self):
        self.suppressed = 0

    def suppress_event(self):
        self.suppressed += 1
        raise NativeSuppressed()


class SlashMatcherTests(unittest.TestCase):
    def test_menu_starts_with_single_slash_and_filters_as_typing(self):
        matcher = ShortcutMatcher(["/teste", "/tempo", "/bomdia"])
        self.assertEqual(matcher.suggestion_prefix(), "")
        matcher.feed("/")
        self.assertEqual(matcher.suggestion_prefix(), "/")
        matcher.feed("t")
        self.assertEqual(matcher.suggestion_prefix(), "/t")
        matcher.feed("e")
        self.assertEqual(matcher.suggestion_prefix(), "/te")
        matcher.feed(None, "backspace")
        self.assertEqual(matcher.suggestion_prefix(), "/t")
        matcher.feed("x")
        self.assertEqual(matcher.suggestion_prefix(), "")
        matcher.clear()
        matcher.feed("/")
        matcher.feed(" ")
        self.assertEqual(matcher.suggestion_prefix(), "")
        matcher.feed(None, "tab")
        self.assertEqual(matcher.suggestion_prefix(), "")

    def test_ui_acknowledgment_blocks_unrelated_fields_and_disabled_mode(self):
        focus = FocusContext(101, 202)
        other = FocusContext(101, 999)
        callback = []
        listener = GlobalHotkeyListener(
            lambda _: None, on_suggestion_state=callback.append)
        listener.update_shortcuts(["/teste"])
        with patch("app.hotkeys.capture_focus", return_value=focus),              patch("app.hotkeys.windows_modifiers", return_value=None):
            listener._on_press(key("/"))
            self.assertEqual(callback[-1], ("/", focus))
            listener.set_suggestion_visible("/", focus)
            self.assertFalse(listener._visible_suggestion_prefix)
            listener.set_suggestions_enabled(True)
            listener.set_suggestion_visible("/", other)
            self.assertFalse(listener._visible_suggestion_prefix)
            listener.set_suggestion_visible("/", focus)
            self.assertEqual(listener._visible_suggestion_prefix, "/")
            self.assertIsNone(listener.choose_suggestion("/", "/teste", other))
            selected = listener.choose_suggestion("/", "/teste", focus)
            self.assertIsInstance(selected, ExpansionCandidate)
            self.assertEqual((selected.shortcut, selected.selected_shortcut),
                             ("/", "/teste"))
            self.assertIsNone(listener.choose_suggestion("/", "/teste", focus))
            self.assertEqual(listener._matcher.suggestion_prefix(), "")

    def test_windows_only_swallow_selected_navigation_with_paired_keyup(self):
        focus = FocusContext(101, 202)
        navigated = []
        listener = GlobalHotkeyListener(lambda _: None,
                                       on_navigation=navigated.append)
        listener.update_shortcuts(["/teste", "/tempo"])
        listener.set_suggestions_enabled(True)
        hook = FakeHook()
        listener._listener = hook
        listener._running = True
        data = lambda vk, marker=0: SimpleNamespace(vkCode=vk,
                                                    dwExtraInfo=marker)
        with patch("app.hotkeys.capture_focus", return_value=focus),              patch("app.hotkeys.windows_modifiers", return_value=None):
            for ch in "/te":
                listener._on_press(key(ch))
            listener.set_suggestion_visible("/te", focus)
            with self.assertRaises(NativeSuppressed):
                listener._win32_event_filter(0x0100, data(0x28))  # Down
            self.assertEqual(navigated, [("down", "/te", focus)])
            with self.assertRaises(NativeSuppressed):
                listener._win32_event_filter(0x0101, data(0x28))
            self.assertEqual(hook.suppressed, 2)
            self.assertEqual(listener._suppressed_nav_keys, set())
            self.assertTrue(listener._win32_event_filter(0x0100, data(0x41)))
            self.assertFalse(listener._win32_event_filter(
                0x0100, data(0x41, INJECTION_TAG)))
            listener.set_suggestions_enabled(False)
            self.assertTrue(listener._win32_event_filter(0x0100, data(0x09)))
        listener._running = False

    def test_focus_change_and_modifier_prevent_suppression(self):
        focus, wrong = FocusContext(1, 2), FocusContext(5, 6)
        listener = GlobalHotkeyListener(lambda _: None,
                                       on_navigation=lambda _: None)
        listener.update_shortcuts(["/teste"])
        listener.set_suggestions_enabled(True)
        listener._listener = FakeHook()
        listener._running = True
        with patch("app.hotkeys.capture_focus", return_value=focus),              patch("app.hotkeys.windows_modifiers", return_value=None):
            listener._on_press(key("/"))
            listener.set_suggestion_visible("/", focus)
            listener._modifiers.add("ctrl_l")
            self.assertTrue(listener._win32_event_filter(
                0x0100, SimpleNamespace(vkCode=9, dwExtraInfo=0)))
            listener._modifiers.clear()
        with patch("app.hotkeys.capture_focus", return_value=wrong):
            self.assertTrue(listener._win32_event_filter(
                0x0100, SimpleNamespace(vkCode=9, dwExtraInfo=0)))
        listener._running = False


class SlashPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_focused_command_navigation_and_scrolling(self):
        panel = SlashCommandPopup()
        try:
            choices = [(f"/comando{i}", f"Resposta {i}") for i in range(12)]
            panel.present("/", choices, QPoint(20, 60))
            self.app.processEvents()
            self.assertTrue(panel.isVisible())
            self.assertFalse(panel.focusPolicy())
            self.assertEqual(panel.results.count(), 12)
            self.assertEqual(panel.current_shortcut(), "/comando0")
            for _ in range(7):
                panel.navigate(1)
            self.assertEqual(panel.current_shortcut(), "/comando7")
            panel.navigate(-1)
            self.assertEqual(panel.current_shortcut(), "/comando6")
            panel.present("/com", choices, QPoint(20, 60))
            self.assertEqual(panel.current_shortcut(), "/comando0")
            panel.navigate(-1)
            self.assertEqual(panel.current_shortcut(), "/comando11")
            panel.dismiss()
            self.assertFalse(panel.isVisible())
        finally:
            panel.close()
            panel.deleteLater()

    def test_placement_below_when_room_and_above_near_bottom(self):
        area = QRect(0, 0, 800, 600)
        popup = QSize(410, 275)
        near_top = QRect(50, 30, 1, 22)
        point, side, room = placement_for_caret(near_top, area, popup)
        self.assertEqual(side, "below")
        self.assertGreaterEqual(point.y(), near_top.bottom() + POPUP_GAP)
        self.assertGreaterEqual(room, popup.height())
        near_bottom = QRect(50, 550, 1, 22)
        point, side, room = placement_for_caret(near_bottom, area, popup)
        self.assertEqual(side, "above")
        self.assertLess(point.y() + popup.height(), near_bottom.top())
        self.assertGreaterEqual(room, popup.height())

    def test_popup_clamps_horizontal_and_shrinks_results_before_covering_caret(self):
        panel = SlashCommandPopup()
        try:
            screen = self.app.primaryScreen()
            area = screen.availableGeometry()
            choices = [(f"/comando{i}", f"Modelo {i}") for i in range(25)]
            anchor = QRect(area.right() - 8, area.top() + 26, 1, 22)
            panel.present("/", choices, anchor)
            self.app.processEvents()
            self.assertLessEqual(panel.geometry().right(), area.right())
            self.assertGreaterEqual(panel.geometry().left(), area.left())
            self.assertGreaterEqual(panel.geometry().top(),
                                    anchor.bottom() + POPUP_GAP)
            self.assertEqual(panel.results.count(), 25)
            bottom_anchor = QRect(area.left() + 40, area.bottom() - 29, 1, 22)
            panel.present("/", choices, bottom_anchor)
            self.app.processEvents()
            self.assertLess(panel.geometry().bottom(), bottom_anchor.top())
            self.assertTrue(panel.results.verticalScrollBar().maximum() > 0)
        finally:
            panel.close()
            panel.deleteLater()

    def test_translucent_window_real_rounded_card_and_matching_scroll_arrows(self):
        panel = SlashCommandPopup()
        try:
            self.assertTrue(panel.testAttribute(Qt.WA_TranslucentBackground))
            self.assertEqual(panel.card.objectName(), "slashCard")
            self.assertFalse(panel.autoFillBackground())
            self.assertEqual(panel.focusPolicy(), Qt.NoFocus)
            style = panel.styleSheet()
            self.assertIn("border-radius: 12px", style)
            self.assertIn("QFrame#auroraSlashPopup", style)
            self.assertIn("background: transparent", style)
            self.assertIn("QScrollBar::up-arrow:vertical", style)
            self.assertIn("QScrollBar::down-arrow:vertical", style)
            for name in ("scroll-up-dark.svg", "scroll-down-dark.svg",
                         "scroll-up-light.svg", "scroll-down-light.svg"):
                self.assertTrue((ASSETS / name).is_file(), name)
            self.assertEqual(
                (ASSETS / "scroll-up-dark.svg").read_text().count("<path"), 1)
            panel.present("/", [("/teste", "Teste")], QPoint(30, 70))
            self.app.processEvents()
            self.assertTrue(panel.isVisible())
        finally:
            panel.close()
            panel.deleteLater()

    def test_nonactivating_tool_does_not_auto_hide_on_hover_or_click(self):
        popup = SlashCommandPopup()
        selected = []
        popup.command_selected.connect(selected.append)
        try:
            self.assertEqual(popup.windowFlags() & Qt.Tool, Qt.Tool)
            self.assertTrue(popup.testAttribute(Qt.WA_ShowWithoutActivating))
            self.assertTrue(popup.windowFlags() & Qt.WindowDoesNotAcceptFocus)
            popup.present("/", [("/a", "Alpha"), ("/b", "Beta")], QPoint(40, 70))
            self.app.processEvents()
            item = popup.results.item(1)
            center = popup.results.visualItemRect(item).center()
            QTest.mouseMove(popup.results.viewport(), center)
            self.app.processEvents()
            self.assertTrue(popup.isVisible())
            QTest.mouseClick(popup.results.viewport(), Qt.LeftButton, pos=center)
            self.app.processEvents()
            self.assertEqual(selected, ["/b"])
            self.assertTrue(popup.isVisible())
        finally:
            popup.close()
            popup.deleteLater()

    def test_wheel_and_mouse_inside_popup_do_not_erase_typed_prefix(self):
        listener = GlobalHotkeyListener(lambda _: None)
        listener.update_shortcuts(["/teste", "/tempo"])
        for char in "/te":
            listener._matcher.feed(char)
        listener.set_popup_hitbox((100, 100, 410, 260))
        self.assertEqual(listener._matcher.suggestion_prefix(), "/te")
        listener._on_scroll(300, 180, 0, -2)
        listener._on_click(300, 180, None, True)
        self.assertEqual(listener._matcher.suggestion_prefix(), "/te")
        listener._on_click(20, 20, None, True)
        self.assertEqual(listener._matcher.suggestion_prefix(), "")
        listener._matcher.feed("/")
        listener._on_scroll(20, 20, 0, 1)
        self.assertEqual(listener._matcher.suggestion_prefix(), "")
        listener.set_popup_hitbox(None)

    def test_internal_editor_caret_not_mouse_is_the_popup_anchor(self):
        class LocalHost(ProductivityMixin):
            def isActiveWindow(self):
                return True

            def focusWidget(self):
                return self.test_box

        host = LocalHost()
        host.test_box = QTextEdit()
        host.test_box.setGeometry(80, 90, 600, 120)
        host.test_box.show()
        host.test_box.setPlainText("Um teste /te")
        host.test_box.moveCursor(QTextCursor.End)
        host._slash_popup = SlashCommandPopup()
        host._suggestion_catalog = [("/teste", "Teste")]
        host._hotkeys_enabled = True
        host._quitting = False
        host.preferences = {"suggest_shortcuts": True}
        host._slash_prefix = ""
        host._slash_context = None
        host.hotkeys = Mock()
        context = FocusContext(111, 222)
        try:
            expected = host.test_box.viewport().mapToGlobal(
                host.test_box.cursorRect().topLeft())
            with patch("app.productivity_features.sys.platform", "win32"), \\
                 patch("app.productivity_features.capture_focus", return_value=context), \\
                 patch("app.slash_popup.suggestion_anchor",
                       side_effect=AssertionError("Do not use mouse/fallback")):
                host._show_suggestions(("/te", context))
            self.app.processEvents()
            pos = host._slash_popup.geometry()
            self.assertLessEqual(abs(pos.left()-expected.x()), 10)
            self.assertGreater(
                pos.top(),
                expected.y() + host.test_box.cursorRect().height())
            self.assertEqual(host._slash_prefix, "/te")
            host.hotkeys.set_popup_hitbox.assert_called()
        finally:
            host._hide_suggestion_popup()
            host._slash_popup.close()
            host._slash_popup.deleteLater()
            host.test_box.close()
            host.test_box.deleteLater()

    def test_only_shortcut_and_title_are_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SnippetStore(Path(folder) / "snippets.sqlite3")
            try:
                group = db.create_folder("Modelos")
                db.save(group, "Resposta técnica", "/tecnico",
                        "Conteúdo privado", rich_content="<b>Imagem</b>")
                self.assertEqual(db.shortcut_catalog(),
                                 [("/tecnico", "Resposta técnica")])
                self.assertEqual(
                    EditSnapshot(FocusContext(1, 2), "Oi /te", 6, 6)
                    .shortcut_range("/te"), (3, 6))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
