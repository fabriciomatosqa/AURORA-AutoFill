"""Version 0.6.0: data safety, audio preferences and release-update contracts."""
import io
import json
import os
import sqlite3
import tempfile
import unittest
import wave
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from app.core import SnippetStore
from app import backups, audio, preferences, updates
from app.version import APP_VERSION, BASE_VERSION


class DataSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aurora-v060-")
        self.root = Path(self.temporary.name)
        self.database = self.root / "AutoFillStudio" / "snippets.sqlite3"
        self.store = SnippetStore(self.database)
        self.backup_path = self.database.parent / "settings.json"
        self.original_patches = [
            patch("app.backups.application_db_path", return_value=self.database),
            patch("app.backups.preferences_path", return_value=self.backup_path),
            patch("app.preferences.preferences_path", return_value=self.backup_path),
        ]
        for item in self.original_patches:
            item.start()

    def tearDown(self):
        self.store.close()
        for item in reversed(self.original_patches):
            item.stop()
        self.temporary.cleanup()

    def test_folder_delete_can_be_undone_without_losing_snippets(self):
        main = self.store.create_folder("Meus atalhos")
        doomed = self.store.create_folder("Trabalho")
        one = self.store.save(doomed, "Modelo", "/trabalho", "Texto", rich_content="<b>Texto</b>")
        two = self.store.save(doomed, "Modelo 2", "/resposta2", "Outra resposta")
        count, target, deleted = self.store.delete_folder_with_undo(doomed)
        self.assertEqual((count, target), (2, "Meus atalhos"))
        self.assertTrue(all(item.folder_id == main for item in self.store.snippets()))
        self.store.restore_deleted_folder(deleted)
        self.assertEqual(dict(self.store.folders())[doomed], "Trabalho")
        self.assertEqual({item.id for item in self.store.snippets(doomed)}, {one, two})
        self.assertEqual(next(item.rich_content for item in self.store.snippets() if item.id == one),
                         "<b>Texto</b>")

    def test_delete_only_folder_and_undo_remove_temp_destination(self):
        only = self.store.create_folder("Meus atalhos")
        item = self.store.save(only, "Exemplo", "/s", "ABC")
        _, _, deleted = self.store.delete_folder_with_undo(only)
        self.assertEqual(self.store.folders()[0][1], "Sem pasta")
        self.store.restore_deleted_folder(deleted)
        self.assertEqual(self.store.folders(), [(only, "Meus atalhos")])
        self.assertEqual(self.store.snippets()[0].id, item)

    def test_delete_snippet_undo_restores_metadata(self):
        folder = self.store.create_folder("Trabalho")
        item = self.store.save(folder, "Mensagem", "/m", "A{{cursor}}B",
                               rich_content="<strong>ABC</strong>")
        snapshot = self.store.delete_with_undo(item)
        self.assertFalse(self.store.snippets())
        self.store.restore_deleted_snippet(snapshot)
        restored = self.store.snippets()[0]
        self.assertEqual((restored.id, restored.content, restored.rich_content),
                         (item, "A{{cursor}}B", "<strong>ABC</strong>"))

    def test_complete_backup_restores_all_folders_order_and_settings(self):
        a = self.store.create_folder("QA")
        b = self.store.create_folder("HU")
        first = self.store.save(a, "Primeiro", "/one", "Texto 1", rich_content="<b>1</b>")
        second = self.store.save(b, "Segundo", "/two", "Texto 2")
        self.store.reorder_snippets(None, [first, second])
        preferences.save_preferences({"sound_enabled": False, "sound_volume": 27,
                                      "check_updates": False})
        archived = backups.create_backup(self.store, reason="manual")
        self.assertTrue(archived.name.endswith(backups.BACKUP_SUFFIX))
        self.store.delete(first)
        self.store.delete_folder(b)
        preferences.save_preferences({"sound_enabled": True, "sound_volume": 80,
                                      "check_updates": True})
        backups.restore_backup(self.store, archived)
        self.assertEqual([x.shortcut for x in self.store.snippets()], ["/one", "/two"])
        self.assertEqual(set(dict(self.store.folders()).values()), {"QA", "HU"})
        self.assertEqual(self.store.snippets()[0].rich_content, "<b>1</b>")
        self.assertEqual(preferences.load_preferences()["sound_volume"], 27)
        self.assertFalse(preferences.load_preferences()["sound_enabled"])
        # Manual snapshots are never pruned during later automatic backups.
        for _ in range(6):
            backups.create_backup(self.store, reason="pre-update", keep=3)
        self.assertTrue(archived.exists())
        self.assertEqual(len(list(backups.backups_directory().glob(
            "aurora-pre-update-*" + backups.BACKUP_SUFFIX))), 3)


