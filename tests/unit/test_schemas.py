from __future__ import annotations

import unittest
import sys
from pathlib import Path

import yaml

from modelo.schemas import SchemaSet
ROOT = Path(__file__).resolve().parents[2]


class SchemaRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = SchemaSet(ROOT, ROOT.joinpath("schemas").relative_to(ROOT))

    def test_all_schemas_load_and_config_validates_offline(self) -> None:
        document = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        self.assertEqual(self.schemas.validate("modelo.schema.json", document, "modelo.yaml"), ())

    def test_format_checker_is_enforced(self) -> None:
        schema = self.schemas.schema("evidence.schema.json")
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        document = {
            "id": "sha256-" + "a" * 64,
            "source": {"type": "official-vendor-documentation", "uri": "https://example.invalid/x"},
            "retrieved_by": "manual", "observed_at": "2026-02-30T00:00:00Z",
            "scope": {}, "projection": {}, "visibility": "public",
        }
        findings = self.schemas.validate("evidence.schema.json", document, "e.yaml")
        self.assertTrue(any("format" in finding.message for finding in findings))

    def test_date_time_is_strict_rfc3339(self) -> None:
        valid = "2026-08-30T12:34:56.123+05:30"
        invalid = (
            "2026-08-30 12:34:56Z",
            "2026-08-30T12:34:56",
            "2026-08-30T12:34:56+24:00",
            "2026-08-30T12:34:60Z",
            "2026-08-30t12:34:56z",
            "2026-02-30T12:34:56Z",
        )
        validator = self.schemas.validator("evidence.schema.json")
        base = {
            "id": "sha256-" + "a" * 64,
            "source": {"type": "official-vendor-documentation", "uri": "https://example.invalid/x"},
            "retrieved_by": "manual", "observed_at": valid,
            "scope": {}, "projection": {}, "visibility": "public",
        }
        self.assertEqual(list(validator.iter_errors(base)), [])
        for value in invalid:
            with self.subTest(value=value):
                candidate = dict(base, observed_at=value)
                self.assertTrue(any(error.validator == "format" for error in validator.iter_errors(candidate)))


if __name__ == "__main__":
    unittest.main()
