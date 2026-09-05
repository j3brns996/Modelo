from __future__ import annotations

from datetime import date
import json
from unittest.mock import patch
from uuid import UUID

import pytest

from modelo.build import BuildError
from modelo.github_adapter import (
    compile_github_intake, github_control_issue_reference, github_issue_reference,
    prepare_github,
)
from modelo.mac import (
    MacError, extract_adapter_issue_payload, render_adapter_issue_body, validate_payload,
)
from modelo.receipt import canonical_bytes, sha256_bytes


def issue_body(**sections: str) -> str:
    return "\n\n".join(f"### {label}\n\n{value}" for label, value in sections.items()) + "\n"


def event(body: str, number: int = 43) -> dict[str, object]:
    return {
        "repository": {"full_name": "j3brns996/Modelo"},
        "issue": {"number": number, "state": "open", "body": body},
    }


def common(operation: str, request_label: str = "Modelo MAC request type") -> dict[str, str]:
    return {
        request_label: operation,
        "Subject type": "model",
        "Subject identity": "example-model-v1",
        "Purpose": "Make the model available for a reviewed workload",
        "Requested outcome": "Add one evidenced model record to the catalogue.",
        "Why is this needed?": "The platform team needs a governed record before proposing an offering.",
        "Supporting observations": "https://example.invalid/model | 2026-09-02T08:00:00Z | sha256-" + "1" * 64,
        "Acceptance checks": "The model name matches the retained evidence.\nThe record passes Modelo validation.",
    }


def batch_fields() -> dict[str, str]:
    return {
        "Modelo MAC request type": "batch",
        "Batch change type": "add",
        "Subject type": "offering",
        "Subject identities": "bedrock-model-a\nbedrock-model-b",
        "Purpose": "Make the model available for a reviewed workload",
        "Requested outcome": "Add one evidenced model record to the catalogue.",
        "Why is this needed?": "The platform team needs a governed record before proposing an offering.",
        "Evidence source type": "first-party-read-api",
        "Evidence source URL": "https://bedrock.us-east-1.amazonaws.com/foundation-models",
        "Opaque scope reference": "production-scope",
        "Provider partition": "aws",
        "Source region": "us-east-1",
        "Inference service": "aws-bedrock",
        "Supporting observations": "https://example.invalid/model | 2026-09-02T08:00:00Z | sha256-" + "1" * 64,
        "Acceptance checks": "The model name matches the retained evidence.\nThe record passes Modelo validation.",
    }


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
    move = {
        "Modelo MAC request type": "move",
        "Current offering identity": "bedrock-model-old",
        "Replacement offering identity": "bedrock-model-new",
        **{key: value for key, value in common("move").items() if key not in {
            "Modelo MAC request type", "Subject type", "Subject identity",
        }},
    }
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

    revoke = {
        "Modelo MAC request type": "revoke",
        "Offering identity": "bedrock-example-model",
        **{key: value for key, value in common("revoke").items() if key not in {
            "Modelo MAC request type", "Subject type", "Subject identity",
        }},
    }
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

    without_type = ready.issue_body.replace("### Modelo MAC request type\n\nadd\n\n", "", 1)
    missing = compile_github_intake(event(without_type))
    assert not missing.valid
    assert "modelo:intake-generated-start" not in missing.issue_body
    assert "missing Modelo MAC request type" in missing.comment_body


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


def test_legacy_request_heading_remains_compatible_for_direct_compilation() -> None:
    result = compile_github_intake(event(issue_body(**common("add", "Request type"))))
    assert result.valid
    assert result.payload["operation"] == "add"


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            issue_body(**common("add")) + "### Modelo MAC request type\n\nadd\n",
            "duplicate field heading",
        ),
        (
            issue_body(**common("add")) + "### Request type\n\nadd\n",
            "duplicate field heading",
        ),
        (
            "### Purpose\n\nA purpose\n\n" + issue_body(**common("add")),
            "out of order",
        ),
    ],
)
def test_duplicate_alias_and_out_of_order_recognized_headings_fail_closed(
    body: str, expected: str,
) -> None:
    result = compile_github_intake(event(body))
    assert not result.valid
    assert result.payload is None
    assert expected in result.comment_body


def test_unrecognized_level_three_heading_remains_part_of_the_human_answer() -> None:
    values = common("add")
    values["Why is this needed?"] = (
        "The current catalogue is incomplete.\n\n"
        "### Reviewer context\n\nThis text is part of the explanation."
    )
    result = compile_github_intake(event(issue_body(**values)))
    assert result.valid
    assert "Reviewer context" in result.payload["reason"]
    assert "part of the explanation" in result.payload["reason"]

    values = common("add")
    values["Acceptance checks"] = (
        "The record passes validation.\n"
        "### Verification note\n"
        "Retain this line as part of the answer."
    )
    result = compile_github_intake(event(issue_body(**values)))
    assert result.valid
    assert result.payload["acceptance"] == [
        "The record passes validation.",
        "### Verification note",
        "Retain this line as part of the answer.",
    ]


