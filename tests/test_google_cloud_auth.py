"""Desktop OAuth regressions: loopback callback, PKCE and protected client config."""
import base64
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

from app.cloud_backups import (
    CloudBackupClient, CloudBackupError, GOOGLE_CLIENT_SERVICE, GOOGLE_SCOPE,
    KEYRING_SERVICE, _call, import_google_client_configuration,
)

CLIENT_ID = "synthetic-desktop.apps.googleusercontent.com"
CLIENT_SECRET = "synthetic-desktop-client-secret"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleCloudAuthTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"AURORA_GOOGLE_CLIENT_ID": CLIENT_ID})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.passwords = {}
        self.vault = Mock()
        self.vault.get_password.side_effect = lambda service, key: self.passwords.get((service, key))
        self.vault.set_password.side_effect = lambda service, key, value: self.passwords.__setitem__((service, key), value)
        self.vault.delete_password.side_effect = lambda service, key: self.passwords.pop((service, key), None)
        self.vault_patch = patch("app.cloud_backups._secret_store", return_value=self.vault)
        self.vault_patch.start()
        self.addCleanup(self.vault_patch.stop)

    def import_document(self, document):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "desktop-client.json"
            source.write_text(json.dumps(document), encoding="utf-8")
            import_google_client_configuration(source)
            # The selected source is never copied or rewritten.
            self.assertEqual(json.loads(source.read_text(encoding="utf-8")), document)
            self.assertEqual(list(Path(directory).iterdir()), [source])

    def test_import_stores_only_matching_desktop_secret_in_separate_vault_entry(self):
        self.import_document({"installed": {
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            "token_uri": "https://untrusted.example/token",
            "auth_uri": "https://untrusted.example/auth",
        }, "refresh_token": "not-a-client-setting"})
        self.assertEqual(self.passwords, {(GOOGLE_CLIENT_SERVICE, CLIENT_ID): CLIENT_SECRET})
        self.assertEqual(CloudBackupClient("google")._oauth_urls()[1], TOKEN_URL)

    def test_rejects_web_clients_other_client_ids_and_invalid_documents(self):
        for document in (
            {"web": {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}},
            {"installed": {"client_id": "different-client", "client_secret": CLIENT_SECRET}},
            {"installed": {"client_id": CLIENT_ID}},
            {"installed": {"client_id": CLIENT_ID, "client_secret": ""}},
            {"installed": {"client_id": CLIENT_ID, "client_secret": "secret\nvalue"}},
            {"installed": []}, [], None,
        ):
            with self.subTest(document=document), self.assertRaises(CloudBackupError):
                self.import_document(document)
        self.assertEqual(self.passwords, {})

    def test_oversized_file_is_rejected_before_vault_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b"x" * (64 * 1024 + 1))
            with self.assertRaises(CloudBackupError):
                import_google_client_configuration(path)
        self.vault.set_password.assert_not_called()

    def test_vault_failure_does_not_echo_configuration_or_exception(self):
        self.vault.set_password.side_effect = RuntimeError(CLIENT_SECRET)
        with self.assertRaises(CloudBackupError) as failure:
            self.import_document({"installed": {
                "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}})
        self.assertNotIn(CLIENT_SECRET, str(failure.exception))

    def test_browser_callback_pkce_exchange_and_refresh_use_imported_configuration(self):
        self.import_document({"installed": {
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}})
        authorization = {}
        callbacks = []
        callback_failures = []

        def open_browser(url):
            authorization.update(parse_qs(urlparse(url).query))
            redirect = authorization["redirect_uri"][0]

            def deliver_callback():
                try:
                    # A wrong state must not terminate the pending authorization.
                    bad = redirect + "?" + urlencode({"state": "wrong", "code": "ignored"})
                    try:
                        with urlopen(bad, timeout=3):
                            raise AssertionError("Wrong state accepted")
                    except HTTPError as error:
                        self.assertEqual(error.code, 400)
                        error.close()
                    valid = redirect + "?" + urlencode({
                        "state": authorization["state"][0], "code": "synthetic-code"})
                    with urlopen(valid, timeout=3) as response:
                        self.assertEqual(response.status, 200)
                except Exception as exc:
                    callback_failures.append(exc)

            thread = Thread(target=deliver_callback, daemon=True)
            callbacks.append(thread)
            thread.start()
            return True

        requests = []

        def token_request(url, **kwargs):
            self.assertEqual(url, TOKEN_URL)
            fields = parse_qs(kwargs["body"].decode("ascii"))
            requests.append(fields)
            self.assertEqual(fields["client_id"], [CLIENT_ID])
            self.assertEqual(fields["client_secret"], [CLIENT_SECRET])
            self.assertEqual(kwargs["content_type"], "application/x-www-form-urlencoded")
            if fields["grant_type"] == ["authorization_code"]:
                self.assertEqual(fields["code"], ["synthetic-code"])
                self.assertEqual(fields["redirect_uri"], authorization["redirect_uri"])
                verifier = fields["code_verifier"][0]
                challenge = base64.urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
                self.assertEqual(authorization["code_challenge"], [challenge])
                return {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh"}
            self.assertEqual(fields["refresh_token"], ["synthetic-refresh"])
            return {"access_token": "refreshed-access", "refresh_token": "rotated-refresh"}

        client = CloudBackupClient("google")
        try:
            with patch("app.cloud_backups.webbrowser.open", side_effect=open_browser), patch(
                    "app.cloud_backups._json_call", side_effect=token_request):
                client.connect(timeout=5)
                self.assertTrue(client.connected())
                self.assertEqual(client._access_token(), "refreshed-access")
        finally:
            for thread in callbacks:
                thread.join(timeout=4)
                self.assertFalse(thread.is_alive())
        self.assertEqual(callback_failures, [])
        self.assertEqual(len(requests), 2)
        self.assertEqual(authorization["scope"], [GOOGLE_SCOPE])
        self.assertEqual(authorization["code_challenge_method"], ["S256"])
        self.assertNotIn("client_secret", authorization)
        self.assertEqual(self.passwords[(KEYRING_SERVICE + ":google", CLIENT_ID)], "rotated-refresh")
        self.assertEqual(self.passwords[(GOOGLE_CLIENT_SERVICE, CLIENT_ID)], CLIENT_SECRET)

    def test_client_secret_is_never_sent_to_microsoft(self):
        self.passwords[(GOOGLE_CLIENT_SERVICE, CLIENT_ID)] = CLIENT_SECRET
        with patch.dict(os.environ, {"AURORA_MICROSOFT_CLIENT_ID": "synthetic-ms-client"}):
            client = CloudBackupClient("onedrive")
        self.assertEqual(client._token_parameters(), {"client_id": "synthetic-ms-client"})

    def test_disconnect_removes_account_authorization_and_preserves_desktop_configuration(self):
        self.import_document({"installed": {
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}})
        self.passwords[(KEYRING_SERVICE + ":google", CLIENT_ID)] = "synthetic-refresh"
        client = CloudBackupClient("google")
        client.disconnect()
        self.assertFalse(client.connected())
        self.assertEqual(self.passwords[(GOOGLE_CLIENT_SERVICE, CLIENT_ID)], CLIENT_SECRET)

    def test_missing_secret_gives_actionable_error_instead_of_generic_http_400(self):
        error = HTTPError(TOKEN_URL, 400, "Bad Request", {}, BytesIO(json.dumps({
            "error": "invalid_request", "error_description": "client_secret is missing.",
            "access_token": "must-not-be-shown",
        }).encode("utf-8")))
        with patch("app.cloud_backups.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(CloudBackupError) as failure:
                _call(TOKEN_URL, method="POST", body=b"synthetic")
        self.assertIn("Configurar Google Drive", str(failure.exception))
        self.assertNotIn("must-not-be-shown", str(failure.exception))
        self.assertTrue(error.closed)

    def test_provider_error_text_is_not_exposed_and_invalid_json_is_safe(self):
        for body in (
            b'{"error":"invalid_grant","error_description":"private-token-value"}',
            b'{"error":"unknown","error_description":"private-token-value"}',
            b'not-json private-token-value', b'x' * 9000,
        ):
            with self.subTest(body=body[:30]):
                error = HTTPError(TOKEN_URL, 400, "Bad Request", {}, BytesIO(body))
                with patch("app.cloud_backups.build_opener") as opener:
                    opener.return_value.open.side_effect = error
                    with self.assertRaises(CloudBackupError) as failure:
                        _call(TOKEN_URL, method="POST")
                self.assertNotIn("private-token-value", str(failure.exception))
                self.assertTrue(error.closed)


if __name__ == "__main__":
    unittest.main()
