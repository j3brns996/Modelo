"""Provider-neutral trusted-check assembly.

The Git-provider adapter supplies one bounded context and MAC envelope.  This
module performs no network access and treats both files as untrusted until all
schema, Git and artefact correlations have been proved locally.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from modelo.build import BuildError, _git, _layout, _strict_json_bytes, _strict_json_file
from modelo.change import with_snapshot
from modelo.config import CONTRACT_VERSION, load_config
from modelo.receipt import (
    canonical_bytes,
    publication_digest,
    release_correlation_errors,
    sha256_bytes,
)
from modelo.schemas import SchemaSet
from modelo.site import (
    FinalBuildRequest,
    ValidationBuildRequest,
    _committed_yaml_config,
    build_final_site,
    build_validation_site,
)


@dataclass(frozen=True, slots=True)
class TrustedCheckRequest:
    root: Path
    context: Path
    mac_metadata: Path
    output: Path


@dataclass(frozen=True, slots=True)
class TrustedControlCheckRequest:
    root: Path
    context: Path
    output: Path


@dataclass(frozen=True, slots=True)
class ReleaseRequest:
    """Inputs supplied only after the host adapter verifies acceptance and approval."""

    root: Path
    accepted_check: Path
    accepted_check_digest: str
    approval: dict[str, Any]
    merge_commit: str
    release: str
    mac_metadata: Path
    publication_capability: str


def build_release(request: ReleaseRequest) -> dict[str, Any]:
    """Build one final publication and its detached receipt from accepted inputs.

    This local assembly does not authenticate a Git-host review or CI run. The
    trusted host adapter must establish those facts before calling it.
    """
    root = request.root.resolve()
    config = load_config(root)
    check = _read_json(request.accepted_check, "accepted check receipt")
    if sha256_bytes(canonical_bytes(check)) != request.accepted_check_digest:
        raise BuildError("accepted check receipt digest differs from trusted acceptance")
    schemas = SchemaSet(root, config.paths["schemas"])
    findings = schemas.validate(config.paths["check_receipt_schema"].name, check, "accepted check")
    if findings:
        raise BuildError(f"accepted check violates schema: {findings[0].message}")
    head = check["head_sha"]
    base = check["base_sha"]
    merge = request.merge_commit
    if str(_git(root, "rev-parse", "--verify", f"{merge}^{{commit}}")).strip() != merge:
        raise BuildError("release merge must be a complete canonical commit SHA")
    parents = str(_git(root, "rev-list", "--parents", "-n", "1", merge)).split()[1:]
    if parents != [base]:
        raise BuildError("release requires a squash commit whose parent is the accepted base")
    merge_tree = str(_git(root, "rev-parse", f"{merge}^{{tree}}")).strip()
    head_tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    if merge_tree != head_tree or head_tree != check["head_tree_sha"]:
        raise BuildError("release merge tree differs from the accepted head tree")
    document = _committed_yaml_config(root, base, "modelo.yaml")
    _verify_protected_workflow(check["ci"] | {"repository": check["repository"]}, document)
    if check["ci"]["workflow_sha"] != base or check["ci"]["head_sha"] != head:
        raise BuildError("accepted check workflow/base/head correlation failed")
    if check["ci"]["provider"] != check["repository"]["provider"]:
        raise BuildError("accepted check provider differs from repository")
    metadata = _strict_json_file(request.mac_metadata)
    for field, expected in {
        "repository": check["repository"],
        "base_sha": base,
        "head_sha": head,
        "head_tree_sha": head_tree,
        "payload_digest": check["mac_payload_digest"],
        "expected_change_delta": check["change_delta"],
    }.items():
        if metadata.get(field) != expected:
            raise BuildError(f"accepted MAC metadata differs: {field}")
    if metadata.get("issue", {}).get("reference") != check["mac_issue"]:
        raise BuildError("accepted MAC issue differs from receipt")
    actors_path = config.paths["actors_registry"].as_posix()
    actors_digest = sha256_bytes(bytes(_git(root, "show", f"{head}:{actors_path}", binary=True)))
    tool_digest = publication_digest(
        _committed_files(root, head, ("pyproject.toml", "tooling/modelo"))
    )
    lock_digest = sha256_bytes(bytes(_git(root, "show", f"{head}:uv.lock", binary=True)))
    if (actors_digest, tool_digest, lock_digest) != (
        check["actors_registry_digest"],
        check["tool_digest"],
        check["lock_digest"],
    ):
        raise BuildError("accepted source tool, lock or actor digest differs")
    receipt = {
        field: check[field]
        for field in (
            "contract_version",
            "repository",
            "base_sha",
            "head_tree_sha",
            "as_of",
            "source_date_epoch",
            "profile",
            "base_url",
            "base_path",
            "promotion_durability",
            "artifacts",
            "tool_digest",
            "lock_digest",
            "ci",
            "mac_issue",
            "change_request",
            "change_delta",
        )
    }
    receipt.update(
        release=request.release,
        source_sha=head,
        merge_sha=merge,
        merge_tree_sha=merge_tree,
        accepted_check_receipt_digest=request.accepted_check_digest,
        approval=request.approval,
    )
    findings = schemas.validate(
        config.paths["release_receipt_schema"].name, receipt, "release receipt"
    )
    if findings:
        raise BuildError(f"release receipt violates schema: {findings[0].message}")
    errors = release_correlation_errors(check, receipt)
    if errors:
        raise BuildError("release receipt correlation failed: " + ", ".join(sorted(errors)))
    output = root / "dist/receipts/release.json"
    if output.exists():
        raise BuildError("release receipt already exists; use a fresh release workspace")
    result = build_final_site(
        FinalBuildRequest(
            root=root,
            base_commit=base,
            source_commit=head,
            source_tree=head_tree,
            merge_commit=merge,
            merge_tree=merge_tree,
            as_of=date.fromisoformat(check["as_of"]),
            source_date_epoch=check["source_date_epoch"],
            profile=check["profile"],
            base_url=check["base_url"],
            base_path=check["base_path"],
            output="dist/final",
            mac_metadata=request.mac_metadata,
            publication_capability=request.publication_capability,
        )
    )
    catalogue_digest = sha256_bytes((result.output / "site/data/catalogue.json").read_bytes())
    if catalogue_digest != check["artifacts"]["catalogue"]["sha256"]:
        raise BuildError("final catalogue differs from accepted catalogue")
    receipt["artifacts"] = {
        "catalogue": {"path": "site/data/catalogue.json", "sha256": catalogue_digest},
        "publication": {"path": "site", "sha256": result.publication_digest},
        "manifest": {
            "path": "site/data/manifest.json",
            "sha256": sha256_bytes(result.manifest_bytes),
        },
    }
    findings = schemas.validate(
        config.paths["release_receipt_schema"].name, receipt, "release receipt"
    )
    if findings or release_correlation_errors(check, receipt):
        raise BuildError("final release receipt failed validation")
    _atomic_write(output, canonical_bytes(receipt))
    return receipt


def _committed_files(root: Path, commit: str, prefixes: tuple[str, ...]) -> dict[str, bytes]:
    names = str(_git(root, "ls-tree", "-r", "--name-only", commit, "--", *prefixes)).splitlines()
    return {
        name: bytes(_git(root, "show", f"{commit}:{name}", binary=True))
        for name in names
        if name == "pyproject.toml" or name.startswith("tooling/modelo/")
    }


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) > 262_144:
            raise BuildError(f"{label} exceeds 262144 bytes")
        value = _strict_json_bytes(raw, label)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, BuildError) as exc:
        raise BuildError(f"cannot read strict {label} JSON") from exc
    if not isinstance(value, dict):
        raise BuildError(f"{label} must be a JSON object")
    return value


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_protected_workflow(context: dict[str, Any], protected: dict[str, Any]) -> None:
    repository = context["repository"]
    protected_repository = protected["repository"]
    provider = protected_repository["adapter"]
    if provider not in {"github", "gitlab"} or repository["provider"] not in {
        "github",
        "gitlab",
    }:
        raise BuildError("trusted workflow provider is unsupported")
    if repository != {
        "provider": provider,
        "host": protected_repository["host"],
        "namespace": protected_repository["namespace"],
        "name": protected_repository["name"],
    }:
        raise BuildError("trusted workflow repository identity differs from protected modelo.yaml")
    if provider == "github":
        workflow_path = f"{protected['paths']['github_adapter']}/workflows/modelo.yml"
    else:
        workflow_path = protected["paths"]["gitlab_ci"]
    expected = (
        f"{protected_repository['namespace']}/{protected_repository['name']}/"
        f"{workflow_path}@{protected['project']['default_branch']}"
    )
    if context["workflow_identity"] != expected:
        raise BuildError("trusted workflow identity differs from protected modelo.yaml")


def run_trusted_check(request: TrustedCheckRequest) -> dict[str, Any]:
    root = request.root.resolve()
    config = load_config(root)
    layout = _layout(root)
    expected_output = root / "dist/receipts/check.json"
    if request.output.resolve(strict=False) != expected_output:
        raise BuildError("check receipt output must equal dist/receipts/check.json")
    context = _read_json(request.context, "trusted check context")
    metadata = _strict_json_file(request.mac_metadata)
    head = context.get("head_sha", "")
    schemas = with_snapshot(
        root, head, lambda snapshot: SchemaSet(snapshot, config.paths["schemas"])
    )
    context_schema = config.paths["trusted_check_context_schema"].name
    findings = schemas.validate(context_schema, context, str(request.context))
    if findings:
        raise BuildError(f"trusted check context violates schema: {findings[0].message}")
    repository = context["repository"]
    configured = layout.repository
    if repository != {
        "provider": configured["adapter"],
        "host": configured["host"],
        "namespace": configured["namespace"],
        "name": configured["name"],
    }:
        raise BuildError("trusted repository identity differs from modelo.yaml")
    if context["workflow_sha"] != context["base_sha"]:
        raise BuildError("trusted workflow SHA must equal the protected base SHA")
    protected_document = _committed_yaml_config(root, context["base_sha"], "modelo.yaml")
    _verify_protected_workflow(context, protected_document)
    if context["validation_tree_sha"] != context["head_tree_sha"]:
        raise BuildError("validation tree must equal proposed head tree")
    changed_raw = bytes(
        _git(root, "diff", "--name-only", "-z", context["base_sha"], head, binary=True)
    )
    changed_paths = [item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item]
    if not changed_paths or any(not path.startswith("catalogue/") for path in changed_paths):
        raise BuildError("MAC data mode accepts catalogue-only changes")
    if metadata.get("base_sha") != context["base_sha"] or metadata.get("head_sha") != head:
        raise BuildError("MAC metadata base/head differs from trusted context")
    if metadata.get("head_tree_sha") != context["head_tree_sha"]:
        raise BuildError("MAC metadata tree differs from trusted context")

    build_validation_site(
        ValidationBuildRequest(
            root=root,
            base_commit=context["base_sha"],
            source_commit=head,
            source_tree=context["head_tree_sha"],
            validation_commit=context["validation_sha"],
            validation_tree=context["validation_tree_sha"],
            as_of=date.fromisoformat(context["as_of"]),
            source_date_epoch=context["source_date_epoch"],
            profile=context["profile"],
            base_url=context["base_url"],
            base_path=context["base_path"],
            output=layout.validation_root.as_posix(),
            mac_metadata=request.mac_metadata,
            publication_capability=context["publication_capability"],
        )
    )
    site_root = root / layout.validation_root / layout.publication_subdir
    catalogue_path = site_root / layout.catalogue_path
    manifest_path = site_root / layout.manifest_path
    manifest = _read_json(manifest_path, "validation manifest")
    if manifest.get("validation_commit") != context["validation_sha"]:
        raise BuildError("validation manifest is not bound to trusted validation commit")
    tool_files = _committed_files(root, head, ("tooling/modelo", "pyproject.toml"))
    if not tool_files:
        raise BuildError("trusted tool input set is empty")
    actors_path = config.paths["actors_registry"].as_posix()
    actors_raw = bytes(_git(root, "show", f"{head}:{actors_path}", binary=True))
    lock_raw = bytes(_git(root, "show", f"{head}:uv.lock", binary=True))
    receipt = {
        "contract_version": CONTRACT_VERSION,
        "repository": repository,
        "change_request": context["change_request"],
        "base_sha": context["base_sha"],
        "head_sha": head,
        "head_tree_sha": context["head_tree_sha"],
        "validation_sha": context["validation_sha"],
        "validation_tree_sha": context["validation_tree_sha"],
        "as_of": context["as_of"],
        "source_date_epoch": context["source_date_epoch"],
        "profile": context["profile"],
        "base_url": context["base_url"],
        "base_path": context["base_path"],
        "promotion_durability": "fsync-durable",
        "artifacts": {
            "catalogue": {
                "path": "site/data/catalogue.json",
                "sha256": sha256_bytes(catalogue_path.read_bytes()),
            },
            "publication": {"path": "site", "sha256": manifest["publication_digest"]},
            "manifest": {
                "path": "site/data/manifest.json",
                "sha256": sha256_bytes(manifest_path.read_bytes()),
            },
        },
        "tool_digest": publication_digest(tool_files),
        "lock_digest": sha256_bytes(lock_raw),
        "actors_registry_digest": sha256_bytes(actors_raw),
        "mac_issue": metadata["issue"]["reference"],
        "mac_payload_digest": metadata["payload_digest"],
        "change_delta": metadata["expected_change_delta"],
        "ci": {
            "provider": repository["provider"],
            "workflow_identity": context["workflow_identity"],
            "workflow_sha": context["workflow_sha"],
            "run_id": context["run_id"],
            "check": context["check_name"],
            "result": "success",
            "head_sha": head,
            "gates": {**context["gates"], "validation_site": "success"},
        },
    }
    receipt_schema = config.paths["check_receipt_schema"].name
    findings = schemas.validate(receipt_schema, receipt, str(request.output))
    if findings:
        raise BuildError(f"check receipt violates schema: {findings[0].message}")
    _atomic_write(request.output, canonical_bytes(receipt))
    return receipt


def run_trusted_control_check(request: TrustedControlCheckRequest) -> dict[str, Any]:
    root = request.root.resolve()
    expected_output = root / "dist/receipts/control-check.json"
    if request.output.resolve(strict=False) != expected_output:
        raise BuildError("control receipt output must equal dist/receipts/control-check.json")
    context = _read_json(request.context, "trusted control context")
    head = context.get("head_sha", "")
    base = context.get("base_sha", "")
    base_config = with_snapshot(root, base, lambda snapshot: load_config(snapshot))
    schemas = with_snapshot(
        root, base, lambda snapshot: SchemaSet(snapshot, base_config.paths["schemas"])
    )
    findings = schemas.validate(
        base_config.paths["trusted_control_context_schema"].name, context, str(request.context)
    )
    if findings:
        raise BuildError(f"trusted control context violates schema: {findings[0].message}")
    document = _committed_yaml_config(root, head, "modelo.yaml")
    repository = context["repository"]
    configured = document["repository"]
    if repository != {
        "provider": configured["adapter"],
        "host": configured["host"],
        "namespace": configured["namespace"],
        "name": configured["name"],
    }:
        raise BuildError("trusted repository identity differs from proposed modelo.yaml")
    if context["workflow_sha"] != context["base_sha"]:
        raise BuildError("trusted workflow SHA must equal the protected base SHA")
    protected_document = _committed_yaml_config(root, base, "modelo.yaml")
    _verify_protected_workflow(context, protected_document)
    validation = context["validation_sha"]
    actual_head_tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    actual_validation_tree = str(_git(root, "rev-parse", f"{validation}^{{tree}}")).strip()
    parents = str(_git(root, "rev-list", "--parents", "-n", "1", validation)).split()
    if actual_head_tree != context["head_tree_sha"]:
        raise BuildError("proposed head tree differs from trusted context")
    if (
        actual_validation_tree != context["validation_tree_sha"]
        or actual_validation_tree != actual_head_tree
    ):
        raise BuildError("control validation tree must equal proposed head tree")
    if parents != [validation, base, head]:
        raise BuildError("control validation commit must have exact base and head parents")
    if str(_git(root, "rev-parse", "HEAD")).strip() != validation:
        raise BuildError("checked-out HEAD differs from control validation commit")
    if str(_git(root, "status", "--porcelain=v1", "--untracked-files=all")).strip():
        raise BuildError("working tree is dirty")
    raw_paths = bytes(_git(root, "diff", "--name-only", "-z", base, head, binary=True))
    paths = sorted(item.decode("utf-8", "strict") for item in raw_paths.split(b"\0") if item)
    if not paths or any(path.startswith("catalogue/") for path in paths):
        raise BuildError("control-plane mode forbids catalogue paths")
    trusted_tools = _committed_files(root, base, ("tooling/modelo", "pyproject.toml"))
    proposed_tools = _committed_files(root, head, ("tooling/modelo", "pyproject.toml"))
    if not trusted_tools or not proposed_tools:
        raise BuildError("control-plane tool input set is empty")
    trusted_lock = bytes(_git(root, "show", f"{base}:uv.lock", binary=True))
    proposed_lock = bytes(_git(root, "show", f"{head}:uv.lock", binary=True))
    receipt = {
        "contract_version": CONTRACT_VERSION,
        "kind": "control-plane",
        "repository": repository,
        "control_issue": context["control_issue"],
        "control_issue_digest": context["control_issue_digest"],
        "change_request": context["change_request"],
        "base_sha": base,
        "head_sha": head,
        "head_tree_sha": actual_head_tree,
        "validation_sha": validation,
        "validation_tree_sha": actual_validation_tree,
        "as_of": context["as_of"],
        "source_date_epoch": context["source_date_epoch"],
        "changed_paths": paths,
        "trusted_tool_digest": publication_digest(trusted_tools),
        "proposed_tool_digest": publication_digest(proposed_tools),
        "trusted_lock_digest": sha256_bytes(trusted_lock),
        "proposed_lock_digest": sha256_bytes(proposed_lock),
        "approval_mode": "human-codeowner-only",
        "ci": {
            "provider": repository["provider"],
            "workflow_identity": context["workflow_identity"],
            "workflow_sha": context["workflow_sha"],
            "run_id": context["run_id"],
            "check": context["check_name"],
            "result": "success",
            "head_sha": head,
            "gates": context["gates"],
        },
    }
    findings = schemas.validate(
        base_config.paths["control_check_receipt_schema"].name, receipt, str(request.output)
    )
    if findings:
        raise BuildError(f"control check receipt violates schema: {findings[0].message}")
    _atomic_write(request.output, canonical_bytes(receipt))
    return receipt
