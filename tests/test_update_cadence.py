"""Regressões do aviso de atualização e relógio de uptime."""
import ctypes
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.update_cadence import (UpdateCadence, computer_uptime_seconds,
                               SIX_HOURS, THREE_HOURS)
from app.features import AuroraFeaturesMixin


class UptimeSchedulerTests(unittest.TestCase):
    def test_six_hour_boundaries_come_from_computer_boot_not_app_start(self):
        # A aplicação iniciou 5h58 após ligar o computador.
        scheduler = UpdateCadence(5 * 3600 + 58 * 60)
        self.assertEqual(scheduler.next_regular, SIX_HOURS)
        self.assertFalse(scheduler.should_check(SIX_HOURS - 1))
        self.assertTrue(scheduler.should_check(SIX_HOURS))
        self.assertFalse(scheduler.should_check(SIX_HOURS + 1))
        self.assertTrue(scheduler.should_check(2 * SIX_HOURS))

    def test_multiple_missed_windows_trigger_one_check_only(self):
        scheduler = UpdateCadence(120)
        self.assertTrue(scheduler.should_check(48 * 3600))
        self.assertFalse(scheduler.should_check(48 * 3600 + 1))
        self.assertEqual(scheduler.next_regular, 54 * 3600)

    def test_no_snoozes_exact_version_for_three_hours_of_pc_uptime(self):
        scheduler = UpdateCadence(100)
        scheduler.decline('0.6.1-xxx', 200)
        self.assertFalse(scheduler.should_notify('0.6.1-xxx', 200 + THREE_HOURS - 1))
        self.assertTrue(scheduler.should_notify('outra-versao', 200 + 1))
        self.assertFalse(scheduler.should_check(200 + THREE_HOURS - 1))
        self.assertTrue(scheduler.should_check(200 + THREE_HOURS))
        self.assertTrue(scheduler.should_notify('0.6.1-xxx', 200 + THREE_HOURS))
        self.assertFalse(scheduler.should_check(200 + THREE_HOURS + 1))

    def test_periodic_check_does_not_break_snooze(self):
        scheduler = UpdateCadence(0)
        scheduler.decline('v1', SIX_HOURS - 100)
        self.assertTrue(scheduler.should_check(SIX_HOURS))
        self.assertFalse(scheduler.should_notify('v1', SIX_HOURS))
        self.assertTrue(scheduler.should_check(SIX_HOURS - 100 + THREE_HOURS))
        self.assertTrue(scheduler.should_notify('v1', SIX_HOURS - 100 + THREE_HOURS))

    def test_yes_clears_snooze(self):
        scheduler = UpdateCadence(5)
        scheduler.decline('v1', 10)
        scheduler.accept()
        self.assertIsNone(scheduler.snoozed_until)
        self.assertFalse(scheduler.should_check(11))

    def test_windows_uses_64_bit_system_uptime(self):
        kernel32 = SimpleNamespace(GetTickCount64=Mock(return_value=9_876_543_210))
        with patch('app.update_cadence.sys.platform', 'win32'), \
             patch.object(ctypes, 'windll', SimpleNamespace(kernel32=kernel32), create=True):
            self.assertAlmostEqual(computer_uptime_seconds(), 9_876_543.210)
        self.assertIs(kernel32.GetTickCount64.restype, ctypes.c_ulonglong)


class FeatureSchedulerHarness(AuroraFeaturesMixin):
    def __init__(self):
        self.preferences = {'check_updates': True, 'include_prereleases': True}
        self._update_cadence = UpdateCadence(60)
        self._check_thread = None
        self._download_thread = None
        self._exit_when_updates_done = False
        self._available_update_release = None
        self._update_notice = None
        self._check_updates = Mock()
        self._display_update_notice = Mock()
        self._download_update = Mock()
        self.status = Mock()

    def statusBar(self):
        return self.status


class FeatureScheduleIntegrationTests(unittest.TestCase):
    def test_startup_always_checks_when_opted_in(self):
        window = FeatureSchedulerHarness()
        with patch('app.features.computer_uptime_seconds', return_value=123):
            window._initial_release_check()
        window._check_updates.assert_called_once_with(manual=False)

    def test_periodic_check_runs_only_on_six_hour_uptime(self):
        window = FeatureSchedulerHarness()
        with patch('app.features.computer_uptime_seconds', return_value=SIX_HOURS-1):
            window._periodic_update_check()
        window._check_updates.assert_not_called()
        with patch('app.features.computer_uptime_seconds', return_value=SIX_HOURS):
            window._periodic_update_check()
            window._periodic_update_check()
        window._check_updates.assert_called_once_with(manual=False)

    def test_snooze_suppresses_alert_even_when_regular_check_finds_release(self):
        window = FeatureSchedulerHarness()
        candidate = SimpleNamespace(version='99.0.0')
        window._update_cadence.decline(candidate.version, 100)
        with patch('app.features.computer_uptime_seconds', return_value=200):
            window._handle_release(candidate, False)
        window._display_update_notice.assert_not_called()
        with patch('app.features.computer_uptime_seconds', return_value=100 + THREE_HOURS):
            window._handle_release(candidate, False)
        window._display_update_notice.assert_called_once_with(candidate)

    def test_no_means_retry_and_yes_starts_verified_download(self):
        window = FeatureSchedulerHarness()
        candidate = SimpleNamespace(version='99.0.0', page_url='https://github.com/',
                                    installer_url='https://github.com/installer',
                                    checksum_url='https://github.com/checksum')
        window._available_update_release = candidate
        with patch('app.features.computer_uptime_seconds', return_value=1000):
            window._decline_update_notice()
        self.assertEqual(window._update_cadence.snoozed_until, 1000 + THREE_HOURS)
        window._available_update_release = candidate
        with patch('app.features.sys.frozen', True, create=True), \
             patch('app.features.is_newer', return_value=True):
            window._accept_update_notice()
        window._download_update.assert_called_once_with(candidate)
        self.assertIsNone(window._update_cadence.snoozed_until)


class NoticeWidgetTests(unittest.TestCase):
    def test_popup_has_two_working_buttons_and_displays_version(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from app.update_notice import UpdateNotice
        app = QApplication.instance() or QApplication([])
        type(self)._application = app
        notice = UpdateNotice()
        clicked = []
        notice.accepted.connect(lambda: clicked.append('sim'))
        notice.declined.connect(lambda: clicked.append('nao'))
        try:
            notice.display('0.6.1-221026.1', '0.6.1-211026.5')
            self.assertIn('221026', notice.versions.text())
            self.assertEqual(notice.yes_button.text(), 'Sim')
            self.assertEqual(notice.no_button.text(), 'Não')
            notice.no_button.click()
            self.assertEqual(clicked, ['nao'])
            notice.display('0.6.1-221026.1', '0.6.1-211026.5')
            notice.yes_button.click()
            self.assertEqual(clicked, ['nao', 'sim'])
        finally:
            notice.close()
            notice.deleteLater()
        app.processEvents()


if __name__ == '__main__':
    unittest.main()
