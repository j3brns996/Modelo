"""Pinned local/CI checks. UBS findings require review, not automatic suppression."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from modelo.loader import strict_unique_json_pairs

UBS_REVISION = "0af10c926d6fbb14a1f589326d75c03f610207f0"
UBS_REPOSITORY = "https://github.com/Dicklesworthstone/ultimate_bug_scanner.git"


def command(arguments: list[str], root: Path, *, timeout: int = 120) -> str:
    result = subprocess.run(
        arguments, cwd=root, capture_output=True, text=True, check=True, timeout=timeout
    )
    return result.stdout


def validate_scan(report: dict, expected: dict[str, int], returncode: int) -> None:
    """Reject failed, empty, incomplete or inconsistent scan summaries."""
    if (
        returncode not in (0, 1)
        or report.get("error")
        or report.get("failed_modules")
        or report.get("status") not in (None, "ok")
    ):
        raise ValueError("UBS scanner failed; this is not a completed findings report")
    scanners = report.get("scanners", [])
    if len(scanners) != len(expected):
        raise ValueError("UBS did not report every selected language")
    counts = {}
    totals = dict.fromkeys(("files", "critical", "warning", "info"), 0)
    for scanner in scanners:
        if (
            scanner.get("error")
            or scanner.get("module_error")
            or scanner.get("status") not in (None, "ok")
        ):
            raise ValueError("UBS reported a failed or partial language scanner")
        language = scanner.get("language")
        if language not in expected or language in counts:
            raise ValueError("UBS reported an unexpected or duplicate language")
        counts[language] = scanner.get("files")
        for key in totals:
            value = scanner.get(key)
            if type(value) is not int or value < 0:
                raise ValueError("UBS reported invalid counts")
            totals[key] += value
    if counts != expected or any(count <= 0 for count in counts.values()):
        raise ValueError("UBS scan inventory does not match the selected source files")
    if report.get("totals") != totals or any(
        type(value) is not int for value in report.get("totals", {}).values()
    ):
        raise ValueError("UBS totals do not match language summaries")
    if returncode == 1 and not (totals["critical"] or totals["warning"]):
        raise ValueError("UBS returned failure without reported findings")


def scanner_environment() -> dict[str, str]:
    """Do not inherit skip settings, shell startup files or unpinned analyzers."""
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(Path.home()),
        "LANG": "C.UTF-8",
        "ENABLE_UV_TOOLS": "0",
        "UBS_NO_AUTO_UPDATE": "1",
        "UBS_ALLOW_NO_SCAN": "0",
    }


def scan(root: Path) -> dict:
    output = root / "dist/quality"
    output.mkdir(parents=True, exist_ok=True)
    for name in ("ubs.json", "source.json"):
        (output / name).write_text('{"error":"not_completed"}\n', encoding="utf-8")
    (output / "ubs.log").write_text("Scan started; completion not established.\n", encoding="utf-8")
    if sys.platform != "linux":
        raise ValueError("Full quality checks require Linux or WSL, as does trusted CI")
    for name in ("bash", "git", "jq", "rg", "timeout", "ast-grep"):
        if shutil.which(name) is None:
            raise ValueError(f"Missing quality prerequisite: {name}")
    for name in ("ubs-python", "ubs-js"):
        if shutil.which(name):
            raise ValueError(f"Remove {name} from PATH; it overrides pinned UBS modules")
    if command(["ast-grep", "--version"], root).strip() != "ast-grep 0.40.1":
        raise ValueError("ast-grep must come from the locked environment (0.40.1)")
    cache = Path.home() / ".cache" / "modelo" / f"ubs-{UBS_REVISION}"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        command(
            [
                "git",
                "clone",
                "--quiet",
                "--depth",
                "1",
                "--branch",
                "v5.3.13",
                UBS_REPOSITORY,
                str(cache),
            ],
            root,
            timeout=300,
        )
    if command(["git", "rev-parse", "HEAD"], cache).strip() != UBS_REVISION:
        raise ValueError("UBS checkout does not match its pinned revision")
    if command(["git", "status", "--porcelain", "--untracked-files=all"], cache).strip():
        raise ValueError("UBS checkout has local modifications")
    for name in ("ubs-python.sh", "ubs-js.sh"):
        if not os.access(cache / "modules" / name, os.X_OK):
            raise ValueError(f"Pinned UBS module is unavailable: {name}")
    files = {
        "python": sorted((root / "tooling/modelo/src/modelo").rglob("*.py"))
        + sorted((root / "tooling/modelo/scripts").rglob("*.py")),
        "js": sorted((root / "site/assets").glob("*.js")),
    }
    with tempfile.TemporaryDirectory(prefix="modelo-quality-") as temporary:
        source = Path(temporary)
        scanned_bytes = {}
        for paths in files.values():
            for path in paths:
                target = source / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                data = path.read_bytes()
                target.write_bytes(data)
                scanned_bytes[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
        try:
            result = subprocess.run(
                [
                    "bash",
                    str(cache / "ubs"),
                    "--ci",
                    "--no-auto-update",
                    "--only=python,js",
                    "--format=json",
                    "--fail-on-warning",
                    str(source),
                ],
                cwd=root,
                env=scanner_environment(),
                text=True,
                capture_output=True,
                check=False,
                timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            diagnostics = exc.stderr or b""
            if isinstance(diagnostics, bytes):
                diagnostics = diagnostics.decode("utf-8", "replace")
            (output / "ubs.log").write_text("UBS timed out.\n" + diagnostics, encoding="utf-8")
            raise
        (output / "ubs.json").write_text(result.stdout, encoding="utf-8")
        (output / "ubs.log").write_text(result.stderr, encoding="utf-8")
        (output / "source.json").write_text(
            json.dumps(
                {
                    "ubs_revision": UBS_REVISION,
                    "source_commit": command(["git", "rev-parse", "HEAD"], root).strip()
                    if (root / ".git").exists()
                    else None,
                    "exit_code": result.returncode,
                    "file_sha256": scanned_bytes,
                    "files": {
                        key: [path.relative_to(root).as_posix() for path in paths]
                        for key, paths in files.items()
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        report = json.loads(result.stdout, object_pairs_hook=strict_unique_json_pairs)
        validate_scan(report, {key: len(value) for key, value in files.items()}, result.returncode)
    return report


def check(root: Path) -> None:
    root = root.resolve()
    for arguments in (
        [sys.executable, "-m", "ruff", "check", "--config", "pyproject.toml", "tooling", "tests"],
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "--config",
            "pyproject.toml",
            "tooling",
            "tests",
        ],
        [sys.executable, "-m", "yamllint", "--strict", "."],
    ):
        print(command(arguments, root), end="")
    report = scan(root)
    print(f"UBS completed: {report['totals']}. Review raw findings in dist/quality/ubs.json.")


if __name__ == "__main__":
    check(Path.cwd())
