"""Offline regression tests for GitHub 504 recovery and safe manual fallback."""
from io import BytesIO
from urllib.error import HTTPError, URLError
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import updates
from app.features import AuroraFeaturesMixin
from app.version import GITHUB_RELEASES_URL

API_URL = updates.GITHUB_RELEASES_API + "?per_page=50&page=1"
VERSION = "0.6.1-061126.2"
BASE = "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases"


def _gateway(code=504):
    return HTTPError(API_URL, code, "Gateway Time-out", {}, None)


def _metadata(version=VERSION):
    tag = "v" + version
    filename = f"AURORA-AutoFill-v{version}-Windows-Setup.exe"
    return [{
        "tag_name": tag, "prerelease": True, "draft": False,
        "html_url": f"{BASE}/tag/{tag}",
        "assets": [
            {"name": filename, "state": "uploaded", "size": 123456,
             "browser_download_url": f"{BASE}/download/{tag}/{filename}"},
            {"name": "SHA256SUMS-Windows.txt", "state": "uploaded",
             "browser_download_url": f"{BASE}/download/{tag}/SHA256SUMS-Windows.txt"}
        ]
    }]


class TransientGithubTests(unittest.TestCase):
    def test_retry_504_then_success_without_extra_downloads(self):
        raw = b'[{"ok": true}]'
        with patch("app.updates.urlopen",
                   side_effect=[_gateway(), BytesIO(raw)]) as opening, \
             patch("app.updates.time.sleep") as pause:
            result = updates._get(API_URL)
        self.assertEqual(result, raw)
        self.assertEqual(opening.call_count, 2)
        self.assertEqual(pause.call_count, 1)
        for call in opening.call_args_list:
            self.assertEqual(call.args[0].full_url, API_URL)

    def test_bounded_504_retries_produce_actionable_error(self):
        with patch("app.updates.urlopen", side_effect=_gateway()) as opening, \
             patch("app.updates.time.sleep") as pause:
            with self.assertRaisesRegex(updates.GitHubUnavailable, "HTTP 504"):
                updates._get(API_URL)
        self.assertEqual(opening.call_count, updates.REQUEST_RETRIES)
        self.assertEqual(pause.call_count, updates.REQUEST_RETRIES - 1)

    def test_timeout_retries_but_rate_limit_does_not(self):
        with patch("app.updates.urlopen",
                   side_effect=[URLError("timed out"), BytesIO(b"ok")]) as opening, \
             patch("app.updates.time.sleep") as pause:
            self.assertEqual(updates._get(API_URL), b"ok")
        self.assertEqual(opening.call_count, 2)
        self.assertEqual(pause.call_count, 1)
        with patch("app.updates.urlopen", side_effect=_gateway(403)) as opening, \
             patch("app.updates.time.sleep") as pause, self.assertRaises(HTTPError):
            updates._get(API_URL)
        opening.assert_called_once()
        pause.assert_not_called()

    def test_untrusted_urls_and_oversized_data_are_never_retried(self):
        with patch("app.updates.urlopen") as opening, \
             patch("app.updates.time.sleep") as pause:
            with self.assertRaises(ValueError):
                updates._get("https://untrusted.example/releases")
            opening.assert_not_called()
            pause.assert_not_called()
        with patch("app.updates.urlopen", return_value=BytesIO(b"x" * 101)) as opening, \
             patch("app.updates.time.sleep") as pause, self.assertRaisesRegex(
                    ValueError, "maior que o permitido"):
            updates._get(API_URL, max_bytes=100)
        opening.assert_called_once()
        pause.assert_not_called()

    def test_fallback_to_small_pages_after_repeated_gateway_errors(self):
        data = json.dumps(_metadata()).encode()
        with patch("app.updates._get", side_effect=[
                updates.GitHubUnavailable("HTTP 504"), data]) as get:
            latest = updates.latest_release(platform_name="win32", machine="amd64")
        self.assertEqual(latest.version, VERSION)
        self.assertIn(f"per_page={updates.RELEASE_PAGE_SIZE}", get.call_args_list[0].args[0])
        self.assertIn(f"per_page={updates.FALLBACK_PAGE_SIZE}", get.call_args_list[1].args[0])
        self.assertEqual(get.call_count, 2)
        self.assertTrue(latest.checksum_url.startswith(BASE))

    def test_repeated_error_across_both_page_sizes_propagates(self):
        with patch("app.updates._get",
                   side_effect=updates.GitHubUnavailable("HTTP 504")) as get, \
             self.assertRaisesRegex(updates.GitHubUnavailable, "HTTP 504"):
            updates.latest_release(platform_name="win32")
        self.assertEqual(get.call_count, 2)


class ManualRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.window = SimpleNamespace(
            _exit_when_updates_done=False,
            statusBar=lambda: SimpleNamespace(showMessage=Mock()))

    def test_manual_error_offers_browser_link_only_after_click(self):
        with patch("app.features.QMessageBox") as message_class, \
             patch("app.features.webbrowser.open") as browse:
            dialog = message_class.return_value
            open_button, close_button = object(), object()
            dialog.addButton.side_effect = [open_button, close_button]
            dialog.clickedButton.return_value = open_button
            AuroraFeaturesMixin._update_error(
                self.window, "O GitHub está temporariamente indisponível (HTTP 504).",
                manual=True)
            browse.assert_called_once_with(GITHUB_RELEASES_URL)
            self.assertIn("HTTP 504", message_class.call_args.args[2])
            dialog.setEscapeButton.assert_called_once_with(close_button)

    def test_dismissal_and_background_error_do_not_open_browser(self):
        with patch("app.features.QMessageBox") as message_class, \
             patch("app.features.webbrowser.open") as browse:
            dialog = message_class.return_value
            open_button, close_button = object(), object()
            dialog.addButton.side_effect = [open_button, close_button]
            dialog.clickedButton.return_value = close_button
            AuroraFeaturesMixin._update_error(self.window, "HTTP 504", manual=True)
            browse.assert_not_called()
            message_class.reset_mock()
            AuroraFeaturesMixin._update_error(self.window, "HTTP 504", manual=False)
            message_class.assert_not_called()
            browse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
