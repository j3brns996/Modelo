"""Bounded GitLab event/issue adapter for the provider-neutral trusted core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from modelo.build import BuildError, _git
from modelo.mac import (
    MAX_BODY_BYTES, MacError, extract_adapter_issue_payload, payload_digest,
    with_computed_keys,
)
from modelo.platform import _atomic_write, _read_json
from modelo.receipt import canonical_bytes, sha256_bytes, sort_change_delta
from modelo.site import _committed_yaml_config


_ISSUE = re.compile(r"<!-- modelo:mac-issue -->(https://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z0-9-]+/([^/]+)/([^/]+)/-/issues/([1-9][0-9]{0,19}))<!-- /modelo:mac-issue -->")
_CONTROL_ISSUE = re.compile(r"<!-- modelo:control-issue -->(https://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z0-9-]+/([^/]+)/([^/]+)/-/issues/([1-9][0-9]{0,19}))<!-- /modelo:control-issue -->")
_DELTA = re.compile(r"(?ms)<!-- modelo:change-delta -->\s*```json\n(\[[\s\S]*?\])\n```\s*<!-- /modelo:change-delta -->")
_DIGEST = re.compile(r"(?m)^- Neutral payload digest: `(sha256:[0-9a-f]{64})`$")
_INTAKE_START = "<!-- modelo:intake-generated-start -->"
_INTAKE_END = "<!-- modelo:intake-generated-end -->"
_INTAKE_RESULT = "<!-- modelo:intake-result -->"
_SECTION = re.compile(r"(?m)^### ([^\n]{1,80})\n\n")


@dataclass(frozen=True, slots=True)
class GitLabIntakeResult:
    valid: bool
    issue_body: str
    comment_body: str
    payload: dict[str, Any] | None


def _without_generated_intake(body: str) -> str:
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError(f"issue body exceeds {MAX_BODY_BYTES} bytes")
    start = body.find(_INTAKE_START)
    end = body.find(_INTAKE_END)
    if start < 0 and end < 0:
        return body.rstrip()
    if start < 0 or end < start or body.find(_INTAKE_START, start + 1) >= 0 or body.find(_INTAKE_END, end + 1) >= 0:
        raise ValueError("issue contains an ambiguous generated intake block")
    if body[end + len(_INTAKE_END):].strip():
        raise ValueError("generated intake block must be the final issue section")
    return body[:start].rstrip()


def _issue_sections(body: str) -> dict[str, str]:
    matches = list(_SECTION.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        label = match.group(1)
        if label in sections:
            raise MacError("guided proposal contains a duplicate field heading")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[label] = body[match.end():end].strip()
    return sections


def _answer(sections: dict[str, str], label: str, *, plain: bool = False) -> str:
    value = sections.get(label, "").strip()
    if not value or value == "_No response_":
        raise MacError(f"guided proposal is missing {label}")
    return " ".join(value.split()) if plain else value


def _lines(sections: dict[str, str], label: str, *, required: bool = True) -> list[str]:
    value = sections.get(label, "").strip()
    if not value or value == "_No response_":
        if required:
            raise MacError(f"guided proposal is missing {label}")
        return []
    values = [" ".join(line.split()) for line in value.splitlines() if line.strip()]
    if required and not values:
        raise MacError(f"guided proposal is missing {label}")
    return values


def _candidate_evidence(sections: dict[str, str]) -> list[dict[str, str]]:
    records = []
    for line in _lines(sections, "Supporting observations", required=False):
        parts = line.split(" | ")
        if len(parts) != 3:
            raise MacError("each supporting observation must contain URL | UTC time | sha256- digest")
        records.append({"uri": parts[0], "observed_at": parts[1], "digest": parts[2]})
    return records


def _compile_guided_payload(
    sections: dict[str, str], repository: str, issue_number: int, host: str = "gitlab.com",
) -> dict[str, Any]:
    operation = _answer(sections, "Request type")
    if operation not in {"add", "change", "revoke", "move", "batch"}:
        raise MacError("guided proposal has an unsupported request type")
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "request_id": str(uuid5(NAMESPACE_URL, f"https://{host}/{repository}/-/issues/{issue_number}")),
        "operation": operation,
        "purpose": _answer(sections, "Purpose", plain=True),
        "requested_outcome": _answer(sections, "Requested outcome", plain=True),
        "reason": _answer(sections, "Why is this needed?", plain=True),
        "candidate_evidence": _candidate_evidence(sections),
        "acceptance": _lines(sections, "Acceptance checks"),
    }
    if operation in {"add", "change"}:
        payload["subjects"] = [{
            "kind": _answer(sections, "Subject type"),
            "identity": _answer(sections, "Subject identity"),
        }]
    elif operation == "revoke":
        payload["subjects"] = [{
            "kind": "offering", "identity": _answer(sections, "Offering identity"),
        }]
    elif operation == "move":
        payload["subjects"] = [
            {"kind": "offering", "identity": _answer(sections, "Current offering identity"), "role": "source"},
            {"kind": "offering", "identity": _answer(sections, "Replacement offering identity"), "role": "destination"},
        ]
    else:
        kind = _answer(sections, "Subject type")
        payload["item_operation"] = _answer(sections, "Batch change type")
        payload["subjects"] = [
            {"kind": kind, "identity": identity}
            for identity in _lines(sections, "Subject identities")
        ]
        payload["batch_scope"] = {
            "source": {
                "type": _answer(sections, "Evidence source type"),
                "uri": _answer(sections, "Evidence source URL"),
            },
            "observation_scope": {
                "scope_ref": _answer(sections, "Opaque scope reference"),
                "partition": _answer(sections, "Provider partition"),
                "region": _answer(sections, "Source region"),
            },
            "inference_service_id": _answer(sections, "Inference service"),
        }
    return with_computed_keys(payload)


def _intake_issue_body(source: str, payload: dict[str, Any]) -> str:
    pretty = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
    body = (
        source + "\n\n" + _INTAKE_START + "\n"
        + f"<!-- modelo:intake-source {sha256_bytes(source.encode('utf-8'))} -->\n"
        + f"### Change details (JSON)\n\n```json\n{pretty}\n```\n\n"
        + f"### Change fingerprint\n\n{payload_digest(payload)}\n"
        + _INTAKE_END + "\n"
    )
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise MacError("generated proposal exceeds the GitLab issue body limit")
    return body


def _intake_comment(payload: dict[str, Any]) -> str:
    identities = ", ".join(
        f"{item['kind']}:{item['identity']}" for item in payload["subjects"]
    )
    digest = sha256_bytes(canonical_bytes(payload))
    return (
        _INTAKE_RESULT + "\n## Proposal ready\n\n"
        "Modelo validated the guided answers and generated the canonical request above. "
        "This is still a proposal, not approval.\n\n"
        "### Copy into the merge request\n\n"
        f"- Neutral payload digest: `{digest}`\n"
        f"- Operation: `{payload['operation']}`\n"
        f"- Affected logical identities: {identities}\n\n"
        "Next: add the governed records and admissible evidence on a topic branch, then open the MAC merge request.\n"
    )


def compile_gitlab_intake(event: dict[str, Any]) -> GitLabIntakeResult:
    project = event.get("project")
    object_attributes = event.get("object_attributes")
    if not isinstance(project, dict) or not isinstance(object_attributes, dict) or object_attributes.get("state") != "opened":
        raise ValueError("GitLab intake requires an open issue event")
    path_with_namespace = project.get("path_with_namespace")
    iid = object_attributes.get("iid")
    description = object_attributes.get("description")
    if not isinstance(path_with_namespace, str) or not isinstance(iid, int) or not isinstance(description, str):
        raise ValueError("GitLab intake event fields are invalid")
    had_generated = _INTAKE_START in description or _INTAKE_END in description
    source = _without_generated_intake(description)
    sections = _issue_sections(source)
    if "Request type" not in sections:
        if had_generated:
            comment = (
                _INTAKE_RESULT + "\n## Proposal needs attention\n\n"
                "guided proposal is missing Request type. Restore the form field or open a new proposal.\n"
            )
            return GitLabIntakeResult(False, source + "\n", comment, None)
        raise ValueError("issue is not a supported guided proposal")
    try:
        payload = _compile_guided_payload(sections, path_with_namespace, iid)
        issue_body = _intake_issue_body(source, payload)
        comment_body = _intake_comment(payload)
    except (MacError, ValueError) as exc:
        message = str(exc).splitlines()[0]
        comment = (
            _INTAKE_RESULT + "\n## Proposal needs attention\n\n"
            + message + ". Update the issue fields and Modelo will check them again.\n"
        )
        return GitLabIntakeResult(False, source + "\n", comment, None)
    return GitLabIntakeResult(True, issue_body, comment_body, payload)


def write_gitlab_intake_outputs(
    *, event_path: Path, issue_body_output: Path, comment_output: Path,
) -> None:
    result = compile_gitlab_intake(_read_json(event_path, "GitLab issue event"))
    _atomic_write(issue_body_output, result.issue_body.encode("utf-8"))
    _atomic_write(comment_output, result.comment_body.encode("utf-8"))


def _merge_request(event_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    event = _read_json(event_path, "GitLab event")
    object_attributes = event.get("object_attributes")
    project = event.get("project")
    if not isinstance(object_attributes, dict) or not isinstance(project, dict):
        raise BuildError("GitLab event is not a merge request")
    if object_attributes.get("target_branch") != project.get("default_branch"):
        raise BuildError("merge request does not target the repository default branch")
    if object_attributes.get("state") != "opened" or object_attributes.get("source_project_id") != object_attributes.get("target_project_id"):
        raise BuildError("trusted GitLab check accepts only open same-repository merge requests")
    return object_attributes, project


def gitlab_issue_reference(event_path: Path) -> str:
    mr, project = _merge_request(event_path)
    matches = _ISSUE.findall(str(mr.get("description", "")))
    if len(matches) != 1 or f"{matches[0][1]}/{matches[0][2]}" != project.get("path_with_namespace"):
        raise BuildError("merge request lacks one same-repository MAC issue marker")
    return matches[0][3]


def gitlab_control_issue_reference(event_path: Path) -> str:
    mr, project = _merge_request(event_path)
    matches = _CONTROL_ISSUE.findall(str(mr.get("description", "")))
    if len(matches) != 1 or f"{matches[0][1]}/{matches[0][2]}" != project.get("path_with_namespace"):
        raise BuildError("control merge request lacks one same-repository implementation issue marker")
    return matches[0][3]


def prepare_gitlab(
    *, root: Path, event_path: Path, issue_path: Path, validation_sha: str,
    validation_tree: str, as_of: date, metadata_output: Path, context_output: Path,
) -> None:
    mr, project = _merge_request(event_path)
    issue_reference = gitlab_issue_reference(event_path)
    issue = _read_json(issue_path, "GitLab issue")
    if str(issue.get("iid") or issue.get("number")) != issue_reference or (issue.get("state") != "opened" and issue.get("state") != "open"):
        raise BuildError("GitLab issue response differs from linked open MAC issue")
    try:
        payload = extract_adapter_issue_payload(str(issue.get("description") or issue.get("body", "")), "gitlab")
    except MacError as exc:
        raise BuildError(f"invalid GitLab MAC issue body: {exc}") from exc
    description = str(mr.get("description", ""))
    delta_matches = _DELTA.findall(description)
    digest_matches = _DIGEST.findall(description)
    if len(delta_matches) != 1:
        raise BuildError("merge request lacks one expected change delta marker")
    if digest_matches != [sha256_bytes(canonical_bytes(payload))]:
        raise BuildError("merge request payload digest differs from the linked MAC issue")
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result
        delta = json.loads(
            delta_matches[0], object_pairs_hook=unique,
            parse_float=lambda token: (_ for _ in ()).throw(ValueError(token)),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise BuildError("merge request expected change delta is invalid JSON") from exc
    if not isinstance(delta, list) or not delta or len(delta) > 25:
        raise BuildError("merge request expected change delta must contain 1 to 25 records")
    base = str(mr.get("target", {}).get("sha") or mr.get("diff_base_sha", ""))
    head = str(mr.get("last_commit", {}).get("id") or mr.get("head_sha", ""))
    tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    epoch = int(str(_git(root, "show", "-s", "--format=%at", head)).strip())
    configured = _committed_yaml_config(root, head, "modelo.yaml")
    if configured["repository"]["adapter"] != "gitlab":
        raise BuildError("proposed configuration does not select the GitLab adapter")
    if configured["project"]["default_branch"] != project.get("default_branch"):
        raise BuildError("GitLab default branch differs from modelo.yaml")
    profile = configured["publication"]["active_profile"]
    owner, name = str(project["path_with_namespace"]).split("/", 1)
    host = configured["repository"]["host"]
    metadata = {
        "contract_version": "0.1.0",
        "repository": {"provider": "gitlab", "host": host, "namespace": owner, "name": name},
        "issue": {"reference": issue_reference, "url": str(issue.get("web_url", "")), "state": "open"},
        "base_sha": base, "head_sha": head, "head_tree_sha": tree,
        "payload": payload, "payload_digest": sha256_bytes(canonical_bytes(payload)),
        "expected_change_delta": sort_change_delta(delta),
    }
    context = {
        "contract_version": "0.1.0", "repository": metadata["repository"],
        "change_request": str(mr.get("iid") or mr.get("id", "")), "base_sha": base, "head_sha": head,
        "head_tree_sha": tree, "validation_sha": validation_sha,
        "validation_tree_sha": validation_tree, "as_of": as_of.isoformat(),
        "source_date_epoch": epoch, "profile": profile,
        "base_url": configured["site"]["base_url"], "base_path": configured["site"]["base_path"],
        "publication_capability": "public-pages",
        "workflow_identity": f"{project['path_with_namespace']}/{configured['paths']['gitlab_ci']:.gitlab-ci.yml}@{configured['project']['default_branch']}",
        "workflow_sha": base, "run_id": str(__import__('os').environ.get("CI_PIPELINE_ID", "local")),
        "check_name": "modelo/check",
        "gates": {"lock": "success", "schema": "success", "tests": "success", "package": "success"},
    }
    _atomic_write(metadata_output, canonical_bytes(metadata))
    _atomic_write(context_output, canonical_bytes(context))


def prepare_gitlab_control(
    *, root: Path, event_path: Path, issue_path: Path, validation_sha: str, validation_tree: str,
    as_of: date, context_output: Path,
) -> None:
    mr, project = _merge_request(event_path)
    issue_reference = gitlab_control_issue_reference(event_path)
    issue = _read_json(issue_path, "GitLab control issue")
    host = project.get("web_url", "").split("/")[2] if project.get("web_url") else "gitlab.com"
    expected_issue_url = f"https://{host}/{project['path_with_namespace']}/-/issues/{issue_reference}"
    if (
        str(issue.get("iid") or issue.get("number")) != issue_reference or (issue.get("state") != "opened" and issue.get("state") != "open")
    ):
        raise BuildError("GitLab control issue response differs from linked open issue")
    base = str(mr.get("target", {}).get("sha") or mr.get("diff_base_sha", ""))
    head = str(mr.get("last_commit", {}).get("id") or mr.get("head_sha", ""))
    tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    epoch = int(str(_git(root, "show", "-s", "--format=%at", head)).strip())
    configured = _committed_yaml_config(root, head, "modelo.yaml")
    protected = _committed_yaml_config(root, base, "modelo.yaml")
    if configured["repository"]["adapter"] != "gitlab" or configured["project"]["default_branch"] != project.get("default_branch"):
        raise BuildError("GitLab adapter/default branch differs from proposed modelo.yaml")
    if protected["repository"]["adapter"] != "gitlab" or protected["project"]["default_branch"] != project.get("default_branch"):
        raise BuildError("trusted workflow identity differs from protected modelo.yaml")
    owner, name = str(project["path_with_namespace"]).split("/", 1)
    context = {
        "contract_version": "0.1.0",
        "repository": {"provider": "gitlab", "host": configured["repository"]["host"], "namespace": owner, "name": name},
        "control_issue": issue_reference,
        "control_issue_digest": sha256_bytes(str(issue.get("description") or issue.get("body", "")).encode("utf-8")),
        "change_request": str(mr.get("iid") or mr.get("id", "")),
        "base_sha": base, "head_sha": head,
        "head_tree_sha": tree, "validation_sha": validation_sha,
        "validation_tree_sha": validation_tree, "as_of": as_of.isoformat(),
        "source_date_epoch": epoch,
        "workflow_identity": f"{project['path_with_namespace']}/{protected['paths']['gitlab_ci']}@{protected['project']['default_branch']}",
        "workflow_sha": base, "run_id": str(__import__('os').environ.get("CI_PIPELINE_ID", "local")),
        "check_name": "modelo/check",
        "gates": {
            "lock": "success", "schema": "success", "trusted_tests": "success",
            "proposed_tests": "success", "trusted_package": "success",
            "proposed_package": "success",
        },
    }
    _atomic_write(context_output, canonical_bytes(context))
