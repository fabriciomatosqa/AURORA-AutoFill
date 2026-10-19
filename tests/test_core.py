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


class FirstRunExamplesTests(unittest.TestCase):
    def test_new_installation_creates_only_four_examples_in_one_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snippets.sqlite3"
            store = SnippetStore(path)
            try:
                store.seed_if_empty()
                folders = store.folders()
                self.assertEqual(len(folders), 1)
                self.assertEqual(folders[0][1], "Conheça o AURORA")
                snippets = store.snippets()
                self.assertEqual(
                    {s.shortcut for s in snippets},
                    {"/bemvindo", "/tutorial", "/datahora", "/obrigado"},
                )
                self.assertTrue(all(s.folder_id == folders[0][0] for s in snippets))
                tutorial = next(s for s in snippets if s.shortcut == "/tutorial")
                self.assertIn("criar pastas", tutorial.content)
                self.assertIn("Conheça o AURORA", tutorial.content)
                date = next(s for s in snippets if s.shortcut == "/datahora")
                self.assertIn("{{data}}", date.content)
                self.assertIn("{{hora}}", date.content)
                preview = render_snippet(date.content, now=datetime(2026, 10, 19, 20, 44))
                self.assertIn("19/10/2026", preview.text)
                self.assertIn("20:44", preview.text)
                self.assertNotIn("{{data}}", preview.text)
                self.assertNotIn("{{hora}}", preview.text)
                store.seed_if_empty()
                self.assertEqual(len(store.snippets()), 4)
            finally:
                store.close()

    def test_existing_empty_database_is_not_populated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snippets.sqlite3"
            first = SnippetStore(path)
            first.close()
            reopened = SnippetStore(path)
            try:
                reopened.seed_if_empty()
                self.assertEqual(reopened.folders(), [])
                self.assertEqual(reopened.snippets(), [])
            finally:
                reopened.close()

    def test_custom_folder_prevents_examples(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SnippetStore(Path(directory) / "data.sqlite3")
            try:
                store.create_folder("Minhas mensagens")
                store.seed_if_empty()
                self.assertEqual(len(store.folders()), 1)
                self.assertEqual(store.snippets(), [])
            finally:
                store.close()

    def test_deleted_examples_do_not_return_after_restarting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snippets.sqlite3"
            store = SnippetStore(path)
            store.seed_if_empty()
            for snippet in store.snippets():
                store.delete(snippet.id)
            store.close()
            reopened = SnippetStore(path)
            try:
                reopened.seed_if_empty()
                self.assertEqual(reopened.snippets(), [])
                self.assertEqual(len(reopened.folders()), 1)
            finally:
                reopened.close()

    def test_existing_backed_up_data_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snippets.sqlite3"
            store = SnippetStore(path)
            store.create_folder("Pessoal")
            store.save(store.folders()[0][0], "Minha frase", "/frase", "Texto pessoal")
            store.close()
            reopened = SnippetStore(path)
            try:
                reopened.seed_if_empty()
                self.assertEqual([s.shortcut for s in reopened.snippets()], ["/frase"])
                self.assertEqual([name for _, name in reopened.folders()], ["Pessoal"])
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()