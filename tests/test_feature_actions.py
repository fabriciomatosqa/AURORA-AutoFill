"""User consent, backup-before-install and safe shutdown of update workers."""
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.features import AuroraFeaturesMixin, QMessageBox


class Harness(AuroraFeaturesMixin):
    def __init__(self):
        self._check_thread = None
        self._download_thread = None
        self._download_release = None
        self._download_progress = None
        self._exit_when_updates_done = False
        self._quitting = True
        self.settings_page = SimpleNamespace(check_button=Mock(), sound=Mock(), updates=Mock(),
                                             volume=Mock(), volume_label=Mock(), sample_button=Mock(),
                                             prereleases=Mock())
        self.preferences = {"sound_enabled": True, "sound_volume": 65, "check_updates": True,
                            "include_prereleases": True}
        self.store = Mock()
        self.status = Mock()
        self._confirm_change = Mock(return_value=True)
        self._exit_application = Mock()
        self._refresh_all = Mock()
        self._render_undo = Mock()
        self._show_welcome = Mock()
        self._undo_actions = []
        self.dirty = True

    def statusBar(self):
        return self.status


def release():
    return SimpleNamespace(version="99.0.0-dev.99.1", prerelease=True,
                           installer_url="https://github.com/installer.exe",
                           checksum_url="https://github.com/checksum.txt", installer_kind="exe")


class FeatureActionsTests(unittest.TestCase):
    def test_selected_release_channel_reaches_background_worker(self):
        window = Harness()
        window.preferences["include_prereleases"] = False
        with patch("app.features.ReleaseCheckThread") as worker:
            window._check_updates(manual=True)
        worker.assert_called_once_with(window, include_prereleases=False)
        worker.return_value.start.assert_called_once()

    def test_failed_preference_save_restores_audio_controls_and_value(self):
        window = Harness()
        with patch("app.features.save_preferences", side_effect=OSError("Disk full")), \
             patch("app.features.QMessageBox.warning"):
            window._change_preference("sound_enabled", False)
        self.assertTrue(window.preferences["sound_enabled"])
        window.settings_page.sound.setChecked.assert_called_once_with(True)
        window.settings_page.volume.setEnabled.assert_called_once_with(True)
        window.settings_page.sample_button.setEnabled.assert_called_once_with(True)

    def test_test_release_is_offered_and_download_requires_consent(self):
        window = Harness()
        window._download_update = Mock()
        candidate = release()
        with patch("app.features.sys.frozen", True, create=True), \
             patch("app.features.QMessageBox.question", return_value=QMessageBox.No) as question:
            window._handle_release(candidate, True)
        self.assertIn("de teste", question.call_args.args[2])
        window._download_update.assert_not_called()
        with patch("app.features.sys.frozen", True, create=True), \
             patch("app.features.QMessageBox.question", return_value=QMessageBox.Yes):
            window._handle_release(candidate, True)
        window._download_update.assert_called_once_with(candidate)

    def test_install_backup_is_completed_before_launch_and_backup_failure_blocks_launch(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                window = Harness()
                window._download_release = candidate = release()
                calls = []
                def backup(*args, **kwargs):
                    calls.append("backup")
                    if failure:
                        raise OSError("Disk full")
                    return Path("snapshot.aurora-backup.zip")
                def launch(*args):
                    self.assertEqual(args, (Path("installer.exe"), candidate))
                    calls.append("launch")
                with patch("app.features.QMessageBox.question", return_value=QMessageBox.Yes), \
                     patch("app.features.QMessageBox.warning"), \
                     patch("app.features.create_backup", side_effect=backup), \
                     patch("app.features.launch_installer", side_effect=launch):
                    window._installer_ready(Path("installer.exe"))
                self.assertEqual(calls, ["backup"] if failure else ["backup", "launch"])
                self.assertEqual(window._exit_application.call_count, 0 if failure else 1)

    def test_declining_install_keeps_app_open_without_creating_backup(self):
        window = Harness()
        window._download_release = release()
        with patch("app.features.QMessageBox.question", return_value=QMessageBox.No), \
             patch("app.features.create_backup") as backup, \
             patch("app.features.launch_installer") as launch:
            window._installer_ready(Path("installer.exe"))
        backup.assert_not_called()
        launch.assert_not_called()
        window._exit_application.assert_not_called()

    def test_quit_cancels_download_and_retains_threads_until_finished(self):
        window = Harness()
        check, download = Mock(), Mock()
        window._check_thread, window._download_thread = check, download
        self.assertFalse(window._prepare_updates_shutdown())
        self.assertFalse(window._quitting)
        check.requestInterruption.assert_called_once()
        download.request_cancel.assert_called_once()
        with patch("app.features.QTimer.singleShot") as timer:
            window._release_check_done()
            timer.assert_not_called()
            window._download_done()
            timer.assert_called_once_with(0, window._exit_application)
        self.assertTrue(window._prepare_updates_shutdown())
        check.deleteLater.assert_called_once()
        download.deleteLater.assert_called_once()

    def test_failed_undo_remains_available_to_retry(self):
        window = Harness()
        entry = {"kind": "snippet", "snapshot": {}, "expires": monotonic() + 10}
        window._undo_actions.append(entry)
        window.store.restore_deleted_snippet.side_effect = ValueError("Duplicate shortcut")
        with patch("app.features.QMessageBox.warning"):
            window._undo_last()
        self.assertEqual(window._undo_actions, [entry])
        window.store.restore_deleted_snippet.side_effect = None
        window._undo_last()
        self.assertEqual(window._undo_actions, [])

    def test_successful_restore_clears_old_undo_without_reopening_another_database(self):
        window = Harness()
        window._undo_actions = [{"old": True}]
        original_store = window.store
        with patch("app.features.QFileDialog.getOpenFileName", return_value=("backup.zip", "")), \
             patch("app.features.QMessageBox.question", return_value=QMessageBox.Yes), \
             patch("app.features.QMessageBox.information"), \
             patch("app.features.create_backup", return_value=Path("safety.zip")), \
             patch("app.features.restore_backup") as restore, \
             patch("app.features.load_preferences", return_value=window.preferences):
            window._restore_user_backup()
        restore.assert_called_once_with(original_store, Path("backup.zip"))
        self.assertIs(window.store, original_store)
        original_store.close.assert_not_called()
        self.assertEqual(window._undo_actions, [])
        self.assertIsNone(window.current_id)
        self.assertFalse(window.dirty)
