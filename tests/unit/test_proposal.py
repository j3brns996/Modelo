import json
from pathlib import Path

import yaml
from modelo.guided_intake import _FIELD_LABELS, _FIELD_ORDER, _compile_payload, _issue_sections
from modelo.proposal import OPERATIONS, lookup_records, render_fields, render_gitlab_template

ROOT = Path(__file__).resolve().parents[2]
FIELDS = json.loads((ROOT / "site/content/proposal-fields.json").read_text(encoding="utf-8"))


def answers(payload):
    subjects = payload["subjects"]
    values = {
        "request_type": payload["operation"],
        "subject_kind": subjects[0]["kind"],
        "subject_identity": subjects[0]["identity"],
        "offering_identity": subjects[0]["identity"],
        "source_identity": subjects[0]["identity"],
        "destination_identity": subjects[-1]["identity"],
        "subject_identities": "\n".join(item["identity"] for item in subjects),
        "purpose": payload["purpose"],
        "requested_outcome": payload["requested_outcome"],
        "reason": payload["reason"],
        "acceptance": "\n".join(payload["acceptance"]),
        "candidate_evidence": "\n".join(
            " | ".join((item["uri"], item["observed_at"], item["digest"]))
            for item in payload["candidate_evidence"]
        ),
    }
    if payload["operation"] == "batch":
        scope = payload["batch_scope"]
        values.update(
            item_operation=payload["item_operation"],
            source_type=scope["source"]["type"],
            source_url=scope["source"]["uri"],
            inference_service=scope["inference_service_id"],
            **scope["observation_scope"],
        )
    return values


def test_guides_and_provider_forms_share_fields_and_round_trip_all_operations():
    config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
    lookup = (
        config["site"]["base_url"].rstrip("/")
        + config["site"]["routes"]["propose"]
        + "#lookup-requested_outcome"
    )
    assert [field["name"] for field in FIELDS] == [
        key for key in _FIELD_ORDER if key != "final_checks"
    ]
    for operation in OPERATIONS:
        template = render_gitlab_template(operation, FIELDS, lookup)
        assert template == (ROOT / f".gitlab/issue_templates/MAC-{operation.title()}.md").read_text(
            encoding="utf-8"
        )
        fixture = json.loads(
            (ROOT / f"tests/fixtures/mac/{operation}.json").read_text(encoding="utf-8")
        )
        values = answers(fixture)
        for field in FIELDS:
            if operation in field["operations"] and field["name"] != "request_type":
                template = template.replace(
                    f"### {field['label']}\n\n_No response_",
                    f"### {field['label']}\n\n{values[field['name']] or '_No response_'}",
                )
        for labels in (("Request type",), ("Modelo MAC request type", "Request type")):
            parsed = _compile_payload(
                _issue_sections(template, labels),
                "https://gitlab.example.invalid/group/project/-/issues/1",
                labels[0],
            )
            for key in fixture.keys() - {"request_id", "dedupe_key", "idempotency_key"}:
                assert parsed[key] == fixture[key], (operation, key)
        assert "- [x]" not in template
        form = yaml.safe_load(
            (ROOT / f".github/ISSUE_TEMPLATE/mac-{operation}.yml").read_text(encoding="utf-8")
        )
        for entry in form["body"]:
            if not entry.get("id") or entry["id"] == "final_checks":
                continue
            attrs = entry["attributes"]
            name = (
                "request_type" if entry["id"] == "request_type" else _FIELD_LABELS[attrs["label"]]
            )
            definition = next(field for field in FIELDS if field["name"] == name)
            assert attrs["description"].startswith(definition["help"])
            if definition["type"] == "dropdown":
                assert entry["type"] == "input", (
                    "GitHub URL transport must use prefillable text controls"
                )
                assert attrs["value"] == (
                    operation if name == "request_type" else definition["options"][0]
                )
                for choice in [operation] if name == "request_type" else definition["options"]:
                    assert "`" + choice + "`" in attrs["description"]


def test_lookup_uses_only_supplied_publication_records_and_preserves_condition_versions():
    catalogue = {
        "models": [{"id": "public", "name": "Visible <model>", "vendor_id": "vendor"}],
        "offerings": [],
        "evidence": [],
        "conditions": [
            {"id": "rule", "version": 1, "title": "First"},
            {"id": "rule", "version": 2, "title": "Second"},
        ],
        "vendors": {"vendors": {}},
        "inference_services": {"inference_services": {}},
    }
    records = lookup_records(catalogue)
    assert {item["reference"] for item in records} == {"public", "rule@1", "rule@2"}
    assert all(set(item) <= {"kind", "id", "reference", "label", "observation"} for item in records)
    fields = [{**FIELDS[0], "help": "<script>bad</script>", "label": "<unsafe>"}]
    rendered = render_fields(fields)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert "&lt;unsafe&gt;" in rendered
    controls = render_fields(FIELDS)
    for name in (
        "subject_identity",
        "offering_identity",
        "inference_service",
        "requested_outcome",
        "candidate_evidence",
    ):
        assert f'data-lookup="{name}"' in controls
        assert f'aria-describedby="help-{name} error-{name}"' in controls


def test_evidence_lookup_converts_observation_to_utc():
    catalogue = {
        "models": [],
        "offerings": [],
        "conditions": [],
        "vendors": {"vendors": {}},
        "inference_services": {"inference_services": {}},
        "evidence": [
            {
                "id": "sha256-" + "a" * 64,
                "observed_at": "2026-09-01T10:00:00+01:00",
                "source": {"uri": "https://example.invalid/docs"},
            }
        ],
    }
    assert " | 2026-09-01T09:00:00Z | " in lookup_records(catalogue)[0]["observation"]
