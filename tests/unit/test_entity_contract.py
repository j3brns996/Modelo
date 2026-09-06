"""Entity acceptance regressions: identity, bounded policy and optional facts."""

from copy import deepcopy
from datetime import date
from pathlib import Path, PurePosixPath
import json

import pytest

from modelo.schemas import SchemaSet
from modelo.validators import _load_state, _reference_checks


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def repository():
    # Use the ordinary fixture loader without Git history or repository copying.
    import sys
    sys.path.insert(0, str(ROOT / "tests/fixtures/semantic"))
    from repository import Repository
    repo = Repository()
    try:
        yield repo
    finally:
        repo.close()


@pytest.fixture
def state(repository):
    return _load_state(repository.root)


@pytest.mark.parametrize("status", ["verified", "vendor-asserted", "provider-mapped"])
def test_route_eligible_identity_cannot_bind_two_releases(state, status):
    model = state.models["test-model"]
    model["identity_claims"][0]["status"] = status
    other = deepcopy(model)
    other["id"] = "another-model"
    other.pop("canonical_urn", None)
    state.models[other["id"]] = other
    state.model_paths[other["id"]] = "catalogue/models/another-model.yaml"
    _reference_checks(state)
    assert any("conflicting" in item.message for item in state.diagnostics)


def test_supersession_cycle_is_rejected(state):
    model = state.models["test-model"]
    other = deepcopy(model)
    other.update(id="another-model", identity_claims=[], supersedes_model_id="test-model")
    other.pop("canonical_urn", None)
    state.models[other["id"]] = other
    state.model_paths[other["id"]] = "catalogue/models/another-model.yaml"
    model["supersedes_model_id"] = "another-model"
    _reference_checks(state)
    assert any("cycle" in item.message for item in state.diagnostics)


@pytest.mark.parametrize("status", ["probable", "conflicting", "unresolved"])
def test_disputed_claims_can_be_retained_but_cannot_bind_routes(state, status):
    from modelo.identity import has_provider_claim
    model = state.models["test-model"]
    model["identity_claims"][0]["status"] = status
    assert not has_provider_claim(model, model["identity_claims"][0]["value"])
    other = deepcopy(model)
    other.update(id="another-model")
    other.pop("canonical_urn", None)
    state.models[other["id"]] = other
    state.model_paths[other["id"]] = "catalogue/models/another-model.yaml"
    _reference_checks(state)
    assert not state.diagnostics


@pytest.mark.parametrize("field,kind", [("rights_owner_vendor_id", "model"), ("operator_vendor_id", "service")])
def test_legal_entity_bindings_require_existing_legal_entity(state, field, kind):
    record = state.models["test-model"] if kind == "model" else state.services["aws-bedrock"]
    for identifier in ("missing", "test-vendor"):
        record[field] = identifier
        state.diagnostics.clear()
        _reference_checks(state)
        assert any(item.json_pointer.endswith(field) for item in state.diagnostics)
    state.vendors["test-vendor"]["legal_name"] = "Test Vendor Ltd"
    state.diagnostics.clear()
    _reference_checks(state)
    assert not state.diagnostics  # Evidence is a separate mandatory stage.


def test_optional_legal_facts_require_evidence(state):
    from modelo.validators import _evidence_checks
    state.vendors["test-vendor"].update(legal_name="Test Vendor Ltd", domicile="United Kingdom")
    state.models["test-model"]["licence_uri"] = "https://example.invalid/terms"
    _evidence_checks(state, date(2026, 9, 1))
    assert {"/legal_name", "/domicile", "/licence_uri"} <= {d.json_pointer for d in state.diagnostics}


def test_evidenced_legal_facts_and_licence_are_accepted(state):
    from modelo.evidence import evidence_id
    from modelo.validators import _evidence_checks
    observation = deepcopy(next(iter(state.evidence.values())))
    observation["projection"] = {"legal_name": "Test Vendor Ltd", "domicile": "United Kingdom", "licence_uri": "https://example.invalid/terms"}
    observation["id"] = evidence_id(observation)
    state.evidence[observation["id"]] = observation
    state.evidence_paths[observation["id"]] = f"catalogue/evidence/{observation['id']}.yaml"
    for field in ("legal_name", "domicile", "licence_uri"):
        record = state.models["test-model"] if field == "licence_uri" else state.vendors["test-vendor"]
        record[field] = observation["projection"][field]
        record["evidence_refs"][f"/{field}"] = {"id": observation["id"], "projection_pointer": f"/{field}"}
    _evidence_checks(state, date(2026, 9, 1))
    assert not state.diagnostics


