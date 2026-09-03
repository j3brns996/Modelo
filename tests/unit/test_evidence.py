from __future__ import annotations

import unittest

from modelo.evidence import (
    canonical_json,
    create_evidence_record,
    evidence_id,
    resolve_pointer,
    validate_content_addresses,
)


class EvidenceTests(unittest.TestCase):
    def test_canonicalisation_is_deterministic_and_utf16_sorted(self) -> None:
        first = {"\U00010000": 1, "\ue000": 2, "a": [True, None, "x"]}
        second = dict(reversed(tuple(first.items())))
        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertLess(canonical_json(first).index("𐀀"), canonical_json(first).index(""))

    def test_content_address_omits_only_root_id(self) -> None:
        document = {"id": "wrong", "projection": {"id": "retained"}}
        self.assertEqual(evidence_id(document), evidence_id({"projection": {"id": "retained"}}))
        self.assertNotEqual(evidence_id(document), evidence_id({"projection": {}}))

    def test_json_pointer_is_exact_and_does_not_search(self) -> None:
        document = {"a/b": {"~key": ["value"]}}
        self.assertEqual(resolve_pointer(document, "/a~1b/~0key/0"), "value")
        with self.assertRaises(KeyError):
            resolve_pointer(document, "/value")

    def test_create_evidence_record_doc_source(self) -> None:
        record = create_evidence_record(
            source_type="official-provider-documentation",
            uri="https://example.invalid/doc",
            observed_at="2026-09-01T00:00:00Z",
            projection={"modelName": "Test Model"},
        )
        self.assertTrue(record["id"].startswith("sha256-"))
        self.assertEqual(
            record["source"],
            {"type": "official-provider-documentation", "uri": "https://example.invalid/doc"},
        )
        self.assertEqual(record["retrieved_by"], "cli")
        self.assertEqual(record["observed_at"], "2026-09-01T00:00:00Z")
        self.assertEqual(record["scope"], {})
        self.assertEqual(record["projection"], {"modelName": "Test Model"})
        self.assertEqual(record["visibility"], "internal")
        self.assertEqual(validate_content_addresses([("test", record)]), ())

    def test_create_evidence_record_api_source(self) -> None:
        record = create_evidence_record(
            source_type="first-party-read-api",
            uri="https://example.invalid/api",
            observed_at="2026-09-01T00:00:00Z",
            projection={"modelName": "API Model"},
            operation="GetFoundationModel",
            partition="aws",
            region="us-east-1",
            retrieved_by="mcp",
            scope={"scope_ref": "synth"},
            visibility="public",
        )
        self.assertTrue(record["id"].startswith("sha256-"))
        self.assertEqual(
            record["source"],
            {
                "type": "first-party-read-api",
                "provider": "aws",
                "service": "bedrock",
                "operation": "GetFoundationModel",
                "partition": "aws",
                "region": "us-east-1",
                "sanitised_parameters": {},
                "documentation_uri": "https://example.invalid/api",
            },
        )
        self.assertEqual(record["retrieved_by"], "mcp")
        self.assertEqual(record["scope"], {"scope_ref": "synth"})
        self.assertEqual(record["visibility"], "public")
        self.assertEqual(validate_content_addresses([("test", record)]), ())


if __name__ == "__main__":
    unittest.main()

