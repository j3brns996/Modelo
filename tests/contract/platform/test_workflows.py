from __future__ import annotations

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_github_trusted_workflow_is_pinned_read_only_and_node_free() -> None:
    path = ROOT / ".github/workflows/modelo.yml"
    raw = path.read_text(encoding="utf-8")
    document = yaml.safe_load(raw)
    assert "pull_request_target" in document[True]
    assert document["permissions"] == {
        "contents": "read", "issues": "read", "pull-requests": "read"
    }
    assert "npx" not in raw and "npm " not in raw and "actions/checkout" not in raw
    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", raw, re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", value) for value in uses)
    assert "enable-cache: false" in raw
    assert "kind=control-plane" in raw and "kind=mac-data" in raw
    assert "modelo/check" in raw
    adapter = (ROOT / "tooling/modelo/src/modelo/github_adapter.py").read_text(encoding="utf-8")
    assert "same-repository pull requests" in adapter
    assert "repository default branch" in adapter
    assert "len(matches) != 1" in adapter and "len(delta_matches) != 1" in adapter
    assert "pull_request_target" in raw and "workflow_dispatch" not in raw
    assert "github.event.pull_request.base.sha" in raw
    assert "github.event.pull_request.head.sha" in raw
    assert "proposed-control:" in raw and "trusted-check:" in raw
    assert "needs: [classify, proposed-control]" in raw
    assert "if: ${{ always() }}" in raw
    assert 'test "${PROPOSED_RESULT}" = success' in raw
    assert "Catalogue and control-plane changes require separate pull requests" in raw
    locked_gate = raw.split("- name: Locked dependency and schema gates", 1)[1].split(
        "- name: Trusted tests", 1
    )[0]
    assert "if: needs.classify.outputs.kind == 'mac-data'" in locked_gate
    proposed = raw.split("  proposed-control:", 1)[1].split("  trusted-check:", 1)[0]
    assert "upload-artifact" not in proposed and "download-artifact" not in proposed
    proposed_execution = proposed.split("- name: Test and package proposed code", 1)[1]
    assert "GH_TOKEN" not in proposed_execution and "github.token" not in proposed_execution
    assert "unset auth GH_TOKEN" in proposed
    assert "github-prepare-control" in raw and "platform control-check" in raw
    assert "curl --fail --silent --show-error --location" not in raw


def test_skills_are_not_workflow_or_package_inputs() -> None:
    workflow = (ROOT / ".github/workflows/modelo.yml").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert ".agents/skills" not in workflow
    assert ".agents/skills" not in pyproject


def test_gitlab_adapter_is_explicitly_fail_closed_until_rehearsed() -> None:
    raw = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    document = yaml.safe_load(raw)
    assert "modelo/check" in document
    assert "npx" not in raw and "npm " not in raw
    assert "receipt adapter capability must be activated" in raw
    assert raw.rstrip().endswith("- exit 1")
