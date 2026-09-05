from __future__ import annotations

import unittest
from pathlib import Path, PurePosixPath

from modelo.evidence import (
    canonical_json,
    create_evidence_record,
    evidence_id,
    resolve_pointer,
    validate_content_addresses,
)
from modelo.schemas import SchemaSet


ROOT = Path(__file__).resolve().parents[2]


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = SchemaSet(ROOT, PurePosixPath("schemas"))

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
            schemas=self.schemas,
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
            schemas=self.schemas,
            provider="aws",
            service="bedrock",
            operation="GetFoundationModel",
            partition="aws",
            region="us-east-1",
            sanitised_parameters={"modelIdentifier": "model-1"},
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
                "sanitised_parameters": {"modelIdentifier": "model-1"},
                "documentation_uri": "https://example.invalid/api",
            },
        )
        self.assertEqual(record["retrieved_by"], "mcp")
        self.assertEqual(record["scope"], {"scope_ref": "synth"})
        self.assertEqual(record["visibility"], "public")
        self.assertEqual(validate_content_addresses([("test", record)]), ())

    def test_create_evidence_record_rejects_schema_invalid_candidates(self) -> None:
        cases = (
            {"source_type": "marketing-page"},
            {"uri": "http://example.invalid/doc"},
            {"observed_at": "2026-02-30T00:00:00Z"},
            {"retrieved_by": "browser"},
            {"visibility": "secret"},
        )
        defaults = {
            "source_type": "official-provider-documentation",
            "uri": "https://example.invalid/doc",
            "observed_at": "2026-09-01T00:00:00Z",
            "projection": {"modelName": "Test Model"},
            "schemas": self.schemas,
        }
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(
                ValueError, "invalid evidence record"
            ):
                create_evidence_record(**(defaults | changes))

    def test_create_api_evidence_requires_every_api_field(self) -> None:
        defaults = {
            "source_type": "first-party-read-api",
            "uri": "https://example.invalid/api",
            "observed_at": "2026-09-01T00:00:00Z",
            "projection": {"modelName": "API Model"},
            "schemas": self.schemas,
            "provider": "aws",
            "service": "bedrock",
            "operation": "GetFoundationModel",
            "partition": "aws",
            "region": "us-east-1",
            "sanitised_parameters": {},
        }
        for omitted in (
            "provider", "service", "operation", "partition", "region",
            "sanitised_parameters",
        ):
            arguments = dict(defaults)
            arguments.pop(omitted)
            with self.subTest(omitted=omitted), self.assertRaisesRegex(
                ValueError, "invalid evidence record"
            ):
                create_evidence_record(**arguments)

    def test_create_documentation_evidence_rejects_api_fields(self) -> None:
        defaults = {
            "source_type": "official-provider-documentation",
            "uri": "https://example.invalid/doc",
            "observed_at": "2026-09-01T00:00:00Z",
            "projection": {},
            "schemas": self.schemas,
        }
        for name, value in (
            ("provider", "aws"),
            ("service", "bedrock"),
            ("operation", "GetFoundationModel"),
            ("partition", "aws"),
            ("region", "us-east-1"),
            ("sanitised_parameters", {}),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "documentation sources do not accept"
            ):
                create_evidence_record(**(defaults | {name: value}))

    def test_create_api_evidence_rejects_non_aws_bedrock_pairs(self) -> None:
        defaults = {
            "source_type": "first-party-read-api",
            "uri": "https://example.invalid/api",
            "observed_at": "2026-09-01T00:00:00Z",
            "projection": {},
            "schemas": self.schemas,
            "operation": "GetFoundationModel",
            "partition": "aws",
            "region": "us-east-1",
            "sanitised_parameters": {},
        }
        for provider, service in (
            ("gcp", "vertex"),
            ("aws", "vertex"),
            ("gcp", "bedrock"),
        ):
            with self.subTest(provider=provider, service=service), self.assertRaisesRegex(
                ValueError, "supports only provider aws with service bedrock"
            ):
                create_evidence_record(
                    **defaults,
                    provider=provider,
                    service=service,
                )

    def test_create_api_evidence_rejects_nested_sensitive_parameter_keys(self) -> None:
        defaults = {
            "source_type": "first-party-read-api",
            "uri": "https://example.invalid/api",
            "observed_at": "2026-09-01T00:00:00Z",
            "projection": {},
            "schemas": self.schemas,
            "provider": "aws",
            "service": "bedrock",
            "operation": "GetFoundationModel",
            "partition": "aws",
            "region": "us-east-1",
        }
        cases = (
            ({"offerToken": "secret"}, "offerToken"),
            ({"auth": {"credentials": "secret"}}, "credentials"),
            ({"items": [{"OFFER_TOKEN": "secret"}]}, "offerToken"),
            ({"items": [{"CrE_Den-TiAls": "secret"}]}, "credentials"),
        )
        for parameters, key in cases:
            with self.subTest(parameters=parameters), self.assertRaisesRegex(
                ValueError,
                f"sanitised_parameters contains prohibited sensitive key {key}",
            ) as caught:
                create_evidence_record(
                    **defaults,
                    sanitised_parameters=parameters,
                )
            self.assertNotIn("secret", str(caught.exception))

        allowed = create_evidence_record(
            **defaults,
            sanitised_parameters={"maxTokens": 256},
        )
        self.assertEqual(
            allowed["source"]["sanitised_parameters"],
            {"maxTokens": 256},
        )


if __name__ == "__main__":
    unittest.main()
