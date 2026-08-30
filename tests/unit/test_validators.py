from __future__ import annotations

from datetime import date
import unittest
import sys
from pathlib import Path

import yaml

from modelo.validators import check_repository

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/fixtures/semantic"))
from repository import Repository  # noqa: E402


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Repository()

    def tearDown(self) -> None:
        self.repository.close()

    def check(self, base: str | None = None, head: str | None = None, as_of: date = date(2026, 8, 30)):
        return check_repository(
            self.repository.root,
            base or self.repository.base,
            head or self.repository.base,
            as_of,
        )

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
        profile_id = "sha256-b244dda1f4b5af9ba1e9bc74c62ca910261eb3d50c9b7cab80c59a5ab91ca5fe"
        profile = {
            "id": profile_id,
            "source": {"type": "first-party-read-api", "provider": "aws", "service": "bedrock", "operation": "GetInferenceProfile", "partition": "aws", "region": "eu-west-2", "sanitised_parameters": {"inferenceProfileIdentifier": "eu.test.profile-v1"}, "documentation_uri": "https://example.invalid/aws-profile-api"},
            "retrieved_by": "cli", "observed_at": "2026-08-01T00:00:00Z",
            "scope": {"scope_ref": "synthetic", "region": "eu-west-2"},
            "projection": {"profileId": "eu.test.profile-v1", "models": [{"modelArn": "arn:aws:bedrock:eu-west-2::foundation-model/test.model-v1"}]},
            "visibility": "public",
        }
        evidence_path = self.repository.root / "catalogue/evidence" / f"{profile_id}.yaml"
        evidence_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8", newline="\n")
        offering_path = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = yaml.safe_load(offering_path.read_text(encoding="utf-8"))
        offering["routes"][0] = {
            "id": "eu-profile", "adapter": "aws-bedrock", "reference": "eu.test.profile-v1",
            "model_binding": {"kind": "system-inference-profile", "profile_evidence": {"id": profile_id, "projection_pointer": "/profileId"}, "destinations": [{"destination_pointer": "/models/0/modelArn", "model_evidence": {"id": "sha256-3cc6bbaee52dff309202c8aed63c219a8277199cadafdbeeac3b0e2c91c746fb", "arn_pointer": "/modelArn", "name_pointer": "/modelName", "provider_pointer": "/providerName"}}]},
        }
        offering["evidence_refs"]["/routes/0/reference"] = {"id": profile_id, "projection_pointer": "/profileId"}
        offering_path.write_text(yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n")
        head = self.repository.commit()
        self.assertEqual(self.check(head=head), ())


if __name__ == "__main__":
    unittest.main()
