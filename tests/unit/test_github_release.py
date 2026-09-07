from copy import deepcopy

import pytest
from modelo.build import BuildError
from modelo.github_adapter import github_publication_capability
from modelo.github_release import accepted_files, approved_review, capability_failures


def test_release_workflow_preserves_acceptance_and_credential_boundaries():
    from pathlib import Path

    import yaml

    root = Path(__file__).parents[2]
    workflow = yaml.safe_load((root / ".github/workflows/release.yml").read_text())
    assert workflow["permissions"]["contents"] == "read"
    assert workflow["permissions"]["pages"] == "read"
    steps = workflow["jobs"]["release"]["steps"]
    fetch = next(step for step in steps if "Fetch accepted merge" in step["name"])
    assert "refs/pull/${CHANGE_REQUEST}/head:refs/modelo/accepted-head" in fetch["run"]
    assert "rev-parse refs/modelo/accepted-head)" in fetch["run"]
    lint = next(step for step in steps if "local quality" in step["name"])
    assert "env" not in lint and "secrets." not in lint["run"]
    publish = next(step for step in steps if step.get("id") == "publish")
    assert "--publish" in publish["run"]
    assert workflow["jobs"]["pages"]["if"] == "needs.release.outputs.profile == 'synthetic'"
    intake = (root / ".github/workflows/modelo.yml").read_text()
    assert "validation/dist/receipts/push.json" in intake
    assert "sender: .sender.login" in intake


def test_private_delivery_never_downgrades_to_public_artifacts():
    config = {
        "publication": {
            "active_profile": "private",
            "profiles": {
                "private": {
                    "visibility": "private",
                    "delivery": "restricted_artifact_or_capability_checked_pages",
                }
            },
        }
    }
    assert github_publication_capability(config, {"private": True}) == "restricted-artifact"
    for repository in ({}, {"private": False}, {"private": "true"}):
        with pytest.raises(BuildError, match="private repository"):
            github_publication_capability(config, repository)


def test_capabilities_require_each_acceptance_control():
    rules = [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_review_thread_resolution": True,
            },
        },
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [{"context": "modelo/check", "integration_id": 15368}],
            },
        },
    ]
    tags = [{"type": "update"}, {"type": "deletion"}]
    assert capability_failures(rules, tags, 15368) == []
    for index in range(len(rules)):
        assert capability_failures(rules[:index] + rules[index + 1 :], tags, 15368)
    for key in rules[2]["parameters"]:
        changed = deepcopy(rules)
        changed[2]["parameters"][key] = False
        assert capability_failures(changed, tags, 15368)
    changed = deepcopy(rules)
    changed[3]["parameters"]["required_status_checks"][0]["integration_id"] = None
    assert capability_failures(changed, tags, 15368)
    assert capability_failures(rules, tags[:1], 15368)


def test_review_is_current_independent_and_not_withdrawn():
    pull = {
        "user": {"login": "author"},
        "commits": 1,
        "head": {"sha": "a" * 40},
        "merged_at": "2026-09-07T12:00:00Z",
    }
    commits = [{"author": {"login": "author"}, "committer": {"login": "committer"}}]
    review = {
        "id": 10,
        "user": {"login": "j3brns", "type": "User"},
        "state": "APPROVED",
        "commit_id": "a" * 40,
        "submitted_at": "2026-09-07T11:00:00Z",
    }
    assert approved_review(pull, [review], commits, "j3brns", "pusher") == review
    for changed in (
        review | {"commit_id": "b" * 40},
        review | {"state": "DISMISSED"},
        review | {"submitted_at": "2026-09-07T13:00:00Z"},
        review | {"user": {"login": "j3brns", "type": "Bot"}},
    ):
        with pytest.raises(BuildError):
            approved_review(pull, [changed], commits, "j3brns", "pusher")
    with pytest.raises(BuildError, match="approval is missing"):
        approved_review(
            pull, [review, review | {"id": 11, "state": "DISMISSED"}], commits, "j3brns", "pusher"
        )
    with pytest.raises(BuildError, match="cannot approve"):
        approved_review(pull, [review], commits, "author", "pusher")
    with pytest.raises(BuildError, match="unresolved"):
        approved_review(
            pull,
            [review],
            [{"author": None, "committer": {"login": "committer"}}],
            "j3brns",
            "pusher",
        )


