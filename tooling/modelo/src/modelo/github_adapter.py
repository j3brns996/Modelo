"""Bounded GitHub event/issue adapter for the provider-neutral trusted core."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
from typing import Any

from modelo.build import BuildError, _git
from modelo.mac import MacError, extract_adapter_issue_payload
from modelo.platform import _atomic_write, _read_json
from modelo.receipt import canonical_bytes, sha256_bytes, sort_change_delta
from modelo.site import _committed_yaml_config


_ISSUE = re.compile(r"<!-- modelo:mac-issue -->(https://github\.com/([^/]+)/([^/]+)/issues/([1-9][0-9]{0,19}))<!-- /modelo:mac-issue -->")
_CONTROL_ISSUE = re.compile(r"<!-- modelo:control-issue -->(https://github\.com/([^/]+)/([^/]+)/issues/([1-9][0-9]{0,19}))<!-- /modelo:control-issue -->")
_DELTA = re.compile(r"(?ms)<!-- modelo:change-delta -->\s*```json\n(\[[\s\S]*?\])\n```\s*<!-- /modelo:change-delta -->")
_DIGEST = re.compile(r"(?m)^- Neutral payload digest: `(sha256:[0-9a-f]{64})`$")


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
    matches = _ISSUE.findall(str(pull.get("body", "")))
    if len(matches) != 1 or f"{matches[0][1]}/{matches[0][2]}" != repository.get("full_name"):
        raise BuildError("pull request lacks one same-repository MAC issue marker")
    return matches[0][3]


def github_control_issue_reference(event_path: Path) -> str:
    pull, repository = _pull_request(event_path)
    matches = _CONTROL_ISSUE.findall(str(pull.get("body", "")))
    if len(matches) != 1 or f"{matches[0][1]}/{matches[0][2]}" != repository.get("full_name"):
        raise BuildError("control pull request lacks one same-repository implementation issue marker")
    return matches[0][3]


def prepare_github(
    *, root: Path, event_path: Path, issue_path: Path, validation_sha: str,
    validation_tree: str, as_of: date, metadata_output: Path, context_output: Path,
) -> None:
    pull, repository = _pull_request(event_path)
    issue_reference = github_issue_reference(event_path)
    issue = _read_json(issue_path, "GitHub issue")
    if str(issue.get("number")) != issue_reference or issue.get("state") != "open":
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
    if configured["repository"]["adapter"] != "github":
        raise BuildError("proposed configuration does not select the GitHub adapter")
    if configured["project"]["default_branch"] != repository.get("default_branch"):
        raise BuildError("GitHub default branch differs from modelo.yaml")
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
    issue_reference = github_control_issue_reference(event_path)
    issue = _read_json(issue_path, "GitHub control issue")
    expected_issue_url = f"https://github.com/{repository['full_name']}/issues/{issue_reference}"
    if (
        str(issue.get("number")) != issue_reference or issue.get("state") != "open"
        or issue.get("html_url") != expected_issue_url
    ):
        raise BuildError("GitHub control issue response differs from linked open issue")
    base = str(pull.get("base", {}).get("sha", ""))
    head = str(pull.get("head", {}).get("sha", ""))
    tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    epoch = int(str(_git(root, "show", "-s", "--format=%at", head)).strip())
    configured = _committed_yaml_config(root, head, "modelo.yaml")
    protected = _committed_yaml_config(root, base, "modelo.yaml")
    if configured["repository"]["adapter"] != "github" or configured["project"]["default_branch"] != repository.get("default_branch"):
        raise BuildError("GitHub adapter/default branch differs from proposed modelo.yaml")
    if protected["repository"]["adapter"] != "github" or protected["project"]["default_branch"] != repository.get("default_branch"):
        raise BuildError("trusted workflow identity differs from protected modelo.yaml")
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
