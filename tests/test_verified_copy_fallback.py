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
    def test_unavailable_uia_expands_only_after_real_copy_matches_shortcut(self):
        with EngineFixture() as e:
            e.save("/eu", "Mensagem com formatação")
            with patch("app.ui.capture_edit", side_effect=readonly_uia), \
                 patch("app.ui.supports_verified_copy", return_value=True):
                e.type("/eu")
                e.until(0)
                assert e.api_calls == 1  # Selecionar + copiar em lote
                assert e.field.text == "/eu"
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
                 patch("app.ui.select_and_copy_shortcut",
                       side_effect=lambda count: e.clipboard.setText("texto-diferente")):
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
                 patch("app.ui.select_and_copy_shortcut", return_value=None):
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
                 patch("app.ui.select_and_copy_shortcut", return_value=None):
                e.type("/eu")
                def user_continues_typing():
                    e.field.anchor = e.field.caret = len(e.field.text)
                    e.type("X")
                e.schedule(5, user_continues_typing)
                e.drain()
            assert e.field.text.endswith("/euX")
            assert e.clipboard.text() == "original"
            assert e.host._play_confirmation.call_count == 0
    
    
    def test_teams_uia_selection_ack_without_visible_ack_can_copy_verify(self):
        with EngineFixture() as e:
            e.save("/teams", "Resposta{{cursor}}")
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
