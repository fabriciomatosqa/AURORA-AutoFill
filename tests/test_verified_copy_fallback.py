"""Regressões para seleção verificada quando Word/Teams negam UI Automation."""
from __future__ import annotations

import unittest
from unittest.mock import patch, Mock

from engine_fixture import EngineFixture
from app.expansion import EditSnapshot, utf16_slice
from app.windows_context import ContextUnavailable
from app.accessibility_context import SELECTION_SUBMITTED


def copied_selection(engine):
    field = engine.field
    start, end = sorted((field.anchor, field.caret))
    engine.clipboard.setText(utf16_slice(field.text, start, end))


def readonly_uia(*args, **kwargs):
    raise ContextUnavailable("Texto ou seleção indisponível pela acessibilidade.")


def accessible_ui_snapshot(engine):
    def snapshot(context, *, accessibility=False):
        raw = engine.snapshot(context)
        if raw is None:
            return None
        return EditSnapshot(context, raw.text, raw.start, raw.end,
                            ("renderer", "teams", "document"))
    return snapshot


class VerifiedCopyFallbackTests(unittest.TestCase):
    def test_web_editors_with_readable_uia_do_not_require_uia_select(self):
        # Reproduz a falha reportada: o campo é legível, mas Select() lança
        # exatamente a mensagem que aparecia no Teams/editor online.
        for executable in ("ms-teams.exe", "teams.exe", "chrome.exe", "msedge.exe"):
            with self.subTest(executable=executable), EngineFixture() as e:
                e.save("/teste", "Resposta 😀")
                e.field.insert("/teste anterior\nAntes 😀 ")
                with patch("app.ui.capture_edit", side_effect=accessible_ui_snapshot(e)), \
                     patch("app.verified_fallback.focused_executable", return_value=executable), \
                     patch("app.ui.copy_selected_text", side_effect=lambda: copied_selection(e)):
                    e.selection.side_effect = readonly_uia
                    e.type("/teste")
                    e.drain()
                self.assertEqual(e.field.text, "/teste anterior\nAntes 😀 Resposta 😀")
                e.selection.assert_not_called()
                self.assertEqual(e.clipboard.text(), "original")
                self.assertEqual(sum(vk == 86 and not flags & 2
                                     for vk, flags, _ in e.sent), 1)

    def test_readable_web_editor_rejects_inexact_copy_without_pasting(self):
        with EngineFixture() as e:
            e.save("/teste", "Resposta")
            with patch("app.ui.capture_edit", side_effect=accessible_ui_snapshot(e)), \
                 patch("app.verified_fallback.focused_executable", return_value="chrome.exe"), \
                 patch("app.ui.copy_selected_text",
                       side_effect=lambda: e.clipboard.setText(" /teste")):
                e.type("/teste")
                e.drain()
            self.assertEqual(e.field.text, "/teste")
            e.selection.assert_not_called()
            self.assertFalse(any(vk == 86 for vk, _, _ in e.sent))
            self.assertEqual(e.clipboard.text(), "original")

    def test_readable_web_editor_keeps_rich_payload_and_confirms_result(self):
        from app.clipboard_content import expansion_mime
        html = '<p><span style="color:#ff0000;font-weight:700">Resposta</span></p>'
        for executable in ("ms-teams.exe", "chrome.exe"):
            with self.subTest(executable=executable), EngineFixture() as e:
                e.save("/rich", "Resposta", html)
                captured = []
                def record(*args, **kwargs):
                    payload = expansion_mime(*args, **kwargs)
                    captured.append((payload, kwargs))
                    return payload
                with patch("app.ui.capture_edit", side_effect=accessible_ui_snapshot(e)), \
                     patch("app.verified_fallback.focused_executable", return_value=executable), \
                     patch("app.ui.copy_selected_text", side_effect=lambda: copied_selection(e)), \
                     patch("app.ui.expansion_mime", side_effect=record):
                    e.type("/rich")
                    e.drain()
                self.assertEqual(e.field.text, "Resposta")
                self.assertEqual(len(captured), 1)
                self.assertTrue(captured[0][0].hasHtml())
                self.assertEqual(captured[0][1]["web_html_only"], executable == "ms-teams.exe")
                e.selection.assert_not_called()
                self.assertTrue(any("Expandido:" in call.args[0]
                                    for call in e.status.showMessage.call_args_list))

    def test_readable_web_editor_can_position_cursor_after_copy_verified_paste(self):
        with EngineFixture() as e:
            e.save("/cursor", "Antes {{cursor}}depois")
            with patch("app.ui.capture_edit", side_effect=accessible_ui_snapshot(e)), \
                 patch("app.verified_fallback.focused_executable", return_value="chrome.exe"), \
                 patch("app.ui.copy_selected_text", side_effect=lambda: copied_selection(e)):
                e.type("/cursor")
                e.drain()
            self.assertEqual(e.field.text, "Antes depois")
            self.assertEqual(e.field.caret, 6)
            e.selection.assert_not_called()
            self.assertEqual(e.position.call_count, 1)
            self.assertEqual(e.clipboard.text(), "original")

    def test_copy_preference_requires_an_identified_web_executable(self):
        from app.verified_fallback import prefers_verified_copy
        for executable in ("teams.exe", "chrome.exe", "msedge.exe", "firefox.exe",
                           "winword.exe", "unknown.exe", "not-chrome.exe", ""):
            with self.subTest(executable=executable), \
                 patch("app.verified_fallback.focused_executable", return_value=executable):
                self.assertEqual(prefers_verified_copy(None),
                                 executable in {"teams.exe", "chrome.exe", "msedge.exe", "firefox.exe"})

    def test_web_copy_proof_rejects_changed_document_before_paste(self):
        for mutation in ("identity", "text", "selection", "clipboard"):
            with self.subTest(mutation=mutation), EngineFixture() as e:
                e.save("/teste", "Resposta")
                normal = accessible_ui_snapshot(e)
                def snapshot(context, *, accessibility=False):
                    current = normal(context, accessibility=accessibility)
                    op = e.host._expansion_operation
                    if op is None or op.stage != "verifying":
                        return current
                    if mutation == "identity":
                        return EditSnapshot(context, current.text, current.start, current.end,
                                            ("renderer", "other-field", "document"))
                    if mutation == "text":
                        return EditSnapshot(context, "Changed " + current.text,
                                            current.start, current.end, current.identity)
                    if mutation == "selection":
                        return EditSnapshot(context, current.text, 0, 0, current.identity)
                    e.clipboard.setText("USER COPY")
                    return current
                with patch("app.ui.capture_edit", side_effect=snapshot), \
                     patch("app.verified_fallback.focused_executable", return_value="chrome.exe"), \
                     patch("app.ui.copy_selected_text", side_effect=lambda: copied_selection(e)):
                    e.type("/teste")
                    e.drain()
                self.assertEqual(e.field.text, "/teste")
                self.assertFalse(any(vk == 86 for vk, _, _ in e.sent))
                self.assertEqual(e.clipboard.text(), "USER COPY" if mutation == "clipboard" else "original")

    def test_web_editor_losing_uia_after_copy_can_paste_without_requiring_select(self):
        with EngineFixture() as e:
            e.save("/teste", "Resposta")
            normal = accessible_ui_snapshot(e)
            def snapshot(context, *, accessibility=False):
                op = e.host._expansion_operation
                if op is not None and op.stage == "verifying":
                    return readonly_uia()
                return normal(context, accessibility=accessibility)
            with patch("app.ui.capture_edit", side_effect=snapshot), \
                 patch("app.verified_fallback.focused_executable", return_value="chrome.exe"), \
                 patch("app.ui.copy_selected_text", side_effect=lambda: copied_selection(e)):
                e.type("/teste")
                e.drain()
            self.assertEqual(e.field.text, "Resposta")
            e.selection.assert_not_called()
            self.assertEqual(sum(vk == 86 and not flags & 2 for vk, flags, _ in e.sent), 1)
            self.assertEqual(e.clipboard.text(), "original")

    def test_rich_copy_with_many_revisions_restores_only_target_owned_clipboard(self):
        for owned in (False, True):
            with self.subTest(owned=owned), EngineFixture() as e:
                e.save("/teste", "Resposta")
                def rich_copy():
                    for _ in range(4):
                        e.clipboard.setText("other")
                with patch("app.ui.capture_edit", side_effect=readonly_uia), \
                     patch("app.ui.supports_verified_copy", return_value=True), \
                     patch("app.ui.copy_selected_text", side_effect=rich_copy), \
                     patch("app.ui.clipboard_owned_by_target", return_value=owned):
                    e.type("/teste")
                    e.drain()
                self.assertEqual(e.field.text, "/teste")
                self.assertFalse(any(vk == 86 for vk, _, _ in e.sent))
                self.assertEqual(e.clipboard.text(), "original" if owned else "other")

    def test_clipboard_owner_must_match_the_target_process(self):
        import ctypes
        from types import SimpleNamespace
        from app.expansion import FocusContext
        from app.verified_fallback import clipboard_owned_by_target
        for source, expected in ((11, True), (22, True), (33, False), (0, False)):
            with self.subTest(source=source):
                def pid(window, pointer):
                    pointer._obj.value = {123: 11, 456: 22, 789: source}[window]
                    return 1
                api = SimpleNamespace(GetClipboardOwner=Mock(return_value=789),
                                      GetWindowThreadProcessId=Mock(side_effect=pid))
                with patch("sys.platform", "win32"), \
                     patch.object(ctypes, "windll", SimpleNamespace(user32=api), create=True):
                    self.assertEqual(clipboard_owned_by_target(FocusContext(123, 456)), expected)

    def test_unavailable_uia_expands_only_after_real_copy_matches_shortcut(self):
        with EngineFixture() as e:
            e.save("/eu", "Mensagem com formatação")
            with patch("app.ui.capture_edit", side_effect=readonly_uia), \
                 patch("app.ui.supports_verified_copy", return_value=True), \
                 patch("app.ui.copy_selected_text", side_effect=lambda: copied_selection(e)):
                e.type("/eu")
                e.until(140)
                assert e.api_calls == 0
                e.drain()
            assert e.field.text == "Mensagem com formatação"
            assert e.api_calls == 2  # Shift+Left, depois Ctrl+V, nunca backspace
            assert e.clipboard.text() == "original"
            assert not (e.shift or e.ctrl)
    
    
    def test_invalid_copy_does_not_delete_unrelated_text(self):
        with EngineFixture() as e:
            e.save("/eu", "REPOSTA")
            e.field.insert("Outra palavra ")
            with patch("app.ui.capture_edit", side_effect=readonly_uia), \
                 patch("app.ui.supports_verified_copy", return_value=True), \
                 patch("app.ui.copy_selected_text",
                       side_effect=lambda: e.clipboard.setText("texto-diferente")):
                e.type("/eu")
                e.drain()
            assert e.field.text == "Outra palavra /eu"
            assert e.clipboard.text() == "original"
            assert e.host._play_confirmation.call_count == 0
            assert e.host._expansion_operation is None
    
    
    def test_ignored_copy_leaves_shortcut_intact_and_restores_clipboard(self):
        with EngineFixture() as e:
            e.save("/eu", "REPOSTA")
            with patch("app.ui.capture_edit", side_effect=readonly_uia), \
                 patch("app.ui.supports_verified_copy", return_value=True), \
                 patch("app.ui.copy_selected_text", return_value=None):
                e.type("/eu")
                e.drain()
            assert e.field.text == "/eu"
            assert e.clipboard.text() == "original"
            assert e.host._play_confirmation.call_count == 0
    
    
    def test_user_types_while_copy_pending_and_fallback_is_cancelled(self):
        with EngineFixture() as e:
            e.save("/eu", "REPOSTA")
            with patch("app.ui.capture_edit", side_effect=readonly_uia), \
                 patch("app.ui.supports_verified_copy", return_value=True), \
                 patch("app.ui.copy_selected_text", return_value=None):
                e.type("/eu")
                def user_continues_typing():
                    e.field.anchor = e.field.caret = len(e.field.text)
                    e.type("X")
                e.schedule(175, user_continues_typing)
                e.drain()
            assert e.field.text.endswith("/euX")
            assert e.clipboard.text() == "original"
            assert e.host._play_confirmation.call_count == 0
    
    
    def test_teams_uia_selection_ack_without_visible_ack_can_copy_verify(self):
        with EngineFixture() as e:
            e.save("/teams", "Resposta")
            def snapshot(context, *, accessibility=False):
                actual = e.snapshot(context)
                if actual is None:
                    return None
                if (e.host._expansion_operation is not None
                        and e.host._expansion_operation.stage == "selected"
                        and actual.start != actual.end):
                    # O GetSelection permanece com caret antigo apesar de a
                    # seleção já estar materializada no editor.
                    end = len(actual.text)
                    actual = EditSnapshot(context, actual.text, end, end)
                return EditSnapshot(context, actual.text, actual.start, actual.end,
                                    ("renderer", "teams", "document"))
            def select_ack(before, start, end):
                e.select(before, start, end)
                return SELECTION_SUBMITTED
            with patch("app.ui.capture_edit", side_effect=snapshot), \
                 patch("app.ui.supports_verified_copy", return_value=True), \
                 patch("app.ui.copy_selected_text", side_effect=lambda: copied_selection(e)):
                e.selection.side_effect = select_ack
                e.type("/teams")
                e.drain()
            assert e.field.text == "Resposta"
            assert e.selection.call_count == 1
            assert e.clipboard.text() == "original"
    
    
    def test_teams_profile_requires_exact_windows_executable(self):
        from app.verified_fallback import is_teams_target, supports_verified_copy
        from app.expansion import FocusContext
        context = FocusContext(123, 456)
        for executable in ("teams.exe", "ms-teams.exe"):
            with self.subTest(executable=executable), \
                 patch("app.verified_fallback.focused_executable", return_value=executable):
                self.assertTrue(is_teams_target(context))
                self.assertTrue(supports_verified_copy(context))
        for executable in ("winword.exe", "chrome.exe", "msedgewebview2.exe", ""):
            with self.subTest(executable=executable), \
                 patch("app.verified_fallback.focused_executable", return_value=executable):
                self.assertFalse(is_teams_target(context))

    def test_teams_rich_snippet_keeps_html_on_keyboard_verified_fallback(self):
        from app.clipboard_content import expansion_mime
        html = '<p><span style="background-color:#ffff00;color:#ff0000">Texto importante</span></p>'
        with EngineFixture() as e:
            e.save("/teste", "Texto importante", html)
            captured = []
            def record_mime(*args, **kwargs):
                payload = expansion_mime(*args, **kwargs)
                captured.append((payload, dict(kwargs)))
                return payload
            with patch("app.ui.capture_edit", side_effect=readonly_uia), \
                 patch("app.ui.supports_verified_copy", return_value=True), \
                 patch("app.ui.is_teams_target", return_value=True), \
                 patch("app.ui.copy_selected_text", side_effect=lambda: copied_selection(e)), \
                 patch("app.ui.expansion_mime", side_effect=record_mime):
                e.type("/teste")
                e.drain()
            self.assertEqual(e.field.text, "Texto importante")
            self.assertEqual(e.clipboard.text(), "original")
            self.assertEqual(len(captured), 1)
            self.assertTrue(captured[0][1]["web_html_only"])
            self.assertTrue(captured[0][0].hasHtml())

    def test_unknown_app_never_runs_keyboard_fallback(self):
        with EngineFixture() as e:
            e.save("/eu", "Mensagem")
            copy_spy = Mock()
            with patch("app.ui.capture_edit", side_effect=readonly_uia), \
                 patch("app.ui.supports_verified_copy", return_value=False), \
                 patch("app.ui.copy_selected_text", copy_spy):
                e.type("/eu")
                e.drain()
            copy_spy.assert_not_called()
            assert e.field.text == "/eu"
            assert e.clipboard.text() == "original"
    

if __name__ == '__main__':
    unittest.main()
