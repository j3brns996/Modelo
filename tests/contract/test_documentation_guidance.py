from __future__ import annotations

import ast
from pathlib import Path
import re
import struct
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
SECURITY = ROOT / "SECURITY.md"
DOCS_README = ROOT / "docs/README.md"
AUTHORING_GUIDE = ROOT / "docs/authoring.md"
IMPLEMENTATION_PLAN = ROOT / "docs/implementation-plan.md"
LAUNCH_RUNBOOK = ROOT / "docs/launch-runbook.md"
AGENTS = ROOT / "AGENTS.md"
SITE_DOCS = ROOT / "site/content/docs.md"
SITE_PROPOSE = ROOT / "site/content/propose.md"
CLI_SOURCE = ROOT / "tooling/modelo/src/modelo/cli.py"
MODELO_CONFIG = ROOT / "modelo.yaml"
README_SCREENSHOTS = {
    "docs/img/modelo-home.png": ("home", "navigation", "synthetic", "status", "catalogue"),
    "docs/img/modelo-catalogue.png": ("catalogue", "filters", "model", "result", "cards"),
}


def _read(path: Path) -> str:
    assert path.is_file(), f"expected file to exist: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _headings(text: str, level: int) -> list[str]:
    marker = "#" * level
    return [
        line[len(marker):].strip()
        for line in text.splitlines()
        if line.startswith(f"{marker} ")
    ]


def _markdown_links(text: str) -> list[str]:
    return re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)


def _markdown_images(text: str) -> list[tuple[str, str]]:
    return re.findall(r"!\[([^\]]+)\]\(([^)]+)\)", text)


def _word_count(text: str) -> int:
    stripped = re.sub(r"```[\s\S]*?```", " ", text)
    stripped = re.sub(r"`[^`]*`", " ", stripped)
    return len(re.findall(r"\b[\w.-]+\b", stripped))


def _assert_heading_contains(headings: list[str], expected: str) -> None:
    token = _normalise(expected)
    assert any(token in _normalise(heading) for heading in headings), (
        f"expected heading containing {expected!r}, found {headings!r}"
    )


def _assert_contains_all_tokens(text: str, groups: tuple[str, ...]) -> None:
    lowered = text.lower()
    missing = [token for token in groups if token not in lowered]
    assert not missing, f"missing expected tokens: {missing!r}"


def _registered_cli_commands() -> set[str]:
    tree = ast.parse(_read(CLI_SOURCE))
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_parser"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


def _configured_site_url(route_name: str) -> str:
    config = yaml.safe_load(_read(MODELO_CONFIG))
    base_url = config["site"]["base_url"].rstrip("/")
    route = config["site"]["routes"][route_name]
    assert route.startswith("/")
    return base_url + route


def test_readme_guidance_contract_is_human_navigable() -> None:
    text = _read(README)
    assert 550 <= _word_count(text) <= 850
    assert len(_headings(text, 2)) >= 6
    links = _markdown_links(text)
    assert any("github.io/modelo" in link.lower() for link in links), (
        "README must link readers to the live synthetic demo or catalogue"
    )
    assert any("issues/new/choose" in link.lower() for link in links), (
        "README must link readers to the issue chooser"
    )
    assert any(link == "CONTRIBUTING.md" for link in links)
    assert any(link == "docs/README.md" for link in links)
    assert any(link == "docs/authoring.md" for link in links)
    assert any(link == "SECURITY.md" for link in links)
    assert _configured_site_url("propose") + "#builder" in links
    lowered = text.lower()
    assert "t10" in lowered
    assert "public visibility" in lowered
    assert any(token in lowered for token in ("reuse", "reuse rights"))
    assert any(token in lowered for token in ("no root licence", "no root license", "undecided")), (
        "README must explain that root licence/reuse remains undecided"
    )


def test_readme_product_tour_uses_real_bounded_screenshots() -> None:
    images = {path: alt for alt, path in _markdown_images(_read(README))}
    for relative_path, alt_tokens in README_SCREENSHOTS.items():
        assert relative_path in images, f"README must embed {relative_path}"
        normalised_alt = _normalise(images[relative_path])
        assert all(token in normalised_alt for token in alt_tokens), (
            f"README alt text for {relative_path} must describe its visible content"
        )

        screenshot = ROOT / relative_path
        assert screenshot.is_file(), f"expected screenshot to exist: {relative_path}"
        data = screenshot.read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n"), f"expected PNG signature: {relative_path}"
        assert data[12:16] == b"IHDR", f"expected PNG IHDR chunk: {relative_path}"
        assert struct.unpack(">II", data[16:24]) == (1440, 900), (
            f"expected 1440x900 screenshot: {relative_path}"
        )
        assert 50_000 <= len(data) <= 2_000_000, (
            f"expected a nontrivial, repository-sized screenshot: {relative_path}"
        )


def test_relative_markdown_links_resolve_for_guidance_documents() -> None:
    for path in (README, CONTRIBUTING, DOCS_README, SECURITY):
        text = _read(path)
        for link in _markdown_links(text):
            destination = link.split("#", 1)[0].strip()
            if not destination or destination.startswith("<") or destination.startswith("mailto:"):
                continue
            parsed = urlparse(destination)
            if parsed.scheme or destination.startswith("/"):
                assert parsed.scheme == "https", (
                    f"{path.relative_to(ROOT)} uses non-https absolute link: {destination}"
                )
                continue
            target = (path.parent / destination).resolve()
            assert target.exists(), (
                f"{path.relative_to(ROOT)} has broken relative link: {destination}"
            )


