"""Regressões do caminho crítico: localizar atalhos sem varrer imagens do banco."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import SnippetStore
from engine_fixture import EngineFixture


class IndexedShortcutTests(unittest.TestCase):
    def test_uses_only_one_row_even_with_many_rich_image_snippets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SnippetStore(Path(tmp) / "snippets.sqlite3")
            try:
                folder = store.create_folder("Atalhos ilustrados")
                filler = "<html><body>" + "a" * 180000 + "</body></html>"
                for i in range(50):
                    store.save(folder, f"Exemplo {i}", f"/ex{i:03d}", "Exemplo", rich_content=filler)
                store.save(folder, "Resposta", "/rapido", "Conteúdo correto", rich_content="")
                with patch.object(store, "snippets",
                                  side_effect=AssertionError("Não pode listar todo o banco")):
                    target = store.snippet_by_shortcut("/rapido")
                    self.assertIsNotNone(target)
                    self.assertEqual(target.content, "Conteúdo correto")
                    self.assertEqual(store.snippet_by_shortcut("/naoexiste"), None)
                    # A restrição UNIQUE COLLATE NOCASE continua funcionando.
                    self.assertEqual(store.snippet_by_shortcut("/RAPIDO").id, target.id)
            finally:
                store.close()

    def test_engine_expands_without_listing_full_database(self):
        with EngineFixture() as engine:
            engine.save("/rapido", "Tudo certo")
            with patch.object(engine.store, "snippets",
                                  side_effect=AssertionError("Varredura desnecessária")):
                engine.type("/rapido")
                engine.until(45)
                self.assertEqual(engine.field.text, "Tudo certo")
                engine.drain()
                self.assertEqual(engine.clipboard.text(), "original")


if __name__ == "__main__":
    unittest.main()
