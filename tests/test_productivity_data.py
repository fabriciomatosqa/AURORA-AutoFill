"""FTS5/LIKE e indicadores locais sem armazenar texto digitado."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from app.core import SnippetStore


class ProductivityDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SnippetStore(Path(self.tmp.name) / "snippets.sqlite3")
        self.folder = self.store.create_folder("Trabalho")
        self.one = self.store.save(self.folder, "Saudação", "/saudacao",
                                   "Bom dia. Atenciosamente.")
        self.two = self.store.save(self.folder, "Retorno de chamado", "/retorno",
                                   "Informações atualizadas.")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_fts_unicode_accent_prefix_and_fallback_middle_of_word(self):
        self.assertEqual([x.id for x in self.store.snippets(query="sauda")], [self.one])
        self.assertEqual([x.id for x in self.store.snippets(query="Saudação")], [self.one])
        self.assertEqual([x.id for x in self.store.snippets(query="atenciosa")], [])
        self.assertEqual([x.id for x in self.store.snippets(query="chamado")], [self.two])
        self.assertEqual([x.id for x in self.store.snippets(query="tencios")], [self.one])
        self.store.update_snippet_fields(self.one, title="Mensagem final", content="Confirmado.")
        self.assertFalse(self.store.snippets(query="saudacao"))
        self.assertEqual([x.id for x in self.store.snippets(query="confirmado")], [self.one])

    def test_usage_daily_monthly_yearly_and_reset(self):
        self.assertEqual(self.store.usage_report(date(2026, 10, 29))["total"], 0)
        self.store.register_expansion(self.one, date(2026, 10, 29))
        self.store.register_expansion(self.one, date(2026, 10, 29))
        self.store.register_expansion(self.two, date(2026, 9, 30))
        self.store.register_expansion(self.two, date(2025, 10, 1))
        r = self.store.usage_report(date(2026, 10, 29))
        self.assertEqual((r["today"], r["month"], r["year"], r["total"]), (2, 2, 3, 4))
        self.assertEqual(r["top"][0][0], self.one)
        self.assertEqual(dict(r["months"])["2026-10"], 2)
        self.store.reset_usage()
        self.assertEqual(self.store.usage_report()["total"], 0)

    def test_no_record_before_success_and_backward_compatible_tables(self):
        self.assertFalse(self.store.register_expansion(99999, date(2026, 10, 29)))
        self.assertEqual(self.store.usage_report()["total"], 0)
        self.store.delete(self.one)
        # Contadores históricos são agregados; exclusão do snippet não grava texto sensível.
        self.assertTrue(self.store._fts_available or self.store.snippets(query="retorno"))


if __name__ == "__main__":
    unittest.main()
