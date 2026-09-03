from __future__ import annotations

from datetime import date
from copy import deepcopy
import unittest
import sys
from pathlib import Path

import yaml

from modelo.evidence import evidence_id
from modelo.validators import check_repository

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/fixtures/semantic"))
from repository import Repository  # noqa: E402


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Repository()

    def tearDown(self) -> None:
        self.repository.close()

    def check(self, base: str | None = None, head: str | None = None, as_of: date = date(2026, 9, 1)):
        return check_repository(
            self.repository.root,
            base or self.repository.base,
            head or self.repository.base,
            as_of,
        )

    def replace_direct_evidence(self, transform) -> None:
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        old_id = offering["routes"][0]["model_binding"]["model_evidence"]["id"]
        old_path = self.repository.root / "catalogue/evidence" / f"{old_id}.yaml"
        record = yaml.safe_load(old_path.read_text(encoding="utf-8"))
        record.pop("id")
        transform(record, offering)
        new_id = evidence_id(record)
        record["id"] = new_id
        new_path = old_path.with_name(f"{new_id}.yaml")
        new_path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8", newline="\n")
        binding = offering["routes"][0]["model_binding"]["model_evidence"]
        binding["id"] = new_id
        offering["evidence_refs"]["/routes/0/reference"]["id"] = new_id
        offering_path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")

    def install_profile(self, transform=lambda record, offering: None) -> None:
        profile = {
            "source": {"type": "first-party-read-api", "provider": "aws", "service": "bedrock", "operation": "GetInferenceProfile", "partition": "aws", "region": "eu-west-2", "sanitised_parameters": {"inferenceProfileIdentifier": "eu.test.profile-v1"}, "documentation_uri": "https://example.invalid/aws-profile-api"},
            "retrieved_by": "cli", "observed_at": "2026-09-01T00:00:00Z",
            "scope": {"scope_ref": "synthetic", "region": "eu-west-2"},
            "projection": {"profileId": "eu.test.profile-v1", "type": "SYSTEM_DEFINED", "status": "ACTIVE", "models": [{"modelArn": "arn:aws:bedrock:eu-west-2::foundation-model/test.model-v1"}]},
            "visibility": "public",
        }
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        transform(profile, offering)
        profile_id = evidence_id(profile)
        profile["id"] = profile_id
        evidence_path = self.repository.root / "catalogue/evidence" / f"{profile_id}.yaml"
        evidence_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8", newline="\n")
        offering["routes"][0] = {
            "id": "eu-profile", "source_region": "eu-west-2", "reference": "eu.test.profile-v1",
            "model_binding": {
                "kind": "system-inference-profile",
                "profile_evidence": {
                    "id": profile_id, "projection_pointer": "/profileId",
                    "type_pointer": "/type", "status_pointer": "/status",
                    "destinations_pointer": "/models",
                },
                "destinations": [{
                    "destination_pointer": "/models/0/modelArn",
                    "model_evidence": {
                        "id": "sha256-9f19d4dfb29b0414ef63fe8ef528f37e5d50deca65a6de0ab752f46b316cbf43",
                        "arn_pointer": "/modelArn", "name_pointer": "/modelName",
                        "provider_pointer": "/providerName",
                    },
                }],
            },
        }
        offering["evidence_refs"]["/routes/0/reference"] = {
            "id": profile_id, "projection_pointer": "/profileId",
        }
        offering_path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")

    def test_base_equals_head_scheduled_audit_is_valid(self) -> None:
        self.assertEqual(self.check(), ())

    def test_unknown_reference_and_path_identity_fail(self) -> None:
        path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        text = path.read_text(encoding="utf-8").replace("model_id: test-model", "model_id: missing-model")
        path.write_text(text, encoding="utf-8", newline="\n")
        head = self.repository.commit()
        findings = self.check(head=head)
        self.assertIn("UNKNOWN_REFERENCE", {finding.code for finding in findings})

    def test_schema_annotated_external_leaf_requires_exact_fact_pointer(self) -> None:
        path = self.repository.root / "catalogue/models/test-model.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["evidence_refs"] = {}
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit()
        findings = self.check(head=head)
        missing = [finding for finding in findings if finding.code == "EVIDENCE_MISSING"]
        self.assertTrue(any(finding.json_pointer == "/name" for finding in missing))

    def test_evidence_value_mismatch_and_freshness_fail(self) -> None:
        path = self.repository.root / "catalogue/models/test-model.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("name: Test Model", "name: Other Model"), encoding="utf-8", newline="\n")
        head = self.repository.commit()
        findings = self.check(head=head, as_of=date(2027, 9, 1))
        codes = {finding.code for finding in findings}
        self.assertIn("EVIDENCE_VALUE_MISMATCH", codes)
        self.assertIn("EVIDENCE_STALE", codes)

    def test_evidence_edit_is_both_content_and_change_invalid(self) -> None:
        path = next((self.repository.root / "catalogue/evidence").glob("*.yaml"))
        path.write_text(path.read_text(encoding="utf-8").replace("visibility: public", "visibility: internal"), encoding="utf-8", newline="\n")
        head = self.repository.commit()
        codes = {finding.code for finding in self.check(head=head)}
        self.assertIn("EVIDENCE_ID_MISMATCH", codes)
        self.assertIn("EVIDENCE_IMMUTABLE", codes)

    def test_offering_revoke_does_not_depend_on_discovery(self) -> None:
        (self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml").unlink()
        head = self.repository.commit()
        self.assertEqual(self.check(head=head), ())

    def test_condition_version_edit_is_immutable(self) -> None:
        path = self.repository.root / "catalogue/policies/conditions/test-condition/1.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("Synthetic condition", "Changed condition"), encoding="utf-8", newline="\n")
        head = self.repository.commit()
        self.assertIn("CHANGE_INVALID", {finding.code for finding in self.check(head=head)})

    def test_scheduled_audit_detects_historical_condition_mutation(self) -> None:
        path = self.repository.root / "catalogue/policies/conditions/test-condition/1.yaml"
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace("Synthetic condition", "Historically changed condition"), encoding="utf-8", newline="\n")
        final = self.repository.commit("historical mutation")
        self.assertIn("CHANGE_INVALID", {finding.code for finding in self.check(base=final, head=final)})

    def test_changed_condition_reintroduction_after_deletion_fails(self) -> None:
        path = self.repository.root / "catalogue/policies/conditions/test-condition/1.yaml"
        original = path.read_text(encoding="utf-8")
        offering = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering_text = offering.read_text(encoding="utf-8")
        path.unlink()
        offering.write_text(offering_text.replace("condition_refs:\n  - id: test-condition\n    version: 1", "condition_refs: []"), encoding="utf-8", newline="\n")
        deleted = self.repository.commit("delete condition")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(original.replace("Synthetic condition", "Reintroduced meaning"), encoding="utf-8", newline="\n")
        offering.write_text(offering_text, encoding="utf-8", newline="\n")
        head = self.repository.commit("reintroduce condition")
        self.assertIn("CHANGE_INVALID", {finding.code for finding in self.check(base=deleted, head=head)})

    def test_atomic_offering_move_is_add_destination_and_revoke_source(self) -> None:
        source = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
        source.unlink()
        document["id"] = "moved-offering"
        destination = source.with_name("moved-offering.yaml")
        destination.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit()
        self.assertEqual(self.check(head=head), ())

    def test_system_inference_profile_binding_is_explicit_and_equal(self) -> None:
        profile = {
            "source": {"type": "first-party-read-api", "provider": "aws", "service": "bedrock", "operation": "GetInferenceProfile", "partition": "aws", "region": "eu-west-2", "sanitised_parameters": {"inferenceProfileIdentifier": "eu.test.profile-v1"}, "documentation_uri": "https://example.invalid/aws-profile-api"},
            "retrieved_by": "cli", "observed_at": "2026-09-01T00:00:00Z",
            "scope": {"scope_ref": "synthetic", "region": "eu-west-2"},
            "projection": {"profileId": "eu.test.profile-v1", "type": "SYSTEM_DEFINED", "status": "ACTIVE", "models": [{"modelArn": "arn:aws:bedrock:eu-west-2::foundation-model/test.model-v1"}]},
            "visibility": "public",
        }
        profile_id = evidence_id(profile)
        profile["id"] = profile_id
        evidence_path = self.repository.root / "catalogue/evidence" / f"{profile_id}.yaml"
        evidence_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8", newline="\n")
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        offering["routes"][0] = {
            "id": "eu-profile", "source_region": "eu-west-2", "reference": "eu.test.profile-v1",
            "model_binding": {"kind": "system-inference-profile", "profile_evidence": {"id": profile_id, "projection_pointer": "/profileId", "type_pointer": "/type", "status_pointer": "/status", "destinations_pointer": "/models"}, "destinations": [{"destination_pointer": "/models/0/modelArn", "model_evidence": {"id": "sha256-9f19d4dfb29b0414ef63fe8ef528f37e5d50deca65a6de0ab752f46b316cbf43", "arn_pointer": "/modelArn", "name_pointer": "/modelName", "provider_pointer": "/providerName"}}]},
        }
        offering["evidence_refs"]["/routes/0/reference"] = {"id": profile_id, "projection_pointer": "/profileId"}
        offering_path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit()
        self.assertEqual(self.check(head=head), ())

    def test_direct_route_requires_correlated_aws_bedrock_api_evidence(self) -> None:
        cases = {
            "documentation": lambda record: record.update(source={
                "type": "official-provider-documentation",
                "uri": "https://example.invalid/aws-docs",
            }),
            "provider": lambda record: record["source"].update(provider="not-aws"),
            "service": lambda record: record["source"].update(service="not-bedrock"),
            "operation": lambda record: record["source"].update(operation="GetInferenceProfile"),
            "region": lambda record: record["source"].update(region="eu-west-1"),
            "partition": lambda record: record["source"].update(partition="aws-cn"),
        }
        for name, mutation in cases.items():
            with self.subTest(name=name):
                repository = Repository()
                original = self.repository
                self.repository = repository
                try:
                    self.replace_direct_evidence(lambda record, offering: mutation(record))
                    head = repository.commit(name)
                    codes = {finding.code for finding in self.check(head=head)}
                    self.assertIn("EVIDENCE_VALUE_MISMATCH", codes)
                finally:
                    self.repository = original
                    repository.close()

    def test_fresh_document_reference_cannot_mask_stale_route_binding_evidence(self) -> None:
        self.replace_direct_evidence(
            lambda record, offering: record.update(observed_at="2020-01-01T00:00:00Z")
        )
        document = {
            "source": {
                "type": "official-provider-documentation",
                "uri": "https://example.invalid/current-route",
            },
            "retrieved_by": "manual",
            "observed_at": "2026-08-29T00:00:00Z",
            "scope": {},
            "projection": {"modelId": "test.model-v1"},
            "visibility": "public",
        }
        document_id = evidence_id(document)
        document["id"] = document_id
        evidence_path = self.repository.root / "catalogue/evidence" / f"{document_id}.yaml"
        evidence_path.write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n"
        )
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        offering["evidence_refs"]["/routes/0/reference"] = {
            "id": document_id, "projection_pointer": "/modelId",
        }
        offering_path.write_text(
            yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n"
        )
        head = self.repository.commit("mask stale route evidence")
        findings = self.check(head=head)
        self.assertTrue(any(
            finding.code == "EVIDENCE_VALUE_MISMATCH"
            and "not its explicit model binding evidence" in finding.message
            for finding in findings
        ))

    def test_direct_route_arn_must_match_source_partition_and_region(self) -> None:
        def transform(record, offering):
            wrong = "arn:aws:bedrock:us-east-1::foundation-model/test.model-v1"
            record["projection"]["modelArn"] = wrong
            offering["routes"][0]["reference"] = wrong
            offering["evidence_refs"]["/routes/0/reference"]["projection_pointer"] = "/modelArn"

        self.replace_direct_evidence(transform)
        head = self.repository.commit("wrong direct ARN scope")
        self.assertIn("EVIDENCE_VALUE_MISMATCH", {finding.code for finding in self.check(head=head)})

    def test_direct_model_evidence_rejects_malformed_arn(self) -> None:
        self.replace_direct_evidence(
            lambda record, offering: record["projection"].update(modelArn="not-an-arn")
        )
        head = self.repository.commit("malformed direct model ARN")
        findings = self.check(head=head)
        malformed = [
            finding for finding in findings
            if finding.code == "EVIDENCE_VALUE_MISMATCH"
            and "not a canonical supported ARN" in finding.message
        ]
        self.assertEqual(
            [finding.json_pointer for finding in malformed],
            ["/routes/0/model_binding/model_evidence"],
        )

    def test_commercial_govcloud_and_china_partition_region_pairs_are_supported(self) -> None:
        cases = (
            ("aws", "ap-southeast-2"),
            ("aws-us-gov", "us-gov-west-1"),
            ("aws-cn", "cn-north-1"),
        )
        for partition, region in cases:
            with self.subTest(partition=partition, region=region):
                repository = Repository()
                original = self.repository
                self.repository = repository
                try:
                    def transform(record, offering):
                        arn = f"arn:{partition}:bedrock:{region}::foundation-model/test.model-v1"
                        record["source"].update(partition=partition, region=region)
                        record["scope"]["region"] = region
                        record["projection"]["modelArn"] = arn
                        offering["routes"][0]["source_region"] = region
                        offering["routes"][0]["reference"] = arn
                        offering["evidence_refs"]["/routes/0/reference"]["projection_pointer"] = "/modelArn"

                    self.replace_direct_evidence(transform)
                    head = repository.commit(f"{partition} {region}")
                    self.assertEqual(self.check(head=head), ())
                finally:
                    self.repository = original
                    repository.close()

    def test_service_alias_dispatches_aws_validation_without_route_adapter(self) -> None:
        registry_path = self.repository.root / "catalogue/governance/inference-services.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["inference_services"]["bedrock-production"] = {
            "id": "bedrock-production", "adapter": "aws-bedrock",
        }
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8", newline="\n")
        old = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(old.read_text(encoding="utf-8"))
        offering["inference_service_id"] = "bedrock-production"
        new = self.repository.root / "catalogue/offerings/bedrock-production/test-offering.yaml"
        new.parent.mkdir(parents=True)
        new.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        old.unlink()
        head = self.repository.commit("service alias")
        self.assertEqual(self.check(head=head), ())

    def test_unknown_service_fails_without_provider_cascade(self) -> None:
        old = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(old.read_text(encoding="utf-8"))
        offering["inference_service_id"] = "missing-service"
        new = self.repository.root / "catalogue/offerings/missing-service/test-offering.yaml"
        new.parent.mkdir(parents=True)
        new.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        old.unlink()
        head = self.repository.commit("unknown service")
        findings = self.check(head=head)
        self.assertEqual({finding.code for finding in findings}, {"UNKNOWN_REFERENCE"})

    def test_duplicate_semantic_aws_route_is_rejected(self) -> None:
        path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(path.read_text(encoding="utf-8"))
        duplicate = deepcopy(offering["routes"][0])
        duplicate["id"] = "duplicate-id"
        offering["routes"].append(duplicate)
        offering["evidence_refs"]["/routes/1/reference"] = deepcopy(
            offering["evidence_refs"]["/routes/0/reference"]
        )
        path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit("duplicate route")
        self.assertIn("PATH_IDENTITY_MISMATCH", {finding.code for finding in self.check(head=head)})

    def test_profile_requires_correlated_api_source_system_status_and_complete_destinations(self) -> None:
        cases = {
            "documentation": lambda profile, offering: profile.update(source={
                "type": "official-provider-documentation",
                "uri": "https://example.invalid/aws-docs",
            }),
            "wrong-operation": lambda profile, offering: profile["source"].update(operation="GetFoundationModel"),
            "wrong-provider": lambda profile, offering: profile["source"].update(provider="not-aws"),
            "wrong-service": lambda profile, offering: profile["source"].update(service="not-bedrock"),
            "wrong-source-region": lambda profile, offering: profile["source"].update(region="eu-west-1"),
            "wrong-partition": lambda profile, offering: profile["source"].update(partition="aws-cn"),
            "application-profile": lambda profile, offering: profile["projection"].update(type="APPLICATION"),
            "inactive-profile": lambda profile, offering: profile["projection"].update(status="INACTIVE"),
            "unbound-destination": lambda profile, offering: profile["projection"]["models"].append({
                "modelArn": "arn:aws:bedrock:eu-west-1::foundation-model/test.model-v1"
            }),
        }
        for name, transform in cases.items():
            with self.subTest(name=name):
                repository = Repository()
                original = self.repository
                self.repository = repository
                try:
                    self.install_profile(transform)
                    head = repository.commit(name)
                    self.assertIn(
                        "EVIDENCE_VALUE_MISMATCH",
                        {finding.code for finding in self.check(head=head)},
                    )
                finally:
                    self.repository = original
                    repository.close()

    def test_profile_destination_bijection_is_by_pointer_not_repeated_value(self) -> None:
        def transform(profile, offering):
            profile["projection"]["models"].append(
                deepcopy(profile["projection"]["models"][0])
            )

        self.install_profile(transform)
        path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(path.read_text(encoding="utf-8"))
        first = offering["routes"][0]["model_binding"]["destinations"][0]
        offering["routes"][0]["model_binding"]["destinations"].append(deepcopy(first))
        path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit("duplicate destination pointer")
        findings = self.check(head=head)
        self.assertTrue(any(
            finding.code == "EVIDENCE_VALUE_MISMATCH"
            and "complete one-to-one projection" in finding.message
            for finding in findings
        ))

    def test_profile_destination_arn_must_match_destination_evidence_region(self) -> None:
        wrong = "arn:aws:bedrock:us-east-1::foundation-model/test.model-v1"

        def change_direct(record, offering):
            record["projection"]["modelArn"] = wrong

        self.replace_direct_evidence(change_direct)
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        destination_evidence_id = offering["routes"][0]["model_binding"]["model_evidence"]["id"]

        def profile_transform(profile, ignored):
            profile["projection"]["models"][0]["modelArn"] = wrong

        self.install_profile(profile_transform)
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        offering["routes"][0]["model_binding"]["destinations"][0]["model_evidence"]["id"] = destination_evidence_id
        offering_path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit("destination Region mismatch")
        self.assertIn("EVIDENCE_VALUE_MISMATCH", {finding.code for finding in self.check(head=head)})

    def test_profile_destination_and_bound_evidence_reject_malformed_arns(self) -> None:
        self.replace_direct_evidence(
            lambda record, offering: record["projection"].update(modelArn="not-an-arn")
        )
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        destination_evidence_id = offering["routes"][0]["model_binding"]["model_evidence"]["id"]

        def profile_transform(profile, ignored):
            profile["projection"]["models"][0]["modelArn"] = "not-an-arn"

        self.install_profile(profile_transform)
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        offering["routes"][0]["model_binding"]["destinations"][0]["model_evidence"]["id"] = destination_evidence_id
        offering_path.write_text(
            yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n"
        )
        head = self.repository.commit("malformed profile destination ARNs")
        self.assertIn(
            "EVIDENCE_VALUE_MISMATCH",
            {finding.code for finding in self.check(head=head)},
        )

    def test_profile_arn_must_match_source_partition_and_region(self) -> None:
        wrong = "arn:aws:bedrock:us-east-1::inference-profile/eu.test.profile-v1"

        def transform(profile, offering):
            profile["projection"]["profileId"] = wrong

        self.install_profile(transform)
        path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(path.read_text(encoding="utf-8"))
        offering["routes"][0]["reference"] = wrong
        path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit("wrong profile ARN scope")
        self.assertIn("EVIDENCE_VALUE_MISMATCH", {finding.code for finding in self.check(head=head)})

    def test_unsupported_service_adapter_fails_closed(self) -> None:
        registry_path = self.repository.root / "catalogue/governance/inference-services.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["inference_services"]["aws-bedrock"]["adapter"] = "unsupported"
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit("unsupported adapter")
        codes = {finding.code for finding in self.check(head=head)}
        self.assertIn("SCHEMA_VIOLATION", codes)
        self.assertNotIn("EVIDENCE_VALUE_MISMATCH", codes)

    def _gcp_shaped_route(self, route_id: str, reference: str) -> dict:
        return {
            "id": route_id,
            "location": "us-central1",
            "reference": reference,
            "model_binding": {
                "kind": "publisher-model",
                "model_evidence": {
                    "id": "sha256-" + "1" * 64,
                    "id_pointer": "/name",
                    "resource_pointer": "/resourceName",
                    "name_pointer": "/displayName",
                    "provider_pointer": "/publisher",
                },
            },
        }

    def test_gcp_shaped_route_under_aws_bedrock_service_fails_closed_without_crash(self) -> None:
        # offering.schema.json's routes.items is now a provider-agnostic
        # oneOf (widened enum, Phase 1), so a schema-valid offering can
        # resolve to the aws-bedrock adapter while its only route is
        # GCP-shaped. _aws_offering_checks must not KeyError on the missing
        # `source_region`; it must fail this route closed with a diagnostic.
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        offering["routes"][0] = self._gcp_shaped_route(
            "gcp-mismatched", "publishers/google/models/gemini-1.5-pro"
        )
        offering["evidence_refs"] = {}
        offering_path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit("gcp-shaped route under aws-bedrock service")
        findings = self.check(head=head)  # must not raise
        self.assertTrue(any(
            finding.code == "UNKNOWN_REFERENCE" and finding.json_pointer == "/routes/0"
            for finding in findings
        ))

    def test_mixed_offering_route_mismatch_yields_exactly_one_diagnostic_and_preserves_aws_rigor(self) -> None:
        # Distinct from the single-route case above (§6.2 of the wiring
        # plan): one correctly-shaped AWS route and one mismatched
        # GCP-shaped route together in the same aws-bedrock offering must
        # yield exactly one diagnostic (the mismatched route), with the
        # valid AWS sibling route validated with full, unweakened rigor and
        # correctly excluded from the mismatched route's dedup handling.
        # A guard that is accidentally offering-scoped instead of
        # route-scoped would silently pass here (zero diagnostics) or
        # downgrade the valid AWS route too - this test would catch either.
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        mismatched_reference = "publishers/google/models/gemini-1.5-pro"
        offering["routes"].append(
            self._gcp_shaped_route("gcp-mismatched", mismatched_reference)
        )
        availability_evidence = {
            "source": {
                "type": "official-provider-documentation",
                "uri": "https://example.invalid/gcp-vertex-route",
            },
            "retrieved_by": "manual",
            "observed_at": "2026-09-01T00:00:00Z",
            "scope": {},
            "projection": {"reference": mismatched_reference},
            "visibility": "public",
        }
        evidence_identifier = evidence_id(availability_evidence)
        availability_evidence["id"] = evidence_identifier
        evidence_path = self.repository.root / "catalogue/evidence" / f"{evidence_identifier}.yaml"
        evidence_path.write_text(yaml.safe_dump(availability_evidence, sort_keys=False), encoding="utf-8", newline="\n")
        offering["evidence_refs"]["/routes/1/reference"] = {
            "id": evidence_identifier, "projection_pointer": "/reference",
        }
        offering_path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit("mixed aws and gcp-shaped routes")
        findings = self.check(head=head)
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0].code, "UNKNOWN_REFERENCE")
        self.assertEqual(findings[0].json_pointer, "/routes/1")

    def test_schema_valid_gcp_vertex_adapter_has_no_implemented_validator_and_no_evidence_cascade(self) -> None:
        # Genuinely new code path (§6.5 of the wiring plan): once the
        # registry `adapter` enum widens, a service that legitimately
        # registers `gcp-vertex` is schema-VALID and reaches _aws_checks'
        # `else` branch for the first time - unlike
        # test_unsupported_service_adapter_fails_closed above, whose
        # adapter: "unsupported" fails the registry's own SCHEMA_VIOLATION
        # before state.services is ever populated, so that test never
        # reaches this branch at all.
        registry_path = self.repository.root / "catalogue/governance/inference-services.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["inference_services"]["gcp-vertex"] = {
            "id": "gcp-vertex", "adapter": "gcp-vertex",
        }
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8", newline="\n")
        old = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(old.read_text(encoding="utf-8"))
        offering["inference_service_id"] = "gcp-vertex"
        new = self.repository.root / "catalogue/offerings/gcp-vertex/test-offering.yaml"
        new.parent.mkdir(parents=True)
        new.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        old.unlink()
        head = self.repository.commit("schema-valid but unimplemented gcp-vertex adapter")
        findings = self.check(head=head)
        self.assertEqual({finding.code for finding in findings}, {"UNKNOWN_REFERENCE"})


if __name__ == "__main__":
    unittest.main()
