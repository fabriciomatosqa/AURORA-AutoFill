"""Public date names and migration aliases represent one chronological release."""
from datetime import date
import unittest

from app.versioning import (canonical_to_bridge, display_version,
                            parse_dated_version, parse_version, version_key)


class DateVersionTests(unittest.TestCase):
    def test_canonical_date_and_bridge_have_same_identity(self):
        expected = ((0, 6, 1), date(2026, 10, 16), 1)
        for value in ("0.6.1-161026", "v0.6.1-161026", "0.6.1-update.20261016"):
            with self.subTest(value=value):
                self.assertEqual(parse_dated_version(value), expected)
                self.assertEqual(display_version(value), "0.6.1-161026")
                self.assertEqual(version_key(value), version_key("0.6.1-161026"))
        self.assertEqual(canonical_to_bridge("v0.6.1-161026"),
                         "0.6.1-update.20261016")

    def test_day_zero_padding_and_leap_days_are_real_dates(self):
        for value, expected in (("0.6.1-010126", date(2026, 1, 1)),
                                ("0.6.1-290200", date(2000, 2, 29)),
                                ("0.6.1-update.20240229", date(2024, 2, 29))):
            with self.subTest(value=value):
                self.assertEqual(parse_dated_version(value)[1], expected)
        self.assertEqual(canonical_to_bridge("0.6.1-010126"),
                         "0.6.1-update.20260101")

    def test_revisions_aliases_and_metadata_do_not_repeat_same_update(self):
        first = "0.6.1-161026"
        self.assertEqual(version_key(first), version_key(first + ".1"))
        self.assertEqual(version_key(first), version_key(first + "+sha.aaa"))
        self.assertEqual(canonical_to_bridge(first + ".2"), "0.6.1-update.20261016.2")
        self.assertEqual(display_version("0.6.1-update.20261016.2+sha.abc"), first + ".2")
        self.assertGreater(version_key(first + ".2"), version_key(first))
        self.assertEqual(version_key(first + ".2"),
                         version_key("0.6.1-update.20261016.2"))

    def test_dates_sort_chronologically_across_month_and_year(self):
        ordered = ["0.6.1-dev.22.1", "0.6.1-rc.99", "0.6.1-311026",
                   "0.6.1-011126", "0.6.1-311226", "0.6.1-010127",
                   "0.6.1", "0.6.2-dev.1.1"]
        self.assertEqual(sorted(ordered, key=version_key), ordered)
        for older, newer in zip(ordered, ordered[1:]):
            self.assertGreater(version_key(newer), version_key(older))

    def test_legacy_semver_order_and_stable_promotion_are_preserved(self):
        ordered = ["1.2.3-alpha", "1.2.3-alpha.1", "1.2.3-alpha.beta",
                   "1.2.3-beta", "1.2.3-beta.2", "1.2.3-beta.11",
                   "1.2.3-rc.1", "1.2.3"]
        self.assertEqual(sorted(reversed(ordered), key=version_key), ordered)
        for value in ordered:
            self.assertIsNone(parse_dated_version(value))
        self.assertEqual(version_key("1.2.3+build.01"), version_key("v1.2.3"))
        self.assertEqual(display_version("v1.2.3-dev.22.1"), "1.2.3-dev.22.1")

    def test_parse_match_retains_original_groups_for_release_discovery(self):
        match = parse_version("v0.6.1-010126.2+build.3")
        self.assertEqual(match.groups(), ("0", "6", "1", "010126.2", "build.3"))

    def test_invalid_dates_aliases_and_revisions_are_rejected(self):
        invalid = ["0.6.1-300226", "0.6.1-290226", "0.6.1-000126",
                   "0.6.1-161326", "0.6.1-161026.0", "0.6.1-161026.02",
                   "0.6.1-161026.2.3", "0.6.1-161026.foo",
                   "0.6.1-update.20261301", "0.6.1-update.19991231",
                   "0.6.1-update.21000101", "0.6.1-update.20261016.0",
                   "0.6.1-update.20261016.02", "0.6.1-update.20261016.extra",
                   "0.6.1-update.not-a-date", "0.6.1-update.202610"]
        for value in invalid:
            with self.subTest(value=value):
                for parser in (parse_version, parse_dated_version, version_key, display_version):
                    with self.assertRaises(ValueError):
                        parser(value)

    def test_unknown_versions_and_ordinary_numeric_leading_zeros_stay_invalid(self):
        for value in (None, 123, "latest", "1.2", "01.2.3", "1.2.3-dev.01",
                      "1.2.3-01", "1.2.3-", "1.2.3\n", "1.2.3/evil", "x" * 161):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_version(value)

    def test_bridge_conversion_requires_a_public_dated_name(self):
        for value in ("0.6.1", "0.6.1-dev.22.1", "0.6.1-update.20261016"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_to_bridge(value)


if __name__ == "__main__":
    unittest.main()
