"""Regressões: a seleção via cópia não é o caminho padrão do Teams/Word.

O lote SendInput "Shift+Left + Ctrl+C" da versão .7 selecionava o atalho
mas podia deixá-lo no editor sem substituir. A leitura UIA/Win32 verificável
deve continuar sendo prioritária e não usar o probe de clipboard se funcionar.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from engine_fixture import EngineFixture
from app.windows_context import ContextUnavailable


class StableExpansionRollbackTests(unittest.TestCase):
    def test_accessible_known_editor_does_not_copy_probe_for_shortcuts(self):
        for shortcut in ("/1", "/teste", "/eu"):
            with self.subTest(shortcut=shortcut), EngineFixture() as engine:
                engine.save(shortcut, f"Resposta para {shortcut}")
                with patch("app.ui.supports_verified_copy", return_value=True), \
                     patch("app.ui.copy_selected_text",
                           side_effect=AssertionError("Ctrl+C não é caminho padrão")):
                    engine.type(shortcut)
                    engine.drain()
                self.assertEqual(engine.field.text, f"Resposta para {shortcut}")
                self.assertEqual(engine.clipboard.text(), "original")
                self.assertIsNone(engine.host._expansion_operation)

    def test_accessibility_failure_uses_fallback_only_after_bounded_retries(self):
        with EngineFixture() as engine:
            engine.save("/1", "Resposta")
            def inaccessible(*_args, **_kwargs):
                raise ContextUnavailable("Provendo texto indisponível")
            copy_requests = []
            with patch("app.ui.capture_edit", side_effect=inaccessible), \
                 patch("app.ui.supports_verified_copy", return_value=True), \
                 patch("app.ui.copy_selected_text", side_effect=lambda: copy_requests.append(engine.now)):
                engine.type("/1")
                engine.until(100)
                self.assertEqual(copy_requests, [])
                self.assertEqual(engine.field.text, "/1")
                engine.drain()
            self.assertGreaterEqual(len(copy_requests), 1)
            self.assertEqual(engine.field.text, "/1")
            self.assertEqual(engine.clipboard.text(), "original")

    def test_unrecognised_target_does_not_select_or_copy_without_a11y(self):
        with EngineFixture() as engine:
            engine.save("/teste", "Mensagem")
            def inaccessible(*_args, **_kwargs):
                raise ContextUnavailable("Sem UIA")
            with patch("app.ui.capture_edit", side_effect=inaccessible), \
                 patch("app.ui.supports_verified_copy", return_value=False), \
                 patch("app.ui.copy_selected_text",
                       side_effect=AssertionError("Destino desconhecido")):
                engine.type("/teste")
                engine.drain()
            self.assertEqual(engine.field.text, "/teste")
            self.assertEqual(engine.clipboard.text(), "original")


if __name__ == "__main__":
    unittest.main()
