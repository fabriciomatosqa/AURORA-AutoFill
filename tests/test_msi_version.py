"""Cross-platform MSI version and publication compatibility checks."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aurora_msi_version", ROOT / "packaging/windows/msi_version.py")
msi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(msi)


class MsiVersionTests(unittest.TestCase):
    def test_release_dates_are_ordered_and_windows_installer_uses_three_fields(self):
        versions = ["0.6.1-171026", "0.6.1-171026.2",
                    "0.6.1-171026.3", "0.6.1-171026.4",
                    "0.6.1-181026"]
        numbers = [tuple(int(p) for p in msi.msi_version(v).split(".")) for v in versions]
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(len(set(numbers)), len(versions))
        self.assertTrue(all(len(item) == 3 and item[2] <= 65535 for item in numbers))

    def test_stable_build_is_higher_than_prerelease_on_publication_day(self):
        dated = msi.msi_version("0.6.1-171026.2")
        stable = msi.msi_version("0.6.1", stable_date=date(2026, 10, 17))
        self.assertGreater(tuple(map(int, stable.split("."))),
                           tuple(map(int, dated.split("."))))

    def test_rejects_unordered_legacy_and_invalid_dates(self):
        for bad in ("0.6.1-dev.5", "0.6.1-321026", "0.6.1-update.20261317"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                msi.msi_version(bad)


if __name__ == "__main__":
    unittest.main()