def test_contributing_assigns_roles_and_governance_tokens() -> None:
    text = _read(CONTRIBUTING)
    headings = _headings(text, 2) + _headings(text, 3)
    for role in ("Requester", "Author", "Contributor", "Reviewer", "Approver"):
        _assert_heading_contains(headings, role)
    lowered = text.lower()
    for token in ("linked issue", "one writer", "exact current head", "t10"):
        assert token in lowered
    assert "trusted ci" in lowered
    assert "accepting" in lowered


def test_authoring_guidance_matches_registered_helpers_and_authority() -> None:
    commands = _registered_cli_commands()
    assert {"dev", "evidence-create", "mac-init"} <= commands

    guide = _read(AUTHORING_GUIDE).lower()
    contributing = _read(CONTRIBUTING).lower()
    for command in ("modelo dev evidence-create", "modelo dev mac-init"):
        assert command in guide
        assert command in contributing
    _assert_contains_all_tokens(guide, ("--output", "draft", "linked issue", "trusted"))
    assert any(token in guide for token in ("standard output", "stdout"))
    assert "approval" in guide and "admissib" in guide


def test_site_authoring_prose_explains_bounded_interactive_scope() -> None:
    docs = _read(SITE_DOCS).lower()
    proposal = _read(SITE_PROPOSE).lower()

    _assert_contains_all_tokens(docs, ("docs/authoring.md", "modelo dev", "draft", "admissib"))
    _assert_contains_all_tokens(proposal, ("static", "interactive", "add", "change"))
    for operation in ("revoke", "move", "batch"):
        assert operation in proposal
    _assert_contains_all_tokens(proposal, ("non-canonical", "trusted", "compiler"))
    assert "mac payload" in proposal and "not a mac payload" in proposal


def test_agents_distinguishes_public_demo_from_absent_production_publication() -> None:
    text = _read(AGENTS)
    lowered = text.lower()
    assert "synthetic" in lowered
    assert "pages" in lowered
    assert "demo" in lowered
    assert "production" in lowered
    assert "post-merge" in lowered
    assert any(token in lowered for token in ("remain absent", "remains absent", "absent"))


def test_agents_limits_read_only_cli_rule_to_cloud_providers() -> None:
    text = _read(AGENTS).lower()
    _assert_contains_all_tokens(text, ("cloud-provider cli", "read-only", "modelo dev", "--output"))
    assert "local file" in text


def test_implementation_plan_has_history_and_removes_stale_issue_reference() -> None:
    text = _read(IMPLEMENTATION_PLAN)
    lowered = text.lower()
    assert "histor" in lowered, "implementation plan must include historical framing"
    assert "issue #37 candidate" not in lowered


def test_launch_runbook_separates_bootstrap_controls_and_remaining_launch_gates() -> None:
    headings = _headings(_read(LAUNCH_RUNBOOK), 2)
    _assert_heading_contains(headings, "completed bootstrap")
    _assert_heading_contains(headings, "current control posture")
    _assert_heading_contains(headings, "remaining production launch gates")


def test_security_policy_states_current_reporting_and_reuse_limits() -> None:
    text = _read(SECURITY)
    lowered = text.lower()
    assert "2026-09-02" in text
    _assert_contains_all_tokens(lowered, ("private vulnerability reporting", "not configured"))
    assert ("private" in lowered or "confidential" in lowered)
    assert (
        "promised" in lowered
        and "private" in lowered
        and "confidential" in lowered
        and "repository" in lowered
        and "channel" in lowered
    ), "SECURITY.md must state that no private/confidential repository channel is promised"
    assert "public" in lowered and any(token in lowered for token in ("secrets", "credentials", "tokens"))
    assert "public visibility" in lowered
    assert any(token in lowered for token in ("reuse", "reuse rights"))
    assert any(token in lowered for token in ("no root licence", "no root license", "undecided"))


def test_repository_has_no_root_licence_file_until_decided() -> None:
    assert not (ROOT / "LICENSE").exists()
    assert not (ROOT / "LICENCE").exists()


def test_docs_readme_marks_internal_docs_as_non_site_content() -> None:
    text = _read(DOCS_README)
    lowered = text.lower()
    assert "repository contributors" in lowered
    assert "published site route" in lowered
    assert any(phrase in lowered for phrase in ("not the published site route", "is not the published site route"))
    assert "authoring.md" in lowered


def test_contract_status_tokens_stay_aligned_with_guidance_docs() -> None:
    contract = yaml.safe_load((ROOT / "docs/contract.yaml").read_text(encoding="utf-8"))
    readme = _read(README).lower()
    agents = _read(AGENTS).lower()
    assert contract["contract"]["status"] == (
        "t8_premerge_t9_synthetic_pages_demo_and_functional_explorer_implemented_"
        "production_launch_slice_pending"
    )
    assert "synthetic pages" in readme and "demo" in readme
    assert "t10" in readme
    assert "do not add real production catalogue data before t10 passes remotely" in readme
    assert contract["approval"]["agent_approval"]["enabled"] is False
    assert "agent approval" in readme
    assert "disabled" in readme
    assert "production catalogue records" in agents
    assert "t10 passes remotely" in agents
