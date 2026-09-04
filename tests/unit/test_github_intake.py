from __future__ import annotations

from uuid import UUID

import pytest

from modelo.github_adapter import compile_github_intake
from modelo.mac import MacError, extract_adapter_issue_payload, validate_payload


def issue_body(**sections: str) -> str:
    return "\n\n".join(f"### {label}\n\n{value}" for label, value in sections.items()) + "\n"


def event(body: str, number: int = 43) -> dict[str, object]:
    return {
        "repository": {"full_name": "j3brns996/Modelo"},
        "issue": {"number": number, "state": "open", "body": body},
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


def batch_fields() -> dict[str, str]:
    values = common("batch")
    values.pop("Subject identity")
    values.update({
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
    return values


def test_guided_add_compiles_to_the_existing_neutral_contract() -> None:
    result = compile_github_intake(event(issue_body(**common("add"))))
    assert result.valid
    payload = validate_payload(result.payload)
    assert UUID(payload["request_id"]).version == 5
    assert payload["operation"] == "add"
    assert payload["subjects"] == [{"kind": "model", "identity": "example-model-v1"}]
    assert len(payload["candidate_evidence"]) == 1
    assert len(payload["acceptance"]) == 2
    assert extract_adapter_issue_payload(result.issue_body, "github") == payload
    assert "Proposal ready" in result.comment_body
    assert "Copy into the pull request" in result.comment_body


def test_guided_move_and_batch_compile_operation_specific_fields() -> None:
    move = common("move")
    move.pop("Subject type"); move.pop("Subject identity")
    move["Current offering identity"] = "bedrock-model-old"
    move["Replacement offering identity"] = "bedrock-model-new"
    moved = compile_github_intake(event(issue_body(**move)))
    assert moved.payload["subjects"] == [
        {"kind": "offering", "identity": "bedrock-model-old", "role": "source"},
        {"kind": "offering", "identity": "bedrock-model-new", "role": "destination"},
    ]

    compiled = compile_github_intake(event(issue_body(**batch_fields())))
    assert compiled.payload["item_operation"] == "add"
    assert len(compiled.payload["subjects"]) == 2
    assert compiled.payload["batch_scope"]["observation_scope"]["scope_ref"] == "production-scope"


def test_guided_change_and_revoke_preserve_the_expected_subject_kind() -> None:
    changed = compile_github_intake(event(issue_body(**common("change"))))
    assert changed.payload["subjects"] == [{"kind": "model", "identity": "example-model-v1"}]

    revoke = common("revoke")
    revoke.pop("Subject type"); revoke.pop("Subject identity")
    revoke["Offering identity"] = "bedrock-example-model"
    revoked = compile_github_intake(event(issue_body(**revoke)))
    assert revoked.payload["subjects"] == [{"kind": "offering", "identity": "bedrock-example-model"}]


@pytest.mark.parametrize("operation", ["add", "change", "batch"])
@pytest.mark.parametrize("blank", ["", "_No response_"])
def test_optional_candidate_evidence_compiles_to_an_empty_array(
    operation: str, blank: str,
) -> None:
    values = batch_fields() if operation == "batch" else common(operation)
    values["Supporting observations"] = blank

    result = compile_github_intake(event(issue_body(**values)))

    assert result.valid
    assert result.payload["candidate_evidence"] == []
    assert validate_payload(result.payload)["candidate_evidence"] == []


@pytest.mark.parametrize("operation", ["add", "change", "batch"])
def test_nonblank_malformed_candidate_evidence_still_fails(operation: str) -> None:
    values = batch_fields() if operation == "batch" else common(operation)
    values["Supporting observations"] = "https://example.invalid/model without delimiters"

    result = compile_github_intake(event(issue_body(**values)))

    assert not result.valid
    assert result.payload is None
    assert "must contain URL | UTC time | sha256- digest" in result.comment_body


@pytest.mark.parametrize(
    "required_field",
    [
        "Evidence source type",
        "Evidence source URL",
        "Opaque scope reference",
        "Provider partition",
        "Source region",
        "Inference service",
    ],
)
def test_batch_source_and_scope_fields_remain_required(required_field: str) -> None:
    values = batch_fields()
    values.pop(required_field)
    values["Supporting observations"] = "_No response_"

    result = compile_github_intake(event(issue_body(**values)))

    assert not result.valid
    assert result.payload is None
    assert f"missing {required_field}" in result.comment_body


def test_invalid_edit_removes_stale_generated_payload_and_reports_one_error() -> None:
    ready = compile_github_intake(event(issue_body(**common("add"))))
    edited = ready.issue_body.replace("example-model-v1", "INVALID ID", 1)
    result = compile_github_intake(event(edited))
    assert not result.valid
    assert result.payload is None
    assert "Proposal needs attention" in result.comment_body
    assert "modelo:intake-generated-start" not in result.issue_body
    with pytest.raises(MacError):
        extract_adapter_issue_payload(result.issue_body, "github")

    without_type = ready.issue_body.replace("### Request type\n\nadd\n\n", "", 1)
    missing = compile_github_intake(event(without_type))
    assert not missing.valid
    assert "modelo:intake-generated-start" not in missing.issue_body
    assert "missing Request type" in missing.comment_body


def test_generated_payload_cannot_overflow_the_issue_body() -> None:
    values = common("add")
    values["Acceptance checks"] = "\n".join("check-" + str(index) + "-" + "x" * 1900 for index in range(25))
    result = compile_github_intake(event(issue_body(**values)))
    assert not result.valid
    assert "exceeds the GitHub issue body limit" in result.comment_body


def test_generated_payload_is_bound_to_the_current_human_fields() -> None:
    result = compile_github_intake(event(issue_body(**common("add"))))
    stale = result.issue_body.replace("governed record", "reviewed record", 1)
    with pytest.raises(MacError, match="human fields changed"):
        extract_adapter_issue_payload(stale, "github")


def test_unrelated_or_malformed_issue_event_fails_closed() -> None:
    with pytest.raises(ValueError, match="supported guided proposal"):
        compile_github_intake(event("### Something else\n\nhello\n"))
    with pytest.raises(ValueError, match="open issue"):
        compile_github_intake({"repository": {"full_name": "j3brns996/Modelo"}, "issue": {"number": 1, "state": "closed", "body": ""}})