def test_accepted_archive_is_read_without_extracting_paths():
    import io
    import zipfile

    def archive(extra=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as output:
            output.writestr("receipts/check.json", b"{}\n")
            output.writestr("receipts/mac.json", b"{}\n")
            output.writestr("receipts/push.json", b"{}\n")
            if extra:
                info = zipfile.ZipInfo("placeholder")
                info.filename = extra[0]
                output.writestr(info, extra[1])
        return stream.getvalue()

    assert accepted_files(archive()) == (b"{}\n", b"{}\n", b"{}\n")
    for path in ("../escape", "/absolute", "bad\\path"):
        with pytest.raises(BuildError, match="unsafe"):
            accepted_files(archive((path, b"bad")))
    with pytest.raises(BuildError):
        accepted_files(b"not a zip")


def test_github_acceptance_binds_provider_run_review_and_artifact(monkeypatch, tmp_path):
    import io
    import json
    import zipfile
    from pathlib import Path

    from modelo import github_release as adapter
    from modelo.receipt import canonical_bytes

    cases = json.loads((Path(__file__).parents[1] / "fixtures/schema/cases.json").read_text())[
        "cases"
    ]
    check = deepcopy(
        next(case["valid"][0] for case in cases if case["schema"] == "check-receipt.schema.json")
    )
    check["ci"]["run_id"] = "42"
    head = check["head_sha"]
    name = "j3brns996/Modelo"
    prefix = f"repos/{name}"
    document = {
        "project": {"default_branch": "main"},
        "paths": {"github_adapter": ".github", "codeowners": "CODEOWNERS"},
        "platform": {"identities": {"control_plane_owner": {"github": "j3brns"}}},
        "publication": {
            "active_profile": "synthetic",
            "profiles": {"synthetic": {"delivery": "pages", "visibility": "public"}},
        },
    }
    responses = {
        f"{prefix}/pulls/20": {
            "merged": True,
            "state": "closed",
            "commits": 1,
            "user": {"login": "author"},
            "merged_at": "2026-09-07T12:00:00Z",
            "merge_commit_sha": "d" * 40,
            "head": {"sha": head, "ref": "proposal", "repo": {"full_name": name}},
            "base": {"ref": "main", "repo": {"full_name": name}},
        },
        f"{prefix}/actions/runs/42": {
            "id": 42,
            "status": "completed",
            "conclusion": "success",
            "event": "pull_request_target",
            "path": ".github/workflows/modelo.yml",
            "head_sha": head,
            "head_branch": "proposal",
            "repository": {"full_name": name},
            "head_repository": {"full_name": name},
            "updated_at": "2026-09-07T11:00:00Z",
            "check_suite_id": 55,
        },
        f"{prefix}/actions/runs/42/jobs": {
            "jobs": [
                {
                    "name": "modelo/check",
                    "conclusion": "success",
                    "head_sha": head,
                    "completed_at": "2026-09-07T11:00:00Z",
                    "check_run_url": f"https://api.github.com/{prefix}/check-runs/9",
                }
            ]
        },
        f"{prefix}/check-runs/9": {
            "app": {"id": 15368},
            "head_sha": head,
            "name": "modelo/check",
            "conclusion": "success",
            "check_suite": {"id": 55},
        },
        f"{prefix}/actions/runs/42/artifacts": {
            "artifacts": [
                {
                    "id": 5,
                    "name": f"modelo-check-20-{head}",
                    "expired": False,
                    "size_in_bytes": 1000,
                    "created_at": "2026-09-07T10:59:00Z",
                    "workflow_run": {"id": 42, "head_sha": head},
                }
            ]
        },
        f"{prefix}/pulls/20/reviews": [
            {
                "id": 7,
                "user": {"login": "j3brns", "type": "User"},
                "state": "APPROVED",
                "commit_id": head,
                "submitted_at": "2026-09-07T11:30:00Z",
            }
        ],
        f"{prefix}/pulls/20/commits": [
            {"author": {"login": "author"}, "committer": {"login": "committer"}}
        ],
    }
    stream = io.BytesIO()
    responses[f"{prefix}/actions/workflows/modelo.yml/runs"] = {
        "workflow_runs": [
            responses[f"{prefix}/actions/runs/42"] | {"created_at": "2026-09-07T10:00:00Z"}
        ]
    }
    with zipfile.ZipFile(stream, "w") as output:
        output.writestr("receipts/check.json", canonical_bytes(check))
        output.writestr("receipts/mac.json", b"{}\n")
        output.writestr(
            "receipts/push.json",
            canonical_bytes({"action": "synchronize", "head_sha": head, "sender": "pusher"}),
        )
    monkeypatch.setattr(adapter, "_repository", lambda root: (document, name))
    monkeypatch.setattr(
        adapter,
        "github_capabilities",
        lambda root: {"capable": True, "private": False, "integration_id": 15368},
    )
    monkeypatch.setattr(adapter, "_api", lambda endpoint: responses[endpoint.split("?")[0]])
    monkeypatch.setattr(adapter, "_response", lambda endpoint: stream.getvalue())
    monkeypatch.setattr(adapter, "_git", lambda *args, **kwargs: "# policy\n* @j3brns\n")

    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    monkeypatch.setattr(adapter, "_atomic_write", write)
    accepted = []
    monkeypatch.setattr(
        adapter,
        "build_release",
        lambda request: accepted.append(request) or {"release": request.release},
    )
    assert adapter.prepare_release(tmp_path, 20, 42, "catalogue-20260907.1") == {
        "release": "catalogue-20260907.1"
    }
    assert accepted[0].approval["reviewer_platform_identity"] == "j3brns"
    original = deepcopy(responses)
    for endpoint, path, value in (
        (f"{prefix}/actions/runs/42", ["conclusion"], "cancelled"),
        (f"{prefix}/actions/workflows/modelo.yml/runs", ["workflow_runs", 0, "id"], 43),
        (f"{prefix}/actions/runs/42/jobs", ["jobs", 0, "completed_at"], "2026-09-07T12:00:01Z"),
        (f"{prefix}/check-runs/9", ["app", "id"], 999),
        (f"{prefix}/actions/runs/42/artifacts", ["artifacts", 0, "expired"], True),
        (f"{prefix}/pulls/20/reviews", [0, "state"], "DISMISSED"),
    ):
        responses.clear()
        responses.update(deepcopy(original))
        target = responses[endpoint]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(BuildError):
            adapter.prepare_release(tmp_path, 20, 42, "catalogue-20260907.1")
    assert len(accepted) == 1


def test_publication_verifies_bytes_and_never_clobbers_existing_release(monkeypatch, tmp_path):
    from modelo import github_release as adapter
    from modelo.receipt import canonical_bytes, publication_digest, sha256_bytes

    files = {"data/catalogue.json": b"{}\n", "index.html": b"<p>Synthetic</p>\n"}
    site = tmp_path / "dist/final/site"
    for name, data in files.items():
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (site / "data/manifest.json").write_bytes(b"{}\n")
    receipt = {
        "profile": "synthetic",
        "release": "catalogue-20260907.1",
        "merge_sha": "a" * 40,
        "accepted_check_receipt_digest": sha256_bytes(b"{}\n"),
        "artifacts": {
            "catalogue": {"sha256": sha256_bytes(files["data/catalogue.json"])},
            "publication": {"sha256": publication_digest(files)},
            "manifest": {"sha256": sha256_bytes(b"{}\n")},
        },
    }
    receipts = tmp_path / "dist/receipts"
    receipts.mkdir()
    for name in ("check.json", "mac.json", "push.json"):
        (receipts / name).write_bytes(b"{}\n")
    assets = {
        "publication.zip": adapter.release_archive(tmp_path, receipt),
        "release.json": canonical_bytes(receipt),
        "check.json": b"{}\n",
        "mac.json": b"{}\n",
        "push.json": b"{}\n",
    }
    assert adapter.release_archive(tmp_path, receipt) == assets["publication.zip"]
    name = "j3brns996/Modelo"
    prefix = f"repos/{name}"
    inventory = [{"name": filename, "id": index} for index, filename in enumerate(assets, 1)]
    remote = {"id": 7, "draft": False}
    monkeypatch.setattr(adapter, "_repository", lambda root: ({}, name))
    monkeypatch.setattr(
        adapter, "github_capabilities", lambda root: {"capable": True, "private": False}
    )

    def api(endpoint, **kwargs):
        if "/git/ref/" in endpoint:
            return {"object": {"type": "tag", "sha": "b" * 40}}
        if "/git/tags/" in endpoint:
            return {
                "tag": receipt["release"],
                "object": {
                    "sha": receipt["merge_sha"],
                    "type": "commit",
                    "url": f"https://api.github.com/{prefix}/git/commits/{receipt['merge_sha']}",
                },
            }
        return remote

    monkeypatch.setattr(adapter, "_api", api)
    monkeypatch.setattr(adapter, "_items", lambda endpoint: inventory)
    monkeypatch.setattr(
        adapter,
        "_response",
        lambda endpoint, **kwargs: assets[inventory[int(endpoint.rsplit("/", 1)[1]) - 1]["name"]],
    )

    def no_write(*args, **kwargs):
        pytest.fail("matching published release must not be rewritten")

    monkeypatch.setattr(adapter, "_write_api", no_write)
    assert adapter.publish_release(tmp_path, receipt) == remote
    assets["publication.zip"] = b"different remote bytes"
    with pytest.raises(BuildError, match="existing release asset differs"):
        adapter.publish_release(tmp_path, receipt)
    (site / "index.html").write_bytes(b"changed local bytes")
    with pytest.raises(BuildError, match="changed after"):
        adapter.publish_release(tmp_path, receipt)
