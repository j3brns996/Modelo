from copy import deepcopy
from datetime import date
from pathlib import Path
import re

import yaml

from modelo.assurance import DISCLAIMER, MAPPING_PATH, reverse_mapping, validate_mapping
from modelo.identity import ENTITY_PROFILE

ROOT = Path(__file__).resolve().parents[2]


def mapping():
    return yaml.safe_load((ROOT / MAPPING_PATH).read_text())


def test_mapping_validates_and_reverse_index_is_deterministic():
    document = mapping()
    assert not validate_mapping(ROOT, document, as_of=date(2026, 9, 6))
    reversed_document = deepcopy(document)
    reversed_document["mappings"].reverse()
    assert reverse_mapping(document) == reverse_mapping(reversed_document)
    for item in document["mappings"]:
        assert all(item["id"] in reverse_mapping(document)[path] for path in item["artefacts"])


def test_mapping_rejects_bad_claims_and_missing_artefacts():
    for field, value in [("current_level", "certified"), ("artefacts", ["missing.file"]), ("source", "https://example.invalid/not-nist")]:
        document = mapping()
        document["mappings"][0][field] = value
        assert validate_mapping(ROOT, document, as_of=date(2026, 9, 6))
    document = mapping()
    document["disclaimer"] = "NIST compliant"
    assert validate_mapping(ROOT, document, as_of=date(2026, 9, 6))


def test_operating_equivalence_cannot_be_inferred_from_forms_or_tests():
    document = mapping()
    item = document["mappings"][0]
    item["current_level"] = "O"
    assert validate_mapping(ROOT, document, as_of=date(2026, 9, 6))
    item["operating_assessments"] = [{"period_start": "2026-08-01", "period_end": "2026-09-01", "assessor": "example", "population": "synthetic", "findings": "tests passed", "evidence_refs": ["README.md"], "remediation": "none", "independent_review_ref": "example"}]
    assert any("non-operating" in error for error in validate_mapping(ROOT, document, as_of=date(2026, 9, 6)))
    item["operating_assessments"][0]["period_end"] = "2099-01-01"
    assert any("elapsed period" in error for error in validate_mapping(ROOT, document, as_of=date(2026, 9, 6)))


def test_contract_mapping_maturity_and_site_do_not_drift():
    contract = yaml.safe_load((ROOT / "docs/contract.yaml").read_text())
    profile = contract["assurance"]
    assert profile["current_levels"] == {item["id"]: item["current_level"] for item in mapping()["mappings"]}
    assert contract["entities"]["model"]["entity_acceptance_profile"] == ENTITY_PROFILE
    assert profile["target_product_maturity"] == "M1"
    assert profile["production_operating_maturity"] == "unproven"
    assert contract["approval"]["agent_approval"]["enabled"] is False
    assert contract["approval"]["consumption_granted_only_by_current_offering"] is True
    assert profile["covered_by_parent_is_governance_exemption"] is False
    assert mapping()["disclaimer"] == DISCLAIMER
    site = (ROOT / "site/content/docs.md").read_text()
    for statement in ["Supports selected NIST AI RMF outcomes", "Not a certification", "Not a complete organisational AI-system inventory"]:
        assert statement in site
    maturity = (ROOT / "docs/assurance/modelo-maturity-profile.md").read_text()
    for marker in ["Target contract", "Locally implemented", "Remotely proven", "Production operating", "T10", "organisation-defined"]:
        assert marker in maturity


def test_diagrams_and_external_examples_are_not_catalogue_authority():
    document = (ROOT / "docs/adr/0003-ai-inventory-boundary.md").read_text()
    assert "erDiagram" in document and "sequenceDiagram" in document
    for entity in ["MODEL_RELEASE", "IDENTITY_CLAIM", "OFFERING", "ROUTE", "CONDITION", "EVIDENCE", "MAC", "AI_USE_BINDING"]:
        assert entity in document
    coverage = (ROOT / "docs/assurance/embedded-ai-coverage.md").read_text()
    examples = re.findall(r"```yaml\n(.*?)```", document + "\n" + coverage, re.S)
    assert {yaml.safe_load(example)["kind"] for example in examples} == {"AIUseBinding", "InventoryCoverageDetermination"}
    assert "not-disclosed" in coverage and "It is not exempt" in coverage
    eli = (ROOT / "docs/eli21.md").read_text()
    assert len(eli.split()) < 800
    assert "covered-by-parent" in eli and "not production" in eli
