from __future__ import annotations

from uuid import UUID

import pytest

from modelo.gitlab_adapter import compile_gitlab_intake
from modelo.mac import MacError, extract_adapter_issue_payload, validate_payload


def issue_body(**sections: str) -> str:
    return "\n\n".join(f"### {label}\n\n{value}" for label, value in sections.items()) + "\n"


def event(body: str, iid: int = 43) -> dict[str, object]:
    return {
        "project": {"path_with_namespace": "j3brns996/Modelo"},
        "object_attributes": {"iid": iid, "state": "opened", "description": body},
    }


def common(operation: str) -> dict[str, str]:
    return {
        "Request type": operation,
        "Subject type": "model",
        "Subject identity": "example-model-v1",
        "Purpose": "Make the model available for a reviewed workload",
        "Requested outcome": "Add one evidenced model record to the catalogue.",
        "Why is this needed?": "The platform team needs a governed record before proposing an offering.",
        "Supporting observations": "https://example.invalid/model | 2026-09-02T08:00:00Z | sha256-" + "1" * 64,
        "Acceptance checks": "The model name matches the retained evidence.\nThe record passes Modelo validation.",
    }


def test_gitlab_guided_add_compiles_to_the_existing_neutral_contract() -> None:
    result = compile_gitlab_intake(event(issue_body(**common("add"))))
    assert result.valid
    payload = validate_payload(result.payload)
    assert UUID(payload["request_id"]).version == 5
    assert payload["operation"] == "add"
    assert payload["subjects"] == [{"kind": "model", "identity": "example-model-v1"}]
    assert len(payload["candidate_evidence"]) == 1
    assert len(payload["acceptance"]) == 2
    assert extract_adapter_issue_payload(result.issue_body, "gitlab") == payload
    assert "Proposal ready" in result.comment_body
    assert "Copy into the merge request" in result.comment_body


def test_gitlab_guided_move_and_batch_compile_operation_specific_fields() -> None:
    move = common("move")
    move.pop("Subject type"); move.pop("Subject identity")
    move["Current offering identity"] = "bedrock-model-old"
    move["Replacement offering identity"] = "bedrock-model-new"
    moved = compile_gitlab_intake(event(issue_body(**move)))
    assert moved.payload["subjects"] == [
        {"kind": "offering", "identity": "bedrock-model-old", "role": "source"},
        {"kind": "offering", "identity": "bedrock-model-new", "role": "destination"},
    ]

    batch = common("batch")
    batch.pop("Subject identity")
    batch.update({
        "Batch change type": "add",
        "Subject type": "offering",
        "Subject identities": "bedrock-model-a\nbedrock-model-b",
        "Evidence source type": "first-party-read-api",
        "Evidence source URL": "https://bedrock.us-east-1.amazonaws.com/foundation-models",
        "Opaque scope reference": "production-scope",
        "Provider partition": "aws",
        "Source region": "us-east-1",
        "Inference service": "aws-bedrock",
    })
    compiled = compile_gitlab_intake(event(issue_body(**batch)))
    assert compiled.payload["item_operation"] == "add"
    assert len(compiled.payload["subjects"]) == 2
    assert compiled.payload["batch_scope"]["observation_scope"]["scope_ref"] == "production-scope"


def test_gitlab_guided_change_and_revoke_preserve_the_expected_subject_kind() -> None:
    changed = compile_gitlab_intake(event(issue_body(**common("change"))))
    assert changed.payload["subjects"] == [{"kind": "model", "identity": "example-model-v1"}]

    revoke = common("revoke")
    revoke.pop("Subject type"); revoke.pop("Subject identity")
    revoke["Offering identity"] = "bedrock-example-model"
    revoked = compile_gitlab_intake(event(issue_body(**revoke)))
    assert revoked.payload["subjects"] == [{"kind": "offering", "identity": "bedrock-example-model"}]


def test_gitlab_invalid_edit_removes_stale_generated_payload_and_reports_one_error() -> None:
    ready = compile_gitlab_intake(event(issue_body(**common("add"))))
    edited = ready.issue_body.replace("example-model-v1", "INVALID ID", 1)
    result = compile_gitlab_intake(event(edited))
    assert not result.valid
    assert result.payload is None
    assert "Proposal needs attention" in result.comment_body
    assert "modelo:intake-generated-start" not in result.issue_body
    with pytest.raises(MacError):
        extract_adapter_issue_payload(result.issue_body, "gitlab")
