"""Datas e horários em português, com os mesmos resultados em Windows/Linux."""
import unittest
from datetime import datetime, timedelta, timezone

from app.core import render_snippet
from app.date_formats import FORMAT_CODE_GROUPS, format_date_ptbr
from app.smart_templates import advanced_variables


class DateFormatsPtBrTests(unittest.TestCase):
    def setUp(self):
        self.friday = datetime(2026, 11, 6, 14, 30, 45, 123456)

    def test_weekdays_are_always_portuguese_without_global_locale(self):
        self.assertEqual(format_date_ptbr(
            self.friday, "%a %A %w %u"), "sex sexta-feira 5 5")
        self.assertEqual(format_date_ptbr(
            datetime(2026, 11, 7), "%a/%A"), "sáb/sábado")
        self.assertEqual(format_date_ptbr(
            datetime(2026, 11, 8), "%a/%A/%w/%u"),
            "dom/domingo/0/7")
        self.assertEqual(format_date_ptbr(
            datetime(2026, 11, 9), "%a/%A"), "seg/segunda-feira")
        self.assertEqual(format_date_ptbr(
            datetime(2026, 11, 10), "%A"), "terça-feira")

    def test_months_are_ptbr_including_accented_march(self):
        self.assertEqual(format_date_ptbr(
            self.friday, "%b %B %h %m"), "nov novembro nov 11")
        self.assertEqual(format_date_ptbr(
            datetime(2026, 3, 1), "%b %B"), "mar março")
        self.assertEqual(format_date_ptbr(
            datetime(2026, 12, 1), "%b %B"), "dez dezembro")

    def test_user_reported_preview_renders_in_portuguese(self):
        before = "{{data_formato:%a-%m-%d}}  {{data_formato:%A %a|%y-%m-%d}}"
        expected = "sex-11-06  sexta-feira sex|26-11-06"
        self.assertEqual(render_snippet(before, now=self.friday).text, expected)
        self.assertEqual(advanced_variables(
            "{{data_formato:%A, %d de %B de %Y}}", self.friday),
            "sexta-feira, 06 de novembro de 2026")

    def test_existing_tokens_keep_their_output(self):
        self.assertEqual(render_snippet(
            "{{data}} | {{hora}} | {{data_hora}}", now=self.friday).text,
            "06/11/2026 | 14:30 | 06/11/2026 14:30")
        self.assertEqual(advanced_variables(
            "{{data:+7}} | {{data:-1}} | {{data_formato:%Y-%m-%d}}",
            self.friday),
            "13/11/2026 | 05/11/2026 | 2026-11-06")

    def test_numeric_and_convenience_codes(self):
        self.assertEqual(format_date_ptbr(
            self.friday, "%d/%m/%Y (%y) %C %e %j"),
            "06/11/2026 (26) 20  6 310")
        self.assertEqual(format_date_ptbr(
            self.friday, "%H:%M:%S %I:%M %p %R %T %r %f"),
            "14:30:45 02:30 PM 14:30 14:30:45 02:30:45 PM 123456")
        self.assertEqual(format_date_ptbr(
            self.friday, "%F | %D | %x | %X"),
            "2026-11-06 | 11/06/26 | 06/11/2026 | 14:30:45")
        self.assertEqual(format_date_ptbr(
            self.friday, "%c"),
            "06/11/2026 14:30:45")
        self.assertEqual(format_date_ptbr(
            self.friday, "Progresso: 100%%"),
            "Progresso: 100%")

    def test_week_codes_handle_iso_year_boundary(self):
        year_boundary = datetime(2021, 1, 1, 9)
        self.assertEqual(format_date_ptbr(
            year_boundary, "%G-W%V-%u %g"),
            "2020-W53-5 20")
        self.assertEqual(format_date_ptbr(
            year_boundary, "%U %W"),
            year_boundary.strftime("%U %W"))

    def test_leap_day_and_full_year_day(self):
        leap = datetime(2024, 2, 29)
        self.assertEqual(format_date_ptbr(leap, "%j %A"), "060 quinta-feira")
        self.assertEqual(format_date_ptbr(
            datetime(2024, 12, 31), "%j"), "366")

    def test_timezone_codes_keep_previous_naive_datetime_behavior(self):
        self.assertEqual(format_date_ptbr(self.friday, "antes%z|%Zdepois"),
                         "antes|depois")
        aware = self.friday.replace(tzinfo=timezone(timedelta(hours=-3)))
        self.assertEqual(format_date_ptbr(aware, "%z"),
                         "-0300")
        self.assertTrue(format_date_ptbr(aware, "%Z"))

    def test_invalid_or_unlisted_directives_are_rejected(self):
        for fmt in ("%q", "%:z", "%", "%n", "%t", "%_", "%O", "{{data}}",
                    "a" * 49, ""):
            with self.subTest(fmt=fmt), self.assertRaises(ValueError):
                format_date_ptbr(self.friday, fmt)

    def test_safety_limit_and_literal_content(self):
        self.assertEqual(len(format_date_ptbr(
            self.friday, "%A " * 12)), 100)
        self.assertEqual(format_date_ptbr(self.friday, "%A, %B - Ok"),
                         "sexta-feira, novembro - Ok")
        # The unsupported token is a matched variable and must be rejected.
        with self.assertRaises(ValueError):
            advanced_variables("{{data_formato:%q}}", self.friday)

    def test_catalog_contains_every_supported_code_once(self):
        codes = [code for _group, entries in FORMAT_CODE_GROUPS
                 for code, _description in entries]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertGreaterEqual(len(codes), 30)
        for code in codes:
            with self.subTest(code=code):
                self.assertEqual(
                    format_date_ptbr(self.friday, code),
                    format_date_ptbr(self.friday, code))


if __name__ == "__main__":
    unittest.main()
