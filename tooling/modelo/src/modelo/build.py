"""Deterministic candidate builder and recoverable single-writer publisher."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib.parse import urlsplit

from modelo.change import GitError, changed_paths, require_ancestor, resolve_commit, with_snapshot
from modelo.config import load_config
from modelo.evidence import canonical_json
from modelo.loader import load_yaml_mapping
from modelo.mac import MacError, validate_payload
from modelo.receipt import (
    canonical_bytes,
    catalogue_projection,
    change_delta_bytes,
    manifest_entries,
    publication_digest,
    sha256_bytes,
    sort_change_delta,
)
from modelo.schemas import SchemaSet
from modelo.validators import CheckSystemError, _validate_state, check_repository


MAX_METADATA_BYTES = 262_144


class BuildError(Exception):
    """A fail-closed usage, input, Git, or publication error."""


@dataclass(frozen=True, slots=True)
class BuildRequest:
    root: Path
    kind: str
    base_commit: str
    source_commit: str
    source_tree: str
    as_of: date
    source_date_epoch: int
    mac_metadata: Path
    profile: str
    base_url: str | None
    base_path: str
    output: str


@dataclass(frozen=True, slots=True)
class BuildResult:
    catalogue_bytes: bytes
    change_delta_bytes: bytes
    manifest_bytes: bytes
    catalogue_digest: str
    change_delta_digest: str
    manifest_digest: str
    publication_digest: str
    output: Path


def _git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args], cwd=root, stdin=subprocess.DEVNULL,
        capture_output=True, text=not binary, check=False,
    )
    if result.returncode:
        error = result.stderr.decode("utf-8", "replace") if binary else result.stderr
        raise BuildError(error.strip() or "local Git command failed")
    return result.stdout


def _strict_json_file(path: Path) -> dict[str, Any]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise BuildError("platform cannot enforce non-symlink MAC metadata input")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BuildError(f"cannot open MAC metadata: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not hasattr(before, "st_mtime_ns") or not hasattr(before, "st_ctime_ns"):
            raise BuildError("platform cannot enforce nanosecond MAC metadata identity")
        if not stat.S_ISREG(before.st_mode):
            raise BuildError("MAC metadata must be a regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            part = os.read(descriptor, min(65_536, MAX_METADATA_BYTES + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
            if total > MAX_METADATA_BYTES:
                raise BuildError(f"MAC metadata exceeds {MAX_METADATA_BYTES} bytes")
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise BuildError("MAC metadata changed while it was read")
    finally:
        os.close(descriptor)

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise BuildError("MAC metadata contains a duplicate JSON key")
            result[key] = value
        return result

    def reject_number(value: str) -> Any:
        raise BuildError(f"MAC metadata contains forbidden non-integer number {value!r}")

    try:
        value = json.loads(
            b"".join(chunks).decode("utf-8", "strict"), object_pairs_hook=pairs,
            parse_float=reject_number, parse_constant=reject_number,
        )
    except BuildError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"MAC metadata is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError("MAC metadata root must be a JSON object")
    def domain(item: Any) -> None:
        if isinstance(item, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise BuildError("MAC metadata contains an unpaired Unicode surrogate")
        elif isinstance(item, bool) or item is None:
            return
        elif isinstance(item, int):
            if item < -(2**63) or item > 2**63 - 1:
                raise BuildError("MAC metadata integer is outside the signed 64-bit domain")
        elif isinstance(item, list):
            for child in item: domain(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                domain(key); domain(child)
        else:
            raise BuildError("MAC metadata value is outside the canonical JSON domain")
    domain(value)
    return value


def _blob(root: Path, commit: str, path: str) -> bytes:
    return _git(root, "show", f"{commit}:{path}", binary=True)  # type: ignore[return-value]


def _blob_digest(root: Path, commit: str, path: str) -> str:
    return sha256_bytes(_blob(root, commit, path))


def _computed_delta(
    root: Path, base: str, head: str, expected: list[dict[str, Any]], catalogue_root: str
) -> list[dict[str, Any]]:
    changes = changed_paths(root, base, head, catalogue_root)
    additions = [(status, path) for status, path in changes if status == "A"]
    deletions = [(status, path) for status, path in changes if status == "D"]
    offering_prefix = "catalogue/offerings/"
    if (
        len(additions) == 1 and len(deletions) == 1
        and additions[0][1].startswith(offering_prefix)
        and deletions[0][1].startswith(offering_prefix)
        and len(changes) == 2
    ):
        source_path = deletions[0][1]
        destination_path = additions[0][1]
        match = next((item for item in expected if item.get("operation") == "move"), None)
        if match is None:
            raise BuildError("offering add/delete pair requires an explicit move delta")
        source = dict(match["source"])
        destination = dict(match["destination"])
        source.update(operation="revoke", path=source_path, before=_blob_digest(root, base, source_path))
        destination.update(operation="add", path=destination_path, after=_blob_digest(root, head, destination_path))
        return [{"operation": "move", "source": source, "destination": destination}]
    result: list[dict[str, Any]] = []
    for status, path in changes:
        if status == "A":
            result.append({"operation": "add", "path": path, "after": _blob_digest(root, head, path)})
        elif status == "M":
            result.append({
                "operation": "change", "path": path,
                "before": _blob_digest(root, base, path), "after": _blob_digest(root, head, path),
            })
        else:
            match = next(
                (item for item in expected if item.get("operation") == "revoke" and item.get("path") == path),
                None,
            )
            if match is None:
                raise BuildError(f"deletion {path} lacks explicit revoke metadata")
            item = dict(match)
            item.update(operation="revoke", path=path, before=_blob_digest(root, base, path))
            result.append(item)
    return result


def _registry_maps(root: Path, commit: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for kind, path, key in (
        ("vendor", "catalogue/governance/vendors.yaml", "vendors"),
        ("inference-service", "catalogue/governance/inference-services.yaml", "inference_services"),
    ):
        try:
            raw = _blob(root, commit, path)
        except BuildError:
            result[kind] = {}
            continue
        with TemporaryDirectory(prefix="modelo-registry-") as raw_temporary:
            temporary = Path(raw_temporary)
            target = temporary / "registry.yaml"
            target.write_bytes(raw)
            result[kind] = dict(load_yaml_mapping(temporary, PurePosixPath("registry.yaml"))[key])
    return result


def _metadata_semantics(
    envelope: Mapping[str, Any], request: BuildRequest, computed: list[dict[str, Any]]
) -> None:
    repository = envelope["repository"]
    config_doc = load_yaml_mapping(request.root, PurePosixPath("modelo.yaml"))
    configured = config_doc["repository"]
    actual_repository = {key: configured[key] for key in ("adapter", "host", "namespace", "name")}
    expected_repository = {
        "adapter": repository["provider"], "host": repository["host"],
        "namespace": repository["namespace"], "name": repository["name"],
    }
    if actual_repository != expected_repository:
        raise BuildError("MAC metadata repository differs from modelo.yaml")
    issue = envelope["issue"]
    marker = "issues" if repository["provider"] == "github" else "-/issues"
    expected_url = (
        f"https://{repository['host']}/{repository['namespace']}/{repository['name']}/"
        f"{marker}/{issue['reference']}"
    )
    if issue["url"] != expected_url or issue["state"] != "open":
        raise BuildError("MAC issue is closed or belongs to another repository")
    correlations = (
        ("base commit", request.base_commit, envelope["base_sha"]),
        ("source commit", request.source_commit, envelope["head_sha"]),
        ("source tree", request.source_tree, envelope["head_tree_sha"]),
    )
    for label, explicit, recorded in correlations:
        if explicit != recorded:
            raise BuildError(f"{label} differs from MAC metadata")
    payload = envelope["payload"]
    try:
        normal_payload = validate_payload(payload)
    except MacError as exc:
        raise BuildError(f"invalid neutral MAC payload: {exc}") from exc
    if sha256_bytes(canonical_bytes(normal_payload)) != envelope["payload_digest"]:
        raise BuildError("MAC payload digest mismatch")
    expected_delta = sort_change_delta(envelope["expected_change_delta"])
    if sort_change_delta(computed) != expected_delta:
        raise BuildError("computed Git delta differs from expected MAC delta")

    subjects = normal_payload["subjects"]
    operation = normal_payload.get("item_operation", normal_payload["operation"])
    registry_paths = {
        "vendor": "catalogue/governance/vendors.yaml",
        "inference-service": "catalogue/governance/inference-services.yaml",
    }
    base_maps = _registry_maps(request.root, request.base_commit)
    head_maps = _registry_maps(request.root, request.source_commit)
    registry_subjects = [item for item in subjects if item["kind"] in registry_paths]
    registry_delta = [item for item in expected_delta if item.get("path") in registry_paths.values()]
    if registry_subjects or registry_delta:
        for kind, registry_path in registry_paths.items():
            claimed = {item["identity"] for item in registry_subjects if item["kind"] == kind}
            base_map, head_map = base_maps[kind], head_maps[kind]
            transitions: dict[str, str] = {}
            for key in set(base_map) | set(head_map):
                if key not in base_map:
                    transitions[key] = "add"
                elif key not in head_map:
                    transitions[key] = "delete"
                elif canonical_json(base_map[key]) != canonical_json(head_map[key]):
                    transitions[key] = "change"
            if claimed != set(transitions):
                raise BuildError("MAC registry subjects differ from changed registry keys")
            if "delete" in transitions.values() or any(value != operation for value in transitions.values()):
                raise BuildError("MAC registry transition differs from requested operation")
            matches = [item for item in registry_delta if item["path"] == registry_path]
            if bool(transitions) != (len(matches) == 1):
                raise BuildError("MAC registry file delta is unclaimed or duplicated")

    def matches(subject: Mapping[str, Any], path: str) -> bool:
        kind, identity = subject["kind"], subject["identity"]
        if kind == "model": expected_path = f"catalogue/models/{identity}.yaml"
        elif kind == "offering": return path.startswith("catalogue/offerings/") and path.endswith(f"/{identity}.yaml")
        elif kind == "evidence": expected_path = f"catalogue/evidence/{identity}.yaml"
        elif kind == "condition": return path.startswith("catalogue/policies/conditions/") and f"/{identity}/" in path
        else: return False
        return path == expected_path

    ordinary_subjects = [item for item in subjects if item["kind"] not in registry_paths]
    if normal_payload["operation"] == "move":
        if len(expected_delta) != 1 or expected_delta[0]["operation"] != "move":
            raise BuildError("move MAC requires exactly one move delta")
        source = next(item for item in ordinary_subjects if item.get("role") == "source")
        destination = next(item for item in ordinary_subjects if item.get("role") == "destination")
        delta = expected_delta[0]
        if not matches(source, delta["source"]["path"]) or not matches(destination, delta["destination"]["path"]):
            raise BuildError("move subjects differ from delta paths")
        if delta["source"].get("replacement") != delta["destination"]["path"]:
            raise BuildError("move replacement must equal its destination")
    else:
        ordinary_delta = [item for item in expected_delta if item not in registry_delta]
        unmatched = list(ordinary_delta)
        for subject in ordinary_subjects:
            match = next((item for item in unmatched if item["operation"] == operation and matches(subject, item["path"])), None)
            if match is None:
                raise BuildError("MAC subjects/operation differ from delta")
            unmatched.remove(match)
        if unmatched:
            raise BuildError("MAC delta contains an unclaimed subject")
        if operation == "revoke":
            head_offerings = {
                path for status, path in changed_paths(request.root, request.source_commit, request.source_commit)
            }
            # ls-tree, not a diff, is the authoritative set at head.
            output = _git(request.root, "ls-tree", "-r", "--name-only", request.source_commit, "--", "catalogue/offerings")
            head_offerings = set(str(output).splitlines())
            for delta in ordinary_delta:
                replacement = delta.get("replacement")
                if replacement is not None and (replacement == delta["path"] or replacement not in head_offerings):
                    raise BuildError("revoke replacement is not a distinct current head offering")


def _safe_url(base_url: str | None, base_path: str) -> None:
    path = PurePosixPath(base_path)
    if not base_path.startswith("/") or not base_path.endswith("/") or "//" in base_path or "%" in base_path or any(part in {".", ".."} for part in path.parts):
        raise BuildError("base path is not canonical")
    if base_url is None:
        return
    try:
        parsed = urlsplit(base_url)
        valid = (
            parsed.scheme == "https" and parsed.hostname is not None
            and parsed.hostname == parsed.hostname.lower() and parsed.port is None
            and parsed.username is None and parsed.password is None
            and not parsed.query and not parsed.fragment and parsed.path == base_path
            and "%" not in parsed.path and base_url.endswith("/")
        )
    except ValueError:
        valid = False
    if not valid:
        raise BuildError("base URL is not canonical HTTPS or differs from base path")


def _projection_from_snapshot(snapshot: Path, profile: str, source_commit: str, source_tree: str, as_of: date) -> dict[str, Any]:
    config_document = load_yaml_mapping(snapshot, PurePosixPath("modelo.yaml"))
    try:
        source = PurePosixPath(config_document["publication"]["profiles"][profile]["source"])
    except (KeyError, TypeError) as exc:
        raise BuildError(f"unknown publication profile {profile!r}") from exc
    catalogue = PurePosixPath(config_document["paths"]["catalogue"])
    if source != catalogue:
        source_path = snapshot.joinpath(*source.parts)
        target = snapshot.joinpath(*catalogue.parts)
        if source_path.is_symlink() or not source_path.is_dir():
            raise BuildError("publication profile source is missing or unsafe")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source_path, target)
    state = _validate_state(snapshot, as_of)
    if state.diagnostics:
        first = state.diagnostics[0]
        raise BuildError(f"selected publication projection is invalid: {first.code} {first.path}{first.json_pointer}")
    projection = catalogue_projection(
        contract_version="0.1.0", source_commit=source_commit, source_tree=source_tree,
        as_of=as_of.isoformat(), profile=profile, models=state.models.values(),
        offerings=state.offerings.values(), evidence=state.evidence.values(),
        conditions=state.conditions.values(), vendors={"vendors": state.vendors},
        inference_services={"inference_services": state.services},
        freshness={"classes_days": state.thresholds},
    )
    findings = state.schemas.validate("catalogue-output.schema.json", projection, "data/catalogue.json")
    if findings:
        raise BuildError(f"canonical projection violates its schema: {findings[0].message}")
    return projection


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _write_journal(descriptor: int, value: Mapping[str, Any]) -> None:
    raw = canonical_bytes(dict(value))
    if len(raw) > 8192:
        raise BuildError("build journal exceeds its bound")
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.ftruncate(descriptor, 0)
    os.write(descriptor, raw)
    os.fsync(descriptor)


def _verify_candidate(target: Path, expected: Mapping[str, bytes], manifest: Mapping[str, Any]) -> None:
    actual_paths = {
        path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()
    }
    required = {"site/data/catalogue.json", "site/data/change-delta.json", "site/data/manifest.json"}
    if actual_paths != required:
        raise BuildError("candidate output inventory is incomplete or contains extras")
    for relative, data in expected.items():
        path = target / "site" / relative
        if path.is_symlink() or path.read_bytes() != data:
            raise BuildError(f"candidate output verification failed for {relative}")
    manifest_bytes = (target / "site/data/manifest.json").read_bytes()
    if canonical_bytes(dict(manifest)) != manifest_bytes:
        raise BuildError("candidate manifest bytes changed during promotion")


def _candidate_self_valid(target: Path) -> bool:
    try:
        if target.is_symlink() or not target.is_dir():
            return False
        paths = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
        if paths != {"site/data/catalogue.json", "site/data/change-delta.json", "site/data/manifest.json"}:
            return False
        manifest_raw = (target / "site/data/manifest.json").read_bytes()
        manifest = json.loads(manifest_raw)
        if canonical_bytes(manifest) != manifest_raw:
            return False
        files = {
            "data/catalogue.json": (target / "site/data/catalogue.json").read_bytes(),
            "data/change-delta.json": (target / "site/data/change-delta.json").read_bytes(),
        }
        return (
            manifest["files"] == manifest_entries(files)
            and manifest["publication_digest"] == publication_digest(files)
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def recover_candidate(root: Path) -> None:
    """Perform the only safe rollback/cleanup described by a stale journal.

    Recovery never guesses which of two invalid candidates is correct.  It
    restores a verified backup when present; otherwise it removes only a
    disposable staging tree and retains a verified promoted target.
    """

    repository = root.resolve()
    parent = repository / "dist"
    lock = parent / ".modelo-build.lock"
    if not lock.exists():
        return
    journal = _strict_json_file(lock)
    if set(journal) != {"version", "phase", "target", "token"} or journal["version"] != 1:
        raise BuildError("build recovery journal has an unknown shape")
    token = journal["token"]
    if (
        journal["target"] != "candidate" or not isinstance(token, str)
        or len(token) != 32 or any(character not in "0123456789abcdef" for character in token)
    ):
        raise BuildError("build recovery journal contains unsafe paths")
    target = parent / "candidate"
    staging = parent / f"candidate.{token}.staging"
    backup = parent / f"candidate.{token}.backup"
    if backup.exists():
        if not _candidate_self_valid(backup):
            raise BuildError("build recovery backup is incomplete or corrupt")
        if target.exists():
            if not _candidate_self_valid(target):
                raise BuildError("build recovery target is ambiguous or corrupt")
            shutil.rmtree(target)
        os.replace(backup, target)
        if staging.exists():
            if staging.is_symlink() or not staging.is_dir():
                raise BuildError("build recovery staging path is unsafe")
            shutil.rmtree(staging)
    else:
        if target.exists() and not _candidate_self_valid(target):
            raise BuildError("build recovery target is incomplete or corrupt")
        if staging.exists():
            if staging.is_symlink() or not staging.is_dir():
                raise BuildError("build recovery staging path is unsafe")
            shutil.rmtree(staging)
        if not target.exists() and journal["phase"] not in {"lock", "stage", "fsync_stage", "validate_stage"}:
            raise BuildError("build recovery has no complete target or backup")
    lock.unlink()
    _fsync_dir(parent)


def _publish(root: Path, output: Path, files: Mapping[str, bytes], manifest: Mapping[str, Any]) -> None:
    parent = output.parent
    parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    lock = parent / ".modelo-build.lock"
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    except FileExistsError as exc:
        raise BuildError("another build is active or explicit recovery is required") from exc
    for _ in range(16):
        token = secrets.token_hex(16)
        staging = parent / f"{output.name}.{token}.staging"
        backup = parent / f"{output.name}.{token}.backup"
        try:
            staging.mkdir(mode=0o755)
            break
        except FileExistsError:
            continue
    else:
        os.close(lock_fd)
        lock.unlink(missing_ok=True)
        raise BuildError("cannot allocate collision-free staging directory")
    journal = {"version": 1, "phase": "lock", "target": output.name, "token": token}
    had_backup = False
    safe_to_release_lock = False
    try:
        _write_journal(lock_fd, journal)
        journal["phase"] = "stage"; _write_journal(lock_fd, journal)
        for relative, data in files.items():
            destination = staging / "site" / relative
            destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
        manifest_path = staging / "site/data/manifest.json"
        with manifest_path.open("xb") as stream:
            stream.write(canonical_bytes(dict(manifest))); stream.flush(); os.fsync(stream.fileno())
        for directory in sorted((path for path in staging.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
            _fsync_dir(directory)
        _fsync_dir(staging)
        journal["phase"] = "fsync_stage"; _write_journal(lock_fd, journal)
        _verify_candidate(staging, files, manifest)
        journal["phase"] = "validate_stage"; _write_journal(lock_fd, journal)
        if output.exists():
            if output.is_symlink() or not output.is_dir():
                raise BuildError("candidate target is not a regular directory")
            os.replace(output, backup); had_backup = True
        journal["phase"] = "backup_old"; _write_journal(lock_fd, journal)
        os.replace(staging, output)
        journal["phase"] = "promote_new"; _write_journal(lock_fd, journal)
        _fsync_dir(parent)
        journal["phase"] = "fsync_parent"; _write_journal(lock_fd, journal)
        _verify_candidate(output, files, manifest)
        journal["phase"] = "verify_target"; _write_journal(lock_fd, journal)
        if had_backup:
            shutil.rmtree(backup)
        _fsync_dir(parent)
        journal["phase"] = "remove_backup"; _write_journal(lock_fd, journal)
        safe_to_release_lock = True
    except Exception as original:
        try:
            if had_backup and backup.exists():
                if output.exists(): shutil.rmtree(output)
                os.replace(backup, output)
                _fsync_dir(parent)
            if staging.exists(): shutil.rmtree(staging)
            safe_to_release_lock = True
        except Exception as recovery_error:
            raise BuildError(
                f"publication failed and automatic restoration failed; explicit recovery required: {recovery_error}"
            ) from original
        raise
    finally:
        os.close(lock_fd)
        if safe_to_release_lock:
            try: lock.unlink()
            except FileNotFoundError: pass
            _fsync_dir(parent)


def build_candidate(request: BuildRequest) -> BuildResult:
    root = request.root.resolve()
    if request.kind != "candidate":
        raise BuildError("final builds remain unavailable until T6")
    config = load_config(root)
    if request.output != "dist/candidate":
        raise BuildError("candidate output must equal configured dist/candidate")
    output = root / request.output
    if output.is_symlink() or any((root / part).is_symlink() for part in ("dist", "dist/candidate")):
        raise BuildError("candidate output may not traverse a symlink")
    try:
        metadata_resolved = request.mac_metadata.resolve(strict=True)
    except OSError as exc:
        raise BuildError(f"cannot resolve MAC metadata path: {exc}") from exc
    if metadata_resolved == output or output in metadata_resolved.parents:
        raise BuildError("candidate output may not contain the MAC metadata input")
    _safe_url(request.base_url, request.base_path)
    if request.source_date_epoch < 0:
        raise BuildError("source date epoch must be non-negative")
    try:
        base = resolve_commit(root, request.base_commit)
        head = resolve_commit(root, request.source_commit)
        require_ancestor(root, base, head)
    except GitError as exc:
        raise BuildError(str(exc)) from exc
    if base != request.base_commit or head != request.source_commit:
        raise BuildError("base and source commit must be complete canonical SHAs")
    actual_tree = str(_git(root, "rev-parse", f"{head}^{{tree}}")).strip()
    if actual_tree != request.source_tree:
        raise BuildError("source tree does not match source commit")
    author_epoch = int(str(_git(root, "show", "-s", "--format=%at", head)).strip())
    if author_epoch != request.source_date_epoch:
        raise BuildError("source date epoch differs from source commit author time")
    if str(_git(root, "rev-parse", "HEAD")).strip() != head:
        raise BuildError("checked-out HEAD differs from explicit source commit")
    if str(_git(root, "status", "--porcelain=v1", "--untracked-files=all")).strip():
        raise BuildError("working tree is dirty")
    try:
        diagnostics = check_repository(root, base, head, request.as_of)
    except CheckSystemError as exc:
        raise BuildError(str(exc)) from exc
    if diagnostics:
        raise BuildError(f"repository validation failed: {diagnostics[0].code}")
    envelope = _strict_json_file(request.mac_metadata)
    schemas = SchemaSet(root, config.paths["schemas"])
    findings = schemas.validate("mac-metadata.schema.json", envelope, str(request.mac_metadata))
    if findings:
        raise BuildError(f"MAC metadata violates schema: {findings[0].message}")
    expected = list(envelope["expected_change_delta"])
    computed = _computed_delta(root, base, head, expected, config.paths["catalogue"].as_posix())
    _metadata_semantics(envelope, request, computed)
    projection = with_snapshot(
        root, head,
        lambda snapshot: _projection_from_snapshot(snapshot, request.profile, head, actual_tree, request.as_of),
    )
    catalogue_data = canonical_bytes(projection)
    delta_data = change_delta_bytes(expected)
    files = {"data/catalogue.json": catalogue_data, "data/change-delta.json": delta_data}
    manifest = {
        "contract_version": "0.1.0", "kind": "candidate", "base_commit": base, "source_commit": head,
        "source_tree": actual_tree, "as_of": request.as_of.isoformat(),
        "source_date_epoch": request.source_date_epoch, "profile": request.profile,
        "base_url": request.base_url, "base_path": request.base_path,
        "promotion_durability": "fsync-durable", "catalogue_path": "data/catalogue.json",
        "change_delta_path": "data/change-delta.json", "manifest_path": "data/manifest.json",
        "digest_algorithm": "sha256", "publication_digest": publication_digest(files),
        "files": manifest_entries(files),
    }
    findings = schemas.validate("build-manifest.schema.json", manifest, "data/manifest.json")
    if findings:
        raise BuildError(f"candidate manifest violates schema: {findings[0].message}")
    _publish(root, output, files, manifest)
    manifest_data = canonical_bytes(manifest)
    return BuildResult(
        catalogue_data, delta_data, manifest_data, sha256_bytes(catalogue_data),
        sha256_bytes(delta_data), sha256_bytes(manifest_data), manifest["publication_digest"], output,
    )
