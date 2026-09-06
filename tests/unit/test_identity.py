from copy import deepcopy
from datetime import date
import json
from pathlib import Path, PurePosixPath
import sys

import pytest
import yaml

from modelo.identity import canonical_urn, migrate_bound_model, migrate_offering, release_precision
from modelo.mac import compute_keys, validate_payload
from modelo.schemas import SchemaSet
from modelo.validators import _validate_state, check_repository

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/fixtures/semantic"))
from repository import Repository


@pytest.fixture
def repo():
    instance = Repository()
    yield instance
    instance.close()


def read(repo, path):
    return yaml.safe_load((repo.root / path).read_text())


def write(repo, path, document):
    (repo.root / path).write_text(yaml.safe_dump(document, sort_keys=False))


MODEL = "catalogue/models/test-model.yaml"
OFFERING = "catalogue/offerings/aws-bedrock/test-offering.yaml"


def test_urns_are_deterministic_internal_not_universal():
    assert canonical_urn("model-release", "test-model") == "urn:modelo:model-release:test-model"
    assert canonical_urn("offering", "test-offering") == "urn:modelo:offering:test-offering"
    for value in ["../test", "test\n", "", "vendor/model", "A"]:
        with pytest.raises(ValueError):
            canonical_urn("model-release", value)
    assert release_precision({"id": "test"}) == "named-release"


def test_optional_external_identity_and_named_release_schema():
    schemas = SchemaSet(ROOT, PurePosixPath("schemas"))
    model = {"id": "release", "vendor_id": "vendor", "name": "Release", "evidence_refs": {}}
    assert not schemas.validate("model.schema.json", model, "model.yaml")
    model["release"] = {"vendor_label": "Release", "precision": "family"}
    assert schemas.validate("model.schema.json", model, "model.yaml")


@pytest.mark.parametrize("mutation", ["missing-evidence", "bad-namespace", "bad-status", "wrong-urn", "family-is-release", "no-claim", "missing-selector", "false-immutable", "floating-selector", "no-binding"])
def test_identity_and_selector_fail_closed(repo, mutation):
    model, offering = read(repo, MODEL), read(repo, OFFERING)
    if mutation == "missing-evidence":
        del model["evidence_refs"]["/identity_claims/0/value"]
    elif mutation == "bad-namespace":
        model["identity_claims"][0]["namespace"] = "invalid namespace"
    elif mutation == "bad-status":
        model["identity_claims"][0]["status"] = "certain"
    elif mutation == "wrong-urn":
        model["canonical_urn"] = "urn:modelo:model-release:other"
    elif mutation == "family-is-release":
        model["family_id"] = model["id"]
    elif mutation == "no-claim":
        del model["identity_claims"]  # unchanged display names do not prove identity
    elif mutation == "missing-selector":
        del offering["routes"][0]["selector_type"]
    elif mutation == "false-immutable":
        offering["routes"][0]["selector_type"] = "immutable-version"
    elif mutation == "floating-selector":
        offering["routes"][0]["selector_type"] = "floating-alias"
    else:
        del offering["routes"][0]["model_binding"]
    write(repo, MODEL, model)
    write(repo, OFFERING, offering)
    assert _validate_state(repo.root, date(2026, 9, 1)).diagnostics


def test_verified_identity_cannot_identify_two_releases(repo):
    model = read(repo, MODEL)
    model["identity_claims"][0]["status"] = "verified"
    write(repo, MODEL, model)
    second = deepcopy(model)
    second["id"] = "different-release"
    second["canonical_urn"] = canonical_urn("model-release", second["id"])
    write(repo, "catalogue/models/different-release.yaml", second)
    assert any("conflicting verified" in d.message for d in _validate_state(repo.root, date(2026, 9, 1)).diagnostics)


def test_offering_cannot_inherit_another_release(repo):
    second = read(repo, MODEL)
    second["id"] = "different-release"
    second["canonical_urn"] = canonical_urn("model-release", second["id"])
    write(repo, "catalogue/models/different-release.yaml", second)
    offering = read(repo, OFFERING)
    offering["model_id"] = second["id"]
    write(repo, OFFERING, offering)
    head = repo.commit()
    assert any("inherit approval" in d.message for d in check_repository(repo.root, repo.base, head, date(2026, 9, 1)))


