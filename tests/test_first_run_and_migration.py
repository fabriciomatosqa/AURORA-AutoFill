"""Instalação limpa e diretório exclusivo de dados da v0.6.1."""
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
    def test_creates_only_official_directory_on_first_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("app.data_paths._profile_root", return_value=root):
                target = application_db_path()
                self.assertEqual(target, root / "AuroraAutoFill" / "snippets.sqlite3")
                self.assertTrue(target.parent.is_dir())
                self.assertEqual(data_paths.application_data_dir(), target.parent)
                self.assertFalse((root / "AutoFillStudio").exists())

    def test_existing_legacy_directory_is_never_read_moved_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "AutoFillStudio"
            old.mkdir()
            store = SnippetStore(old / "snippets.sqlite3")
            folder = store.create_folder("Antiga")
            store.save(folder, "Mensagem", "/antigo", "Preservar sem acessar")
            store.close()
            original_db = (old / "snippets.sqlite3").read_bytes()
            (old / "settings.json").write_text('{"sound_volume": 50}', encoding="utf-8")
            (old / "backups").mkdir()
            (old / "backups" / "preservar.zip").write_bytes(b"backup")

            with patch("app.data_paths._profile_root", return_value=root), \
                 patch.object(Path, "rename", side_effect=AssertionError("Migração proibida")):
                target = application_db_path()
                self.assertEqual(target, root / "AuroraAutoFill" / "snippets.sqlite3")
                self.assertTrue(target.parent.is_dir())
                fresh = SnippetStore(target)
                try:
                    fresh.seed_if_empty()
                    self.assertEqual({s.shortcut for s in fresh.snippets()},
                                     {"/bemvindo", "/tutorial", "/datahora", "/obrigado"})
                finally:
                    fresh.close()

            self.assertEqual((old / "snippets.sqlite3").read_bytes(), original_db)
            self.assertEqual((old / "settings.json").read_text(encoding="utf-8"),
                             '{"sound_volume": 50}')
            self.assertEqual((old / "backups" / "preservar.zip").read_bytes(),
                             b"backup")

    def test_existing_new_directory_is_reused_without_resetting_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "AuroraAutoFill"
            target.mkdir()
            store = SnippetStore(target / "snippets.sqlite3")
            folder = store.create_folder("Pessoal")
            store.save(folder, "Mensagem", "/meu", "Conteúdo mantido")
            store.close()
            with patch("app.data_paths._profile_root", return_value=root):
                db = application_db_path()
                again = SnippetStore(db)
                try:
                    again.seed_if_empty()
                    self.assertEqual([(s.shortcut, s.content) for s in again.snippets()],
                                     [("/meu", "Conteúdo mantido")])
                finally:
                    again.close()

    def test_invalid_official_path_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            occupied = root / "AuroraAutoFill"
            occupied.write_bytes(b"nao substituir")
            with patch("app.data_paths._profile_root", return_value=root):
                with self.assertRaises(OSError):
                    application_db_path()
            self.assertEqual(occupied.read_bytes(), b"nao substituir")


if __name__ == "__main__":
    unittest.main()