def test_github_prepare_binds_exact_repository_and_issue_and_preserves_outputs_on_failure(
    tmp_path,
) -> None:
    payload = compile_github_intake(event(issue_body(**common("add")))).payload
    digest = sha256_bytes(canonical_bytes(payload))
    delta = [{
        "operation": "add",
        "path": "catalogue/models/example-model-v1.yaml",
        "after": "sha256:" + "a" * 64,
    }]
    pull_body = (
        "<!-- modelo:mac-issue -->https://github.com/j3brns996/Modelo/issues/43"
        "<!-- /modelo:mac-issue -->\n"
        f"- Neutral payload digest: `{digest}`\n"
        "<!-- modelo:change-delta -->\n```json\n"
        + json.dumps(delta, indent=2, sort_keys=True)
        + "\n```\n<!-- /modelo:change-delta -->\n"
    )
    base = "1" * 40
    head = "2" * 40
    repository = {"full_name": "j3brns996/Modelo", "default_branch": "main"}
    raw_event = {
        "repository": repository,
        "pull_request": {
            "number": 8,
            "state": "open",
            "body": pull_body,
            "base": {"sha": base, "ref": "main"},
            "head": {"sha": head, "repo": {"full_name": "j3brns996/Modelo"}},
        },
    }
    raw_issue = {
        "number": 43,
        "state": "open",
        "html_url": "https://github.com/j3brns996/Modelo/issues/43",
        "body": render_adapter_issue_body(payload, "github"),
    }
    config = {
        "repository": {
            "adapter": "github",
            "host": "github.com",
            "namespace": "j3brns996",
            "name": "Modelo",
            "web_base": "https://github.com/j3brns996/Modelo",
        },
        "project": {"default_branch": "main"},
        "publication": {
            "active_profile": "synthetic",
            "profiles": {"synthetic": {"delivery": "pages", "visibility": "public"}},
        },
        "site": {"base_url": "https://example.invalid/Modelo/", "base_path": "/Modelo/"},
        "paths": {"github_adapter": ".github"},
    }
    event_path = tmp_path / "event.json"
    issue_path = tmp_path / "issue.json"
    metadata_output = tmp_path / "metadata.json"
    context_output = tmp_path / "context.json"

    def invoke(selected_event=raw_event, selected_issue=raw_issue, selected_config=config):
        event_path.write_bytes(canonical_bytes(selected_event))
        issue_path.write_bytes(canonical_bytes(selected_issue))
        with (
            patch("modelo.github_adapter._committed_yaml_config", return_value=selected_config),
            patch(
                "modelo.github_adapter._git",
                side_effect=lambda _root, command, *args: "3" * 40
                if command == "rev-parse" else "100",
            ),
        ):
            prepare_github(
                root=tmp_path,
                event_path=event_path,
                issue_path=issue_path,
                validation_sha="4" * 40,
                validation_tree="5" * 40,
                as_of=date(2026, 9, 5),
                metadata_output=metadata_output,
                context_output=context_output,
            )

    invoke()
    assert json.loads(metadata_output.read_text())["issue"]["url"] == raw_issue["html_url"]

    sentinel = b"unchanged\n"
    for selected_issue, selected_config in (
        ({**raw_issue, "html_url": "https://github.com/other/Repo/issues/43"}, config),
        (raw_issue, {**config, "repository": {**config["repository"], "name": "Other"}}),
    ):
        metadata_output.write_bytes(sentinel)
        context_output.write_bytes(sentinel)
        with pytest.raises(BuildError):
            invoke(selected_issue=selected_issue, selected_config=selected_config)
        assert metadata_output.read_bytes() == sentinel
        assert context_output.read_bytes() == sentinel


@pytest.mark.parametrize(
    "marker, reference, extra_token",
    [
        ("mac-issue", github_issue_reference, "<!-- modelo:mac-issue -->"),
        (
            "control-issue",
            github_control_issue_reference,
            "<!-- /modelo:control-issue -->",
        ),
    ],
)
def test_github_issue_markers_reject_ambiguous_raw_tokens(
    tmp_path, marker: str, reference, extra_token: str,
) -> None:
    issue_url = "https://github.com/j3brns996/Modelo/issues/43"
    body = (
        f"<!-- modelo:{marker} -->{issue_url}<!-- /modelo:{marker} -->\n"
        + extra_token
    )
    raw_event = {
        "repository": {"full_name": "j3brns996/Modelo", "default_branch": "main"},
        "pull_request": {
            "state": "open",
            "body": body,
            "base": {"ref": "main"},
            "head": {"repo": {"full_name": "j3brns996/Modelo"}},
        },
    }
    event_path = tmp_path / f"{marker}.json"
    event_path.write_bytes(canonical_bytes(raw_event))
    with pytest.raises(BuildError, match="one same-repository"):
        reference(event_path)
