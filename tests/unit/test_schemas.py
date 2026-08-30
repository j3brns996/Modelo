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


if __name__ == "__main__":
    unittest.main()
