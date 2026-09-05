from datetime import date
import json
from pathlib import Path
from uuid import UUID

import pytest

from modelo.gitlab_adapter import compile_gitlab_intake, prepare_gitlab
from modelo.mac import MacError, extract_adapter_issue_payload, validate_payload
from modelo.receipt import canonical_bytes, sha256_bytes



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


def test_prepare_gitlab_generates_valid_workflow_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event_path = tmp_path / "event.json"
    issue_path = tmp_path / "issue.json"
    meta_path = tmp_path / "metadata.json"
    ctx_path = tmp_path / "context.json"

    intake_res = compile_gitlab_intake(event(issue_body(**common("add"))))
    digest = sha256_bytes(canonical_bytes(intake_res.payload))
    event_data = {
        "project": {"path_with_namespace": "j3brns996/Modelo", "default_branch": "main", "web_url": "https://gitlab.com/j3brns996/Modelo"},
        "object_attributes": {
            "iid": 12, "state": "opened", "target_branch": "main", "source_branch": "feat/test",
            "description": (
                "<!-- modelo:mac-issue -->https://gitlab.com/j3brns996/Modelo/-/issues/12<!-- /modelo:mac-issue -->\n"
                "<!-- modelo:change-delta -->\n```json\n[{\"operation\": \"add\", \"path\": \"catalogue/models/example.yaml\", \"subject_kind\": \"model\", \"subject_identity\": \"example-model-v1\", \"after\": \"sha256-1111111111111111111111111111111111111111111111111111111111111111\"}]\n```\n<!-- /modelo:change-delta -->\n"
                f"- Neutral payload digest: `{digest}`"
            ),
            "last_commit": {"id": "1" * 40}, "target": {"sha": "0" * 40},
        },
    }
    issue_data = {
        "iid": 12, "state": "opened", "web_url": "https://gitlab.com/j3brns996/Modelo/-/issues/12",
        "description": intake_res.issue_body,
    }
    event_path.write_text(json.dumps(event_data), encoding="utf-8")
    issue_path.write_text(json.dumps(issue_data), encoding="utf-8")

    monkeypatch.setattr("modelo.gitlab_adapter._git", lambda root, *args: "0" * 40 if "rev-parse" in args else "1700000000")
    monkeypatch.setattr("modelo.gitlab_adapter._committed_yaml_config", lambda root, commit, path: {
        "repository": {"adapter": "gitlab", "host": "gitlab.com"},
        "project": {"default_branch": "main"},
        "publication": {"active_profile": "public-pages-demo", "profiles": {"public-pages-demo": {"delivery": "pages", "visibility": "public"}}},
        "site": {"base_url": "https://example.invalid", "base_path": "/"},
        "paths": {"gitlab_ci": ".gitlab-ci.yml"},
    })

    prepare_gitlab(
        root=Path.cwd(), event_path=event_path, issue_path=issue_path,
        validation_sha="0" * 40, validation_tree="0" * 40, as_of=date(2026, 9, 5),
        metadata_output=meta_path, context_output=ctx_path,
    )

    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    assert ctx["workflow_identity"] == "j3brns996/Modelo/.gitlab-ci.yml@main"

