"""Updater contracts use synthetic network responses; no installers are executed."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
import io
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from app import updates


VERSION = "9.7.1-dev.12.1"
BASE = "https://github.com/fabriciomatosqa/AURORA-AutoFill/releases"
CONTENT = b"MZ-synthetic-installer-DO-NOT-EXECUTE"


def payload(version=VERSION, *, system="Windows", prerelease=True):
    tag = "v" + version
    filename = (f"AURORA-AutoFill-v{version}-Windows-Setup.exe" if system == "Windows"
                else f"AURORA-AutoFill-v{version}-Linux-amd64.deb")
    return {
        "tag_name": tag, "html_url": f"{BASE}/tag/{tag}",
        "draft": False, "prerelease": prerelease,
        "assets": [
            {"name": filename, "browser_download_url": f"{BASE}/download/{tag}/{filename}",
             "size": len(CONTENT), "digest": "sha256:" + sha256(CONTENT).hexdigest()},
            {"name": f"SHA256SUMS-{system}.txt", "browser_download_url":
             f"{BASE}/download/{tag}/SHA256SUMS-{system}.txt"}]}


def release(*, system="Windows"):
    return updates._release_from_payload(
        payload(system=system), include_prereleases=True,
        platform_name="win32" if system == "Windows" else "linux", machine="amd64")


class Response(io.BytesIO):
    def __init__(self, content=CONTENT, *, length="auto"):
        super().__init__(content)
        self.headers = {} if length is None else {
            "Content-Length": str(len(content)) if length == "auto" else length}


class VersionTests(unittest.TestCase):
    def test_semver_ordering_including_dev_builds_and_stable_promotion(self):
        ordered = ["0.6.0", "0.6.1-dev.2.1", "0.6.1-dev.2.2", "0.6.1-dev.10.1",
                   "0.6.1-rc.1", "0.6.1", "0.6.2-dev.1.1", "1.0.0"]
        for older, newer in zip(ordered, ordered[1:]):
            self.assertTrue(updates.is_newer(newer, older), (newer, older))
            self.assertFalse(updates.is_newer(older, newer), (older, newer))
        self.assertFalse(updates.is_newer("v0.6.1-dev.10.1+sha.a", "0.6.1-dev.10.1+sha.b"))

    def test_invalid_tags_are_rejected(self):
        for value in ("latest", "1.2", "1.2.3.4", "1.2.3-dev.01", "01.2.3",
                      "1.2.3-", "1.2.3/evil", "1.2.3\n", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                updates.is_newer(value)


class DiscoveryTests(unittest.TestCase):
    def check(self, records, **kwargs):
        with patch("app.updates._get", return_value=json.dumps(records).encode()) as get:
            found = updates.latest_release(platform_name="win32", **kwargs)
        self.assertIn("/releases?per_page=100", get.call_args.args[0])
        self.assertNotIn("/latest", get.call_args.args[0])
        return found

    def test_offers_tests_before_any_stable_release_exists(self):
        found = self.check([payload()])
        self.assertEqual(found.version, VERSION)
        self.assertTrue(found.prerelease)
        self.assertEqual(found.installer_kind, "exe")

    def test_version_sort_does_not_depend_on_github_publication_order(self):
        found = self.check([payload("0.6.1-dev.2.1"), payload("0.6.1-dev.11.1"),
                            payload("0.6.0", prerelease=False)])
        self.assertEqual(found.version, "0.6.1-dev.11.1")

    def test_stable_channel_filters_both_flag_and_version_suffix(self):
        found = self.check([payload(), payload("9.7.0", prerelease=False),
                            payload("10.0.0-dev.1", prerelease=False)], include_prereleases=False)
        self.assertEqual(found.version, "9.7.0")

    def test_drafts_unknown_tags_and_foreign_pages_are_skipped(self):
        draft = payload("10.0.0")
        draft["draft"] = True
        foreign = payload("11.0.0")
        foreign["html_url"] = foreign["html_url"].replace("fabriciomatosqa/", "someone/")
        invalid = payload("12.0.0")
        invalid["tag_name"] = "nightly"
        self.assertIsNone(self.check([draft, foreign, invalid]))

    def test_linux_selects_verified_deb_and_never_wrong_architecture(self):
        data = payload(system="Linux")
        with patch("app.updates._get", return_value=json.dumps([data]).encode()):
            found = updates.latest_release(platform_name="linux", machine="x86_64")
            unsupported = updates.latest_release(platform_name="linux", machine="arm64")
        self.assertTrue(found.installer_name.endswith("-Linux-amd64.deb"))
        self.assertEqual(found.installer_kind, "deb")
        self.assertIsNone(unsupported)

    def test_asset_origin_and_tag_must_match(self):
        for source in ("https://evil.example/installer.exe",
                       f"{BASE}/download/v9.7.0/installer.exe"):
            data = payload()
            data["assets"][0]["browser_download_url"] = source
            self.assertIsNone(self.check([data]))

    def test_newer_release_without_complete_assets_does_not_hide_ready_update(self):
        incomplete = payload("10.0.0")
        incomplete["assets"] = []
        self.assertEqual(self.check([incomplete, payload()]).version, VERSION)

    def test_pagination_is_bounded_and_newest_can_be_on_next_page(self):
        first = [payload("0.6.0", prerelease=False)] * 100
        with patch("app.updates._get", side_effect=[json.dumps(first).encode(),
                   json.dumps([payload()]).encode()]) as get:
            self.assertEqual(updates.latest_release().version, VERSION)
        self.assertEqual(get.call_count, 2)
        with patch("app.updates._get", return_value=json.dumps(first).encode()) as get:
            updates.latest_release()
        self.assertEqual(get.call_count, updates.MAX_RELEASE_PAGES)

    def test_empty_repo_and_github_rate_limit_have_clear_results(self):
        for code in (404, 403):
            error = HTTPError("url", code, "", {}, None)
            try:
                with patch("app.updates._get", side_effect=error):
                    if code == 404:
                        self.assertIsNone(updates.latest_release())
                    else:
                        with self.assertRaisesRegex(ValueError, "limitou"):
                            updates.latest_release()
            finally:
                error.close()


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.release = release()
        self.manifest = (sha256(CONTENT).hexdigest() + "  " +
                         self.release.installer_name).encode()
        updates._verified_downloads.clear()

    def download(self, response=None, *, manifest=None, item=None, **kwargs):
        with patch("app.updates._get", return_value=manifest or self.manifest), \
             patch("app.updates.urlopen", return_value=response or Response()):
            return updates.download_verified_installer(
                item or self.release, self.directory, **kwargs)

    def test_complete_download_reaches_100_only_after_verification(self):
        progress = []
        result = self.download(progress=progress.append)
        self.assertEqual(result.read_bytes(), CONTENT)
        self.assertEqual(progress[0], 0)
        self.assertEqual(progress[-1], 100)
        self.assertNotIn(100, progress[:-1])
        self.assertFalse(list(self.directory.glob("*.part")))

    def test_missing_checksum_or_conflicting_api_digest_blocks_download(self):
        for manifest in (b"", b"0" * 64 + b"  " + self.release.installer_name.encode(),
                         self.manifest + b"\n" + self.manifest):
            with self.subTest(manifest=manifest):
                with patch("app.updates._get", return_value=manifest), \
                     patch("app.updates.urlopen") as opened, self.assertRaises(ValueError):
                    updates.download_verified_installer(self.release, self.directory)
                opened.assert_not_called()

    def test_digest_mismatch_and_incomplete_size_remove_partial_files(self):
        for response in (Response(b"corrupted", length=str(len(CONTENT))),
                         Response(CONTENT[:-1], length=str(len(CONTENT))),
                         Response(CONTENT, length="invalid")):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.download(response)
            self.assertEqual(list(self.directory.iterdir()), [])

    def test_content_hash_without_api_digest_still_requires_manifest(self):
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.download(Response(b"x" * len(CONTENT)), item=replace(self.release, sha256=None))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_cancellation_works_without_content_length(self):
        checks = iter([False, False, False, True])
        with self.assertRaisesRegex(ValueError, "cancelado"):
            self.download(Response(length=None), cancelled=lambda: next(checks, True))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_size_limits_and_declared_size_mismatch_are_rejected(self):
        for response in (Response(length=str(updates.MAX_INSTALLER_BYTES + 1)),
                         Response(length="0"), Response(length="1")):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.download(response)
        with self.assertRaises(ValueError):
            self.download(item=replace(self.release, size=updates.MAX_INSTALLER_BYTES + 1))

    def test_foreign_url_or_checksum_tag_never_reaches_network(self):
        for item in (replace(self.release, installer_url="https://evil.example/installer.exe"),
                     replace(self.release, checksum_url=self.release.checksum_url.replace(
                         "/v" + VERSION + "/", "/v9.0.0/")),
                     replace(self.release, installer_name="../installer.exe")):
            with patch("app.updates.urlopen") as opened, self.assertRaises(ValueError):
                updates.download_verified_installer(item, self.directory)
            opened.assert_not_called()

    def test_launcher_rehashes_without_network_and_detects_late_modification(self):
        path = self.download()
        with patch("app.updates.sys.platform", "win32"), \
             patch("app.updates.subprocess.Popen") as launch, \
             patch("app.updates._get") as network:
            updates.launch_installer(path, self.release)
            self.assertEqual(launch.call_args.args[0], [str(path.resolve()), "/NORESTART"])
            network.assert_not_called()
            path.write_bytes(b"tampered after download")
            launch.reset_mock()
            with self.assertRaisesRegex(ValueError, "modificado"):
                updates.launch_installer(path, self.release)
            launch.assert_not_called()

    def test_launcher_requires_an_in_memory_verified_receipt(self):
        path = self.directory / self.release.installer_name
        path.write_bytes(CONTENT)
        with patch("app.updates._get") as network, self.assertRaisesRegex(ValueError, "novamente"):
            updates.launch_installer(path, self.release)
        network.assert_not_called()

    def test_linux_hands_deb_to_desktop_without_privilege_commands(self):
        item = release(system="Linux")
        manifest = (sha256(CONTENT).hexdigest() + "  " + item.installer_name).encode()
        path = self.download(item=item, manifest=manifest)
        with patch("app.updates.sys.platform", "linux"), \
             patch("app.updates.shutil.which", return_value="/usr/bin/xdg-open"), \
             patch("app.updates.subprocess.Popen") as launch:
            updates.launch_installer(path, item)
        self.assertEqual(launch.call_args.args[0], ["/usr/bin/xdg-open", str(path.resolve())])


class TransportTests(unittest.TestCase):
    def test_redirects_are_restricted_to_https_github_storage(self):
        handler = updates._GitHubRedirects()
        request = Request(f"{BASE}/download/v1.0.0/installer.exe")
        for destination in ("http://github.com/file", "https://evil.example/file",
                            "https://github.com@evil.example/file"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "", {}, destination)
        redirect = handler.redirect_request(request, None, 302, "", {},
                                            "https://release-assets.githubusercontent.com/file?signature=test")
        self.assertEqual(redirect.host, "release-assets.githubusercontent.com")

    def test_metadata_responses_obey_size_limit(self):
        with patch("app.updates.urlopen", return_value=Response(b"12345")):
            with self.assertRaisesRegex(ValueError, "maior"):
                updates._get(updates.GITHUB_RELEASES_API, max_bytes=4)


if __name__ == "__main__":
    unittest.main()
