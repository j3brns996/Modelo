from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_pages_workflow_is_pinned_python_only_and_builds_once() -> None:
    path = ROOT / ".github/workflows/pages.yml"
    raw = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    assert set(workflow["permissions"]) == {"contents", "pages", "id-token"}
    assert workflow["permissions"] == {
        "contents": "read", "pages": "write", "id-token": "write",
    }
    assert "npx" not in raw and "npm " not in raw and "actions/checkout" not in raw
    uses = re.findall(r"uses:\s*([^\s#]+)", raw)
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", value) for value in uses)
    assert raw.count("--kind demo") == 1
    assert "upload-pages-artifact" not in raw
    assert raw.count("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02") == 1
    assert "tar --dereference --hard-dereference" in raw
    assert 'INPUT_PATH: source/dist/pages/site' in raw
    assert 'name: github-pages' in raw
    assert 'path: ${{ runner.temp }}/artifact.tar' in raw
    assert "compression-level: 0" in raw
    assert "needs: build" in raw
    assert "Deploy without rebuilding" in raw


def test_pages_workflow_can_only_publish_the_synthetic_demo() -> None:
    raw = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "--profile synthetic" in raw
    assert "modelo --root source config site" in raw
    assert 'test "${#site_config[@]}" = 3' in raw
    assert 'as_of="${site_config[2]}"' in raw
    assert "date -u +%F" not in raw
    assert "jq" not in raw
    assert "https://j3brns996.github.io/Modelo/" not in raw
    assert "--mac-metadata" not in raw
    assert "--merge-commit" not in raw
    assert "--publication-capability" not in raw
    assert "refs/heads/${DEFAULT_BRANCH}" in raw
    assert "test \"$(git -C source rev-parse" in raw
    assert "actions/upload-artifact@v4" not in raw
