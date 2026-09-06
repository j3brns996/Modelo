"""Reproducible mixed-file capacity check; timings are observations, not SLAs."""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
from time import perf_counter

from modelo.evidence import evidence_id
from modelo.receipt import canonical_bytes, catalogue_projection
from modelo.validators import _load_state, _validate_state, check_repository


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/fixtures/semantic"))
from repository import Repository


def test_5000_mixed_entities_through_files_history_and_projection():
    repo = Repository()
    try:
        initial = _load_state(repo.root)
        model = initial.models["test-model"]
        offering = initial.offerings["test-offering"]
        observation = initial.evidence[model["evidence_refs"]["/name"]["id"]]

        def write(path, value):
            target = repo.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value) + "\n", encoding="utf-8")

        # JSON is a supported YAML subset and still passes the ordinary bounded
        # YAML parser. Every generated provider identity has its own observation.
        for index in range(1663):
            identifier = f"scale-{index}"
            provider_id = f"test.scale-{index}"
            evidence = deepcopy(observation)
            evidence["source"]["sanitised_parameters"]["modelIdentifier"] = provider_id
            evidence["projection"]["modelId"] = provider_id
            evidence["projection"]["modelArn"] = f"arn:aws:bedrock:eu-west-2::foundation-model/{provider_id}"
            evidence["id"] = evidence_id(evidence)
            candidate = deepcopy(model)
            candidate.update(id=identifier, canonical_urn=f"urn:modelo:model-release:{identifier}")
            candidate["identity_claims"][0]["value"] = provider_id
            for reference in candidate["evidence_refs"].values():
                reference["id"] = evidence["id"]
            if index:
                candidate["supersedes_model_id"] = f"scale-{index - 1}"
            access = deepcopy(offering)
            access.update(id=identifier, model_id=identifier)
            access["routes"][0]["reference"] = provider_id
            access["routes"][0]["model_binding"]["model_evidence"]["id"] = evidence["id"]
            access["evidence_refs"]["/routes/0/reference"]["id"] = evidence["id"]
            write(f"catalogue/models/{identifier}.yaml", candidate)
            write(f"catalogue/offerings/aws-bedrock/{identifier}.yaml", access)
            write(f"catalogue/evidence/{evidence['id']}.yaml", evidence)

        count = sum(len(getattr(initial, key)) for key in ("models", "offerings", "evidence", "conditions", "vendors", "services")) + 1663 * 3
        for index in range(5000 - count):
            candidate = deepcopy(model)
            candidate.update(id=f"unbound-{index}", identity_claims=[])
            candidate.pop("canonical_urn", None)
            candidate["evidence_refs"].pop("/identity_claims/0/value")
            write(f"catalogue/models/unbound-{index}.yaml", candidate)
        head = repo.commit("5000 synthetic entities")
        timings = {}
        start = perf_counter()
        state = _validate_state(repo.root, date(2026, 9, 1))
        timings["load_schema_semantics_seconds"] = round(perf_counter() - start, 3)
        assert not state.diagnostics, state.diagnostics[:5]
        counts = {key: len(getattr(state, key)) for key in ("models", "offerings", "evidence", "conditions", "vendors", "services")}
        assert sum(counts.values()) == 5000
        print(json.dumps({"counts": counts, **timings}), flush=True)

        start = perf_counter()
        assert not check_repository(repo.root, head, head, date(2026, 9, 1))
        timings["full_git_check_seconds"] = round(perf_counter() - start, 3)
        # Exercise the changed-path index with a real bulk policy update, not
        # only the base=head scheduled-audit shortcut.
        for identifier, access in state.offerings.items():
            changed = dict(access, approval_rationale="Updated synthetic capacity-test policy; no production permission.")
            write(state.offering_paths[identifier], changed)
        changed_head = repo.commit("bulk synthetic offering policy update")
        start = perf_counter()
        assert not check_repository(repo.root, head, changed_head, date(2026, 9, 1))
        timings["bulk_offering_change_check_seconds"] = round(perf_counter() - start, 3)
        start = perf_counter()
        projection = catalogue_projection(contract_version="0.1.0", source_commit=head,
            source_tree=repo.git("rev-parse", "HEAD^{tree}").strip(), as_of="2026-09-01", profile="synthetic",
            models=state.models.values(), offerings=state.offerings.values(), evidence=state.evidence.values(),
            conditions=state.conditions.values(), vendors={"vendors": state.vendors},
            inference_services={"inference_services": state.services}, freshness={"classes_days": state.thresholds})
        assert not state.schemas.validate("catalogue-output.schema.json", projection, "catalogue.json")
        raw = canonical_bytes(projection)
        timings["projection_schema_and_serialisation_seconds"] = round(perf_counter() - start, 3)
        print(json.dumps({"counts": counts, "publication_bytes": len(raw), **timings}), flush=True)
    finally:
        repo.close()
