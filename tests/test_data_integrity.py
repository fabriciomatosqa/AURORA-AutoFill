"""Regression tests for importing profiles and recovering backups safely."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from app import backups, preferences
from app.core import SnippetStore


class ProfileSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aurora-data-safety-")
        self.root = Path(self.temporary.name)
        self.database = self.root / "profile" / "snippets.sqlite3"
        self.store = SnippetStore(self.database)
        self.settings = self.database.with_name("settings.json")
        self.patches = [
            patch("app.backups.application_db_path", return_value=self.database),
            patch("app.backups.preferences_path", return_value=self.settings),
            patch("app.preferences.preferences_path", return_value=self.settings),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        self.store.close()
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def write_import(self, *, items, folders=None):
        source = self.root / "import.json"
        payload = {"format": "AutoFillStudioBackup", "version": 1,
                   "snippets": items, "folders": folders or []}
        source.write_text(json.dumps(payload), encoding="utf-8")
        return source

    def make_archive(self, script, settings=None):
        database = self.root / "fixture.sqlite3"
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(script)
        path = self.root / "fixture.aurora-backup.zip"
        with ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", json.dumps({
                "format": "AURORA-AutoFill-Backup", "version": 1}))
            archive.write(database, "snippets.sqlite3")
            if settings is not None:
                archive.writestr("settings.json", json.dumps(settings))
        return path

    def test_json_roundtrip_preserves_empty_folders_and_order(self):
        folder = self.store.create_folder("Trabalho")
        self.store.create_folder("Vazia")
        one = self.store.save(folder, "Um", "/um", "Texto 1", rich_content="<b>Texto 1</b>")
        two = self.store.save(folder, "Dois", "/dois", "Texto 2")
        three = self.store.save(folder, "Três", "/tres", "Texto 3")
        self.store.reorder_snippets(None, [one, three, two])
        path = self.root / "export.json"
        self.store.export_json(path)
        other = SnippetStore(self.root / "other.sqlite3")
        try:
            self.assertEqual(other.import_json(path), (3, 0))
            self.assertEqual({name for _, name in other.folders()}, {"Trabalho", "Vazia"})
            self.assertEqual([item.shortcut for item in other.snippets()], ["/um", "/tres", "/dois"])
            self.assertEqual(other.snippets()[0].rich_content, "<b>Texto 1</b>")
        finally:
            other.close()

    def test_json_merge_preserves_existing_order_and_trims_folder_names(self):
        folder = self.store.create_folder("Trabalho")
        first = self.store.save(folder, "Existente", "/existe", "ABC")
        path = self.write_import(items=[
            {"folder": " Trabalho ", "title": "Novo 1", "shortcut": "/n1", "content": "DEF"},
            {"folder": "Trabalho", "title": "Novo 2", "shortcut": "/n2", "content": "GHI"},
        ])
        self.assertEqual(self.store.import_json(path), (2, 0))
        self.assertEqual([item.shortcut for item in self.store.snippets()], ["/existe", "/n1", "/n2"])
        self.assertEqual(self.store.folders(), [(folder, "Trabalho")])
        self.assertEqual(self.store.snippets()[0].id, first)

    def test_malformed_import_items_are_skipped_without_crashing_or_empty_folders(self):
        path = self.write_import(items=[
            {"folder": "Inválida", "title": 123, "shortcut": "/x", "content": "A"},
            {"folder": "Inválida", "title": "A", "shortcut": 123, "content": "A"},
            {"folder": "Inválida", "title": "A", "shortcut": "/x", "content": []},
            {"folder": "Inválida", "title": "A", "shortcut": "sem-barra", "content": "A"},
            {"folder": "Válida", "title": "OK", "shortcut": "/ok", "content": "ABC"},
        ])
        self.assertEqual(self.store.import_json(path), (1, 4))
        self.assertEqual([name for _, name in self.store.folders()], ["Válida"])

    def test_invalid_folder_list_does_not_import_partial_data(self):
        path = self.write_import(items=[], folders=["Boa", 123])
        with self.assertRaises(ValueError):
            self.store.import_json(path)
        self.assertFalse(self.store.folders())

    def test_failed_export_keeps_previous_backup_intact(self):
        path = self.root / "export.json"
        path.write_bytes(b"previous-backup")
        with patch("app.core.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                self.store.export_json(path)
        self.assertEqual(path.read_bytes(), b"previous-backup")
        self.assertFalse(list(self.root.glob(".aurora-export-*")))

    def test_saving_deleted_command_does_not_report_success(self):
        folder = self.store.create_folder("Trabalho")
        snippet = self.store.save(folder, "A", "/a", "ABC")
        self.store.delete(snippet)
        with self.assertRaisesRegex(ValueError, "não existe mais"):
            self.store.save(folder, "A", "/a", "DEF", snippet)

    def test_undo_recovers_command_after_its_folder_disappears(self):
        folder = self.store.create_folder("Origem")
        item = self.store.save(folder, "A", "/a", "Preservar")
        snapshot = self.store.delete_with_undo(item)
        self.store.delete_folder(folder)
        self.store.restore_deleted_snippet(snapshot)
        self.assertEqual(self.store.snippets()[0].content, "Preservar")
        self.assertEqual(dict(self.store.folders())[folder], "Origem")

    def test_json_preserves_distinct_accented_folder_names(self):
        for name, shortcut in (("Área", "/a"), ("área", "/b")):
            folder = self.store.create_folder(name)
            self.store.save(folder, name, shortcut, name)
        path = self.root / "accents.json"
        self.store.export_json(path)
        other = SnippetStore(self.root / "accents.sqlite3")
        try:
            self.assertEqual(other.import_json(path), (2, 0))
            self.assertEqual({name for _, name in other.folders()}, {"Área", "área"})
            self.assertEqual(len({item.folder_id for item in other.snippets()}), 2)
        finally:
            other.close()

    def test_wrong_rich_content_type_is_rejected_before_restore(self):
        archived = self.make_archive("""
            CREATE TABLE folders(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE snippets(id INTEGER PRIMARY KEY, folder_id INTEGER,
                title TEXT, shortcut TEXT, content TEXT, created_at TEXT, updated_at TEXT,
                rich_content BLOB, sort_order INTEGER);
            INSERT INTO folders VALUES (1, 'Pasta');
            INSERT INTO snippets VALUES (1, 1, 'Título', '/a', 'Texto', '', '', x'FF', 0);
        """)
        with self.assertRaisesRegex(ValueError, "formatação"):
            backups.read_backup(archived)

    def test_backup_with_incompatible_folders_is_rejected_before_restore(self):
        folder = self.store.create_folder("Atual")
        self.store.save(folder, "Atual", "/atual", "Preservar")
        archived = self.make_archive("""
            CREATE TABLE folders(id INTEGER PRIMARY KEY);
            CREATE TABLE snippets(id INTEGER PRIMARY KEY, folder_id INTEGER,
                title TEXT, shortcut TEXT, content TEXT, created_at TEXT, updated_at TEXT);
        """)
        with self.assertRaisesRegex(ValueError, "Estrutura"):
            backups.restore_backup(self.store, archived)
        self.assertEqual(self.store.snippets()[0].content, "Preservar")
        self.assertFalse(list(self.database.parent.glob(".aurora-restore-*")))

    def test_backup_without_foreign_key_constraint_cannot_hide_orphans(self):
        archived = self.make_archive("""
            CREATE TABLE folders(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE snippets(id INTEGER PRIMARY KEY, folder_id INTEGER,
                title TEXT, shortcut TEXT, content TEXT, created_at TEXT, updated_at TEXT);
            INSERT INTO snippets VALUES (1, 99, 'Título', '/a', 'Texto', '', '');
        """)
        with self.assertRaisesRegex(ValueError, "sem pasta"):
            backups.read_backup(archived)

    def test_legacy_backup_is_migrated_before_replacing_live_database(self):
        archived = self.make_archive("""
            CREATE TABLE folders(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE);
            CREATE TABLE snippets(id INTEGER PRIMARY KEY,
                folder_id INTEGER NOT NULL REFERENCES folders(id), title TEXT NOT NULL,
                shortcut TEXT NOT NULL UNIQUE COLLATE NOCASE, content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO folders VALUES (1, 'Antiga');
            INSERT INTO snippets(id, folder_id, title, shortcut, content)
                VALUES (1, 1, 'Mensagem', '/msg', 'Olá');
        """)
        backups.restore_backup(self.store, archived)
        self.assertEqual(self.store.snippets()[0].rich_content, "")
        self.assertEqual(self.store.snippets()[0].content, "Olá")
        self.store.save(1, "Mensagem", "/msg", "Editada", 1)
        self.assertEqual(self.store.snippets()[0].content, "Editada")

    def test_settings_failure_rolls_back_restored_database(self):
        folder = self.store.create_folder("Trabalho")
        item = self.store.save(folder, "Modelo", "/msg", "Antes")
        preferences.save_preferences({"sound_volume": 20})
        archived = backups.create_backup(self.store)
        self.store.save(folder, "Modelo", "/msg", "Atual", item)
        with patch("app.preferences.save_preferences", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                backups.restore_backup(self.store, archived)
        self.assertEqual(self.store.snippets()[0].content, "Atual")

    def test_preferences_use_the_same_validation_for_saving_and_loading(self):
        preferences.save_preferences({"sound_enabled": "false", "sound_volume": "invalid",
                                      "check_updates": 0})
        self.assertEqual(preferences.load_preferences(), preferences.DEFAULTS)

    def test_prerelease_channel_is_persisted_as_an_explicit_choice(self):
        for choice in (False, True):
            preferences.save_preferences({"include_prereleases": choice})
            self.assertIs(preferences.load_preferences()["include_prereleases"], choice)

    def test_startup_registry_failure_does_not_prevent_opening_the_app(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock
        registry = SimpleNamespace(HKEY_CURRENT_USER=1, KEY_READ=1,
                                   OpenKey=Mock(side_effect=PermissionError("Policy")))
        with patch.dict(sys.modules, {"winreg": registry}), \
             patch("app.preferences.windows_startup_supported", return_value=True):
            self.assertFalse(preferences.windows_startup_enabled())


if __name__ == "__main__":
    unittest.main()
