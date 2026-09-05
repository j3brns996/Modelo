from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from unittest.mock import patch
from uuid import UUID

import pytest

from modelo.build import BuildError
from modelo.gitlab_adapter import (
    compile_gitlab_intake, gitlab_control_issue_reference, gitlab_issue_reference,
    prepare_gitlab, prepare_gitlab_control,
)
from modelo.mac import (
    MacError, extract_adapter_issue_payload, render_adapter_issue_body, validate_payload,
)
from modelo.receipt import canonical_bytes, sha256_bytes


def issue_body(**sections: str) -> str:
    return "\n\n".join(f"### {label}\n\n{value}" for label, value in sections.items()) + "\n"


def event(
    body: str, iid: int = 43, *,
    project_path: str = "j3brns996/Modelo",
    project_url: str = "https://gitlab.com/j3brns996/Modelo",
) -> dict[str, object]:
    return {
        "project": {"path_with_namespace": project_path, "web_url": project_url},
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
    move = {
        "Request type": "move",
        "Current offering identity": "bedrock-model-old",
        "Replacement offering identity": "bedrock-model-new",
        **{key: value for key, value in common("move").items() if key not in {
            "Request type", "Subject type", "Subject identity",
        }},
    }
    moved = compile_gitlab_intake(event(issue_body(**move)))
    assert moved.payload["subjects"] == [
        {"kind": "offering", "identity": "bedrock-model-old", "role": "source"},
        {"kind": "offering", "identity": "bedrock-model-new", "role": "destination"},
    ]

    batch = {
        "Request type": "batch",
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
    compiled = compile_gitlab_intake(event(issue_body(**batch)))
    assert compiled.payload["item_operation"] == "add"
    assert len(compiled.payload["subjects"]) == 2
    assert compiled.payload["batch_scope"]["observation_scope"]["scope_ref"] == "production-scope"


def test_gitlab_guided_change_and_revoke_preserve_the_expected_subject_kind() -> None:
    changed = compile_gitlab_intake(event(issue_body(**common("change"))))
    assert changed.payload["subjects"] == [{"kind": "model", "identity": "example-model-v1"}]

    revoke = {
        "Request type": "revoke",
        "Offering identity": "bedrock-example-model",
        **{key: value for key, value in common("revoke").items() if key not in {
            "Request type", "Subject type", "Subject identity",
        }},
    }
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


def test_gitlab_nested_namespace_and_self_host_are_part_of_the_stable_request_id() -> None:
    first = compile_gitlab_intake(event(
        issue_body(**common("add")),
        project_path="group/platform/Modelo",
        project_url="https://gitlab.example.invalid/group/platform/Modelo",
    ))
    second = compile_gitlab_intake(event(
        issue_body(**common("add")),
        project_path="group/platform/Modelo",
        project_url="https://gitlab.example.invalid/group/platform/Modelo",
    ))
    other_host = compile_gitlab_intake(event(
        issue_body(**common("add")),
        project_path="group/platform/Modelo",
        project_url="https://gitlab.other.invalid/group/platform/Modelo",
    ))
    assert first.valid and second.valid and other_host.valid
    assert first.payload["request_id"] == second.payload["request_id"]
    assert first.payload["request_id"] != other_host.payload["request_id"]


@pytest.mark.parametrize(
    "project_url",
    [
        "http://gitlab.example.invalid/group/Modelo",
        "https://user@gitlab.example.invalid/group/Modelo",
        "https://gitlab.example.invalid:443/group/Modelo",
        "https://gitlab.example.invalid/group/Modelo?x=1",
        "https://gitlab.example.invalid/group/Modelo#fragment",
        "https://gitlab.example.invalid/group/Modelo/",
        "https://gitlab.example.invalid/other/Modelo",
    ],
)
def test_gitlab_project_url_must_be_canonical_and_match_the_namespace(
    project_url: str,
) -> None:
    with pytest.raises(ValueError, match="canonical HTTPS"):
        compile_gitlab_intake(event(
            issue_body(**common("add")),
            project_path="group/Modelo",
            project_url=project_url,
        ))


def test_gitlab_parser_preserves_unknown_headings_and_rejects_known_reordering() -> None:
    values = common("add")
    values["Why is this needed?"] += "\n\n### Reviewer context\n\nKeep this explanation."
    result = compile_gitlab_intake(event(issue_body(**values)))
    assert result.valid
    assert "Reviewer context" in result.payload["reason"]

    reordered = "### Purpose\n\nFirst\n\n" + issue_body(**common("add"))
    invalid = compile_gitlab_intake(event(reordered))
    assert not invalid.valid
    assert "out of order" in invalid.comment_body


def test_gitlab_rejects_inapplicable_recognized_heading_without_losing_prose() -> None:
    values = common("change")
    values["Why is this needed?"] = (
        "Keep the complete explanation.\n\n"
        "### Evidence source type\n\n"
        "This batch-only heading is user prose."
    )
    result = compile_gitlab_intake(event(issue_body(**values)))
    assert not result.valid
    assert result.payload is None
    assert "Evidence source type is not valid for change" in result.comment_body
    assert "### Evidence source type\n\nThis batch-only heading is user prose." in result.issue_body


def test_gitlab_markers_bind_nested_namespace_host_and_exact_cardinality(tmp_path) -> None:
    project_url = "https://gitlab.example.invalid/group/platform/Modelo"
    marker = (
        f"<!-- modelo:mac-issue -->{project_url}/-/issues/43"
        "<!-- /modelo:mac-issue -->"
    )
    control_marker = (
        f"<!-- modelo:control-issue -->{project_url}/-/issues/44"
        "<!-- /modelo:control-issue -->"
    )
    raw_event = {
        "project": {
            "id": 7,
            "default_branch": "main",
            "path_with_namespace": "group/platform/Modelo",
            "web_url": project_url,
        },
        "object_attributes": {
            "iid": 9,
            "state": "opened",
            "target_branch": "main",
            "source_project_id": 7,
            "target_project_id": 7,
            "description": marker,
        },
    }
    event_path = tmp_path / "event.json"
    event_path.write_bytes(canonical_bytes(raw_event))
    assert gitlab_issue_reference(event_path) == "43"

    raw_event["object_attributes"]["description"] = control_marker
    event_path.write_bytes(canonical_bytes(raw_event))
    assert gitlab_control_issue_reference(event_path) == "44"

    for description in (
        marker + "\n" + marker,
        marker.replace("group/platform", "other/platform"),
        marker.replace("gitlab.example.invalid", "other.example.invalid"),
    ):
        raw_event["object_attributes"]["description"] = description
        event_path.write_bytes(canonical_bytes(raw_event))
        with pytest.raises(BuildError, match="one same-repository MAC issue"):
            gitlab_issue_reference(event_path)


def test_gitlab_prepare_binds_project_issue_profile_and_preserves_outputs_on_failure(
    tmp_path,
) -> None:
    project_url = "https://gitlab.example.invalid/group/platform/Modelo"
    payload = compile_gitlab_intake(event(
        issue_body(**common("add")),
        project_path="group/platform/Modelo",
        project_url=project_url,
    )).payload
    digest = sha256_bytes(canonical_bytes(payload))
    delta = [{
        "operation": "add",
        "path": "catalogue/models/example-model-v1.yaml",
        "after": "sha256:" + "a" * 64,
    }]
    description = (
        f"<!-- modelo:mac-issue -->{project_url}/-/issues/43"
        "<!-- /modelo:mac-issue -->\n"
        f"- Neutral payload digest: `{digest}`\n"
        "<!-- modelo:change-delta -->\n```json\n"
        + json.dumps(delta, indent=2, sort_keys=True)
        + "\n```\n<!-- /modelo:change-delta -->\n"
    )
    base = "1" * 40
    head = "2" * 40
    project = {
        "id": 7,
        "default_branch": "main",
        "path_with_namespace": "group/platform/Modelo",
        "web_url": project_url,
    }
    raw_event = {
        "project": project,
        "object_attributes": {
            "iid": 8,
            "state": "opened",
            "target_branch": "main",
            "source_project_id": 7,
            "target_project_id": 7,
            "description": description,
            "target": {"sha": base},
            "last_commit": {"id": head},
        },
    }
    raw_issue = {
        "iid": 43,
        "state": "opened",
        "project_id": 7,
        "web_url": f"{project_url}/-/issues/43",
        "description": render_adapter_issue_body(payload, "gitlab"),
    }
    config = {
        "repository": {
            "adapter": "gitlab",
            "host": "gitlab.example.invalid",
            "namespace": "group/platform",
            "name": "Modelo",
            "web_base": project_url,
        },
        "project": {"default_branch": "main"},
        "publication": {
            "active_profile": "synthetic",
            "profiles": {"synthetic": {"delivery": "pages", "visibility": "public"}},
        },
        "site": {"base_url": "https://example.invalid/Modelo/", "base_path": "/Modelo/"},
        "paths": {"gitlab_ci": ".gitlab-ci.yml"},
    }
    event_path = tmp_path / "event.json"
    issue_path = tmp_path / "issue.json"
    metadata_output = tmp_path / "metadata.json"
    context_output = tmp_path / "context.json"

    def invoke(selected_event=raw_event, selected_issue=raw_issue, selected_config=config):
        event_path.write_bytes(canonical_bytes(selected_event))
        issue_path.write_bytes(canonical_bytes(selected_issue))
        with (
            patch("modelo.gitlab_adapter._committed_yaml_config", return_value=selected_config),
            patch(
                "modelo.gitlab_adapter._git",
                side_effect=lambda _root, command, *args: "3" * 40
                if command == "rev-parse" else "100",
            ),
        ):
            prepare_gitlab(
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
    metadata = json.loads(metadata_output.read_text())
    context = json.loads(context_output.read_text())
    assert metadata["repository"] == {
        "provider": "gitlab",
        "host": "gitlab.example.invalid",
        "namespace": "group/platform",
        "name": "Modelo",
    }
    assert context["workflow_identity"] == (
        "group/platform/Modelo/.gitlab-ci.yml@main"
    )

    invalid_cases = []
    for container, key in (
        ("project", "id"),
        ("object_attributes", "source_project_id"),
        ("object_attributes", "target_project_id"),
        ("object_attributes", "iid"),
    ):
        missing = deepcopy(raw_event)
        del missing[container][key]
        invalid_cases.append((missing, raw_issue, config))
        zero = deepcopy(raw_event)
        zero[container][key] = 0
        invalid_cases.append((zero, raw_issue, config))
    mismatched_target = deepcopy(raw_event)
    mismatched_target["object_attributes"]["target_project_id"] = 8
    invalid_cases.append((mismatched_target, raw_issue, config))
    changed_issue_id = {**raw_issue, "project_id": 8}
    invalid_cases.append((raw_event, changed_issue_id, config))
    changed_issue_url = {**raw_issue, "web_url": f"{project_url}/-/issues/99"}
    invalid_cases.append((raw_event, changed_issue_url, config))
    changed_config = deepcopy(config)
    changed_config["repository"]["namespace"] = "other/platform"
    invalid_cases.append((raw_event, raw_issue, changed_config))
    private_config = deepcopy(config)
    private_config["publication"]["profiles"]["synthetic"]["visibility"] = "private"
    invalid_cases.append((raw_event, raw_issue, private_config))
    non_pages_config = deepcopy(config)
    non_pages_config["publication"]["profiles"]["synthetic"]["delivery"] = "artifact"
    invalid_cases.append((raw_event, raw_issue, non_pages_config))

    sentinel = b"unchanged\n"
    for selected_event, selected_issue, selected_config in invalid_cases:
        metadata_output.write_bytes(sentinel)
        context_output.write_bytes(sentinel)
        with pytest.raises(BuildError):
            invoke(selected_event, selected_issue, selected_config)
        assert metadata_output.read_bytes() == sentinel
        assert context_output.read_bytes() == sentinel


def test_gitlab_control_prepare_uses_nested_identity_and_preserves_output_on_failure(
    tmp_path,
) -> None:
    project_url = "https://gitlab.example.invalid/group/platform/Modelo"
    base = "1" * 40
    head = "2" * 40
    raw_event = {
        "project": {
            "id": 7,
            "default_branch": "main",
            "path_with_namespace": "group/platform/Modelo",
            "web_url": project_url,
        },
        "object_attributes": {
            "iid": 9,
            "state": "opened",
            "target_branch": "main",
            "source_project_id": 7,
            "target_project_id": 7,
            "description": (
                f"<!-- modelo:control-issue -->{project_url}/-/issues/44"
                "<!-- /modelo:control-issue -->"
            ),
            "target": {"sha": base},
            "last_commit": {"id": head},
        },
    }
    raw_issue = {
        "iid": 44,
        "state": "opened",
        "project_id": 7,
        "web_url": f"{project_url}/-/issues/44",
        "description": "Harden the trusted control path.",
    }
    config = {
        "repository": {
            "adapter": "gitlab",
            "host": "gitlab.example.invalid",
            "namespace": "group/platform",
            "name": "Modelo",
            "web_base": project_url,
        },
        "project": {"default_branch": "main"},
        "paths": {"gitlab_ci": ".gitlab-ci.yml"},
    }
    event_path = tmp_path / "control-event.json"
    issue_path = tmp_path / "control-issue.json"
    context_output = tmp_path / "control-context.json"

    def invoke(selected_issue=raw_issue, selected_config=config):
        event_path.write_bytes(canonical_bytes(raw_event))
        issue_path.write_bytes(canonical_bytes(selected_issue))
        with (
            patch("modelo.gitlab_adapter._committed_yaml_config", return_value=selected_config),
            patch(
                "modelo.gitlab_adapter._git",
                side_effect=lambda _root, command, *args: "3" * 40
                if command == "rev-parse" else "100",
            ),
        ):
            prepare_gitlab_control(
                root=tmp_path,
                event_path=event_path,
                issue_path=issue_path,
                validation_sha="4" * 40,
                validation_tree="5" * 40,
                as_of=date(2026, 9, 5),
                context_output=context_output,
            )

    invoke()
    context = json.loads(context_output.read_text())
    assert context["repository"] == {
        "provider": "gitlab",
        "host": "gitlab.example.invalid",
        "namespace": "group/platform",
        "name": "Modelo",
    }
    assert context["change_request"] == "9"
    assert context["workflow_identity"] == (
        "group/platform/Modelo/.gitlab-ci.yml@main"
    )

    wrong_url = {**raw_issue, "web_url": f"{project_url}/-/issues/45"}
    wrong_project = {**raw_issue, "project_id": 8}
    wrong_config = deepcopy(config)
    wrong_config["repository"]["web_base"] = (
        "https://gitlab.example.invalid/group/platform/Other"
    )
    sentinel = b"unchanged\n"
    for selected_issue, selected_config in (
        (wrong_url, config),
        (wrong_project, config),
        (raw_issue, wrong_config),
    ):
        context_output.write_bytes(sentinel)
        with pytest.raises(BuildError):
            invoke(selected_issue, selected_config)
        assert context_output.read_bytes() == sentinel
