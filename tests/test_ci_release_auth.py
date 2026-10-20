"""Regression: authenticated CI metadata must never authenticate asset downloads."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))
from github_api_auth import authenticate_release_metadata
from app import updates


class CIGitHubTokenTests(unittest.TestCase):
    def setUp(self):
        self.mock_module = SimpleNamespace(_request=updates._request)

    def test_only_metadata_calls_send_ci_token(self):
        authenticate_release_metadata(self.mock_module, "ci-test-only")
        api = self.mock_module._request(
            "https://api.github.com/repos/fabriciomatosqa/AURORA-AutoFill/releases"
            "?per_page=100&page=1", json_response=True)
        self.assertEqual(api.get_header("Authorization"), "Bearer ci-test-only")
        self.assertNotIn("Authorization", api.headers)
        self.assertIn("Authorization", api.unredirected_hdrs)
        for target in (
            "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases/"
            "download/v0.6.1-201026.3/SHA256SUMS-Windows.txt",
            "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases/"
            "download/v0.6.1-201026.3/AURORA-AutoFill-v0.6.1-201026.3-Windows-Setup.exe"
        ):
            request = self.mock_module._request(target)
            self.assertIsNone(request.get_header("Authorization"))
        other = self.mock_module._request(
            "https://api.github.com/repos/fabriciomatosqa/AURORA-AutoFill/releases",
            json_response=False)
        self.assertIsNone(other.get_header("Authorization"))

    def test_no_token_matches_unchanged_public_updater(self):
        original = self.mock_module._request
        authenticate_release_metadata(self.mock_module, None)
        self.assertIs(self.mock_module._request, original)
        public = self.mock_module._request(
            "https://api.github.com/repos/fabriciomatosqa/AURORA-AutoFill/releases",
            json_response=True)
        self.assertIsNone(public.get_header("Authorization"))

    def test_repeated_configuration_is_idempotent(self):
        authenticate_release_metadata(self.mock_module, "ci-test-only")
        wrapped = self.mock_module._request
        authenticate_release_metadata(self.mock_module, "ci-test-only")
        self.assertIs(self.mock_module._request, wrapped)

    def test_token_does_not_bypass_url_allowlist(self):
        authenticate_release_metadata(self.mock_module, "ci-test-only")
        for address in (
            "https://example.org/repos/fabriciomatosqa/AURORA-AutoFill/releases",
            "http://api.github.com/repos/fabriciomatosqa/AURORA-AutoFill/releases",
            "https://api.github.com/repos/other/repo/releases",
        ):
            with self.subTest(address=address), self.assertRaises(ValueError):
                self.mock_module._request(address, json_response=True)

    def test_rejects_header_injection(self):
        for token in ("bad\r\nSecret: yes", "invalid\nheader"):
            with self.assertRaises(ValueError):
                authenticate_release_metadata(
                    SimpleNamespace(_request=updates._request), token)

    def test_only_ci_checker_enables_token_for_updaters(self):
        import importlib.util
        location = ROOT / "packaging" / "check_legacy_update.py"
        spec = importlib.util.spec_from_file_location("aurora_ci_legacy_auth", location)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, "load_legacy_updater",
                          return_value=SimpleNamespace(
                              is_newer=lambda *_: False,
                              _request=updates._request)) as load, \\
             patch.dict("os.environ", {"AURORA_CI_GITHUB_TOKEN": "ci-test-only"}):
            with self.assertRaisesRegex(ValueError, "não é mais recente"):
                module.verify_legacy_update("0.6.1-dev.21.1")
            self.assertEqual(
                load.return_value._request(
                    "https://api.github.com/repos/fabriciomatosqa/AURORA-AutoFill/releases",
                    json_response=True).get_header("Authorization"),
                "Bearer ci-test-only")


if __name__ == "__main__":
    unittest.main()
