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


if __name__ == "__main__":
    unittest.main()