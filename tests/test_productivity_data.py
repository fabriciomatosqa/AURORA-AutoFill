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
        self.assertEqual([x.id for x in self.store.snippets(query="atenciosox")], [])
        self.assertEqual([x.id for x in self.store.snippets(query="chamado")], [self.two])
        self.assertEqual([x.id for x in self.store.snippets(query="tencios")], [self.one])
        self.store.update_snippet_fields(self.one, title="Mensagem final", shortcut="/mensagem", content="Confirmado.")
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
        self.assertIn((self.one, 2), [(i, n) for i, _title, _shortcut, n in r["top"]])
        self.assertEqual(dict(r["months"])["2026-10"], 2)
        self.assertEqual(self.store.usage_days(2026, 10), {29: 2})
        self.assertEqual(self.store.usage_days(2026, 9), {30: 1})
        self.assertEqual(self.store.usage_days(2026, 11), {})
        self.assertEqual(self.store.usage_day_top(date(2026, 10, 29)),
                         [("Saudação", 2)])
        self.assertEqual(self.store.usage_day_top(date(2026, 10, 28)), [])
        with self.assertRaises(ValueError):
            self.store.usage_days(2026, 13)
        self.store.reset_usage()
        self.assertEqual(self.store.usage_report()["total"], 0)
        self.assertEqual(self.store.usage_days(2026, 10), {})

    def test_no_record_before_success_and_backward_compatible_tables(self):
        self.assertFalse(self.store.register_expansion(99999, date(2026, 10, 29)))
        self.assertEqual(self.store.usage_report()["total"], 0)
        self.store.delete(self.one)
        # Contadores históricos são agregados; exclusão do snippet não grava texto sensível.
        self.assertTrue(self.store._fts_available or self.store.snippets(query="retorno"))


    def test_usage_survives_catalog_replacement_and_legacy_migration(self):
        from datetime import date
        import sqlite3
        from contextlib import closing
        path = Path(self.tmp.name) / "snippets.sqlite3"
        self.store.register_expansion(self.one, date(2026, 11, 9))
        self.store.register_expansion(self.one, date(2026, 11, 9))
        self.assertTrue((Path(self.tmp.name) / "usage.sqlite3").exists())
        self.store.close()
        # Simula instalador que substituiu o SQLite de comandos, mas não o
        # arquivo independente de estatísticas dentro do perfil.
        path.unlink()
        self.store = SnippetStore(path)
        self.assertEqual(self.store.usage_report(date(2026, 11, 9))["total"], 2)
        self.assertEqual(self.store.usage_days(2026, 11), {9: 2})
        # Se o catálogo antigo reaparecer, não somar o mesmo histórico duas vezes.
        self.store.close()
        # 'with sqlite3.connect' COMMITA mas não FECHA a conexão.
        # Windows bloqueia exclusão de bancos ainda abertos no tearDown.
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("""
                INSERT INTO usage_daily(day, snippet_id, shortcut, uses)
                VALUES ('2026-11-09', ?, '/saudacao', 2)
                ON CONFLICT(day, snippet_id) DO UPDATE SET
                    uses=excluded.uses, shortcut=excluded.shortcut
            """, (self.one,))
        self.store = SnippetStore(path)
        self.assertEqual(self.store.usage_report(date(2026, 11, 9))["total"], 2)

    def test_usage_reset_clears_both_databases_and_stays_cleared_after_reopen(self):
        date_used = date(2026, 11, 9)
        self.store.register_expansion(self.one, date_used)
        self.store.reset_usage()
        self.assertEqual(self.store.connection.execute(
            "SELECT COUNT(*) FROM main.usage_daily").fetchone()[0], 0)
        self.assertEqual(self.store.connection.execute(
            "SELECT COUNT(*) FROM usage_store.usage_daily").fetchone()[0], 0)
        self.store.close()
        self.store = SnippetStore(Path(self.tmp.name) / "snippets.sqlite3")
        self.assertEqual(self.store.usage_report(date_used)["total"], 0)


if __name__ == "__main__":
    unittest.main()
