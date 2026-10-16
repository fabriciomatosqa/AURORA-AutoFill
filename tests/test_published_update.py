"""Allow GitHub's public release cache to settle without false build failures."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aurora_published_check", ROOT / "packaging/check_published_update.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class PublishedUpdateTests(unittest.TestCase):
    def test_old_public_listing_is_retried_then_both_downloads_are_verified(self):
        version = "0.6.1-dev.21.1"
        fresh = SimpleNamespace(version=version)
        stale = SimpleNamespace(version="0.6.1-dev.20.1")
        calls = []
        def download(release, folder):
            self.assertIs(release, fresh)
            path = folder / "verified-installer"
            path.write_bytes(b"synthetic")
            calls.append(path)
            return path
        with patch.object(check, "latest_release", side_effect=[None, stale, fresh, fresh]), \
             patch.object(check, "download_verified_installer", side_effect=download), \
             patch.object(check.time, "sleep") as sleep, patch("builtins.print"):
            check.verify_public_update(version)
        self.assertEqual(len(calls), 2)
        self.assertGreater(sum(call.args[0] for call in sleep.call_args_list), 4)
        self.assertTrue(all(not path.exists() for path in calls))

    def test_missing_release_still_fails_with_bounded_wait(self):
        with patch.object(check, "latest_release", return_value=None), \
             patch.object(check, "download_verified_installer") as download, \
             patch.object(check.time, "sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "ainda não está disponível"):
                check.verify_public_update("0.6.1-dev.21.1")
        download.assert_not_called()
        self.assertLessEqual(sum(call.args[0] for call in sleep.call_args_list), 120)
