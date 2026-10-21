import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.core import SnippetStore, render_snippet, validate_shortcut
from app.hotkeys import ShortcutMatcher


class TemplateTests(unittest.TestCase):
    def test_date_and_clipboard(self):
        out = render_snippet("Em {{data}}, às {{hora}}: {{clipboard}}",
                             "copiado", datetime(2026, 10, 13, 14, 25))
        self.assertEqual(out.text, "Em 13/10/2026, às 14:25: copiado")

    def test_cursor_position(self):
        out = render_snippet("Olá {{cursor}} amigo!")
        self.assertEqual(out.text, "Olá  amigo!")
        self.assertEqual(out.left_moves, len(" amigo!"))

    def test_unsupported_variable_kept(self):
        self.assertEqual(render_snippet("{{xyz}} {{cursor}}").text, "{{xyz}} ")

    def test_shortcut_validation(self):
        for s in ("/oi", "/;", "/1"):
            validate_shortcut(s)
        for s in ("oi", "/", "/duas palavras", "/a/b"):
            with self.assertRaises(ValueError):
                validate_shortcut(s)


class ShortcutTests(unittest.TestCase):
    def test_matching_and_backspace(self):
        matcher = ShortcutMatcher(["/ola", "/chamado"])
        for ch in "/olah":
            result = matcher.feed(ch)
        self.assertIsNone(result)
        matcher.feed(None, "backspace")
        self.assertIsNone(matcher.feed("a"))
        matcher.clear()
        matches = [matcher.feed(c) for c in "teste /ola"]
        self.assertEqual(matches[-1], "/ola")

    def test_key_navigation_resets(self):
        matcher = ShortcutMatcher(["/oi"])
        for c in "/o":
            matcher.feed(c)
        matcher.feed(None, "left")
        self.assertIsNone(matcher.feed("i"))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = SnippetStore(Path(self.directory.name) / "data.sqlite3")

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_crud_and_uniqueness(self):
        folder = self.store.create_folder("Geral")
        ident = self.store.save(folder, "Oi", "/oi", "Primeiro")
        self.assertEqual(len(self.store.snippets()), 1)
        self.store.save(folder, "Oi 2", "/oi", "Segundo", ident)
        self.assertEqual(self.store.snippets()[0].content, "Segundo")
        with self.assertRaises(ValueError):
            self.store.save(folder, "Outro", "/OI", "dup")
        self.store.delete(ident)
        self.assertEqual(self.store.snippets(), [])

    def test_prefix_conflicts_in_both_directions_and_exact_match(self):
        folder = self.store.create_folder("HUBRASIL")
        other = self.store.create_folder("Outro setor")
        existing = self.store.save(folder, "CAD", "/2", "Texto inicial")
        cases = ("/2", "/23", "/234", "/2abc", "/2ABC")
        for candidate in cases:
            with self.subTest(candidate=candidate):
                conflict = self.store.shortcut_conflict(candidate)
                self.assertEqual(conflict.id, existing)
                self.assertEqual(conflict.shortcut, "/2")
                self.assertEqual(conflict.title, "CAD")
                self.assertEqual(conflict.folder, "HUBRASIL")
                with self.assertRaisesRegex(ValueError, "HUBRASIL"):
                    self.store.save(other, "Novo", candidate, "texto")
        self.assertIsNone(self.store.shortcut_conflict("/2", excluding_id=existing))
        self.store.save(folder, "CAD editado", "/2", "Conteúdo editado", existing)
        self.store.delete(existing)
        longer = self.store.save(other, "Longo", "/cadcolaborador", "Cadastro")
        for candidate in ("/cad", "/CAD", "/cadCol", "/CADCOLABORADOR"):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(ValueError, "/cadcolaborador"):
                    self.store.save(folder, "Novo", candidate, "Outro texto")
        self.assertIsNone(self.store.shortcut_conflict("/cadcolaborador", excluding_id=longer))
        self.assertIsNone(self.store.shortcut_conflict("/xyz"))
        self.store.save(folder, "Diferente", "/xyz", "Aceito")

    def test_shortcut_edit_rechecks_conflicts_and_is_atomic(self):
        folder = self.store.create_folder("Equipe")
        a = self.store.save(folder, "Mensagem curta", "/1", "Um")
        b = self.store.save(folder, "Outro", "/cadastro", "Dois")
        with self.assertRaises(ValueError):
            self.store.save(folder, "Alterado", "/10", "Nova mensagem", b)
        self.assertEqual(self.store.snippet_by_shortcut("/cadastro").id, b)
        self.assertEqual(self.store.snippet_by_shortcut("/cadastro").content, "Dois")
        self.assertEqual(self.store.snippet_by_shortcut("/1").id, a)
        # Após remover o atalho de prefixo, é permitido cadastrá-lo.
        self.store.delete(a)
        self.store.save(folder, "Alterado", "/10", "Nova mensagem", b)
        self.assertEqual(self.store.snippet_by_shortcut("/10").content, "Nova mensagem")

    def test_import_skips_ambiguous_shortcuts_and_does_not_create_unused_folder(self):
        folder = self.store.create_folder("Original")
        self.store.save(folder, "Existente", "/2", "Atendimento")
        backup = Path(self.directory.name) / "colliding-import.json"
        backup.write_text(json.dumps({
            "format": "AutoFillStudioBackup", "version": 1,
            "folders": ["Original"],
            "snippets": [
                {"folder": "Pasta ignorada", "title": "Duplicado", "shortcut": "/23", "content": "X"},
                {"folder": "Original", "title": "Novo", "shortcut": "/cad", "content": "Y"},
                {"folder": "Original", "title": "Sobreposto", "shortcut": "/cadcolaborador", "content": "Z"},
                {"folder": "Original", "title": "Seguro", "shortcut": "/ola", "content": "Olá"},
                {"folder": "Original", "title": "Duplicado 2", "shortcut": "/OLA", "content": "Outro"}
            ]
        }), encoding="utf-8")
        imported, skipped = self.store.import_json(backup)
        self.assertEqual((imported, skipped), (2, 3))
        self.assertEqual({x.shortcut for x in self.store.snippets()}, {"/2", "/cad", "/ola"})
        self.assertFalse(any(name == "Pasta ignorada" for _, name in self.store.folders()))
        self.assertEqual(self.store.snippet_by_shortcut("/2").content, "Atendimento")

    def test_existing_legacy_prefix_records_survive_migration(self):
        folder = self.store.create_folder("Legado")
        self.store.connection.execute(
            "INSERT INTO snippets(folder_id,title,shortcut,content) VALUES (?,?,?,?)",
            (folder, "Um", "/1", "Texto 1"))
        self.store.connection.execute(
            "INSERT INTO snippets(folder_id,title,shortcut,content) VALUES (?,?,?,?)",
            (folder, "Dez", "/10", "Texto 10"))
        self.store.connection.commit()
        self.assertEqual({s.shortcut for s in self.store.snippets()}, {"/1", "/10"})
        self.store.save(folder, "Separado", "/outro", "Texto diferente")
        self.assertEqual({s.shortcut for s in self.store.snippets()}, {"/1", "/10", "/outro"})
        with self.assertRaisesRegex(ValueError, "/1"):
            self.store.save(folder, "Novo", "/11", "Não permitido")

    def test_backup_roundtrip(self):
        folder = self.store.create_folder("Suporte")
        self.store.save(folder, "Atendimento", "/at", "Texto {{data}}")
        backup = Path(self.directory.name) / "backup.json"
        self.store.export_json(backup)
        self.assertEqual(json.loads(backup.read_text())["version"], 1)
        self.store.close()
        other = SnippetStore(Path(self.directory.name) / "other.sqlite3")
        imported, skipped = other.import_json(backup)
        self.assertEqual((imported, skipped), (1, 0))
        self.assertEqual(other.snippets()[0].shortcut, "/at")
        self.assertEqual(other.import_json(backup), (0, 1))
        other.close()
        self.store = SnippetStore(Path(self.directory.name) / "data.sqlite3")


if __name__ == "__main__":
    unittest.main()