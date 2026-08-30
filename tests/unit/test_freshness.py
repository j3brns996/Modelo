from __future__ import annotations

from datetime import date
import unittest

from modelo.evidence import ExternalFact
from modelo.freshness import observed_utc_date, parse_as_of, validate_freshness


class FreshnessTests(unittest.TestCase):
    def findings(self, observed_at: str, as_of: str, threshold: int = 30):
        return validate_freshness(
            path="fact.yaml", facts=[ExternalFact("/fact", "x", "availability")],
            references={"/fact": {"id": "e"}},
            evidence={"e": {"observed_at": observed_at}},
            as_of=parse_as_of(as_of), thresholds={"availability": threshold},
        )

    def test_calendar_boundary_is_inclusive(self) -> None:
        self.assertEqual(self.findings("2026-07-31T23:30:00-01:00", "2026-08-31"), ())
        self.assertEqual(self.findings("2026-07-31T23:30:00Z", "2026-08-31")[0].code, "EVIDENCE_STALE")

    def test_future_is_an_error(self) -> None:
        self.assertEqual(self.findings("2026-09-01T00:00:00Z", "2026-08-31")[0].code, "EVIDENCE_FUTURE")

    def test_as_of_requires_canonical_date(self) -> None:
        self.assertEqual(parse_as_of("2026-08-30"), date(2026, 8, 30))
        for value in ("2026-8-30", "2026-02-30", "2026-08-30T00:00:00Z"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_as_of(value)

    def test_timestamp_parser_matches_strict_schema_contract(self) -> None:
        self.assertEqual(observed_utc_date("2026-08-30T23:30:00-01:00"), date(2026, 8, 31))
        for value in ("2026-08-30T12:00:00Z", "2026-08-30T12:00:00+23:59", "2026-08-30T12:00:00-23:59"):
            with self.subTest(value=value):
                observed_utc_date(value)
        for value in ("2026-08-30 12:00:00Z", "2026-08-30T12:00:00", "2026-08-30T12:00:60Z", "2026-08-30T12:00:00+24:00", "2026-08-30T12:00:00+01:60", "2026-08-30T12:00:00+00:99", "2026-08-30T12:00:00-01:60"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                observed_utc_date(value)


if __name__ == "__main__":
    unittest.main()
