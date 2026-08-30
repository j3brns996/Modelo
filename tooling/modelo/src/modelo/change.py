"""Local-Git snapshot and catalogue change rules."""

from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from typing import Callable, TypeVar

from modelo.diagnostics import Diagnostic, Severity


class GitError(Exception):
    pass


def _git(root: Path, *arguments: str, text: bool = True):
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=text,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise GitError(f"cannot execute local Git: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip() if text else result.stderr.decode("utf-8", "replace").strip()
        raise GitError(stderr or "local Git command failed")
    return result.stdout


def resolve_commit(root: Path, revision: str) -> str:
    if not revision or "\x00" in revision or revision.startswith("-"):
        raise GitError("Git revision is empty or option-like")
    return _git(root, "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}").strip()


def require_ancestor(root: Path, base: str, head: str) -> None:
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, head],
            cwd=root, check=False, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise GitError(f"cannot execute local Git: {exc}") from exc
    if result.returncode == 1:
        raise GitError("base commit is not an ancestor of head commit")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "cannot verify base/head ancestry")


T = TypeVar("T")


def with_snapshot(root: Path, commit: str, callback: Callable[[Path], T]) -> T:
    archive = _git(root, "archive", "--format=tar", commit, text=False)
    with TemporaryDirectory(prefix="modelo-snapshot-") as temporary:
        destination = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            members = bundle.getmembers()
            for member in members:
                pure = PurePosixPath(member.name)
                if (
                    pure.is_absolute()
                    or any(part in {"", ".", ".."} for part in pure.parts)
                    or member.issym()
                    or member.islnk()
                    or not (member.isfile() or member.isdir())
                ):
                    raise GitError(f"unsafe entry in Git snapshot: {member.name}")
            bundle.extractall(destination, members=members, filter="data")
        return callback(destination)


def changed_paths(
    root: Path, base: str, head: str, catalogue_root: str | tuple[str, ...] = "catalogue"
) -> tuple[tuple[str, str], ...]:
    roots = (catalogue_root,) if isinstance(catalogue_root, str) else catalogue_root
    pure_roots = tuple(PurePosixPath(item) for item in roots)
    if not pure_roots or any(
        item.is_absolute() or any(part in {"", ".", ".."} for part in item.parts)
        for item in pure_roots
    ):
        raise GitError("configured catalogue root is unsafe")
    output = _git(
        root, "diff", "--name-status", "--no-renames", base, head, "--",
        *(item.as_posix() for item in pure_roots),
    )
    changes: list[tuple[str, str]] = []
    for line in output.splitlines():
        status, separator, path = line.partition("\t")
        if not separator or status not in {"A", "M", "D"}:
            raise GitError("Git returned an unsupported catalogue delta")
        changes.append((status, path))
    return tuple(sorted(changes, key=lambda item: (item[1], item[0])))


def validate_changes(
    changes: tuple[tuple[str, str], ...],
    *,
    evidence_root: str,
    conditions_root: str,
    models_root: str,
    offerings_root: str,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for status, path in changes:
        if status in {"M", "D"} and path.startswith(f"{evidence_root}/"):
            diagnostics.append(Diagnostic(
                "EVIDENCE_IMMUTABLE", Severity.ERROR, path, "",
                "evidence merged in the base commit is immutable",
                "Add a new content-addressed evidence record and migrate references.",
            ))
        if status in {"M", "D"} and path.startswith(f"{conditions_root}/"):
            diagnostics.append(Diagnostic(
                "CHANGE_INVALID", Severity.ERROR, path, "",
                "a base condition version is immutable",
                "Add the next condition version and migrate offering references.",
            ))
        if status == "D" and path.startswith(f"{models_root}/"):
            diagnostics.append(Diagnostic(
                "CHANGE_INVALID", Severity.ERROR, path, "",
                "only offerings may be revoked or moved in v0.1",
                "Keep the canonical model and revoke affected offerings instead.",
            ))
        if status == "D" and not path.startswith(f"{offerings_root}/") and not (
            path.startswith(f"{evidence_root}/") or path.startswith(f"{conditions_root}/")
        ):
            diagnostics.append(Diagnostic(
                "CHANGE_INVALID", Severity.ERROR, path, "",
                "deletion is not an allowed v0.1 catalogue operation",
                "Use an allowed offering revoke or preserve the governed record.",
            ))
    return tuple(diagnostics)
