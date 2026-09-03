from __future__ import annotations

import unittest
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

    def test_mac_digest_pattern_matches_common_evidence_id(self) -> None:
        # mac.schema.json is deliberately standalone-validatable (see
        # test_mac_templates.py's bare Draft202012Validator use), so its
        # digest shape is a local copy of common.schema.json's evidenceId
        # rather than a cross-file $ref. Pin the two patterns equal so they
        # cannot drift apart silently.
        mac_schema = self.schemas.schema("mac.schema.json")
        common_schema = self.schemas.schema("common.schema.json")
        self.assertEqual(
            mac_schema["$defs"]["digest"]["pattern"],
            common_schema["$defs"]["evidenceId"]["pattern"],
        )

    def test_every_externally_sourced_field_has_a_valid_freshness_class(self) -> None:
        valid_classes = set(
            self.schemas.schema("freshness-policy.schema.json")["properties"]["classes_days"]["required"]
        )
        self.assertTrue(valid_classes)

        def walk(node: object, name: str) -> None:
            if isinstance(node, dict):
                if node.get("x-modelo-provenance") == "external":
                    self.assertIn(
                        node.get("x-modelo-freshness-class"), valid_classes,
                        f"{name} is externally sourced but has no valid x-modelo-freshness-class",
                    )
                for child in node.values():
                    walk(child, name)
            elif isinstance(node, list):
                for child in node:
                    walk(child, name)

        for name, document in self.schemas.documents.items():
            walk(document, name)

    def test_date_time_is_strict_rfc3339(self) -> None:
        valid = (
            "2026-08-30T12:34:56.123+05:30",
            "2026-08-30T12:34:56+23:59",
            "2026-08-30T12:34:56-23:59",
            "2026-08-30T12:34:56Z",
        )
        invalid = (
            "2026-08-30 12:34:56Z",
            "2026-08-30T12:34:56",
            "2026-08-30T12:34:56+24:00",
            "2026-08-30T12:34:56+01:60",
            "2026-08-30T12:34:56+00:99",
            "2026-08-30T12:34:56-01:60",
            "2026-08-30T12:34:60Z",
            "2026-08-30t12:34:56z",
            "2026-02-30T12:34:56Z",
        )
        validator = self.schemas.validator("evidence.schema.json")
        base = {
            "id": "sha256-" + "a" * 64,
            "source": {"type": "official-vendor-documentation", "uri": "https://example.invalid/x"},
            "retrieved_by": "manual", "observed_at": valid[0],
            "scope": {}, "projection": {}, "visibility": "public",
        }
        for value in valid:
            with self.subTest(value=value):
                self.assertEqual(list(validator.iter_errors(dict(base, observed_at=value))), [])
        for value in invalid:
            with self.subTest(value=value):
                candidate = dict(base, observed_at=value)
                self.assertTrue(any(error.validator == "format" for error in validator.iter_errors(candidate)))

if __name__ == "__main__":
    unittest.main()