def test_release_precision_cannot_silently_change(repo):
    model = read(repo, MODEL)
    model["release"] = {"vendor_label": model["name"], "precision": "immutable-snapshot"}
    model["evidence_refs"]["/release/vendor_label"] = deepcopy(model["evidence_refs"]["/name"])
    write(repo, MODEL, model)
    head = repo.commit()
    assert any("release identity or precision" in d.message for d in check_repository(repo.root, repo.base, head, date(2026, 9, 1)))


def test_retired_offering_id_cannot_be_reused(repo):
    offering = read(repo, OFFERING)
    (repo.root / OFFERING).unlink()
    retired = repo.commit("retire")
    write(repo, OFFERING, offering)
    head = repo.commit("reuse")
    assert any("reserved in accepted history" in d.message for d in check_repository(repo.root, retired, head, date(2026, 9, 1)))


def test_migration_is_explicit_idempotent_and_preserves_evidence(repo):
    original = read(repo, MODEL)
    model = deepcopy(original)
    del model["identity_claims"]
    del model["canonical_urn"]
    del model["evidence_refs"]["/identity_claims/0/value"]
    evidence_id = original["evidence_refs"]["/name"]["id"]
    record = read(repo, f"catalogue/evidence/{evidence_id}.yaml")
    before = deepcopy(record)
    result = migrate_bound_model(model, record, id_pointer="/modelId", reviewed_model_id=model["id"])
    assert result == original
    assert migrate_bound_model(result, record, id_pointer="/modelId", reviewed_model_id=model["id"]) == result
    assert record == before
    assert "identity_claims" not in model
    with pytest.raises(ValueError):
        migrate_bound_model(model, record, id_pointer="/modelId", reviewed_model_id="guessed-from-name")


def test_one_batch_add_contains_model_offering_evidence():
    payload = json.loads((ROOT / "tests/fixtures/mac/batch.json").read_text())
    payload["subjects"] = [{"kind": "model", "identity": "test-model"}, {"kind": "offering", "identity": "test-offering"}, {"kind": "evidence", "identity": "sha256-" + "a" * 64}]
    payload["dedupe_key"], payload["idempotency_key"] = compute_keys(payload)
    validate_payload(payload)


def test_legacy_named_release_label_cannot_change(repo):
    model = read(repo, MODEL)
    model["name"] = "Different Release"
    write(repo, MODEL, model)
    head = repo.commit()
    assert any("release identity or precision" in d.message for d in check_repository(repo.root, repo.base, head, date(2026, 9, 1)))


def test_provider_id_and_arn_cannot_be_cherry_picked(repo):
    from modelo.evidence import evidence_id
    offering = read(repo, OFFERING)
    binding = offering["routes"][0]["model_binding"]["model_evidence"]
    record = read(repo, f"catalogue/evidence/{binding['id']}.yaml")
    record["projection"]["modelArn"] = "arn:aws:bedrock:eu-west-2::foundation-model/different.release-v2"
    record["id"] = evidence_id(record)
    write(repo, f"catalogue/evidence/{record['id']}.yaml", record)
    binding["id"] = record["id"]
    offering["evidence_refs"]["/routes/0/reference"]["id"] = record["id"]
    write(repo, OFFERING, offering)
    assert any("ARN identity" in d.message for d in _validate_state(repo.root, date(2026, 9, 1)).diagnostics)


def test_combined_migration_restores_semantic_acceptance(repo):
    model, offering = read(repo, MODEL), read(repo, OFFERING)
    record = read(repo, f"catalogue/evidence/{model['evidence_refs']['/name']['id']}.yaml")
    del model["identity_claims"]
    del model["canonical_urn"]
    del model["evidence_refs"]["/identity_claims/0/value"]
    del offering["routes"][0]["selector_type"]
    write(repo, MODEL, model)
    write(repo, OFFERING, offering)
    assert _validate_state(repo.root, date(2026, 9, 1)).diagnostics
    write(repo, MODEL, migrate_bound_model(model, record, id_pointer="/modelId", reviewed_model_id=model["id"]))
    migrated = migrate_offering(offering)
    assert migrate_offering(migrated) == migrated
    assert migrated["routes"][0]["selector_type"] == "provider-model-id"
    write(repo, OFFERING, migrated)
    assert not _validate_state(repo.root, date(2026, 9, 1)).diagnostics
    offering["routes"][0]["selector_type"] = "immutable-version"
    with pytest.raises(ValueError):
        migrate_offering(offering)


