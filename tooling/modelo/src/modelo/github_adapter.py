"""Bounded GitHub event/issue adapter for the provider-neutral trusted core."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
from typing import Any

from modelo.build import BuildError, _git
from modelo.guided_intake import GuidedIntakeResult, compile_guided_intake
from modelo.mac import MacError, extract_adapter_issue_payload
from modelo.platform import _atomic_write, _read_json
from modelo.receipt import canonical_bytes, sha256_bytes, sort_change_delta
from modelo.site import _committed_yaml_config


_ISSUE = re.compile(r"<!-- modelo:mac-issue -->(https://github\.com/([^/]+)/([^/]+)/issues/([1-9][0-9]{0,19}))<!-- /modelo:mac-issue -->")
_CONTROL_ISSUE = re.compile(r"<!-- modelo:control-issue -->(https://github\.com/([^/]+)/([^/]+)/issues/([1-9][0-9]{0,19}))<!-- /modelo:control-issue -->")
_DELTA = re.compile(r"(?ms)<!-- modelo:change-delta -->\s*```json\n(\[[\s\S]*?\])\n```\s*<!-- /modelo:change-delta -->")
_DIGEST = re.compile(r"(?m)^- Neutral payload digest: `(sha256:[0-9a-f]{64})`$")
_REPOSITORY = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?/"
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
)
GitHubIntakeResult = GuidedIntakeResult


def compile_github_intake(event: dict[str, Any]) -> GuidedIntakeResult:
    repository = event.get("repository")
    issue = event.get("issue")
    if not isinstance(repository, dict) or not isinstance(issue, dict) or issue.get("state") != "open":
        raise ValueError("GitHub intake requires an open issue event")
    full_name = repository.get("full_name")
    number = issue.get("number")
    body = issue.get("body")
    if (
        not isinstance(full_name, str)
        or not _REPOSITORY.fullmatch(full_name)
        or not isinstance(number, int)
        or isinstance(number, bool)
        or number <= 0
        or not isinstance(body, str)
    ):
        raise ValueError("GitHub intake event fields are invalid")
    return compile_guided_intake(
        body=body,
        issue_url=f"https://github.com/{full_name}/issues/{number}",
        request_labels=("Modelo MAC request type", "Request type"),
        provider_name="GitHub",
        change_request_name="pull request",
    )


def write_github_intake_outputs(
    *, event_path: Path, issue_body_output: Path, comment_output: Path,
) -> None:
    result = compile_github_intake(_read_json(event_path, "GitHub issue event"))
    _atomic_write(issue_body_output, result.issue_body.encode("utf-8"))
    _atomic_write(comment_output, result.comment_body.encode("utf-8"))


def _pull_request(event_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    event = _read_json(event_path, "GitHub event")
    pull = event.get("pull_request")
    repository = event.get("repository")
    if not isinstance(pull, dict) or not isinstance(repository, dict):
        raise BuildError("GitHub event is not a pull request")
    if pull.get("base", {}).get("ref") != repository.get("default_branch"):
        raise BuildError("pull request does not target the repository default branch")
    if pull.get("state") != "open" or pull.get("head", {}).get("repo", {}).get("full_name") != repository.get("full_name"):
        raise BuildError("trusted GitHub check accepts only open same-repository pull requests")
    return pull, repository


def github_issue_reference(event_path: Path) -> str:
    pull, repository = _pull_request(event_path)
    return _github_issue_reference(pull, repository, control=False)


def _github_issue_reference(
    pull: dict[str, Any], repository: dict[str, Any], *, control: bool,
) -> str:
    pattern = _CONTROL_ISSUE if control else _ISSUE
    marker = "control-issue" if control else "mac-issue"
    opening = f"<!-- modelo:{marker} -->"
    closing = f"<!-- /modelo:{marker} -->"
    body = str(pull.get("body", ""))
    matches = pattern.findall(body)
    if (
        len(matches) != 1
        or body.count(opening) != 1
        or body.count(closing) != 1
        or f"{matches[0][1]}/{matches[0][2]}" != repository.get("full_name")
    ):
        noun = "implementation" if control else "MAC"
        prefix = "control " if control else ""
        raise BuildError(
            f"{prefix}pull request lacks one same-repository {noun} issue marker"
        )
    return matches[0][3]


def github_control_issue_reference(event_path: Path) -> str:
    pull, repository = _pull_request(event_path)
    return _github_issue_reference(pull, repository, control=True)


def _require_github_config(configured: dict[str, Any], repository: dict[str, Any]) -> None:
    full_name = repository.get("full_name")
    if not isinstance(full_name, str) or full_name.count("/") != 1:
        raise BuildError("GitHub repository identity is invalid")
    owner, name = full_name.split("/", 1)
    repo_config = configured["repository"]
    if (
        repo_config["adapter"] != "github"
        or repo_config["host"] != "github.com"
        or repo_config["namespace"] != owner
        or repo_config["name"] != name
        or repo_config["web_base"] != f"https://github.com/{full_name}"
        or configured["project"]["default_branch"] != repository.get("default_branch")
    ):
        raise BuildError("GitHub repository identity differs from modelo.yaml")


def prepare_github(
    *, root: Path, event_path: Path, issue_path: Path, validation_sha: str,
    validation_tree: str, as_of: date, metadata_output: Path, context_output: Path,
) -> None:
    pull, repository = _pull_request(event_path)
    issue_reference = _github_issue_reference(pull, repository, control=False)
    issue = _read_json(issue_path, "GitHub issue")
    expected_issue_url = f"https://github.com/{repository['full_name']}/issues/{issue_reference}"
    issue_number = issue.get("number")
    if (
        not isinstance(issue_number, int)
        or isinstance(issue_number, bool)
        or issue_number <= 0
        or str(issue_number) != issue_reference
        or issue.get("state") != "open"
        or issue.get("html_url") != expected_issue_url
    ):
        raise BuildError("GitHub issue response differs from linked open MAC issue")
    try:
        payload = extract_adapter_issue_payload(str(issue.get("body", "")), "github")
    except MacError as exc:
        raise BuildError(f"invalid GitHub MAC issue body: {exc}") from exc
    body = str(pull.get("body", ""))
    delta_matches = _DELTA.findall(body)
    digest_matches = _DIGEST.findall(body)
    if len(delta_matches) != 1:
        raise BuildError("pull request lacks one expected change delta marker")
    if digest_matches != [sha256_bytes(canonical_bytes(payload))]:
        raise BuildError("pull request payload digest differs from the linked MAC issue")
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
        raise BuildError("pull request expected change delta is invalid JSON") from exc
    if not isinstance(delta, list) or not delta or len(delta) > 25:
        raise BuildError("pull request expected change delta must contain 1 to 25 records")
    base = str(pull.get("base", {}).get("sha", ""))
    head = str(pull.get("head", {}).get("sha", ""))
    tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    epoch = int(str(_git(root, "show", "-s", "--format=%at", head)).strip())
    configured = _committed_yaml_config(root, head, "modelo.yaml")
    _require_github_config(configured, repository)
    profile = configured["publication"]["active_profile"]
    profile_config = configured["publication"]["profiles"][profile]
    if profile_config["delivery"] != "pages" or profile_config["visibility"] != "public":
        raise BuildError("GitHub pre-merge adapter currently requires the configured public Pages profile")
    owner, name = str(repository["full_name"]).split("/", 1)
    metadata = {
        "contract_version": "0.1.0",
        "repository": {"provider": "github", "host": "github.com", "namespace": owner, "name": name},
        "issue": {"reference": issue_reference, "url": str(issue.get("html_url", "")), "state": "open"},
        "base_sha": base, "head_sha": head, "head_tree_sha": tree,
        "payload": payload, "payload_digest": sha256_bytes(canonical_bytes(payload)),
        "expected_change_delta": sort_change_delta(delta),
    }
    context = {
        "contract_version": "0.1.0", "repository": metadata["repository"],
        "change_request": str(pull.get("number", "")), "base_sha": base, "head_sha": head,
        "head_tree_sha": tree, "validation_sha": validation_sha,
        "validation_tree_sha": validation_tree, "as_of": as_of.isoformat(),
        "source_date_epoch": epoch, "profile": profile,
        "base_url": configured["site"]["base_url"], "base_path": configured["site"]["base_path"],
        "publication_capability": "public-pages",
        "workflow_identity": f"{repository['full_name']}/{configured['paths']['github_adapter']}/workflows/modelo.yml@{configured['project']['default_branch']}",
        "workflow_sha": base, "run_id": str(__import__('os').environ.get("GITHUB_RUN_ID", "local")),
        "check_name": "modelo/check",
        "gates": {"lock": "success", "schema": "success", "tests": "success", "package": "success"},
    }
    _atomic_write(metadata_output, canonical_bytes(metadata))
    _atomic_write(context_output, canonical_bytes(context))


def prepare_github_control(
    *, root: Path, event_path: Path, issue_path: Path, validation_sha: str, validation_tree: str,
    as_of: date, context_output: Path,
) -> None:
    pull, repository = _pull_request(event_path)
    issue_reference = _github_issue_reference(pull, repository, control=True)
    issue = _read_json(issue_path, "GitHub control issue")
    expected_issue_url = f"https://github.com/{repository['full_name']}/issues/{issue_reference}"
    issue_number = issue.get("number")
    if (
        not isinstance(issue_number, int)
        or isinstance(issue_number, bool)
        or issue_number <= 0
        or str(issue_number) != issue_reference
        or issue.get("state") != "open"
        or issue.get("html_url") != expected_issue_url
    ):
        raise BuildError("GitHub control issue response differs from linked open issue")
    base = str(pull.get("base", {}).get("sha", ""))
    head = str(pull.get("head", {}).get("sha", ""))
    tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    epoch = int(str(_git(root, "show", "-s", "--format=%at", head)).strip())
    configured = _committed_yaml_config(root, head, "modelo.yaml")
    protected = _committed_yaml_config(root, base, "modelo.yaml")
    _require_github_config(configured, repository)
    _require_github_config(protected, repository)
    owner, name = str(repository["full_name"]).split("/", 1)
    context = {
        "contract_version": "0.1.0",
        "repository": {"provider": "github", "host": "github.com", "namespace": owner, "name": name},
        "control_issue": issue_reference,
        "control_issue_digest": sha256_bytes(str(issue.get("body", "")).encode("utf-8")),
        "change_request": str(pull.get("number", "")),
        "base_sha": base, "head_sha": head,
        "head_tree_sha": tree, "validation_sha": validation_sha,
        "validation_tree_sha": validation_tree, "as_of": as_of.isoformat(),
        "source_date_epoch": epoch,
        "workflow_identity": f"{repository['full_name']}/{protected['paths']['github_adapter']}/workflows/modelo.yml@{protected['project']['default_branch']}",
        "workflow_sha": base, "run_id": str(__import__('os').environ.get("GITHUB_RUN_ID", "local")),
        "check_name": "modelo/check",
        "gates": {
            "lock": "success", "schema": "success", "trusted_tests": "success",
            "proposed_tests": "success", "trusted_package": "success",
            "proposed_package": "success",
        },
    }
    _atomic_write(context_output, canonical_bytes(context))
