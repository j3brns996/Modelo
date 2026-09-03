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

    def test_provider_adapter_schemas_validate_valid_and_invalid_routes(self) -> None:
        valid_gcp_publisher = {
            "id": "gemini-pro-route",
            "location": "us-central1",
            "reference": "publishers/google/models/gemini-1.5-pro",
            "model_binding": {
                "kind": "publisher-model",
                "model_evidence": {
                    "id": "sha256-" + "a" * 64,
                    "id_pointer": "/name",
                    "resource_pointer": "/resourceName",
                    "name_pointer": "/displayName",
                    "provider_pointer": "/publisher",
                },
            },
        }
        self.assertEqual(
            self.schemas.validate("providers/gcp-vertex.schema.json", valid_gcp_publisher, "gcp-route.yaml"),
            (),
        )

        valid_gcp_endpoint = {
            "id": "vertex-endpoint-route",
            "location": "us-central1",
            "reference": "projects/my-project/locations/us-central1/endpoints/1234567890",
            "model_binding": {
                "kind": "endpoint-model",
                "model_evidence": {
                    "id": "sha256-" + "b" * 64,
                    "resource_pointer": "/deployedModel",
                    "name_pointer": "/modelDisplayName",
                    "provider_pointer": "/publisher",
                },
            },
        }
        self.assertEqual(
            self.schemas.validate("providers/gcp-vertex.schema.json", valid_gcp_endpoint, "gcp-endpoint.yaml"),
            (),
        )

        invalid_gcp = dict(valid_gcp_publisher, location="INVALID_LOCATION")
        findings = self.schemas.validate("providers/gcp-vertex.schema.json", invalid_gcp, "gcp-invalid.yaml")
        self.assertTrue(len(findings) > 0)

        valid_azure_deployment = {
            "id": "gpt4o-azure-route",
            "region": "eastus",
            "reference": "gpt-4o-deployment",
            "model_binding": {
                "kind": "deployment-model",
                "model_evidence": {
                    "id": "sha256-" + "c" * 64,
                    "id_pointer": "/name",
                    "resource_pointer": "/id",
                    "name_pointer": "/properties/model/name",
                    "provider_pointer": "/properties/model/publisher",
                },
            },
        }
        self.assertEqual(
            self.schemas.validate("providers/azure-foundry.schema.json", valid_azure_deployment, "azure-route.yaml"),
            (),
        )

        invalid_azure = dict(valid_azure_deployment, region="INVALID REGION!")
        findings = self.schemas.validate("providers/azure-foundry.schema.json", invalid_azure, "azure-invalid.yaml")
        self.assertTrue(len(findings) > 0)

    def test_offering_route_oneof_branches_keep_disjoint_discriminator_fields(self) -> None:
        # Forward-compatibility guard (multicloud wiring plan §7): the three
        # provider route schemas in offering.schema.json's `routes.items`
        # oneOf are distinguished only by their own required field name
        # (`source_region` / `location` / `region`), not by an explicit tag.
        # `id`, `reference` and `model_binding` are required by every
        # branch, so the property that must stay true isn't "every required
        # field is globally unique" - it's "once the fields common to every
        # branch are set aside, what's left (each branch's own
        # discriminator) never collides with another branch's". This test
        # proves that property mechanically today, and proves the check
        # itself would catch a future collision, without needing a real
        # fourth schema file: a synthetic fourth branch that reuses Azure's
        # `region` discriminator is fed through the same collision check.
        offering = self.schemas.schema("offering.schema.json")
        branches = offering["properties"]["routes"]["items"]["oneOf"]
        self.assertEqual(len(branches), 3)
        required_sets = [
            frozenset(self.schemas.resolve(branch, offering)[0]["required"])
            for branch in branches
        ]
        common = frozenset.intersection(*required_sets)
        self.assertIn("id", common)
        self.assertIn("reference", common)
        self.assertIn("model_binding", common)
        discriminators = [required - common for required in required_sets]
        self.assertEqual(
            [set(discriminator) for discriminator in discriminators],
            [{"source_region"}, {"location"}, {"region"}],
        )

        def colliding_pairs(sets: list[frozenset]) -> list[tuple[int, int]]:
            return [
                (i, j)
                for i in range(len(sets))
                for j in range(i + 1, len(sets))
                if sets[i] & sets[j]
            ]

        self.assertEqual(colliding_pairs(discriminators), [])

        hypothetical_fourth_branch_discriminator = frozenset({"region"})
        self.assertNotEqual(
            colliding_pairs(discriminators + [hypothetical_fourth_branch_discriminator]),
            [],
            "a hypothetical fourth branch reusing an existing discriminator "
            "field name must be caught as a collision by this same check",
        )


if __name__ == "__main__":
    unittest.main()
