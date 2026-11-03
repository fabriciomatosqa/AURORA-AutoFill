"""Regressões da integração opt-in, sem contas reais ou tráfego de rede."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cloud_backups import (
    BACKUP_SUFFIX, CloudBackupClient, CloudBackupError, RemoteBackup,
    _https, client_id_for, validate_download,
)


class CloudBackupTests(unittest.TestCase):
    def test_provider_ids_must_be_explicitly_configured(self):
        with patch.dict(os.environ, {"AURORA_GOOGLE_CLIENT_ID": "google-id"}):
            self.assertEqual(client_id_for("google"), "google-id")
        with self.assertRaises(CloudBackupError):
            client_id_for("invalid")

    def test_only_known_https_hosts_are_allowed(self):
        self.assertEqual(_https("https://graph.microsoft.com/v1.0/me",
                                {"graph.microsoft.com"}),
                         "https://graph.microsoft.com/v1.0/me")
        for address in ("http://graph.microsoft.com/",
                        "https://evil.com/",
                        "https://graph.microsoft.com@evil.com/a",
                        "file:///tmp/secret"):
            with self.subTest(url=address), self.assertRaises(CloudBackupError):
                _https(address, {"graph.microsoft.com"})

    def test_only_valid_backups_are_listed_for_google(self):
        with patch.dict(os.environ, {"AURORA_GOOGLE_CLIENT_ID": "public-id"}):
            client = CloudBackupClient("google")
        with patch.object(client, "_access_token", return_value="token"), patch(
                "app.cloud_backups._json_call", return_value={
                    "files": [
                        {"id": "1", "name": "aurora-cloud-20261103.aurora-backup.zip",
                         "size": "400", "modifiedTime": "2026-11-03T10:00:00Z"},
                        {"id": "2", "name": "other-file.txt", "size": "100"},
                    ],
                }) as request:
            backups = client.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertIsInstance(backups[0], RemoteBackup)
        self.assertEqual(backups[0].identifier, "1")
        self.assertEqual(backups[0].size, 400)
        self.assertIn("spaces=appDataFolder", request.call_args.args[0])

    def test_onedrive_upload_is_explicit_and_scoped_to_approot(self):
        with patch.dict(os.environ, {"AURORA_MICROSOFT_CLIENT_ID": "public-id"}):
            client = CloudBackupClient("onedrive")
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / ("test" + BACKUP_SUFFIX)
            archive.write_bytes(b"synthetic")
            with patch("app.cloud_backups.validate_download"), patch.object(
                    client, "_access_token", return_value="token"), patch.object(
                    client, "_app_root", return_value="fake-root"), patch(
                    "app.cloud_backups._json_call", return_value={"id": "remote"}) as request:
                filename = client.upload_backup(archive)
        self.assertTrue(filename.startswith("aurora-cloud-"))
        self.assertTrue(filename.endswith(BACKUP_SUFFIX))
        self.assertIn("/me/drive/items/fake-root:/", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["body"], b"synthetic")

    def test_google_upload_uses_appdatafolder_and_new_remote_file(self):
        with patch.dict(os.environ, {"AURORA_GOOGLE_CLIENT_ID": "public-id"}):
            client = CloudBackupClient("google")
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / ("test" + BACKUP_SUFFIX)
            archive.write_bytes(b"synthetic")
            with patch("app.cloud_backups.validate_download"), patch.object(
                    client, "_access_token", return_value="token"), patch(
                    "app.cloud_backups._call", return_value=(
                        b"", {"Location": "https://www.googleapis.com/upload/drive/v3/files?upload_id=x"},
                        200)) as initial, patch(
                    "app.cloud_backups._json_call", return_value={"id": "new"}) as upload:
                name = client.upload_backup(archive)
        self.assertTrue(name.startswith("aurora-cloud-"))
        self.assertIn(b"appDataFolder", initial.call_args.kwargs["body"])
        self.assertEqual(upload.call_args.kwargs["method"], "PUT")

    def test_download_requires_remote_listing_and_valid_zip(self):
        with patch.dict(os.environ, {"AURORA_GOOGLE_CLIENT_ID": "public-id"}):
            client = CloudBackupClient("google")
        with tempfile.TemporaryDirectory() as directory:
            backup = RemoteBackup("id-123", "aurora-cloud-20261103.aurora-backup.zip", 3)
            with patch.object(client, "list_backups", return_value=[backup]), patch.object(
                    client, "_access_token", return_value="token"), patch(
                    "app.cloud_backups._call", return_value=(b"zip", {}, 200)), patch(
                    "app.cloud_backups.validate_download"), patch(
                    "app.cloud_backups.backups_directory", return_value=Path(directory)):
                new_file = client.download_backup("id-123")
            self.assertTrue(new_file.is_file())
            self.assertEqual(new_file.read_bytes(), b"zip")
            self.assertEqual(len(list(Path(directory).glob("*"))), 1)

    def test_rejects_download_with_mismatched_size(self):
        with patch.dict(os.environ, {"AURORA_GOOGLE_CLIENT_ID": "public-id"}):
            client = CloudBackupClient("google")
        backup = RemoteBackup("id-123", "aurora-cloud-20261103.aurora-backup.zip", 99)
        with patch.object(client, "list_backups", return_value=[backup]), patch.object(
                client, "_access_token", return_value="token"), patch(
                "app.cloud_backups._call", return_value=(b"zip", {}, 200)):
            with self.assertRaises(CloudBackupError):
                client.download_backup("id-123")

    def test_restoration_validator_reuses_existing_safe_backup_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / ("fixture" + BACKUP_SUFFIX)
            extracted = Path(directory) / "extracted.sqlite3"
            source.write_bytes(b"fixture")
            extracted.write_bytes(b"synthetic")
            with patch("app.cloud_backups.read_backup", return_value=(
                    extracted, None)) as check:
                validate_download(source)
            check.assert_called_once()
            self.assertTrue(source.exists())
            self.assertFalse(extracted.exists())


if __name__ == "__main__":
    unittest.main()
