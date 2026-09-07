"""GitHub release acceptance from bounded, read-only provider observations."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from modelo.build import BuildError, _git, _strict_json_bytes, _walk_regular_tree
from modelo.config import load_config
from modelo.loader import load_yaml_mapping, strict_unique_json_pairs
from modelo.platform import ReleaseRequest, _atomic_write, build_release
from modelo.receipt import canonical_bytes, publication_digest, sha256_bytes


def _response(endpoint: str, *, allow_missing: bool = False, octet_stream: bool = False) -> bytes:
    try:
        args = ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint]
        if octet_stream:
            args += ["--header", "Accept: application/octet-stream"]
        result = subprocess.run(
            args,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BuildError("GitHub read request could not complete") from exc
    if allow_missing and result.returncode:
        try:
            if (
                json.loads(result.stdout, object_pairs_hook=strict_unique_json_pairs).get("status")
                == "404"
            ):
                return b"null"
        except (ValueError, AttributeError):
            pass
    if result.returncode or len(result.stdout) > 134_217_728:
        raise BuildError("GitHub read request failed or exceeded its response limit")
    return result.stdout


def _api(endpoint: str, *, allow_missing: bool = False) -> Any:
    raw = _response(endpoint, allow_missing=allow_missing)
    if len(raw) > 8_388_608:
        raise BuildError("GitHub JSON response exceeded its response limit")
    try:
        return json.loads(raw, object_pairs_hook=strict_unique_json_pairs)
    except (ValueError, UnicodeError) as exc:
        raise BuildError("GitHub response is not JSON") from exc


def _repository(root: Path) -> tuple[dict[str, Any], str]:
    load_config(root)
    document = dict(load_yaml_mapping(root, PurePosixPath("modelo.yaml")))
    repository = document["repository"]
    if repository["adapter"] != "github" or repository["host"] != "github.com":
        raise BuildError("GitHub release adapter requires configured github.com repository")
    return document, f"{repository['namespace']}/{repository['name']}"


def capability_failures(
    rules: list[dict[str, Any]], tag_rules: list[dict[str, Any]], integration_id: int
) -> list[str]:
    """Evaluate effective branch rules and active matching tag rules."""
    failures = []
    kinds = {rule.get("type") for rule in rules}
    for kind in ("deletion", "non_fast_forward"):
        if kind not in kinds:
            failures.append(f"default branch lacks {kind} protection")
    reviews = [rule.get("parameters", {}) for rule in rules if rule.get("type") == "pull_request"]
    if not any(
        item.get("required_approving_review_count", 0) >= 1
        and all(
            item.get(key) is True
            for key in (
                "dismiss_stale_reviews_on_push",
                "require_code_owner_review",
                "require_last_push_approval",
                "required_review_thread_resolution",
            )
        )
        for item in reviews
    ):
        failures.append(
            "independent CODEOWNER approval, stale dismissal and last-push review are not enforced"
        )
    checks = [
        rule.get("parameters", {}) for rule in rules if rule.get("type") == "required_status_checks"
    ]
    if not any(
        item.get("strict_required_status_checks_policy") is True
        and any(
            check.get("context") == "modelo/check" and check.get("integration_id") == integration_id
            for check in item.get("required_status_checks", [])
        )
        for item in checks
    ):
        failures.append("current-base modelo/check is not required with a bound integration")
    tag_kinds = {rule.get("type") for rule in tag_rules}
    if not {"deletion", "update"}.issubset(tag_kinds):
        failures.append("catalogue release tags are not protected against updates and deletion")
    return failures


def github_capabilities(root: Path) -> dict[str, Any]:
    document, name = _repository(root)
    prefix = f"repos/{name}"
    repository = _api(prefix)
    branch = document["project"]["default_branch"]
    if repository.get("full_name") != name or repository.get("default_branch") != branch:
        raise BuildError("GitHub repository identity differs from configuration")
    rules = _api(f"{prefix}/rules/branches/{quote(branch, safe='')}")
    sets = _api(f"{prefix}/rulesets?per_page=100")
    if not isinstance(rules, list) or not isinstance(sets, list) or len(sets) >= 100:
        raise BuildError("GitHub rules response is incomplete or invalid")
    tag_rules = []
    bypass = []
    for item in sets:
        if item.get("enforcement") != "active":
            continue
        details = _api(f"{prefix}/rulesets/{item['id']}")
        if details.get("bypass_actors"):
            bypass.append(str(item["id"]))
        refs = details.get("conditions", {}).get("ref_name", {})
        if (
            item.get("target") == "tag"
            and not refs.get("exclude")
            and any(
                pattern in {"~ALL", "refs/tags/*", "refs/tags/catalogue-*"}
                for pattern in refs.get("include", [])
            )
        ):
            tag_rules.extend(details.get("rules", []))
    app = _api("apps/github-actions")
    if type(app.get("id")) is not int or app.get("slug") != "github-actions":
        raise BuildError("GitHub Actions integration identity is unavailable")
    failures = capability_failures(rules, tag_rules, app["id"])
    if bypass:
        failures.append("active rulesets contain bypass actors: " + ", ".join(bypass))
    permissions = _api(f"{prefix}/actions/permissions/workflow")
    if permissions.get("default_workflow_permissions") != "read":
        failures.append("Actions default token is not read-only")
    if permissions.get("can_approve_pull_request_reviews") is not False:
        failures.append("Actions may approve pull requests")
    return {
        "repository": name,
        "capable": not failures,
        "failures": failures,
        "private": repository.get("private") is True,
        "integration_id": app["id"],
    }


def _items(prefix: str, field: str | None = None, *, max_pages: int = 10) -> list[dict[str, Any]]:
    result = []
    for page in range(1, max_pages + 1):
        separator = "&" if "?" in prefix else "?"
        response = _api(f"{prefix}{separator}per_page=100&page={page}")
        batch = response.get(field) if field and isinstance(response, dict) else response
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            raise BuildError("GitHub list response is invalid")
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise BuildError(f"GitHub list exceeds the {max_pages * 100}-item bound")


def approved_review(
    pull: dict[str, Any],
    reviews: list[dict[str, Any]],
    commits: list[dict[str, Any]],
    owner: str,
    last_pusher: str,
) -> dict[str, Any]:
    """Require a current independent human CODEOWNER review from provider data."""
    if not isinstance(last_pusher, str) or not last_pusher:
        raise BuildError("last pusher identity is unavailable")
    identities = {pull.get("user", {}).get("login", "").casefold(), last_pusher.casefold()}
    if not commits or len(commits) != pull.get("commits"):
        raise BuildError("GitHub commit authorship evidence is incomplete")
    for commit in commits:
        for role in ("author", "committer"):
            identity = commit.get(role)
            if not isinstance(identity, dict) or not isinstance(identity.get("login"), str):
                raise BuildError("GitHub commit identity is unresolved")
            identities.add(identity["login"].casefold())
    if not owner or owner.casefold() in identities:
        raise BuildError("CODEOWNER is an author or committer and cannot approve")
    latest = {}
    for review in sorted(reviews, key=lambda item: item.get("id", 0)):
        user = review.get("user", {})
        login = user.get("login")
        if not isinstance(login, str) or type(review.get("id")) is not int:
            raise BuildError("GitHub review identity is invalid")
        if review.get("state") not in {"COMMENTED", "PENDING"}:
            latest[login.casefold()] = review
    if any(review.get("state") == "CHANGES_REQUESTED" for review in latest.values()):
        raise BuildError("GitHub reviews include unresolved changes requested")
    review = latest.get(owner.casefold(), {})
    if (
        review.get("state") != "APPROVED"
        or review.get("commit_id") != pull["head"]["sha"]
        or review.get("user", {}).get("type") != "User"
    ):
        raise BuildError("current exact-head human CODEOWNER approval is missing")
    try:
        approved = datetime.fromisoformat(review["submitted_at"].replace("Z", "+00:00"))
        merged = datetime.fromisoformat(pull["merged_at"].replace("Z", "+00:00"))
        if approved.tzinfo is None or merged.tzinfo is None or approved > merged:
            raise ValueError("approval timestamp is outside merge acceptance")
    except (KeyError, TypeError, ValueError) as exc:
        raise BuildError("GitHub approval timestamp is invalid") from exc
    return review


def accepted_files(raw: bytes) -> tuple[bytes, bytes, bytes]:
    """Read just the two accepted inputs, without extracting archive paths."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise BuildError("accepted artifact contains duplicate paths")
            for info in archive.infolist():
                name = info.orig_filename
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise BuildError("accepted artifact contains an unsafe path")
            result = []
            for name in ("receipts/check.json", "receipts/mac.json", "receipts/push.json"):
                info = archive.getinfo(name)
                if info.file_size > 262_144 or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise BuildError("accepted receipt is oversized or a symbolic link")
                result.append(archive.read(info))
            return result[0], result[1], result[2]
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise BuildError("accepted artifact lacks readable check and MAC inputs") from exc


