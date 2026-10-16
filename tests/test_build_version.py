"""Keep prerelease identity consistent across both OS package formats."""
import importlib.util
from datetime import date
from pathlib import Path
import runpy
import tempfile
import unittest

from app.version import BASE_VERSION

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aurora_build_version", ROOT / "packaging/build_version.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildVersionTests(unittest.TestCase):
    def test_date_versions_and_stable_tags_match_source(self):
        self.assertEqual(build.build_version(build_date="161026"), f"{BASE_VERSION}-161026")
        self.assertEqual(build.build_version(build_date="011126"), f"{BASE_VERSION}-011126")
        self.assertEqual(build.build_version(tag=f"v{BASE_VERSION}"), BASE_VERSION)
        with self.assertRaises(ValueError):
            build.build_version(tag="v0.0.1")
        for stamp in ("3010260", "310226", "000000", "latest", "161026.2"):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                build.build_version(build_date=stamp)

    def test_same_day_revisions_and_retries_preserve_published_tags(self):
        version = f"{BASE_VERSION}-161026"
        tags = (f"{'a' * 40}\trefs/tags/v{version}\n"
                f"{'b' * 40}\trefs/tags/v{version}.2\n"
                f"{'c' * 40}\trefs/tags/v{BASE_VERSION}-update.20261016.2\n")
        self.assertEqual(build.build_version(build_date="161026", tags=tags,
                                             commit="d" * 40), version + ".3")
        self.assertEqual(build.build_version(build_date="161026", tags=tags,
                                             commit="b" * 40), version + ".2")

    def test_recorded_version_and_commit_are_exact_and_input_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "_build.py"
            version = build.build_version(build_date="161026")
            build.write_metadata(target, version, "a" * 40)
            metadata = runpy.run_path(str(target))
            self.assertEqual(metadata["BUILD_VERSION"], version)
            self.assertEqual(metadata["SOURCE_COMMIT"], "a" * 40)
            for invalid in ("latest", "0.5.0", BASE_VERSION + "-dev.8/evil",
                            BASE_VERSION + "-dev.8.1", BASE_VERSION + "-update.20261016"):
                with self.assertRaises(ValueError):
                    build.write_metadata(target, invalid)
            with self.assertRaises(ValueError):
                build.write_metadata(target, version, "not a commit")

    def test_linux_prerelease_uses_tilde_and_windows_numeric_file_version(self):
        # Execute version.py with a synthetic generated module, without changing
        # version metadata used by the rest of the test process.
        import sys
        import types
        from unittest.mock import patch
        generated = types.ModuleType("app._build")
        generated.BUILD_VERSION = BASE_VERSION + "-161026"
        generated.SOURCE_COMMIT = "f" * 40
        with patch.dict(sys.modules, {"app._build": generated}):
            version = {"__package__": "app", "__name__": "app.version_fixture"}
            source = ROOT / "app/version.py"
            exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), version)
        self.assertEqual(version["APP_VERSION"], generated.BUILD_VERSION)
        self.assertEqual(version["DEBIAN_VERSION"], BASE_VERSION + "~update.20261016")
        numeric = str((date(2026, 10, 16) - date(2000, 1, 1)).days)
        self.assertEqual(version["WINDOWS_VERSION"], BASE_VERSION + "." + numeric)
