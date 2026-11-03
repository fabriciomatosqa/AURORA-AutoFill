"""Smoke de interface da opção de backup sem abrir navegador nem tocar em dados."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.cloud_backups import CloudBackupError
from app.cloud_backup_dialog import CloudBackupDialog, CloudBackupWorker
from app.preferences import DEFAULTS
from app.settings_panel import SettingsPage


class CloudBackupUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_settings_button_is_explicit_opt_in(self):
        page = SettingsPage(dict(DEFAULTS), startup_supported=False,
                            startup_enabled=False)
        try:
            emitted = []
            page.cloud_backup_requested.connect(lambda: emitted.append(True))
            self.assertEqual(emitted, [])
            self.assertEqual(page.cloud_backup_button.text(),
                             "Backup em nuvem — Google / OneDrive")
            page.cloud_backup_button.click()
            self.assertEqual(emitted, [True])
        finally:
            page.close()

    def test_missing_oauth_configuration_disables_remote_actions(self):
        with patch.object(CloudBackupDialog, "_client",
                          side_effect=CloudBackupError("Credencial ausente")):
            dialog = CloudBackupDialog(store=None, restore_callback=lambda x: None)
            try:
                self.assertFalse(dialog.connect_button.isEnabled())
                self.assertFalse(dialog.upload_button.isEnabled())
                self.assertFalse(dialog.download_button.isEnabled())
                self.assertIn("Credencial ausente", dialog.status.text())
            finally:
                dialog.close()

    def test_dialog_does_not_create_a_backup_just_by_opening(self):
        with patch("app.cloud_backup_dialog.create_backup") as created, patch.object(
                CloudBackupDialog, "_client") as getter:
            getter.return_value.connected.return_value = False
            dialog = CloudBackupDialog(store=object(),
                                       restore_callback=lambda x: None)
            try:
                self.assertFalse(dialog.upload_button.isEnabled())
                created.assert_not_called()
            finally:
                dialog.close()

    def test_worker_catches_provider_errors_without_exposing_data(self):
        with patch("app.cloud_backup_dialog.CloudBackupClient") as factory:
            factory.side_effect = CloudBackupError("Não há autorização.")
            worker = CloudBackupWorker("google", "list")
            worker.run()
            self.assertIn("Não há autorização", worker.failure)
            self.assertIsNone(worker.result)


if __name__ == "__main__":
    unittest.main()
