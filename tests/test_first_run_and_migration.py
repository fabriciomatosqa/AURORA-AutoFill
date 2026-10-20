"""Instalação limpa, migração de perfil e regressões de dados da v0.6.1."""
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app import data_paths
from app.core import SnippetStore, application_db_path, render_snippet
from app.welcome import initial_snippets
from app.formatting import has_rich_formatting


class FirstRunTests(unittest.TestCase):
    def test_only_four_welcome_shortcuts_and_rich_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SnippetStore(Path(tmp) / "db.sqlite3")
            try:
                store.seed_if_empty()
                folders = store.folders()
                self.assertEqual(len(folders), 1)
                self.assertEqual(folders[0][1], "Conheça o AURORA")
                items = store.snippets()
                self.assertEqual({s.shortcut for s in items},
                                 {"/bemvindo", "/tutorial", "/datahora", "/obrigado"})
                self.assertTrue(all(s.folder_id == folders[0][0] for s in items))
                self.assertTrue(all(s.rich_content and has_rich_formatting(s.rich_content)
                                    for s in items))
                tutorial = next(s for s in items if s.shortcut == "/tutorial")
                self.assertIn("criar pastas", tutorial.content)
                self.assertIn("Conheça o AURORA", tutorial.content)
                now = datetime(2026, 10, 19, 20, 44)
                date = next(s for s in items if s.shortcut == "/datahora")
                self.assertIn("{{data}}", date.content)
                self.assertIn("{{hora}}", date.content)
                output = render_snippet(date.content, now=now).text
                self.assertIn("19/10/2026", output)
                self.assertIn("20:44", output)
                self.assertNotIn("{{hora}}", output)
                store.seed_if_empty()
                self.assertEqual(len(store.snippets()), 4)
            finally:
                store.close()

    def test_existing_empty_database_is_never_reseeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "db.sqlite3"
            old = SnippetStore(path)
            old.close()
            reopened = SnippetStore(path)
            try:
                reopened.seed_if_empty()
                self.assertEqual(reopened.folders(), [])
                self.assertEqual(reopened.snippets(), [])
            finally:
                reopened.close()

    def test_deleted_welcome_shortcuts_are_not_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "db.sqlite3"
            store = SnippetStore(path)
            store.seed_if_empty()
            for entry in store.snippets():
                store.delete(entry.id)
            store.close()
            again = SnippetStore(path)
            try:
                again.seed_if_empty()
                self.assertEqual(again.snippets(), [])
            finally:
                again.close()

    def test_backup_or_custom_profile_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "db.sqlite3"
            store = SnippetStore(path)
            folder = store.create_folder("Pessoal")
            store.save(folder, "Minha mensagem", "/minha", "Preservar meus textos")
            store.close()
            again = SnippetStore(path)
            try:
                again.seed_if_empty()
                self.assertEqual([(s.shortcut, s.content) for s in again.snippets()],
                                 [("/minha", "Preservar meus textos")])
                self.assertEqual(again.folders()[0][1], "Pessoal")
            finally:
                again.close()


class DataDirectoryTests(unittest.TestCase):
    def test_existing_profile_moves_entire_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "AutoFillStudio"
            old.mkdir()
            store = SnippetStore(old / "snippets.sqlite3")
            folder = store.create_folder("Pessoal")
            store.save(folder, "Minha mensagem", "/eu", "Texto guardado")
            store.close()
            (old / "settings.json").write_text('{"sound_volume": 55}', encoding="utf-8")
            (old / "backups").mkdir()
            (old / "backups" / "backup.aurora-backup.zip").write_bytes(b"preserve")
            with patch("app.data_paths._profile_root", return_value=root):
                target = application_db_path()
                self.assertEqual(target, root / "AuroraAutoFill" / "snippets.sqlite3")
                self.assertFalse(old.exists())
                self.assertEqual((target.parent / "settings.json").read_text(encoding="utf-8"),
                                 '{"sound_volume": 55}')
                self.assertEqual((target.parent / "backups" / "backup.aurora-backup.zip").read_bytes(),
                                 b"preserve")
                migrated = SnippetStore(target)
                try:
                    migrated.seed_if_empty()
                    self.assertEqual([s.shortcut for s in migrated.snippets()], ["/eu"])
                finally:
                    migrated.close()

    def test_if_both_directories_exist_neither_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, target = root / "AutoFillStudio", root / "AuroraAutoFill"
            old.mkdir()
            target.mkdir()
            (old / "old.txt").write_text("original", encoding="utf-8")
            (target / "new.txt").write_text("new", encoding="utf-8")
            with patch("app.data_paths._profile_root", return_value=root):
                self.assertEqual(data_paths.application_data_dir(), target)
            self.assertEqual((old / "old.txt").read_text(encoding="utf-8"), "original")
            self.assertEqual((target / "new.txt").read_text(encoding="utf-8"), "new")

    def test_failed_migration_must_not_start_empty_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "AutoFillStudio"
            old.mkdir()
            (old / "snippets.sqlite3").write_bytes(b"existing data")
            with patch("app.data_paths._profile_root", return_value=root), \
                 patch.object(Path, "rename", side_effect=OSError("locked")):
                with self.assertRaisesRegex(OSError, "Não foi possível migrar"):
                    application_db_path()
            self.assertTrue((old / "snippets.sqlite3").is_file())
            self.assertFalse((root / "AuroraAutoFill").exists())


if __name__ == "__main__":
    unittest.main()
