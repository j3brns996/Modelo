"""Portable, non-accepting CI preflight and protected workflow gates."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Sequence

from modelo.change import GitError, _git, require_ancestor, resolve_commit
from modelo.freshness import parse_as_of
from modelo.validators import CheckSystemError, check_repository


class LocalCIError(ValueError):
    """A stable failure in advisory or workflow gate orchestration."""


class ChangeMode(StrEnum):
    MAC_DATA = "mac-data"
    CONTROL_PLANE = "control-plane"


def classify_change_mode(paths: Sequence[str]) -> ChangeMode:
    """Classify the change boundary only; reviewer eligibility is separate."""

    if not paths:
        raise LocalCIError("no changed paths")
    if any(
        not path or "\x00" in path or PurePosixPath(path).is_absolute()
        or any(part in {"", ".", ".."} for part in PurePosixPath(path).parts)
        for path in paths
    ):
        raise LocalCIError("changed path is unsafe")
    catalogue = any(path.startswith("catalogue/") for path in paths)
    control = any(not path.startswith("catalogue/") for path in paths)
    if catalogue and control:
        raise LocalCIError("catalogue and control-plane changes require separate pull requests")
    return ChangeMode.MAC_DATA if catalogue else ChangeMode.CONTROL_PLANE


def repository_change_mode(root: Path, base: str, head: str) -> ChangeMode:
    root = root.resolve()
    try:
        resolved_base = resolve_commit(root, base)
        resolved_head = resolve_commit(root, head)
        require_ancestor(root, resolved_base, resolved_head)
        raw = _git(
            root, "diff", "--name-only", "-z", resolved_base, resolved_head, "--",
            text=False,
        )
    except GitError as exc:
        raise LocalCIError(f"cannot classify Git change: {exc}") from exc
    try:
        paths = [item.decode("utf-8", "strict") for item in raw.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise LocalCIError("changed path is not valid UTF-8") from exc
    return classify_change_mode(paths)


def discover_test_files(root: Path) -> tuple[str, ...]:
    root = root.resolve()
    tests = root / "tests"
    if not tests.is_dir() or tests.is_symlink():
        raise LocalCIError("no Python tests found beneath a safe tests directory")
    files = []
    for path in tests.rglob("test_*.py"):
        if path.is_symlink() or not path.is_file():
            raise LocalCIError("Python test inventory contains an unsafe entry")
        files.append(path.relative_to(root).as_posix())
    if not files:
        raise LocalCIError("no Python tests found beneath a safe tests directory")
    return tuple(sorted(files))


def verification_shards(root: Path, jobs: int) -> tuple[tuple[str, ...], ...]:
    if isinstance(jobs, bool) or not isinstance(jobs, int) or not 1 <= jobs <= 3:
        raise LocalCIError("jobs must be between 1 and 3")
    files = discover_test_files(root)
    if jobs == 1:
        return (files,)
    heavy = [
        path for path in ("tests/site/test_site.py", "tests/unit/test_build.py")
        if path in files
    ]
    if jobs == 2 and heavy:
        groups = [(heavy[0],), tuple(path for path in files if path != heavy[0])]
    elif jobs == 3 and len(heavy) == 2:
        groups = [
            (heavy[0],), (heavy[1],), tuple(path for path in files if path not in heavy),
        ]
    else:
        groups = [tuple(files[index::jobs]) for index in range(jobs)]
    return tuple(group for group in groups if group)


def _run(arguments: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(arguments), cwd=cwd, text=True, capture_output=True,
            stdin=subprocess.DEVNULL, check=False,
        )
    except OSError as exc:
        raise LocalCIError(f"cannot execute verification command: {exc}") from exc
    return result


def _show(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def verify(root: Path, jobs: int) -> None:
    root = root.resolve()
    if not (root / "pyproject.toml").is_file() or not (root / "uv.lock").is_file():
        raise LocalCIError("verification root lacks pyproject.toml or uv.lock")
    sync = _run(("uv", "sync", "--project", str(root), "--locked"), cwd=root)
    _show(sync)
    if sync.returncode:
        raise LocalCIError("locked environment sync failed")
    shards = verification_shards(root, jobs)

    def test(shard: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        return _run(
            ("uv", "run", "--project", str(root), "--locked", "python", "-m", "pytest", "-q", *shard),
            cwd=root,
        )

    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        results = list(pool.map(test, shards))
    failed = False
    for index, result in enumerate(results, 1):
        print(f"local-ci: test shard {index}/{len(results)}")
        _show(result)
        failed = failed or result.returncode != 0
    if failed:
        raise LocalCIError("one or more test shards failed")
    package = _run(("uv", "build", "--offline", "--no-cache"), cwd=root)
    _show(package)
    if package.returncode:
        raise LocalCIError("offline package build failed")
    print("local-ci: fixed tests and offline package build passed")


def advisory_run(root: Path, base: str, head: str, as_of: str | None, jobs: int) -> None:
    mode = repository_change_mode(root, base, head)
    print(f"local-ci: advisory change mode is {mode.value}")
    if mode is ChangeMode.CONTROL_PLANE:
        verify(root, jobs)
    else:
        if as_of is None:
            raise LocalCIError("--as-of is required for a catalogue preflight")
        try:
            diagnostics = check_repository(root.resolve(), base, head, parse_as_of(as_of))
        except (GitError, CheckSystemError, ValueError) as exc:
            raise LocalCIError(f"catalogue preflight failed: {exc}") from exc
        if diagnostics:
            for diagnostic in diagnostics:
                print(f"{diagnostic.code} {diagnostic.path}{diagnostic.json_pointer}")
            raise LocalCIError("catalogue preflight found validation errors")
        print("local-ci: catalogue preflight passed")
    print("local-ci: advisory result only; remote modelo/check remains authoritative")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="modelo-local-ci")
    commands = parser.add_subparsers(dest="command", required=True)
    classify = commands.add_parser("classify", help="classify the code/data change boundary")
    verify_command = commands.add_parser("verify", help="run the fixed test and package gates")
    local = commands.add_parser("run", help="run a non-accepting local preflight")
    for command in (classify, local):
        command.add_argument("--root", type=Path, default=Path.cwd())
        command.add_argument("--base", required=True)
        command.add_argument("--head", required=True)
    verify_command.add_argument("--root", type=Path, default=Path.cwd())
    verify_command.add_argument("--jobs", type=int, choices=(1, 2, 3), default=1)
    local.add_argument("--as-of")
    local.add_argument("--jobs", type=int, choices=(1, 2, 3), default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "classify":
            print(repository_change_mode(arguments.root, arguments.base, arguments.head).value)
        elif arguments.command == "verify":
            verify(arguments.root, arguments.jobs)
        else:
            advisory_run(
                arguments.root, arguments.base, arguments.head,
                arguments.as_of, arguments.jobs,
            )
        return 0
    except LocalCIError as exc:
        print(f"modelo-local-ci: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
