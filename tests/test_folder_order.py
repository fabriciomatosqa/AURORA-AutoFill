"""Regressões: excluir pastas sem perder snippets e manter a ordem após reiniciar."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core import SnippetStore


class FolderAndOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "snippets.sqlite3"
        self.store = SnippetStore(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def add(self, folder, suffix):
        return self.store.save(folder, "Modelo " + suffix, "/" + suffix, "Texto " + suffix)

    def ids(self, folder=None):
        return [snippet.id for snippet in self.store.snippets(folder)]

    def test_reorder_persists_across_database_reopen(self):
        folder = self.store.create_folder("Operações")
        one, two, three = [self.add(folder, suffix) for suffix in ("um", "dois", "tres")]
        self.assertEqual(self.ids(), [three, two, one])
        self.store.reorder_snippets(None, [one, three, two])
        self.assertEqual(self.ids(), [one, three, two])
        self.store.close()
        self.store = SnippetStore(self.path)
        self.assertEqual(self.ids(), [one, three, two])
        newer = self.add(folder, "quatro")
        self.assertEqual(self.ids(), [newer, one, three, two])

    def test_reorder_inside_folder_keeps_other_folders_untouched(self):
        alpha = self.store.create_folder("Alpha")
        beta = self.store.create_folder("Beta")
        a1 = self.add(alpha, "a1")
        b1 = self.add(beta, "b1")
        a2 = self.add(alpha, "a2")
        b2 = self.add(beta, "b2")
        self.store.reorder_snippets(alpha, [a1, a2])
        self.assertEqual(self.ids(alpha), [a1, a2])
        self.assertEqual(self.ids(beta), [b2, b1])
        self.assertEqual(set(self.ids()), {a1, a2, b1, b2})

    def test_invalid_reorder_does_not_change_database(self):
        alpha = self.store.create_folder("Alpha")
        beta = self.store.create_folder("Beta")
        a1 = self.add(alpha, "a1")
        a2 = self.add(alpha, "a2")
        b1 = self.add(beta, "b1")
        before = self.ids()
        for invalid in ([a1], [a1, a1], [a1, b1]):
            with self.subTest(order=invalid), self.assertRaises(ValueError):
                self.store.reorder_snippets(alpha, invalid)
            self.assertEqual(self.ids(), before)
        self.assertEqual(self.ids(alpha), [a2, a1])

    def test_delete_nonempty_folder_moves_snippets_without_data_loss(self):
        main = self.store.create_folder("Meus atalhos")
        doomed = self.store.create_folder("Temporária")
        snippet_id = self.add(doomed, "preservar")
        moved, destination = self.store.delete_folder(doomed)
        self.assertEqual((moved, destination), (1, "Meus atalhos"))
        self.assertNotIn(doomed, dict(self.store.folders()))
        saved = next(item for item in self.store.snippets() if item.id == snippet_id)
        self.assertEqual(saved.folder_id, main)
        self.assertEqual((saved.shortcut, saved.content), ("/preservar", "Texto preservar"))

    def test_delete_only_folder_creates_safe_destination(self):
        only = self.store.create_folder("Meus atalhos")
        snippet_id = self.add(only, "unico")
        count, destination = self.store.delete_folder(only)
        self.assertEqual((count, destination), (1, "Sem pasta"))
        self.assertEqual(len(self.store.folders()), 1)
        self.assertEqual(self.store.snippets()[0].id, snippet_id)
        self.assertEqual(self.store.folders()[0][1], "Sem pasta")

    def test_legacy_migration_keeps_original_id_desc_order(self):
        path = Path(self.temp.name) / "legacy.sqlite3"
        db = sqlite3.connect(path)
        db.executescript("""
            CREATE TABLE folders (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                  name TEXT NOT NULL UNIQUE COLLATE NOCASE);
            CREATE TABLE snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL REFERENCES folders(id),
                title TEXT NOT NULL, shortcut TEXT NOT NULL UNIQUE COLLATE NOCASE,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO folders(id, name) VALUES (1, 'Antiga');
            INSERT INTO snippets(folder_id, title, shortcut, content)
              VALUES (1, 'Primeiro', '/primeiro', 'AAA');
            INSERT INTO snippets(folder_id, title, shortcut, content)
              VALUES (1, 'Segundo', '/segundo', 'BBB');
        """)
        db.commit()
        db.close()
        migrated = SnippetStore(path)
        try:
            self.assertEqual([s.shortcut for s in migrated.snippets()], ["/segundo", "/primeiro"])
            self.assertIn("sort_order", [col[1] for col in
                          migrated.connection.execute("PRAGMA table_info(snippets)")])
            self.assertEqual(migrated.snippets()[0].content, "BBB")
        finally:
            migrated.close()


if __name__ == "__main__":
    unittest.main()
