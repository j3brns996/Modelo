"""Deterministic, confined discovery of governed Modelo YAML files."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from modelo.diagnostics import Diagnostic, Severity


class DiscoveryError(Exception):
    """A discovery failure represented by a stable diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def _error(message: str, remediation: str, *, path: str) -> DiscoveryError:
    return DiscoveryError(
        Diagnostic(
            code="FILE_OR_PATH_ERROR",
            severity=Severity.ERROR,
            path=path,
            json_pointer="",
            message=message,
            remediation=remediation,
        )
    )


def _safe_relative_root(value: str | PurePosixPath) -> PurePosixPath:
    raw = str(value)
    candidate = PurePosixPath(raw)
    if (
        not raw
        or raw == "."
        or "\\" in raw
        or any(ord(character) < 32 for character in raw)
        or candidate.is_absolute()
        or candidate.as_posix() != raw
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise _error(
            "discovery root is not a safe repository-relative POSIX path",
            "Use a configured relative directory without traversal or platform separators.",
            path=raw or "<empty>",
        )
    return candidate


def _confined_directory(repository_root: Path, relative: PurePosixPath) -> tuple[Path, Path]:
    try:
        root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise _error(
            f"cannot resolve repository root: {exc}",
            "Provide the checked-out repository root.",
            path=str(repository_root),
        ) from exc
    if not root.is_dir():
        raise _error(
            "repository root is not a directory",
            "Provide the checked-out repository root.",
            path=str(repository_root),
        )
    current = root
    target = root.joinpath(*relative.parts)
    try:
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise _error(
                    "symlinks are forbidden in discovery roots",
                    "Replace the symlink with a regular repository directory.",
                    path=relative.as_posix(),
                )
        resolved = target.resolve(strict=True)
    except DiscoveryError:
        raise
    except OSError as exc:
        raise _error(
            f"cannot resolve discovery root: {exc}",
            "Create the configured directory beneath the repository root.",
            path=relative.as_posix(),
        ) from exc
    if not resolved.is_relative_to(root) or not resolved.is_dir():
        raise _error(
            "discovery root is outside the repository or is not a directory",
            "Use a configured directory beneath the repository root.",
            path=relative.as_posix(),
        )
    return root, target


def discover_yaml_files(
    repository_root: Path, configured_root: str | PurePosixPath
) -> tuple[PurePosixPath, ...]:
    """Return repository-relative ``.yaml`` files in stable lexical order.

    The traversal never follows symlinks. Encountering a symlink or special
    filesystem entry beneath the governed root is an error rather than an
    omission.
    """

    relative_root = _safe_relative_root(configured_root)
    root, start = _confined_directory(repository_root, relative_root)
    discovered: list[PurePosixPath] = []
    pending = [start]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            relative = directory.relative_to(root).as_posix()
            raise _error(
                f"cannot read discovery directory: {exc}",
                "Make the governed directory readable.",
                path=relative,
            ) from exc
        for entry in entries:
            entry_path = Path(entry.path)
            relative = PurePosixPath(entry_path.relative_to(root).as_posix())
            try:
                if entry.is_symlink():
                    raise _error(
                        "symlinks are forbidden beneath governed discovery roots",
                        "Replace the symlink with a regular repository file or directory.",
                        path=relative.as_posix(),
                    )
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry_path)
                elif entry.is_file(follow_symlinks=False):
                    if entry.name.endswith(".yaml"):
                        discovered.append(relative)
                else:
                    raise _error(
                        "special filesystem entries are forbidden beneath governed roots",
                        "Keep only regular files and directories in governed source paths.",
                        path=relative.as_posix(),
                    )
            except DiscoveryError:
                raise
            except OSError as exc:
                raise _error(
                    f"cannot inspect discovered path: {exc}",
                    "Make the governed path readable and remove special entries.",
                    path=relative.as_posix(),
                ) from exc
    return tuple(sorted(discovered, key=PurePosixPath.as_posix))
