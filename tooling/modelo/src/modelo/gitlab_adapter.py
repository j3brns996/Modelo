"""Bounded GitLab event/issue adapter for the provider-neutral trusted core."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from modelo.build import BuildError, _git
from modelo.guided_intake import GuidedIntakeResult, compile_guided_intake
from modelo.mac import MacError, extract_adapter_issue_payload
from modelo.platform import _atomic_write, _read_json
from modelo.receipt import canonical_bytes, sha256_bytes, sort_change_delta
from modelo.site import _committed_yaml_config


_DELTA = re.compile(r"(?ms)<!-- modelo:change-delta -->\s*```json\n(\[[\s\S]*?\])\n```\s*<!-- /modelo:change-delta -->")
_DIGEST = re.compile(r"(?m)^- Neutral payload digest: `(sha256:[0-9a-f]{64})`$")
_HOST = re.compile(
    r"(?=.{1,253}(?![\s\S]))(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
GitLabIntakeResult = GuidedIntakeResult


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _gitlab_project_identity(project: dict[str, Any]) -> tuple[str, str, str, str, str]:
    path = project.get("path_with_namespace")
    web_url = project.get("web_url")
    if not isinstance(path, str) or not isinstance(web_url, str):
        raise ValueError("GitLab project identity fields are invalid")
    segments = path.split("/")
    if len(segments) < 2 or any(not _PATH_SEGMENT.fullmatch(value) for value in segments):
        raise ValueError("GitLab project path is not canonical")
    parsed = urlsplit(web_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("GitLab project URL is not canonical HTTPS") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not _HOST.fullmatch(parsed.hostname)
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or web_url != f"https://{parsed.hostname}/{path}"
    ):
        raise ValueError("GitLab project URL is not canonical HTTPS")
    namespace = "/".join(segments[:-1])
    return parsed.hostname, path, namespace, segments[-1], web_url


def compile_gitlab_intake(event: dict[str, Any]) -> GuidedIntakeResult:
    project = event.get("project")
    object_attributes = event.get("object_attributes")
    if not isinstance(project, dict) or not isinstance(object_attributes, dict) or object_attributes.get("state") != "opened":
        raise ValueError("GitLab intake requires an open issue event")
    iid = object_attributes.get("iid")
    description = object_attributes.get("description")
    if not _is_positive_int(iid) or not isinstance(description, str):
        raise ValueError("GitLab intake event fields are invalid")
    _, _, _, _, project_url = _gitlab_project_identity(project)
    return compile_guided_intake(
        body=description,
        issue_url=f"{project_url}/-/issues/{iid}",
        request_labels=("Request type",),
        provider_name="GitLab",
        change_request_name="merge request",
    )


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
    project_id = project.get("id")
    source_project_id = object_attributes.get("source_project_id")
    target_project_id = object_attributes.get("target_project_id")
    merge_request_iid = object_attributes.get("iid")
    if (
        object_attributes.get("state") != "opened"
        or not _is_positive_int(project_id)
        or not _is_positive_int(source_project_id)
        or not _is_positive_int(target_project_id)
        or not _is_positive_int(merge_request_iid)
        or source_project_id != target_project_id
        or source_project_id != project_id
    ):
        raise BuildError("trusted GitLab check accepts only open same-repository merge requests")
    try:
        _gitlab_project_identity(project)
    except ValueError as exc:
        raise BuildError(str(exc)) from exc
    return object_attributes, project


def _gitlab_issue_reference(
    description: str, project_url: str, *, control: bool,
) -> str:
    marker = "control-issue" if control else "mac-issue"
    opening = f"<!-- modelo:{marker} -->"
    closing = f"<!-- /modelo:{marker} -->"
    matches = re.findall(
        rf"<!-- modelo:{marker} -->([^\r\n<>]{{1,2048}})<!-- /modelo:{marker} -->",
        description,
    )
    prefix = f"{project_url}/-/issues/"
    if (
        len(matches) != 1
        or description.count(opening) != 1
        or description.count(closing) != 1
        or not matches[0].startswith(prefix)
        or not re.fullmatch(r"[1-9][0-9]{0,19}", matches[0][len(prefix):])
    ):
        noun = "implementation" if control else "MAC"
        raise BuildError(
            f"{'control merge request' if control else 'merge request'} lacks one "
            f"same-repository {noun} issue marker"
        )
    return matches[0][len(prefix):]


def gitlab_issue_reference(event_path: Path) -> str:
    mr, project = _merge_request(event_path)
    _, _, _, _, project_url = _gitlab_project_identity(project)
    return _gitlab_issue_reference(str(mr.get("description", "")), project_url, control=False)


def gitlab_control_issue_reference(event_path: Path) -> str:
    mr, project = _merge_request(event_path)
    _, _, _, _, project_url = _gitlab_project_identity(project)
    return _gitlab_issue_reference(str(mr.get("description", "")), project_url, control=True)


def _require_gitlab_config(configured: dict[str, Any], project: dict[str, Any]) -> None:
    try:
        host, _, namespace, name, project_url = _gitlab_project_identity(project)
    except ValueError as exc:
        raise BuildError(str(exc)) from exc
    repo_config = configured["repository"]
    if (
        repo_config["adapter"] != "gitlab"
        or repo_config["host"] != host
        or repo_config["namespace"] != namespace
        or repo_config["name"] != name
        or repo_config["web_base"] != project_url
        or configured["project"]["default_branch"] != project.get("default_branch")
    ):
        raise BuildError("GitLab repository identity differs from modelo.yaml")


def _require_gitlab_issue(
    issue: dict[str, Any], project: dict[str, Any], issue_reference: str,
) -> None:
    _, _, _, _, project_url = _gitlab_project_identity(project)
    expected_issue_url = f"{project_url}/-/issues/{issue_reference}"
    issue_iid = issue.get("iid")
    if (
        not _is_positive_int(issue_iid)
        or str(issue_iid) != issue_reference
        or issue.get("state") not in {"opened", "open"}
        or not _is_positive_int(issue.get("project_id"))
        or issue.get("project_id") != project.get("id")
        or issue.get("web_url") != expected_issue_url
    ):
        raise BuildError("GitLab issue response differs from linked open issue")


def prepare_gitlab(
    *, root: Path, event_path: Path, issue_path: Path, validation_sha: str,
    validation_tree: str, as_of: date, metadata_output: Path, context_output: Path,
) -> None:
    mr, project = _merge_request(event_path)
    _, _, _, _, project_url = _gitlab_project_identity(project)
    issue_reference = _gitlab_issue_reference(
        str(mr.get("description", "")), project_url, control=False,
    )
    issue = _read_json(issue_path, "GitLab issue")
    try:
        _require_gitlab_issue(issue, project, issue_reference)
    except BuildError as exc:
        raise BuildError("GitLab issue response differs from linked open MAC issue") from exc
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
    _require_gitlab_config(configured, project)
    profile = configured["publication"]["active_profile"]
    profile_config = configured["publication"]["profiles"][profile]
    if profile_config["delivery"] != "pages" or profile_config["visibility"] != "public":
        raise BuildError("GitLab pre-merge adapter currently requires the configured public Pages profile")
    host, _, namespace, name, _ = _gitlab_project_identity(project)
    metadata = {
        "contract_version": "0.1.0",
        "repository": {"provider": "gitlab", "host": host, "namespace": namespace, "name": name},
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
        "workflow_identity": f"{project['path_with_namespace']}/{configured['paths']['gitlab_ci']}@{configured['project']['default_branch']}",
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
    _, _, _, _, project_url = _gitlab_project_identity(project)
    issue_reference = _gitlab_issue_reference(
        str(mr.get("description", "")), project_url, control=True,
    )
    issue = _read_json(issue_path, "GitLab control issue")
    try:
        _require_gitlab_issue(issue, project, issue_reference)
    except BuildError as exc:
        raise BuildError("GitLab control issue response differs from linked open issue") from exc
    base = str(mr.get("target", {}).get("sha") or mr.get("diff_base_sha", ""))
    head = str(mr.get("last_commit", {}).get("id") or mr.get("head_sha", ""))
    tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    epoch = int(str(_git(root, "show", "-s", "--format=%at", head)).strip())
    configured = _committed_yaml_config(root, head, "modelo.yaml")
    protected = _committed_yaml_config(root, base, "modelo.yaml")
    _require_gitlab_config(configured, project)
    _require_gitlab_config(protected, project)
    host, _, namespace, name, _ = _gitlab_project_identity(project)
    context = {
        "contract_version": "0.1.0",
        "repository": {"provider": "gitlab", "host": host, "namespace": namespace, "name": name},
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
