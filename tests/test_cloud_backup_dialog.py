"""Smoke de interface da opção de backup sem abrir navegador nem tocar em dados."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.cloud_backups import CloudBackupError
from app.cloud_backup_dialog import CloudBackupDialog, CloudBackupWorker
from app.cloud_brand import provider_pixmap
from app.preferences import DEFAULTS
from app.settings_panel import SettingsPage


class CloudBackupUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _dispose(widget):
        # Delete native Qt widgets while QApplication is still alive.
        # Windows Qt can crash on interpreter shutdown if a deferred dialog
        # (with nested signal connections) outlives QApplication.
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_settings_button_is_explicit_opt_in(self):
        page = SettingsPage(dict(DEFAULTS), startup_supported=False,
                            startup_enabled=False)
        try:
            emitted = []
            page.cloud_backup_requested.connect(lambda: emitted.append(True))
            self.assertEqual(emitted, [])
            self.assertEqual(page.cloud_backup_button.text(),
                             "Gerenciar backup em nuvem")
            self.assertEqual(set(page.cloud_provider_chips), {"google", "onedrive"})
            for chip in page.cloud_provider_chips.values():
                self.assertTrue(chip.isWidgetType())
            page.cloud_backup_button.click()
            self.assertEqual(emitted, [True])
        finally:
            self._dispose(page)

    def test_missing_oauth_configuration_disables_remote_actions(self):
        with patch.object(CloudBackupDialog, "_client",
                          side_effect=CloudBackupError("Credencial ausente")):
            dialog = CloudBackupDialog(store=None, restore_callback=lambda x: None)
            try:
                self.assertFalse(dialog.connect_button.isEnabled())
                self.assertFalse(dialog.upload_button.isEnabled())
                self.assertFalse(dialog.download_button.isEnabled())
                self.assertIn("ainda não está disponível", dialog.status_title.text())
                self.assertIn("Credencial ausente", dialog.technical_details.text())
                self.assertFalse(dialog.technical_details.isVisible())
                dialog.details_button.click()
                self.assertFalse(dialog.technical_details.isHidden())
            finally:
                self._dispose(dialog)

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
                self._dispose(dialog)

    def test_provider_cards_have_real_bundled_logos(self):
        for provider in ("google", "onedrive"):
            with self.subTest(provider=provider):
                logo = provider_pixmap(provider, 48)
                self.assertFalse(logo.isNull())
                self.assertEqual((logo.width(), logo.height()), (48, 48))

    def test_selection_switches_provider_without_touching_cloud_data(self):
        with patch.object(CloudBackupDialog, "_client") as getter:
            getter.return_value.connected.return_value = False
            dialog = CloudBackupDialog(store=None, restore_callback=lambda x: None)
            try:
                self.assertEqual(dialog._provider_id, "google")
                self.assertEqual(dialog.provider_cards["google"].property("selected"),
                                 "true")
                dialog.items.addItem("Cópia anterior")
                dialog._list_loaded = True
                dialog._select_provider("onedrive")
                self.assertEqual(dialog._provider_id, "onedrive")
                self.assertEqual(dialog.provider_cards["onedrive"].property("selected"),
                                 "true")
                self.assertEqual(dialog.provider_cards["google"].property("selected"),
                                 "false")
                self.assertEqual(dialog.items.count(), 0)
                self.assertFalse(dialog._list_loaded)
                self.assertFalse(dialog.upload_button.isEnabled())
            finally:
                self._dispose(dialog)

    def test_provider_can_be_selected_by_keyboard(self):
        with patch.object(CloudBackupDialog, "_client") as getter:
            getter.return_value.connected.return_value = False
            dialog = CloudBackupDialog(store=None, restore_callback=lambda x: None)
            try:
                # Direct key dispatch avoids creating a native Windows top-level
                # window solely for this test.
                card = dialog.provider_cards["onedrive"]
                card.setFocus()
                QTest.keyClick(card, Qt.Key_Return)
                self.assertEqual(dialog._provider_id, "onedrive")
            finally:
                self._dispose(dialog)

    def test_empty_state_and_loaded_list_are_distinct(self):
        with patch.object(CloudBackupDialog, "_client") as getter:
            getter.return_value.connected.return_value = True
            dialog = CloudBackupDialog(store=None, restore_callback=lambda x: None)
            try:
                self.assertIn("Consulte", dialog.empty_title.text())
                dialog._list_loaded = True
                dialog._refresh_buttons()
                self.assertEqual(dialog.empty_title.text(), "Nenhum backup encontrado")
                dialog.items.addItem("Backup de testes")
                dialog._refresh_buttons()
                self.assertIs(dialog.backup_stack.currentWidget(), dialog.items)
            finally:
                self._dispose(dialog)

    def test_worker_catches_provider_errors_without_exposing_data(self):
        with patch("app.cloud_backup_dialog.CloudBackupClient") as factory:
            factory.side_effect = CloudBackupError("Não há autorização.")
            worker = CloudBackupWorker("google", "list")
            worker.run()
            self.assertIn("Não há autorização", worker.failure)
            self.assertIsNone(worker.result)

    def test_google_configuration_import_is_explicit_and_available_only_for_google(self):
        with patch.object(CloudBackupDialog, "_client") as getter, patch(
                "app.cloud_backup_dialog.QFileDialog.getOpenFileName",
                return_value=("synthetic-desktop.json", "")), patch(
                "app.cloud_backup_dialog.import_google_client_configuration") as imported, patch(
                "app.cloud_backup_dialog.QMessageBox.information"):
            getter.return_value.connected.return_value = False
            dialog = CloudBackupDialog(store=None, restore_callback=lambda x: None)
            try:
                imported.assert_not_called()
                self.assertFalse(dialog.configure_google_button.isHidden())
                dialog.configure_google_button.click()
                self.assertEqual(imported.call_count, 1)
                self.assertEqual(str(imported.call_args.args[0]), "synthetic-desktop.json")
                self.assertTrue(dialog.connect_button.isEnabled())
                dialog._select_provider("onedrive")
                self.assertTrue(dialog.configure_google_button.isHidden())
            finally:
                self._dispose(dialog)

    def test_cancelling_google_file_selection_does_not_modify_configuration(self):
        with patch.object(CloudBackupDialog, "_client") as getter, patch(
                "app.cloud_backup_dialog.QFileDialog.getOpenFileName", return_value=("", "")), patch(
                "app.cloud_backup_dialog.import_google_client_configuration") as imported:
            getter.return_value.connected.return_value = False
            dialog = CloudBackupDialog(store=None, restore_callback=lambda x: None)
            try:
                dialog.configure_google_button.click()
                imported.assert_not_called()
            finally:
                self._dispose(dialog)


if __name__ == "__main__":
    unittest.main()
