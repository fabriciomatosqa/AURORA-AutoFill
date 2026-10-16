"""Exercise the updater that existing installations actually contain."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "aurora_legacy_check", ROOT / "packaging/check_legacy_update.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

BRIDGE_VERSION = "0.6.1-update.20261016"


class LegacyLoaderTests(unittest.TestCase):
    def test_loader_keeps_legacy_default_and_does_not_replace_app_modules(self):
        from app import version
        before = dict(sys.modules)
        legacy = check.load_legacy_updater()
        self.assertEqual(legacy.APP_VERSION, "0.6.1-dev.22.1")
        self.assertEqual(legacy.is_newer.__defaults__, ("0.6.1-dev.22.1",))
        self.assertIs(sys.modules["app.version"], version)
        self.assertFalse(any(name.startswith("_aurora_legacy_")
                             for name in set(sys.modules) - before.keys()))
        # Creating this dataclass also verifies that exec registered its module.
        release = legacy.Release(BRIDGE_VERSION, "v" + BRIDGE_VERSION,
                                 "https://github.com/example", None, None)
        self.assertEqual(release.version, BRIDGE_VERSION)

    def test_real_old_comparison_requires_bridge_for_numeric_date_version(self):
        legacy = check.load_legacy_updater()
        self.assertFalse(legacy.is_newer("0.6.1-161026"))
        self.assertTrue(legacy.is_newer(BRIDGE_VERSION))
        self.assertTrue(legacy.is_newer(BRIDGE_VERSION + ".2", BRIDGE_VERSION))

    def test_only_full_immutable_commit_is_accepted(self):
        for value in ("HEAD", "583ff46", "-option", "f" * 39, "g" * 40):
            with self.subTest(value=value), patch.object(check.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "SHA completo"):
                    check.load_legacy_updater(value)
                run.assert_not_called()


class LegacyPublicCheckTests(unittest.TestCase):
    def test_retries_stale_list_and_verifies_both_platforms_without_installing(self):
        fresh = SimpleNamespace(version=BRIDGE_VERSION)
        legacy = SimpleNamespace(
            is_newer=Mock(return_value=True),
            latest_release=Mock(side_effect=[None, SimpleNamespace(version="0.6.1-161026"),
                                            fresh, fresh]),
            download_verified_installer=Mock(), launch_installer=Mock())
        downloads = []
        def download(release, folder):
            self.assertIs(release, fresh)
            installer = folder / "verified-synthetic-installer"
            installer.write_bytes(b"synthetic")
            downloads.append(installer)
            return installer
        legacy.download_verified_installer.side_effect = download
        with patch.object(check, "load_legacy_updater", return_value=legacy) as load, \
             patch.object(check.time, "sleep") as sleep, patch("builtins.print") as output:
            check.verify_legacy_update(BRIDGE_VERSION, display_version="0.6.1-161026")
        load.assert_called_once_with(check.LEGACY_COMMIT)
        legacy.is_newer.assert_called_once_with(BRIDGE_VERSION)
        self.assertEqual([call.kwargs["platform_name"]
                          for call in legacy.latest_release.call_args_list],
                         ["win32", "win32", "win32", "linux"])
        self.assertTrue(all(call.kwargs["include_prereleases"]
                            for call in legacy.latest_release.call_args_list))
        self.assertEqual(len(downloads), 2)
        self.assertTrue(all(not path.exists() for path in downloads))
        self.assertEqual(sum(call.args[0] for call in sleep.call_args_list), 15)
        legacy.launch_installer.assert_not_called()
        self.assertIn("aplicativo v0.6.1-161026", output.call_args.args[0])

    def test_mismatched_newer_version_is_not_accepted_as_the_expected_bridge(self):
        legacy = SimpleNamespace(
            is_newer=Mock(return_value=True),
            latest_release=Mock(return_value=SimpleNamespace(version=BRIDGE_VERSION + ".2")),
            download_verified_installer=Mock())
        with patch.object(check, "load_legacy_updater", return_value=legacy), \
             patch.object(check.time, "sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "ainda não está disponível"):
                check.verify_legacy_update(BRIDGE_VERSION)
        legacy.download_verified_installer.assert_not_called()
        self.assertEqual(legacy.latest_release.call_count, 8)
        self.assertEqual(sum(call.args[0] for call in sleep.call_args_list), 110)

    def test_unreachable_version_fails_before_network_access(self):
        legacy = SimpleNamespace(is_newer=Mock(return_value=False), latest_release=Mock())
        with patch.object(check, "load_legacy_updater", return_value=legacy), \
             self.assertRaisesRegex(ValueError, "não é mais recente"):
            check.verify_legacy_update("0.6.1-161026")
        legacy.latest_release.assert_not_called()
