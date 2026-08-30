"""Local-Git snapshot and catalogue change rules."""

from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from typing import Callable, TypeVar

from modelo.diagnostics import Diagnostic, Severity
from modelo.evidence import canonical_json
from modelo.loader import LoadError, load_yaml_mapping


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
    offering_additions = [
        path for status, path in changes
        if status == "A" and path.startswith(f"{offerings_root}/")
    ]
    offering_deletions = [
        path for status, path in changes
        if status == "D" and path.startswith(f"{offerings_root}/")
    ]
    if offering_additions and offering_deletions and (
        len(offering_additions) != 1 or len(offering_deletions) != 1
    ):
        diagnostics.append(Diagnostic(
            "CHANGE_INVALID", Severity.ERROR, offerings_root, "",
            "a mixed offering add/delete set is not one atomic move",
            "Use exactly one source deletion and one destination addition, or a homogeneous add or revoke batch.",
        ))
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


def _history_commits(root: Path, head: str) -> tuple[str, ...]:
    if _git(root, "for-each-ref", "--format=%(refname)", "refs/replace").strip():
        raise GitError("complete first-parent history is obscured by replacement refs")
    grafts_value = _git(root, "rev-parse", "--git-path", "info/grafts").strip()
    grafts = Path(grafts_value)
    if not grafts.is_absolute():
        grafts = root / grafts
    try:
        if grafts.is_file() and grafts.stat().st_size:
            raise GitError("complete first-parent history is obscured by grafts")
    except OSError as exc:
        raise GitError(f"cannot inspect Git graft state: {exc}") from exc
    shallow = _git(root, "rev-parse", "--is-shallow-repository").strip()
    if shallow != "false":
        raise GitError("complete first-parent history is unavailable in a shallow repository")
    commits = tuple(_git(root, "rev-list", "--first-parent", head).splitlines())
    if not commits or commits[0] != head:
        raise GitError("cannot resolve complete first-parent history")
    # Prove that traversal reached a root commit rather than stopping at a
    # missing object or graft boundary.
    parents = _git(root, "rev-list", "--parents", "-n", "1", commits[-1]).split()
    if len(parents) != 1:
        raise GitError("first-parent history did not reach a root commit")
    return commits


def _tree_blobs(root: Path, commit: str, governed_root: str) -> tuple[tuple[str, str], ...]:
    output = _git(root, "ls-tree", "-r", "-z", commit, "--", governed_root, text=False)
    records: list[tuple[str, str]] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        header, separator, raw_path = raw.partition(b"\t")
        fields = header.split()
        if not separator or len(fields) != 3 or fields[1] != b"blob":
            raise GitError("condition history contains a non-blob or malformed tree entry")
        try:
            path = raw_path.decode("utf-8")
            object_id = fields[2].decode("ascii")
        except UnicodeDecodeError as exc:
            raise GitError("condition history path or object id is not valid text") from exc
        records.append((path, object_id))
    return tuple(sorted(records))


def _load_historical_mapping(root: Path, object_id: str, display_path: str) -> dict[str, object]:
    raw = _git(root, "cat-file", "blob", object_id, text=False)
    with TemporaryDirectory(prefix="modelo-condition-") as temporary:
        temporary_root = Path(temporary)
        relative = PurePosixPath("condition.yaml")
        (temporary_root / relative.as_posix()).write_bytes(raw)
        try:
            return load_yaml_mapping(temporary_root, relative)
        except LoadError as exc:
            raise GitError(
                f"historical governed record {display_path} is not valid restricted YAML: "
                f"{exc.diagnostic.code}"
            ) from exc


def validate_condition_history(
    root: Path, base: str, head: str, conditions_root: str, offerings_root: str
) -> tuple[Diagnostic, ...]:
    """Reject changes after a condition becomes an accepted or referenced fact."""

    root_path = PurePosixPath(conditions_root)
    commits = tuple(reversed(_history_commits(root, head)))
    if base not in commits:
        raise GitError("accepted base is not in the complete first-parent history")
    locked: dict[tuple[str, int], tuple[str, str]] = {}
    changed: dict[tuple[str, int], str] = {}
    missing_references: set[tuple[str, str, int]] = set()
    # A condition is frozen by its accepted-base presence or its first reference.
    # Candidate-only drafts remain mutable until one of those events occurs.
    for commit in commits:
        current: dict[tuple[str, int], tuple[str, str]] = {}
        for path, object_id in _tree_blobs(root, commit, conditions_root):
            document = _load_historical_mapping(root, object_id, path)
            identifier = document.get("id")
            version = document.get("version")
            if not isinstance(identifier, str) or isinstance(version, bool) or not isinstance(version, int):
                raise GitError(f"historical condition has invalid identity: {path}")
            relative = PurePosixPath(path).relative_to(root_path)
            if relative.parts != (identifier, f"{version}.yaml"):
                raise GitError(f"historical condition path and identity differ: {path}")
            canonical = canonical_json(document)
            key = (identifier, version)
            current[key] = (canonical, path)
            previous = locked.get(key)
            if previous is not None and previous[0] != canonical:
                changed[key] = path
        for path, object_id in _tree_blobs(root, commit, offerings_root):
            offering = _load_historical_mapping(root, object_id, path)
            references = offering.get("condition_refs", [])
            if not isinstance(references, list):
                raise GitError(f"historical offering has invalid condition_refs: {path}")
            for reference in references:
                if not isinstance(reference, dict):
                    raise GitError(f"historical offering has invalid condition reference: {path}")
                identifier = reference.get("id")
                version = reference.get("version")
                if not isinstance(identifier, str) or isinstance(version, bool) or not isinstance(version, int):
                    raise GitError(f"historical offering has invalid condition identity: {path}")
                key = (identifier, version)
                if key not in current:
                    missing_references.add((path, identifier, version))
                elif key not in locked:
                    locked[key] = current[key]
        if commit == base:
            for key, value in current.items():
                locked.setdefault(key, value)
    diagnostics = [
        Diagnostic(
            "CHANGE_INVALID", Severity.ERROR, changed[key], "",
            f"condition {key[0]!r} version {key[1]} changed after first merge",
            "Restore the original canonical content and add a new condition version for changed meaning.",
        )
        for key in sorted(changed)
    ]
    diagnostics.extend(
        Diagnostic(
            "CHANGE_INVALID", Severity.ERROR, path, "/condition_refs",
            f"historical offering referenced missing condition {identifier!r} version {version}",
            "Restore a complete immutable condition history and migrate references through a validated change.",
        )
        for path, identifier, version in sorted(missing_references)
    )
    return tuple(diagnostics)
