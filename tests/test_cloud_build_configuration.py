"""Distribution supplies Google registration; fresh PCs never import a JSON."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "aurora_cloud_configuration_build", ROOT / "packaging/build_cloud_configuration.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
CLIENT_ID = "synthetic-build.apps.googleusercontent.com"
CLIENT_SECRET = "synthetic-build-only-registration"


class CloudBuildConfigurationTests(unittest.TestCase):
    def test_release_build_includes_registration_bound_to_public_client_id(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "_cloud_oauth.py"
            builder.build_configuration(target, client_id=CLIENT_ID,
                                        secret=CLIENT_SECRET, event="push")
            namespace = {}
            exec(compile(target.read_text(encoding="utf-8"), str(target), "exec"), namespace)
            self.assertEqual(namespace["GOOGLE_CLIENT_ID"], CLIENT_ID)
            self.assertEqual(namespace["GOOGLE_CLIENT_SECRET"], CLIENT_SECRET)
            self.assertFalse(namespace["IS_TEST_CONFIGURATION"])

    def test_unconfigured_release_fails_and_removes_stale_generated_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "_cloud_oauth.py"
            for secret in ("", "bad\nsecret", None):
                with self.subTest(secret=secret):
                    target.write_text("stale configuration", encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "AURORA_GOOGLE_DESKTOP_CLIENT_SECRET"):
                        builder.build_configuration(target, client_id=CLIENT_ID,
                                                    secret=secret, event="push")
                    self.assertFalse(target.exists())

    def test_pr_build_ignores_real_registration_and_marks_fixture(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "_cloud_oauth.py"
            builder.build_configuration(target, client_id=CLIENT_ID,
                                        secret="must-not-be-used-in-pr", event="pull_request")
            contents = target.read_text(encoding="utf-8")
            self.assertNotIn("must-not-be-used-in-pr", contents)
            namespace = {}
            exec(compile(contents, str(target), "exec"), namespace)
            self.assertEqual(namespace["GOOGLE_CLIENT_SECRET"], builder.FIXTURE_SECRET)
            self.assertTrue(namespace["IS_TEST_CONFIGURATION"])

    def test_frozen_entry_point_validates_without_qt_or_local_configuration(self):
        import main
        registration = ModuleType("app._cloud_oauth")
        registration.GOOGLE_CLIENT_ID = CLIENT_ID
        registration.GOOGLE_CLIENT_SECRET = CLIENT_SECRET
        registration.IS_TEST_CONFIGURATION = False
        with patch.dict(sys.modules, {"app._cloud_oauth": registration}), patch.dict(
                os.environ, {"AURORA_CLOUD_CONFIG_SMOKE_TEST": "release",
                             "AURORA_GOOGLE_CLIENT_ID": CLIENT_ID}), patch(
                "app.cloud_backups._secret_store", side_effect=AssertionError("No local config")), patch(
                "PySide6.QtWidgets.QApplication", side_effect=AssertionError("No GUI")):
            self.assertEqual(main.main(), 0)



if __name__ == "__main__":
    unittest.main()