def test_model_id_cannot_be_reintroduced_after_historical_removal(repo):
    model = read(repo, MODEL)
    (repo.root / MODEL).unlink()
    (repo.root / OFFERING).unlink()
    removed = repo.commit("historical invalid removal")
    write(repo, MODEL, model)
    head = repo.commit("reuse model")
    assert any("reserved in accepted history" in d.message for d in check_repository(repo.root, removed, head, date(2026, 9, 1)))


def test_relocated_offering_still_cannot_change_release(repo):
    registry_path = "catalogue/governance/inference-services.yaml"
    registry = read(repo, registry_path)
    registry["inference_services"]["bedrock-alias"] = {"id": "bedrock-alias", "adapter": "aws-bedrock"}
    write(repo, registry_path, registry)
    model = read(repo, MODEL)
    model["id"] = "second-model"
    model["canonical_urn"] = canonical_urn("model-release", model["id"])
    write(repo, "catalogue/models/second-model.yaml", model)
    offering = read(repo, OFFERING)
    offering["model_id"] = model["id"]
    offering["inference_service_id"] = "bedrock-alias"
    target = "catalogue/offerings/bedrock-alias/test-offering.yaml"
    (repo.root / target).parent.mkdir()
    write(repo, target, offering)
    (repo.root / OFFERING).unlink()
    head = repo.commit()
    assert any("relocated Offering" in d.message for d in check_repository(repo.root, repo.base, head, date(2026, 9, 1)))


@pytest.mark.parametrize("second_region,expected_error", [("eu-west-2", False), ("eu-west-1", True)])
def test_profile_routes_must_share_destination_residency(repo, second_region, expected_error):
    from modelo.evidence import evidence_id
    from modelo.validators import _load_state, _aws_offering_checks
    state = _load_state(repo.root)
    offering = deepcopy(state.offerings["test-offering"])
    original_binding = offering["routes"][0]["model_binding"]["model_evidence"]
    source = state.evidence[original_binding["id"]]
    offering["routes"] = []
    offering["evidence_refs"] = {}
    for index, region in enumerate(["eu-west-2", second_region]):
        model_record = deepcopy(source)
        model_record["source"]["region"] = region
        model_record["scope"]["region"] = region
        arn = f"arn:aws:bedrock:{region}::foundation-model/test.model-v1"
        model_record["projection"]["modelArn"] = arn
        model_record["id"] = evidence_id(model_record)
        state.evidence[model_record["id"]] = model_record
        reference = f"eu.test.profile-{index}"
        profile = {"source": {"type": "first-party-read-api", "provider": "aws", "service": "bedrock", "operation": "GetInferenceProfile", "partition": "aws", "region": "eu-west-2"}, "projection": {"profileId": reference, "type": "SYSTEM_DEFINED", "status": "ACTIVE", "models": [{"modelArn": arn}]}}
        profile["id"] = evidence_id(profile)
        state.evidence[profile["id"]] = profile
        binding = deepcopy(original_binding)
        binding["id"] = model_record["id"]
        offering["routes"].append({"id": f"profile-{index}", "source_region": "eu-west-2", "selector_type": "inference-profile", "reference": reference, "model_binding": {"kind": "system-inference-profile", "profile_evidence": {"id": profile["id"], "projection_pointer": "/profileId", "type_pointer": "/type", "status_pointer": "/status", "destinations_pointer": "/models"}, "destinations": [{"destination_pointer": "/models/0/modelArn", "model_evidence": binding}]}})
        offering["evidence_refs"][f"/routes/{index}/reference"] = {"id": profile["id"], "projection_pointer": "/profileId"}
    _aws_offering_checks(state, offering, OFFERING)
    assert bool(state.diagnostics) == expected_error, state.diagnostics
    if expected_error:
        assert all("destination residency scope" in d.message for d in state.diagnostics)