def test_bounded_approval_and_optional_facts_schema(state):
    schema = state.schemas
    offering = deepcopy(state.offerings["test-offering"])
    assert not schema.validate("offering.schema.json", offering, "offering.yaml")
    for field in ("approval_owner", "approved_use"):
        for value in (None, "", "  ", "x" * 2049):
            invalid = dict(offering, **{field: value})
            assert schema.validate("offering.schema.json", invalid, "offering.yaml")
        invalid = dict(offering)
        del invalid[field]
        assert schema.validate("offering.schema.json", invalid, "offering.yaml")
    offering["condition_refs"] = []
    assert schema.validate("offering.schema.json", offering, "offering.yaml")
    offering["no_conditions_rationale"] = "Isolated synthetic tests have no additional use conditions."
    assert not schema.validate("offering.schema.json", offering, "offering.yaml")
    offering["condition_refs"] = [{"id": "test-condition", "version": 1}]
    assert schema.validate("offering.schema.json", offering, "offering.yaml")
    vendor = deepcopy(state.vendors["test-vendor"])
    vendor["domicile"] = "United Kingdom"
    assert schema.validate("vendors-registry.schema.json", {"vendors": {"test-vendor": vendor}}, "vendors.yaml")


@pytest.mark.parametrize("raw,match", [('{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://example.invalid/a","type":"object","type":"string"}', "duplicate JSON key"), ('{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://example.invalid/a","type":"object"}', "duplicate schema")])
def test_schema_identity_is_unambiguous(tmp_path, raw, match):
    directory = tmp_path / "schemas"
    directory.mkdir()
    (directory / "a.schema.json").write_text(raw)
    (directory / "b.schema.json").write_text(raw)
    with pytest.raises(ValueError, match=match):
        SchemaSet(tmp_path, PurePosixPath("schemas"))


@pytest.mark.parametrize("review_by,overdue", [(None, False), ("2026-09-01", False), ("2026-08-31", True), ("2026-09-02", False)])
def test_review_deadline_is_inclusive_and_does_not_mutate_records(repository, review_by, overdue):
    from modelo.validators import _validate_state
    import yaml
    path = repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
    original = path.read_bytes()
    try:
        offering = yaml.safe_load(original)
        if review_by is not None:
            offering["review_by"] = review_by
        path.write_text(yaml.safe_dump(offering, sort_keys=False))
        before = path.read_bytes()
        findings = _validate_state(repository.root, date(2026, 9, 1)).diagnostics
        assert any(d.json_pointer == "/review_by" for d in findings) == overdue
        assert path.read_bytes() == before
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize("relative", ["catalogue/models/wrong-id.yaml", "catalogue/model/test-model.yaml", "catalogue/governance/unrecognised.yaml"])
def test_wrong_record_location_is_not_silently_accepted(repository, relative):
    target = repository.root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((repository.root / "catalogue/models/test-model.yaml").read_bytes())
    try:
        findings = _load_state(repository.root).diagnostics
        assert any(d.path == relative and d.code == "PATH_IDENTITY_MISMATCH" for d in findings)
    finally:
        target.unlink()


def test_approval_scope_is_visible_and_escaped(state):
    from modelo.site import _approval_scope
    offering = dict(state.offerings["test-offering"], approved_use="Summarise <private> data & check outputs", approval_owner="Team <A>")
    html = _approval_scope(offering)
    assert "Summarise &lt;private&gt; data &amp; check outputs" in html
    assert "Team &lt;A&gt;" in html
    assert "Event-triggered review" in html
    offering["review_by"] = "2026-10-01"
    assert "2026-10-01" in _approval_scope(offering)


def test_schema_profile_matches_published_acceptance_contract(state):
    import yaml
    from modelo.identity import ENTITY_PROFILE
    contract = yaml.safe_load((ROOT / "docs/contract.yaml").read_text(encoding="utf-8"))
    assert contract["entity_acceptance"]["profile"] == ENTITY_PROFILE
    assert state.schemas.schema("model.schema.json")["x-modelo-entity-profile"] == ENTITY_PROFILE
    assert contract["entity_acceptance"]["semantic_adapters"] == ["aws-bedrock"]
    for schema in contract["entity_acceptance"]["source_schemas"].values():
        assert schema in state.schemas.documents


def test_offering_ids_remain_global_and_route_ids_are_local(state):
    # Two different offerings may use the same local route ID. A copied global
    # offering ID in a different directory is checked by the ordinary loader.
    offering = deepcopy(state.offerings["test-offering"])
    offering["id"] = "another-offering"
    state.offerings[offering["id"]] = offering
    state.offering_paths[offering["id"]] = "catalogue/offerings/aws-bedrock/another-offering.yaml"
    _reference_checks(state)
    assert not state.diagnostics
    offering["routes"].append(deepcopy(offering["routes"][0]))
    _reference_checks(state)
    assert any("route ids are not unique" in d.message for d in state.diagnostics)


def test_supersession_deep_chain_is_iterative(state):
    template = state.models["test-model"]
    for index in range(5000):
        identifier = f"release-{index}"
        model = dict(template, id=identifier, identity_claims=[])
        model.pop("canonical_urn", None)
        if index:
            model["supersedes_model_id"] = f"release-{index - 1}"
        state.models[identifier] = model
        state.model_paths[identifier] = f"catalogue/models/{identifier}.yaml"
    _reference_checks(state)
    assert not state.diagnostics
    state.models["release-0"]["supersedes_model_id"] = "release-4999"
    _reference_checks(state)
    assert any("cycle" in item.message for item in state.diagnostics)
