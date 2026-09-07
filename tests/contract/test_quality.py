"""The same real quality gate runs in local verification and protected CI tests."""

from copy import deepcopy
from pathlib import Path

import pytest
from modelo.quality import UBS_REVISION, check, scan, scanner_environment, validate_scan


def test_repository_quality_tools_execute(capsys):
    with capsys.disabled():
        check(Path(__file__).resolve().parents[2])


def test_ubs_detects_harmless_unexecuted_bug_samples_and_accepts_corrections(tmp_path):
    python = tmp_path / "tooling/modelo/src/modelo/sample.py"
    javascript = tmp_path / "site/assets/sample.js"
    python.parent.mkdir(parents=True)
    javascript.parent.mkdir(parents=True)
    for bad in (True, False):
        python.write_text(
            "eval(input())\n" if bad else "def answer():\n    return 42\n", newline="\n"
        )
        javascript.write_text(
            "eval(location.hash);\n" if bad else "const answer = 42;\n", newline="\n"
        )
        report = scan(tmp_path, Path.home() / ".cache/modelo" / f"ubs-{UBS_REVISION}")
        assert (report["totals"]["critical"] > 0) == bad
    missing = tmp_path / "missing-ubs"
    with pytest.raises(ValueError, match="cannot be downloaded"):
        scan(tmp_path, missing)
    assert not missing.exists()


def test_scan_rejects_no_scan_partial_duplicate_and_invalid_summaries():
    scanner = {"language": "python", "files": 1, "critical": 0, "warning": 0, "info": 0}
    valid = {"scanners": [scanner], "totals": {k: v for k, v in scanner.items() if k != "language"}}
    validate_scan(valid, {"python": 1}, 0)
    for key in ("error", "module_error", "status"):
        broken = deepcopy(valid)
        broken["scanners"][0][key] = "timeout"
        with pytest.raises(ValueError):
            validate_scan(broken, {"python": 1}, 0)
    for status in (1, 2, 3, -9):
        with pytest.raises(ValueError):
            validate_scan(valid, {"python": 1}, status)
    for broken in ({}, {"scanners": []}, {**valid, "scanners": [scanner, scanner]}):
        with pytest.raises(ValueError):
            validate_scan(broken, {"python": 1}, 0)

    for key, value in (("files", 0), ("files", True), ("critical", -1), ("warning", "0")):
        broken = deepcopy(valid)
        broken["scanners"][0][key] = value
        with pytest.raises(ValueError):
            validate_scan(broken, {"python": 1}, 0)


def test_scanner_environment_does_not_inherit_reduced_coverage(monkeypatch):
    for key in ("UBS_SKIP_CATEGORIES", "UBS_SKIP_TYPE_NARROWING", "BASH_ENV", "UV_TOOLS"):
        monkeypatch.setenv(key, "injected")
        assert key not in scanner_environment()


def test_failed_scan_replaces_previous_success_report(tmp_path, monkeypatch):
    import json
    import sys

    output = tmp_path / "dist/quality"
    output.mkdir(parents=True)
    (output / "ubs.json").write_text('{"totals":{"critical":0}}')
    monkeypatch.setattr(sys, "platform", "unsupported")
    with pytest.raises(ValueError, match="Linux"):
        scan(tmp_path)
    assert json.loads((output / "ubs.json").read_text()) == {"error": "not_completed"}


def test_real_linters_reject_bad_input_and_accept_correction(tmp_path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    python = tmp_path / "sample.py"
    document = tmp_path / "sample.yaml"
    for bad in (True, False):
        python.write_text("print(undefined_name)\n" if bad else "print('ok')\n")
        document.write_text("value: 1\nvalue: 2\n" if bad else "value: 1\n", newline="\n")
        for args in (
            ["ruff", "check", "--config", str(root / "pyproject.toml"), str(python)],
            ["yamllint", "--strict", "-c", str(root / ".yamllint"), str(document)],
        ):
            result = subprocess.run(
                [sys.executable, "-m", *args], capture_output=True, check=False, timeout=30
            )
            assert (result.returncode != 0) == bad