class PreferencesTests(unittest.TestCase):
    def test_preferences_save_and_read_and_validation(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "settings.json"
            self.assertEqual(preferences.load_preferences(config)["sound_volume"], 65)
            preferences.save_preferences({"sound_enabled": False, "sound_volume": 250,
                                          "check_updates": False}, config)
            restored = preferences.load_preferences(config)
            self.assertEqual(restored, {**preferences.DEFAULTS, "sound_enabled": False,
                                        "sound_volume": 100, "check_updates": False})
            config.write_text('{"sound_volume":"evil","sound_enabled":123}', encoding="utf-8")
            self.assertEqual(preferences.load_preferences(config)["sound_volume"], 65)
            self.assertTrue(preferences.load_preferences(config)["sound_enabled"])


class UpdateContractTests(unittest.TestCase):
    def test_semantic_comparison(self):
        self.assertTrue(APP_VERSION.startswith(BASE_VERSION))
        self.assertTrue(updates.is_newer("0.6.1", "0.6.0"))
        self.assertFalse(updates.is_newer("v0.5.9", "0.6.0"))
        with self.assertRaises(ValueError):
            updates.is_newer("latest")

    def test_checks_only_official_stable_releases(self):
        payload = {
            "tag_name": "v0.6.1", "html_url":
                "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases/tag/v0.6.1",
            "draft": False, "prerelease": False,
            "assets": [
                {"name": "AURORA-AutoFill-v0.6.1-Windows-Setup.exe",
                 "browser_download_url":
                  "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases/download/v0.6.1/AURORA-AutoFill-v0.6.1-Windows-Setup.exe"},
                {"name": "SHA256SUMS-Windows.txt",
                 "browser_download_url":
                  "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases/download/v0.6.1/SHA256SUMS-Windows.txt"},
            ],
        }
        with patch("app.updates._get", return_value=json.dumps(payload).encode()):
            release = updates.latest_release(include_prereleases=False, platform_name="win32")
        self.assertEqual(release.version, "0.6.1")
        self.assertTrue(release.installer_url.endswith(".exe"))
        payload["prerelease"] = True
        with patch("app.updates._get", return_value=json.dumps(payload).encode()):
            self.assertIsNone(updates.latest_release(include_prereleases=False, platform_name="win32"))

    def test_checksum_is_mandatory_before_offering_installer(self):
        filename = "AURORA-AutoFill-v9.0.0-Windows-Setup.exe"
        release = updates.StableRelease(
            "9.0.0", "v9.0.0", "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases/tag/v9.0.0",
            "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases/download/v9.0.0/" + filename,
            "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases/download/v9.0.0/SHA256SUMS-Windows.txt")
        content = b"MZ_AURORA_UNIT_TEST_ONLY"
        correct = sha256(content).hexdigest() + "  " + filename
        class Response(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.headers = {"Content-Length": str(len(data))}
        with tempfile.TemporaryDirectory() as root:
            with patch("app.updates._get", return_value=correct.encode()), \
                 patch("app.updates.urlopen", return_value=Response(content)):
                result = updates.download_verified_installer(release, Path(root))
            self.assertEqual(result.read_bytes(), content)
            with patch("app.updates._get", return_value=(("0"*64) + "  " + filename).encode()), \
                 patch("app.updates.urlopen", return_value=Response(content)), \
                 self.assertRaises(ValueError):
                updates.download_verified_installer(release, Path(root))
            self.assertFalse(Path(root, filename + ".part").exists())


class AudioTests(unittest.TestCase):
    def test_scaled_audio_preserves_wave_format(self):
        file = Path(__file__).resolve().parents[1] / "assets" / "command_click.wav"
        with wave.open(str(file), "rb") as sound:
            frames = sound.getnframes()
            expected_rate = sound.getframerate()
        with tempfile.TemporaryDirectory() as root:
            adjusted = audio.adjusted_sound(file, 30, Path(root))
            with wave.open(str(adjusted), "rb") as sound:
                self.assertEqual(sound.getnframes(), frames)
                self.assertEqual(sound.getframerate(), expected_rate)
                self.assertEqual(sound.getsampwidth(), 2)
            self.assertEqual(audio.adjusted_sound(file, 100, Path(root)), file)


if __name__ == "__main__":
    unittest.main()