def _before_merge(value: Any, merged_at: Any) -> None:
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        merged = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        if observed.tzinfo is None or merged.tzinfo is None or observed > merged:
            raise ValueError("postmerge evidence")
    except (AttributeError, TypeError, ValueError) as exc:
        raise BuildError("accepted CI and artifacts must predate merge") from exc


def prepare_release(root: Path, change_request: int, run_id: int, release: str) -> dict[str, Any]:
    if (
        type(change_request) is not int
        or type(run_id) is not int
        or min(change_request, run_id) < 1
    ):
        raise BuildError("change request and run ID must be positive integers")
    document, name = _repository(root)
    capabilities = github_capabilities(root)
    if not capabilities["capable"]:
        raise BuildError("GitHub release incapable: " + "; ".join(capabilities["failures"]))
    prefix = f"repos/{name}"
    pull = _api(f"{prefix}/pulls/{change_request}")
    run = _api(f"{prefix}/actions/runs/{run_id}")
    if (
        pull.get("merged") is not True
        or pull.get("state") != "closed"
        or pull.get("base", {}).get("ref") != document["project"]["default_branch"]
        or pull.get("head", {}).get("repo", {}).get("full_name") != name
        or pull.get("base", {}).get("repo", {}).get("full_name") != name
    ):
        raise BuildError("release requires a merged same-repository default-branch PR")
    head = pull["head"]["sha"]
    workflow = document["paths"]["github_adapter"] + "/workflows/modelo.yml"
    if (
        run.get("id") != run_id
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("event") != "pull_request_target"
        or run.get("path") != workflow
        or run.get("head_sha") != head
        or run.get("repository", {}).get("full_name") != name
        or run.get("head_repository", {}).get("full_name") != name
    ):
        raise BuildError("release run is not successful trusted exact-head CI")
    branch = pull["head"].get("ref")
    if not isinstance(branch, str) or not branch or run.get("head_branch") != branch:
        raise BuildError("release run branch does not match the accepted PR")
    runs = _items(
        f"{prefix}/actions/workflows/modelo.yml/runs?event=pull_request_target&branch={quote(branch, safe='')}",
        "workflow_runs",
    )
    merged_at = datetime.fromisoformat(pull["merged_at"].replace("Z", "+00:00"))
    applicable = []
    for observed in runs:
        created = datetime.fromisoformat(observed["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None or merged_at.tzinfo is None:
            raise BuildError("trusted run chronology lacks timezone")
        if (
            observed.get("event") == "pull_request_target"
            and observed.get("path") == workflow
            and observed.get("head_branch") == branch
            and created <= merged_at
        ):
            if type(observed.get("id")) is not int:
                raise BuildError("trusted run identity is invalid")
            applicable.append(observed["id"])
    if not applicable or max(applicable) != run_id:
        raise BuildError("selected CI is not the latest premerge trusted branch run")
    jobs = _items(f"{prefix}/actions/runs/{run_id}/jobs", "jobs")
    final = [job for job in jobs if job.get("name") == "modelo/check"]
    if (
        len(final) != 1
        or final[0].get("conclusion") != "success"
        or final[0].get("head_sha") != head
    ):
        raise BuildError("trusted final modelo/check is missing or unsuccessful")
    _before_merge(final[0].get("completed_at"), pull.get("merged_at"))
    _before_merge(run.get("updated_at"), pull.get("merged_at"))
    check_url = final[0].get("check_run_url", "")
    expected_url = f"https://api.github.com/{prefix}/check-runs/"
    if (
        not isinstance(check_url, str)
        or not check_url.startswith(expected_url)
        or not check_url[len(expected_url) :].isdigit()
    ):
        raise BuildError("trusted final check reference is invalid")
    final_check = _api(check_url.removeprefix("https://api.github.com/"))
    if (
        final_check.get("app", {}).get("id") != capabilities["integration_id"]
        or final_check.get("head_sha") != head
        or final_check.get("name") != "modelo/check"
        or final_check.get("conclusion") != "success"
        or final_check.get("check_suite", {}).get("id") != run.get("check_suite_id")
    ):
        raise BuildError("final check is not bound to the trusted GitHub Actions run")
    artifacts = _items(f"{prefix}/actions/runs/{run_id}/artifacts", "artifacts")
    matching = [
        item for item in artifacts if item.get("name") == f"modelo-check-{change_request}-{head}"
    ]
    if len(matching) != 1:
        raise BuildError("release requires one exact-head trusted artifact")
    artifact = matching[0]
    _before_merge(artifact.get("created_at"), pull.get("merged_at"))
    if (
        artifact.get("expired") is not False
        or type(artifact.get("size_in_bytes")) is not int
        or not 0 < artifact["size_in_bytes"] <= 134_217_728
        or artifact.get("workflow_run", {}).get("id") != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != head
    ):
        raise BuildError("accepted artifact provenance or size is invalid")
    check_raw, metadata_raw, push_raw = accepted_files(
        _response(f"{prefix}/actions/artifacts/{artifact['id']}/zip")
    )
    check = _strict_json_bytes(check_raw, "accepted check")
    push = _strict_json_bytes(push_raw, "accepted push observation")
    if push.get("action") != "synchronize" or push.get("head_sha") != head:
        raise BuildError("release requires trusted synchronize-run evidence for the accepted head")
    if check_raw != canonical_bytes(check):
        raise BuildError("accepted check is not canonical")
    if (
        check.get("head_sha") != head
        or check.get("change_request") != str(change_request)
        or check.get("ci", {}).get("run_id") != str(run_id)
    ):
        raise BuildError("accepted check differs from trusted run and PR")
    owner = document["platform"]["identities"]["control_plane_owner"]["github"]
    policy = str(_git(root, "show", f"{check['base_sha']}:{document['paths']['codeowners']}"))
    lines = [
        line.strip()
        for line in policy.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if lines != [f"* @{owner}"]:
        raise BuildError("release requires the supported single-owner CODEOWNERS policy")
    review = approved_review(
        pull,
        _items(f"{prefix}/pulls/{change_request}/reviews"),
        _items(f"{prefix}/pulls/{change_request}/commits"),
        document["platform"]["identities"]["control_plane_owner"]["github"],
        push.get("sender"),
    )
    from modelo.github_adapter import github_publication_capability

    capability = github_publication_capability(document, {"private": capabilities["private"]})
    with tempfile.TemporaryDirectory(prefix="modelo-accepted-") as raw:
        directory = Path(raw)
        accepted = directory / "check.json"
        metadata = directory / "mac.json"
        accepted.write_bytes(check_raw)
        metadata.write_bytes(metadata_raw)
        result = build_release(
            ReleaseRequest(
                root=root,
                accepted_check=accepted,
                accepted_check_digest=sha256_bytes(check_raw),
                merge_commit=pull["merge_commit_sha"],
                release=release,
                mac_metadata=metadata,
                publication_capability=capability,
                approval={
                    "reviewer_platform_identity": review["user"]["login"],
                    "reviewer_kind": "human",
                    "approved_head_sha": head,
                    "approval_timestamp": review["submitted_at"],
                    "actors_registry_digest": check["actors_registry_digest"],
                    "independence_and_eligibility_result": "eligible-independent",
                    "provider_approval_and_check_reference": f"https://github.com/{name}/pull/{change_request}#pullrequestreview-{review['id']}",
                },
            )
        )
        for name, data in (
            ("check.json", check_raw),
            ("mac.json", metadata_raw),
            ("push.json", push_raw),
        ):
            _atomic_write(root / "dist/receipts" / name, data)
        return result


def _write_api(endpoint: str, body: dict[str, Any], method: str = "POST") -> Any:
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com", "--method", method, endpoint, "--input", "-"],
            input=canonical_bytes(body),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BuildError(
            "GitHub write request could not complete; inspect remote state before retry"
        ) from exc
    if result.returncode:
        raise BuildError("GitHub write request failed; inspect remote state before retry")
    try:
        return json.loads(result.stdout, object_pairs_hook=strict_unique_json_pairs)
    except (ValueError, UnicodeError) as exc:
        raise BuildError("GitHub write response is not JSON") from exc


def release_archive(root: Path, receipt: dict[str, Any]) -> bytes:
    files = _walk_regular_tree(root / "dist/final/site")
    manifest = files.pop("data/manifest.json", None)
    if (
        manifest is None
        or sha256_bytes(manifest) != receipt["artifacts"]["manifest"]["sha256"]
        or sha256_bytes(files.get("data/catalogue.json", b""))
        != receipt["artifacts"]["catalogue"]["sha256"]
        or publication_digest(files) != receipt["artifacts"]["publication"]["sha256"]
    ):
        raise BuildError("final publication changed after release verification")
    files["data/manifest.json"] = manifest
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo("site/" + name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    raw = stream.getvalue()
    if len(raw) > 134_217_728:
        raise BuildError("release archive exceeds the 128 MiB publication bound")
    return raw


def publish_release(root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    """Publish only the already verified local result; never rebuild or clobber assets."""
    _, name = _repository(root)
    capabilities = github_capabilities(root)
    if not capabilities["capable"] or (
        receipt["profile"] == "private" and not capabilities["private"]
    ):
        raise BuildError("GitHub publication controls or private delivery are unavailable")
    prefix = f"repos/{name}"
    tag = receipt["release"]
    # Source acceptance is performed by prepare_release in the same CLI operation.
    # This function is intentionally not exposed as a standalone upload command.
    assets = {
        "publication.zip": release_archive(root, receipt),
        "release.json": canonical_bytes(receipt),
    }
    for filename in ("check.json", "mac.json", "push.json"):
        assets[filename] = (root / "dist/receipts" / filename).read_bytes()
    if sha256_bytes(assets["check.json"]) != receipt["accepted_check_receipt_digest"]:
        raise BuildError("accepted check changed before upload")
    reference = _api(f"{prefix}/git/ref/tags/{quote(tag, safe='')}", allow_missing=True)
    if reference is None:
        annotated = _write_api(
            f"{prefix}/git/tags",
            {
                "tag": tag,
                "message": f"Modelo {receipt['profile']} catalogue\n",
                "object": receipt["merge_sha"],
                "type": "commit",
            },
        )
        reference = _write_api(
            f"{prefix}/git/refs", {"ref": "refs/tags/" + tag, "sha": annotated["sha"]}
        )
    if reference.get("object", {}).get("type") != "tag":
        raise BuildError("existing release tag is not annotated")
    annotated = _api(f"{prefix}/git/tags/{reference['object']['sha']}")
    if annotated.get("tag") != tag or annotated.get("object") != {
        "sha": receipt["merge_sha"],
        "type": "commit",
        "url": f"https://api.github.com/{prefix}/git/commits/{receipt['merge_sha']}",
    }:
        raise BuildError("release tag differs from the accepted merge")
    remote = _api(f"{prefix}/releases/tags/{quote(tag, safe='')}", allow_missing=True)
    if remote is None:
        remote = _write_api(
            f"{prefix}/releases",
            {
                "tag_name": tag,
                "target_commitish": receipt["merge_sha"],
                "name": tag,
                "body": f"Modelo {receipt['profile']} catalogue. See release.json for acceptance and artifact digests.",
                "draft": True,
                "prerelease": receipt["profile"] == "synthetic",
            },
        )
    existing = _items(f"{prefix}/releases/{remote['id']}/assets")
    names = [item.get("name") for item in existing]
    if len(names) != len(set(names)) or any(filename not in assets for filename in names):
        raise BuildError("release contains duplicate or unexpected assets")
    with tempfile.TemporaryDirectory(prefix="modelo-upload-") as raw:
        for filename, data in assets.items():
            present = next((item for item in existing if item.get("name") == filename), None)
            if present is not None:
                downloaded = _response(
                    f"{prefix}/releases/assets/{present['id']}", octet_stream=True
                )
                if downloaded != data:
                    raise BuildError("existing release asset differs: " + filename)
                continue
            if remote.get("draft") is not True:
                raise BuildError("published release is incomplete; refuse to modify it")
            path = Path(raw) / filename
            path.write_bytes(data)
            try:
                uploaded = subprocess.run(
                    ["gh", "release", "upload", tag, str(path), "--repo", name],
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise BuildError(
                    "release upload did not complete; retry from a fresh verified workspace"
                ) from exc
            if uploaded.returncode:
                raise BuildError("release upload failed; existing assets were not replaced")
    verified = _items(f"{prefix}/releases/{remote['id']}/assets")
    if len(verified) != len(assets) or {item.get("name") for item in verified} != set(assets):
        raise BuildError("uploaded release inventory differs")
    for item in verified:
        if (
            _response(f"{prefix}/releases/assets/{item['id']}", octet_stream=True)
            != assets[item["name"]]
        ):
            raise BuildError("uploaded release bytes differ")
    if remote.get("draft") is True:
        remote = _write_api(f"{prefix}/releases/{remote['id']}", {"draft": False}, "PATCH")
    return remote
