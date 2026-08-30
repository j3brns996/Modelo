"""Deterministic candidate builder and recoverable single-writer publisher."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import ctypes
import errno
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit

from modelo.change import GitError, changed_paths, require_ancestor, resolve_commit, with_snapshot
from modelo.config import ConfigError, load_config
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


@dataclass(frozen=True, slots=True)
class BuildLayout:
    """The immutable publication/path view of one validated modelo.yaml."""

    catalogue: PurePosixPath
    models: PurePosixPath
    offerings: PurePosixPath
    evidence: PurePosixPath
    governance: PurePosixPath
    conditions: PurePosixPath
    schemas: PurePosixPath
    mac_metadata_schema: str
    catalogue_output_schema: str
    build_manifest_schema: str
    candidate_root: PurePosixPath
    target_parent: PurePosixPath
    publication_subdir: PurePosixPath
    catalogue_path: PurePosixPath
    change_delta_path: PurePosixPath
    manifest_path: PurePosixPath
    candidate_inventory: tuple[PurePosixPath, ...]
    candidate_manifest_files: tuple[PurePosixPath, ...]
    writer_lock: PurePosixPath
    profiles: Mapping[str, PurePosixPath]
    repository: Mapping[str, str]
    issue_route: str
    input_roots: tuple[PurePosixPath, ...]


def _safe_config_path(raw: Any, label: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or raw == "." or "\\" in raw:
        raise BuildError(f"configured {label} is not a safe repository-relative path")
    path = PurePosixPath(raw)
    if path.is_absolute() or path.as_posix() != raw or any(part in {"", ".", ".."} for part in path.parts):
        raise BuildError(f"configured {label} is not a safe repository-relative path")
    return path


def _layout(root: Path) -> BuildLayout:
    document = load_yaml_mapping(root, PurePosixPath("modelo.yaml"))
    try:
        paths = document["paths"]
        build = document["build"]
        repository = document["repository"]
        profiles_raw = document["publication"]["profiles"]
        path = lambda key: _safe_config_path(paths[key], f"paths.{key}")
        profiles = {
            name: _safe_config_path(value["source"], f"publication.profiles.{name}.source")
            for name, value in profiles_raw.items()
        }
        candidate_root = _safe_config_path(build["candidate_root"], "build.candidate_root")
        target_parent = _safe_config_path(build["target_parent"], "build.target_parent")
        publication_subdir = _safe_config_path(build["publication_subdir"], "build.publication_subdir")
        catalogue_path = _safe_config_path(build["catalogue_path"], "build.catalogue_path")
        delta_path = _safe_config_path(build["change_delta_path"], "build.change_delta_path")
        manifest_path = _safe_config_path(build["manifest_path"], "build.manifest_path")
        inventory = tuple(
            _safe_config_path(item, "build.candidate_output_inventory")
            for item in build["candidate_output_inventory"]
        )
        manifest_files = tuple(
            _safe_config_path(item, "build.candidate_manifest_files")
            for item in build["candidate_manifest_files"]
        )
        writer_lock = _safe_config_path(build["writer_lock"], "build.writer_lock")
        repository_values = {
            key: repository[key] for key in ("adapter", "host", "namespace", "name", "web_base")
        }
        issue_route = repository["web_routes"]["issue"]
        if not isinstance(issue_route, str) or issue_route.count("{issue_number}") != 1:
            raise BuildError("configured repository issue route must contain {issue_number} exactly once")
        schema_paths = {
            key: path(key) for key in (
                "mac_metadata_schema", "catalogue_output_schema", "build_manifest_schema"
            )
        }
    except (KeyError, TypeError, AttributeError) as exc:
        raise BuildError("modelo.yaml lacks the complete build layout") from exc
    expected_inventory = {
        publication_subdir / catalogue_path,
        publication_subdir / delta_path,
        publication_subdir / manifest_path,
    }
    if set(inventory) != expected_inventory or set(manifest_files) != {catalogue_path, delta_path}:
        raise BuildError("configured candidate inventory differs from the T5 contract")
    schemas_root = path("schemas")
    if any(value.parent != schemas_root for value in schema_paths.values()):
        raise BuildError("configured build schemas must be direct children of paths.schemas")
    if candidate_root.parent != target_parent or writer_lock.parent != target_parent:
        raise BuildError("configured candidate root and writer lock must share target_parent")
    input_keys = (
        "catalogue", "schemas", "fixtures", "site_source", "site_templates", "site_assets",
        "site_content", "implementation", "tests", "machine_contract", "human_specification",
    )
    inputs = tuple(dict.fromkeys([
        PurePosixPath("modelo.yaml"), *(path(key) for key in input_keys), *profiles.values()
    ]))
    for source in inputs:
        if candidate_root == source or candidate_root in source.parents or source in candidate_root.parents:
            raise BuildError("configured candidate output overlaps a configured input")
    return BuildLayout(
        catalogue=path("catalogue"), models=path("models"), offerings=path("offerings"),
        evidence=path("evidence"), governance=path("governance"), conditions=path("conditions"),
        schemas=schemas_root, mac_metadata_schema=schema_paths["mac_metadata_schema"].name,
        catalogue_output_schema=schema_paths["catalogue_output_schema"].name,
        build_manifest_schema=schema_paths["build_manifest_schema"].name, candidate_root=candidate_root,
        target_parent=target_parent, publication_subdir=publication_subdir,
        catalogue_path=catalogue_path, change_delta_path=delta_path, manifest_path=manifest_path,
        candidate_inventory=inventory, candidate_manifest_files=manifest_files,
        writer_lock=writer_lock, profiles=MappingProxyType(profiles),
        repository=MappingProxyType(repository_values), issue_route=issue_route, input_roots=inputs,
    )


def _git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args], cwd=root, stdin=subprocess.DEVNULL,
        capture_output=True, text=not binary, check=False,
    )
    if result.returncode:
        raise BuildError("local Git command failed")
    return result.stdout


def _strict_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    """Decode the bounded canonical-JSON domain without accepting JSON extensions."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise BuildError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    def reject_number(value: str) -> Any:
        raise BuildError(f"{label} contains forbidden non-integer number {value!r}")

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
            parse_float=reject_number, parse_constant=reject_number,
        )
    except BuildError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"{label} root must be a JSON object")

    def domain(item: Any) -> None:
        if isinstance(item, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise BuildError(f"{label} contains an unpaired Unicode surrogate")
        elif isinstance(item, bool) or item is None:
            return
        elif isinstance(item, int):
            if item < -(2**63) or item > 2**63 - 1:
                raise BuildError(f"{label} integer is outside the signed 64-bit domain")
        elif isinstance(item, list):
            for child in item:
                domain(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                domain(key)
                domain(child)
        else:
            raise BuildError(f"{label} value is outside the canonical JSON domain")
    domain(value)
    return value


def _read_regular_nofollow(path: Path, *, limit: int, label: str) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise BuildError(f"platform cannot enforce non-symlink {label}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BuildError(f"cannot open {label}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not hasattr(before, "st_mtime_ns") or not hasattr(before, "st_ctime_ns"):
            raise BuildError(f"platform cannot enforce nanosecond {label} identity")
        if not stat.S_ISREG(before.st_mode):
            raise BuildError(f"{label} must be a regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            part = os.read(descriptor, min(65_536, limit + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
            if total > limit:
                raise BuildError(f"{label} exceeds {limit} bytes")
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise BuildError(f"{label} changed while it was read")
    finally:
        os.close(descriptor)

    return b"".join(chunks)


def _strict_json_file(path: Path) -> dict[str, Any]:
    return _strict_json_bytes(
        _read_regular_nofollow(path, limit=MAX_METADATA_BYTES, label="MAC metadata"),
        "MAC metadata",
    )


def _blob(root: Path, commit: str, path: str) -> bytes:
    return _git(root, "show", f"{commit}:{path}", binary=True)  # type: ignore[return-value]


def _blob_digest(root: Path, commit: str, path: str) -> str:
    return sha256_bytes(_blob(root, commit, path))


def _computed_delta(
    root: Path, base: str, head: str, expected: list[dict[str, Any]], layout: BuildLayout
) -> list[dict[str, Any]]:
    changes = changed_paths(root, base, head, layout.catalogue.as_posix())
    additions = [(status, path) for status, path in changes if status == "A"]
    deletions = [(status, path) for status, path in changes if status == "D"]
    offering_prefix = layout.offerings.as_posix() + "/"
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


def _registry_maps(root: Path, commit: str, layout: BuildLayout) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for kind, path, key in (
        ("vendor", (layout.governance / "vendors.yaml").as_posix(), "vendors"),
        ("inference-service", (layout.governance / "inference-services.yaml").as_posix(), "inference_services"),
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
    envelope: Mapping[str, Any], request: BuildRequest, computed: list[dict[str, Any]], layout: BuildLayout
) -> None:
    repository = envelope["repository"]
    actual_repository = {
        "adapter": layout.repository["adapter"], "host": layout.repository["host"],
        "namespace": layout.repository["namespace"], "name": layout.repository["name"],
    }
    expected_repository = {
        "adapter": repository["provider"], "host": repository["host"],
        "namespace": repository["namespace"], "name": repository["name"],
    }
    if actual_repository != expected_repository:
        raise BuildError("MAC metadata repository differs from modelo.yaml")
    issue = envelope["issue"]
    expected_url = layout.repository["web_base"].rstrip("/") + layout.issue_route.replace(
        "{issue_number}", issue["reference"]
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
        "vendor": (layout.governance / "vendors.yaml").as_posix(),
        "inference-service": (layout.governance / "inference-services.yaml").as_posix(),
    }
    base_maps = _registry_maps(request.root, request.base_commit, layout)
    head_maps = _registry_maps(request.root, request.source_commit, layout)
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

    def loaded_record(path: str, record_operation: str) -> Mapping[str, Any]:
        commit = request.base_commit if record_operation == "revoke" else request.source_commit
        raw = _blob(request.root, commit, path)
        with TemporaryDirectory(prefix="modelo-subject-") as raw_temporary:
            temporary = Path(raw_temporary)
            (temporary / "record.yaml").write_bytes(raw)
            return dict(load_yaml_mapping(temporary, PurePosixPath("record.yaml")))

    def relative_parts(path: str, root: PurePosixPath) -> tuple[str, ...] | None:
        value = PurePosixPath(path)
        try:
            return value.relative_to(root).parts
        except ValueError:
            return None

    def matches(subject: Mapping[str, Any], path: str, record_operation: str) -> bool:
        kind, identity = subject["kind"], subject["identity"]
        if any(character in identity for character in "/\\"):
            return False
        try:
            record = loaded_record(path, record_operation)
        except (BuildError, OSError, KeyError, TypeError):
            return False
        if kind == "model":
            parts = relative_parts(path, layout.models)
            return parts == (f"{identity}.yaml",) and record.get("id") == identity
        if kind == "evidence":
            parts = relative_parts(path, layout.evidence)
            return parts == (f"{identity}.yaml",) and record.get("id") == identity
        if kind == "offering":
            parts = relative_parts(path, layout.offerings)
            return (
                parts is not None and len(parts) == 2 and parts[1] == f"{identity}.yaml"
                and record.get("id") == identity and record.get("inference_service_id") == parts[0]
            )
        if kind == "condition":
            parts = relative_parts(path, layout.conditions)
            if parts is None or len(parts) != 2 or parts[0] != identity or not parts[1].endswith(".yaml"):
                return False
            version = parts[1][:-5]
            return version.isdigit() and record.get("id") == identity and str(record.get("version")) == version
        return False

    ordinary_subjects = [item for item in subjects if item["kind"] not in registry_paths]
    if normal_payload["operation"] == "move":
        if len(expected_delta) != 1 or expected_delta[0]["operation"] != "move":
            raise BuildError("move MAC requires exactly one move delta")
        source = next(item for item in ordinary_subjects if item.get("role") == "source")
        destination = next(item for item in ordinary_subjects if item.get("role") == "destination")
        delta = expected_delta[0]
        if not matches(source, delta["source"]["path"], "revoke") or not matches(destination, delta["destination"]["path"], "add"):
            raise BuildError("move subjects differ from delta paths")
        if delta["source"].get("replacement") != delta["destination"]["path"]:
            raise BuildError("move replacement must equal its destination")
    else:
        ordinary_delta = [item for item in expected_delta if item not in registry_delta]
        unmatched = list(ordinary_delta)
        for subject in ordinary_subjects:
            match = next((
                item for item in unmatched
                if item["operation"] == operation and matches(subject, item["path"], operation)
            ), None)
            if match is None:
                raise BuildError("MAC subjects/operation differ from delta")
            unmatched.remove(match)
        if unmatched:
            raise BuildError("MAC delta contains an unclaimed subject")
        if operation == "revoke":
            # ls-tree, not a diff, is the authoritative set at head.
            output = _git(request.root, "ls-tree", "-r", "--name-only", request.source_commit, "--", layout.offerings.as_posix())
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


def _projection_from_snapshot(snapshot: Path, profile: str, source_commit: str, source_tree: str, as_of: date, layout: BuildLayout) -> dict[str, Any]:
    try:
        source = layout.profiles[profile]
    except KeyError as exc:
        raise BuildError(f"unknown publication profile {profile!r}") from exc
    catalogue = layout.catalogue
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
    findings = state.schemas.validate(layout.catalogue_output_schema, projection, layout.catalogue_path.as_posix())
    if findings:
        raise BuildError(f"canonical projection violates its schema: {findings[0].message}")
    return projection


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically rename only when destination is absent; never clobber a race."""
    if os.name == "nt":
        os.rename(source, destination)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise BuildError("platform cannot enforce collision-free atomic rename")
    result = renameat2(
        ctypes.c_int(-100), ctypes.c_char_p(os.fsencode(source)),
        ctypes.c_int(-100), ctypes.c_char_p(os.fsencode(destination)), ctypes.c_uint(1),
    )
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise BuildError("atomic publication rename destination already exists")
        raise OSError(code, "collision-free atomic rename failed")


PHASES = (
    "lock", "stage", "fsync_stage", "validate_stage", "backup_old",
    "promote_new", "fsync_parent", "verify_target", "remove_backup", "unlock",
)
class RecoveryOutcome(Enum):
    ROLLED_BACK = "rolled-back"
    COMMITTED = "committed"


def _inventory(files: Mapping[str, bytes]) -> dict[str, Any]:
    return {
        "files": {
            path: {"sha256": sha256_bytes(data), "size": len(data)}
            for path, data in sorted(files.items())
        },
        "tree_digest": publication_digest(files),
    }


def _inventory_digest(files: Mapping[str, Mapping[str, Any]]) -> str:
    records = bytearray()
    for path in sorted(files, key=lambda value: value.encode("utf-8")):
        records.extend(path.encode("utf-8")); records.extend(b"\0")
        records.extend(files[path]["sha256"].encode("ascii")); records.extend(b"\0")
        records.extend(str(files[path]["size"]).encode("ascii")); records.extend(b"\n")
    return sha256_bytes(bytes(records))


def _record(
    phase: str, target: str, token: str,
    old: Mapping[str, Any] | None, new: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "version": 2, "sequence": PHASES.index(phase), "phase": phase,
        "target": target, "token": token, "old": old, "new": new,
    }
    body["record_digest"] = sha256_bytes(canonical_bytes(body))
    return body


def _validate_record(value: Mapping[str, Any], layout: BuildLayout) -> dict[str, Any]:
    expected_keys = {"version", "sequence", "phase", "target", "token", "old", "new", "record_digest"}
    if (
        set(value) != expected_keys
        or type(value.get("version")) is not int
        or value.get("version") != 2
    ):
        raise BuildError("build recovery journal has an unknown shape")
    phase = value.get("phase")
    sequence = value.get("sequence")
    if (
        not isinstance(phase, str) or phase not in PHASES
        or type(sequence) is not int or sequence != PHASES.index(phase)
    ):
        raise BuildError("build recovery journal phase/sequence is invalid")
    token = value.get("token")
    if (
        value.get("target") != layout.candidate_root.name or not isinstance(token, str)
        or len(token) != 32 or any(character not in "0123456789abcdef" for character in token)
    ):
        raise BuildError("build recovery journal contains unsafe paths")
    body = {key: value[key] for key in value if key != "record_digest"}
    if value["record_digest"] != sha256_bytes(canonical_bytes(body)):
        raise BuildError("build recovery journal digest is invalid")
    if phase == "lock" and value["old"] is not None:
        raise BuildError("initial build recovery journal cannot contain an old inventory")
    expected_paths = {path.as_posix() for path in layout.candidate_inventory}
    for name in ("old", "new"):
        inventory = value[name]
        if inventory is None and name == "old":
            continue
        if not isinstance(inventory, dict) or set(inventory) != {"files", "tree_digest"}:
            raise BuildError("build recovery journal inventory is invalid")
        files = inventory["files"]
        if not isinstance(files, dict) or set(files) != expected_paths:
            raise BuildError("build recovery journal inventory paths are invalid")
        for item in files.values():
            if (
                not isinstance(item, dict) or set(item) != {"sha256", "size"}
                or not isinstance(item["size"], int) or isinstance(item["size"], bool) or item["size"] < 0
                or not isinstance(item["sha256"], str) or len(item["sha256"]) != 71
                or not item["sha256"].startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in item["sha256"][7:])
            ):
                raise BuildError("build recovery journal file inventory is invalid")
        if inventory["tree_digest"] != _inventory_digest(files):
            raise BuildError("build recovery journal tree digest is invalid")
    return dict(value)


def _write_all(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise OSError("short journal write")
        offset += written


def _persist_journal(parent: Path, lock: Path, value: Mapping[str, Any], *, initial: bool = False) -> None:
    raw = canonical_bytes(dict(value))
    if len(raw) > 32_768:
        raise BuildError("build journal exceeds its bound")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    path = lock if initial else parent / f".{lock.name}.{value['token']}.{value['sequence']}.tmp"
    descriptor = os.open(path, flags, 0o600)
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if not initial:
        os.replace(path, lock)
    _fsync_dir(parent)


def _reject_journal_temporaries(
    parent: Path, lock: Path, journal: Mapping[str, Any], lock_raw: bytes,
) -> None:
    """Fail closed for every token-shaped journal temporary.

    Portable filesystems do not provide unlink-if-inode semantics.  Recovery
    therefore never guesses ownership and never unlinks a temporary, even if
    it appears to be a hard link or byte-identical to the validated lock.
    """
    prefix = f".{lock.name}.{journal['token']}."
    expected_raw = canonical_bytes(dict(journal))
    if lock_raw != expected_raw:
        raise BuildError("build recovery journal is not canonical")
    for path in parent.iterdir():
        if path.name.startswith(prefix) and path.name.endswith(".tmp"):
            raise BuildError("ambiguous build recovery journal temporary")


def _walk_regular_tree(target: Path) -> dict[str, bytes]:
    if target.is_symlink() or not target.is_dir():
        raise BuildError("candidate tree root is not a regular directory")
    result: dict[str, bytes] = {}
    stack = [target]
    while stack:
        directory = stack.pop()
        if directory.is_symlink() or not directory.is_dir():
            raise BuildError("candidate tree contains a non-directory or symlink ancestor")
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink():
                    raise BuildError("candidate tree contains a symlink")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    relative = path.relative_to(target).as_posix()
                    result[relative] = _read_regular_nofollow(
                        path, limit=2**31 - 1, label=f"candidate file {relative}"
                    )
                else:
                    raise BuildError("candidate tree contains a special filesystem node")
    return result


def _candidate_inventory(root: Path, target: Path, layout: BuildLayout) -> dict[str, Any]:
    raw = _walk_regular_tree(target)
    expected = {path.as_posix() for path in layout.candidate_inventory}
    if set(raw) != expected:
        raise BuildError("candidate output inventory is incomplete or contains extras")
    manifest_relative = (layout.publication_subdir / layout.manifest_path).as_posix()
    catalogue_relative = (layout.publication_subdir / layout.catalogue_path).as_posix()
    delta_relative = (layout.publication_subdir / layout.change_delta_path).as_posix()
    manifest = _strict_json_bytes(raw[manifest_relative], "candidate manifest")
    if canonical_bytes(manifest) != raw[manifest_relative]:
        raise BuildError("candidate manifest is not canonical")
    schemas = SchemaSet(root, layout.schemas)
    findings = schemas.validate(layout.build_manifest_schema, manifest, layout.manifest_path.as_posix())
    if findings:
        raise BuildError("candidate manifest violates its configured schema")
    catalogue = _strict_json_bytes(raw[catalogue_relative], "candidate catalogue")
    if canonical_bytes(catalogue) != raw[catalogue_relative]:
        raise BuildError("candidate catalogue is not canonical")
    findings = schemas.validate(layout.catalogue_output_schema, catalogue, layout.catalogue_path.as_posix())
    if findings:
        raise BuildError("candidate catalogue violates its configured schema")
    try:
        delta = json.loads(raw[delta_relative].decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError("candidate change delta is not strict JSON") from exc
    if not isinstance(delta, list) or change_delta_bytes(delta) != raw[delta_relative]:
        raise BuildError("candidate change delta is not canonical")
    manifest_files = {
        layout.catalogue_path.as_posix(): raw[catalogue_relative],
        layout.change_delta_path.as_posix(): raw[delta_relative],
    }
    if (
        manifest.get("files") != manifest_entries(manifest_files)
        or manifest.get("publication_digest") != publication_digest(manifest_files)
        or manifest.get("catalogue_path") != layout.catalogue_path.as_posix()
        or manifest.get("change_delta_path") != layout.change_delta_path.as_posix()
        or manifest.get("manifest_path") != layout.manifest_path.as_posix()
    ):
        raise BuildError("candidate manifest correlations are invalid")
    return _inventory(raw)


def _matches_inventory(root: Path, target: Path, layout: BuildLayout, expected: Mapping[str, Any]) -> bool:
    try:
        return _candidate_inventory(root, target, layout) == expected
    except (BuildError, OSError, RecursionError):
        return False


def _verified_subset(target: Path, expected: Mapping[str, Any]) -> bool:
    """Accept only a no-link subset left by deletion of a recorded complete tree."""
    try:
        raw = _walk_regular_tree(target)
        files = expected["files"]
        for path, data in raw.items():
            if path not in files or files[path] != {"sha256": sha256_bytes(data), "size": len(data)}:
                return False
        return True
    except (BuildError, OSError, RecursionError):
        return False


def _remove_verified_tree(target: Path, expected: Mapping[str, Any]) -> None:
    if not target.exists():
        return
    if not _verified_subset(target, expected):
        raise BuildError("refusing to remove an unrecorded or unsafe candidate tree")
    raw_paths = sorted(_walk_regular_tree(target), key=lambda item: (item.count("/"), item), reverse=True)
    for relative in raw_paths:
        (target / PurePosixPath(relative)).unlink()
    directories = sorted(
        (path for path in target.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True
    )
    for directory in directories:
        directory.rmdir()
    target.rmdir()


def _owned_partial_staging(target: Path, expected: Mapping[str, Any]) -> bool:
    """Recognise only bounded files at journal-authorised paths during `stage`."""
    try:
        raw = _walk_regular_tree(target)
        files = expected["files"]
        return all(path in files and len(data) <= files[path]["size"] for path, data in raw.items())
    except (BuildError, OSError, RecursionError):
        return False


def _remove_owned_partial_staging(target: Path, expected: Mapping[str, Any]) -> None:
    if not _owned_partial_staging(target, expected):
        raise BuildError("partial staging tree contains unrecorded paths or unsafe nodes")
    for relative in sorted(_walk_regular_tree(target), reverse=True):
        (target / PurePosixPath(relative)).unlink()
    for directory in sorted(
        (path for path in target.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True
    ):
        directory.rmdir()
    target.rmdir()


def recover_candidate(root: Path) -> RecoveryOutcome | None:
    try:
        return _recover_candidate(root)
    except BuildError:
        raise
    except (ConfigError, OSError, UnicodeError, RecursionError, subprocess.SubprocessError) as exc:
        raise BuildError(f"build recovery system error ({type(exc).__name__})") from exc


def _recover_candidate(root: Path) -> RecoveryOutcome | None:
    """Complete the single digest-bound action authorised by a durable journal."""

    repository = root.resolve()
    load_config(repository)
    layout = _layout(repository)
    parent = repository.joinpath(*layout.target_parent.parts)
    lock = repository.joinpath(*layout.writer_lock.parts)
    current = repository
    for part in layout.target_parent.parts:
        current /= part
        if current.is_symlink():
            raise BuildError("build recovery target parent traverses a symlink")
    if not lock.exists() and not lock.is_symlink():
        return None
    lock_raw = _read_regular_nofollow(
        lock, limit=32_768, label="build recovery journal"
    )
    journal = _validate_record(
        _strict_json_bytes(lock_raw, "build recovery journal"), layout
    )
    token = journal["token"]
    _reject_journal_temporaries(parent, lock, journal, lock_raw)
    target = repository.joinpath(*layout.candidate_root.parts)
    staging = parent / f"{target.name}.{token}.staging"
    backup = parent / f"{target.name}.{token}.backup"
    old, new, phase = journal["old"], journal["new"], journal["phase"]
    present = lambda path: path.exists() or path.is_symlink()
    p_target, p_stage, p_backup = present(target), present(staging), present(backup)
    target_old = old is not None and p_target and _matches_inventory(repository, target, layout, old)
    target_new = p_target and _matches_inventory(repository, target, layout, new)
    backup_old = old is not None and p_backup and _matches_inventory(repository, backup, layout, old)
    backup_subset = old is not None and p_backup and _verified_subset(backup, old)
    staging_new = p_stage and _matches_inventory(repository, staging, layout, new)
    staging_subset = p_stage and _verified_subset(staging, new)
    staging_partial = p_stage and _owned_partial_staging(staging, new)

    def finish(outcome: RecoveryOutcome) -> RecoveryOutcome:
        lock.unlink()
        _fsync_dir(parent)
        return outcome

    # The initial lock is durable before old-state capture.  No publication
    # path has been touched, so recovery merely releases it if its namespace is
    # still empty.  A target cannot be interpreted before its old inventory was
    # captured, even when it happens to be a structurally valid candidate.
    if phase == "lock":
        if p_target or p_stage or p_backup:
            raise BuildError("initial-lock recovery found a mutated publication namespace")
        return finish(RecoveryOutcome.ROLLED_BACK)

    if phase in {"remove_backup", "unlock"}:
        if not target_new or p_stage:
            raise BuildError("committed build recovery lacks the recorded complete new target")
        if phase == "unlock" and p_backup:
            raise BuildError("unlock recovery state still contains a backup")
        if p_backup:
            if old is None or not backup_subset:
                raise BuildError("committed backup is unrecorded or unsafe")
            _remove_verified_tree(backup, old)
            _fsync_dir(parent)
        return finish(RecoveryOutcome.COMMITTED)

    base_target = target_old if old is not None else not p_target
    if phase == "stage":
        valid = base_target and not p_backup and (not p_stage or staging_partial)
    elif phase in {"fsync_stage", "validate_stage"}:
        valid = base_target and not p_backup and (not p_stage or staging_subset)
    elif phase == "backup_old":
        valid = (
            (base_target and not p_backup and (not p_stage or staging_subset))
            or (old is not None and not p_target and backup_old and staging_subset)
        )
    elif phase in {"promote_new", "fsync_parent", "verify_target"}:
        if old is None:
            valid = (
                (not p_target and not p_backup and (not p_stage or staging_subset))
                or (target_new and not p_stage and not p_backup)
            )
        else:
            valid = (
                (not p_target and backup_old and staging_subset)
                or (target_new and not p_stage and backup_old)
                or (target_old and not p_backup and (not p_stage or staging_subset))
            )
    else:
        valid = False
    if not valid:
        raise BuildError("build recovery state is ambiguous or differs from its journal")

    # A visible promoted target is moved atomically off-path before rollback;
    # readers therefore observe complete-new, absence, then complete-old.
    promoted_target = target_new and (old is None or backup_old)
    if promoted_target:
        if p_stage:
            raise BuildError("rollback staging path is already occupied")
        _rename_noreplace(target, staging)
        _fsync_dir(parent)
        p_target, p_stage, staging_subset = False, True, True
    if old is not None and not target_old:
        if not backup_old or p_target:
            raise BuildError("rollback cannot prove the recorded old backup")
        _rename_noreplace(backup, target)
        _fsync_dir(parent)
        target_old, p_target, p_backup = True, True, False
    if p_stage:
        if phase == "stage" and not staging_subset:
            _remove_owned_partial_staging(staging, new)
        else:
            _remove_verified_tree(staging, new)
        _fsync_dir(parent)
    return finish(RecoveryOutcome.ROLLED_BACK)


def _publish(root: Path, output: Path, files: Mapping[str, bytes], manifest: Mapping[str, Any], layout: BuildLayout) -> None:
    parent = output.parent
    parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    lock = root.joinpath(*layout.writer_lock.parts)
    manifest_bytes = canonical_bytes(dict(manifest))
    publication_files = {
        (layout.publication_subdir / PurePosixPath(path)).as_posix(): data for path, data in files.items()
    }
    publication_files[(layout.publication_subdir / layout.manifest_path).as_posix()] = manifest_bytes
    new_inventory = _inventory(publication_files)
    for _ in range(16):
        token = secrets.token_hex(16)
        staging = parent / f"{output.name}.{token}.staging"
        backup = parent / f"{output.name}.{token}.backup"
        journal = _record("lock", output.name, token, None, new_inventory)
        try:
            _persist_journal(parent, lock, journal, initial=True)
        except FileExistsError as exc:
            raise BuildError("another build is active or explicit recovery is required") from exc
        except Exception as original:
            if lock.exists() or lock.is_symlink():
                try:
                    recover_candidate(root)
                except Exception:
                    raise BuildError(
                        "initial lock persistence failed and explicit recovery is required"
                    ) from original
            raise
        if not (staging.exists() or staging.is_symlink() or backup.exists() or backup.is_symlink()):
            break
        lock.unlink()
        _fsync_dir(parent)
    else:
        raise BuildError("cannot allocate collision-free staging and backup paths")
    try:
        # Capture the visible target only after exclusive durable lock
        # acquisition.  A stale invocation can therefore never overwrite a
        # newer writer using an inventory sampled before its turn.
        old_inventory = None
        if output.exists() or output.is_symlink():
            old_inventory = _candidate_inventory(root, output, layout)
        journal = _record("stage", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        staging.mkdir(mode=0o755)
        for relative, data in files.items():
            destination = staging.joinpath(*layout.publication_subdir.parts, *PurePosixPath(relative).parts)
            destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
        manifest_path = staging.joinpath(*layout.publication_subdir.parts, *layout.manifest_path.parts)
        with manifest_path.open("xb") as stream:
            stream.write(manifest_bytes); stream.flush(); os.fsync(stream.fileno())
        journal = _record("fsync_stage", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        for directory in sorted((path for path in staging.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
            _fsync_dir(directory)
        _fsync_dir(staging)
        journal = _record("validate_stage", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        if _candidate_inventory(root, staging, layout) != new_inventory:
            raise BuildError("staged candidate differs from its journal")
        journal = _record("backup_old", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        if output.exists() or output.is_symlink():
            if output.is_symlink() or not output.is_dir():
                raise BuildError("candidate target is not a regular directory")
            if backup.exists() or backup.is_symlink():
                raise BuildError("backup path collision occurred before target rename")
            _rename_noreplace(output, backup)
        journal = _record("promote_new", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        _rename_noreplace(staging, output)
        journal = _record("fsync_parent", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        _fsync_dir(parent)
        journal = _record("verify_target", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        if _candidate_inventory(root, output, layout) != new_inventory:
            raise BuildError("promoted candidate differs from its journal")
        journal = _record("remove_backup", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        if backup.exists():
            _remove_verified_tree(backup, old_inventory)  # type: ignore[arg-type]
        _fsync_dir(parent)
        journal = _record("unlock", output.name, token, old_inventory, new_inventory)
        _persist_journal(parent, lock, journal)
        lock.unlink()
        _fsync_dir(parent)
    except Exception as original:
        try:
            outcome = recover_candidate(root)
        except Exception:
            raise BuildError(
                "publication failed and automatic recovery could not prove a safe state; explicit recovery required"
            ) from original
        if outcome is RecoveryOutcome.COMMITTED:
            return
        raise


def build_candidate(request: BuildRequest) -> BuildResult:
    """Build a candidate while normalising operational faults at the API boundary."""
    try:
        return _build_candidate(request)
    except (BuildError, ConfigError):
        raise
    except (
        OSError, UnicodeError, RecursionError, subprocess.SubprocessError, GitError,
        tarfile.TarError, ValueError,
    ) as exc:
        raise BuildError(f"build system error ({type(exc).__name__})") from exc


def _build_candidate(request: BuildRequest) -> BuildResult:
    root = request.root.resolve()
    if request.kind != "candidate":
        raise BuildError("final builds remain unavailable until T6")
    load_config(root)
    layout = _layout(root)
    if request.output != layout.candidate_root.as_posix():
        raise BuildError("candidate output must equal configured candidate_root")
    output = root.joinpath(*layout.candidate_root.parts)
    current = root
    for part in layout.candidate_root.parts:
        current /= part
        if current.is_symlink():
            raise BuildError("candidate output may not traverse a symlink")
    if output.is_symlink():
        raise BuildError("candidate output may not traverse a symlink")
    try:
        metadata_resolved = request.mac_metadata.resolve(strict=True)
    except OSError as exc:
        raise BuildError(f"cannot resolve MAC metadata path: {exc}") from exc
    if (
        metadata_resolved == output or output in metadata_resolved.parents
        or metadata_resolved in output.parents
    ):
        raise BuildError("candidate output may not overlap the MAC metadata input")
    if request.profile not in layout.profiles:
        raise BuildError(f"unknown publication profile {request.profile!r}")
    _safe_url(request.base_url, request.base_path)
    if request.source_date_epoch < 0:
        raise BuildError("source date epoch must be non-negative")
    try:
        base = resolve_commit(root, request.base_commit)
        head = resolve_commit(root, request.source_commit)
        require_ancestor(root, base, head)
    except GitError as exc:
        raise BuildError("local Git validation failed") from exc
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
    schemas = SchemaSet(root, layout.schemas)
    findings = schemas.validate(layout.mac_metadata_schema, envelope, str(request.mac_metadata))
    if findings:
        raise BuildError(f"MAC metadata violates schema: {findings[0].message}")
    expected = list(envelope["expected_change_delta"])
    computed = _computed_delta(root, base, head, expected, layout)
    _metadata_semantics(envelope, request, computed, layout)
    projection = with_snapshot(
        root, head,
        lambda snapshot: _projection_from_snapshot(snapshot, request.profile, head, actual_tree, request.as_of, layout),
    )
    catalogue_data = canonical_bytes(projection)
    delta_data = change_delta_bytes(expected)
    files = {layout.catalogue_path.as_posix(): catalogue_data, layout.change_delta_path.as_posix(): delta_data}
    manifest = {
        "contract_version": "0.1.0", "kind": "candidate", "base_commit": base, "source_commit": head,
        "source_tree": actual_tree, "as_of": request.as_of.isoformat(),
        "source_date_epoch": request.source_date_epoch, "profile": request.profile,
        "base_url": request.base_url, "base_path": request.base_path,
        "promotion_durability": "fsync-durable", "catalogue_path": layout.catalogue_path.as_posix(),
        "change_delta_path": layout.change_delta_path.as_posix(), "manifest_path": layout.manifest_path.as_posix(),
        "digest_algorithm": "sha256", "publication_digest": publication_digest(files),
        "files": manifest_entries(files),
    }
    findings = schemas.validate(layout.build_manifest_schema, manifest, layout.manifest_path.as_posix())
    if findings:
        raise BuildError(f"candidate manifest violates schema: {findings[0].message}")
    _publish(root, output, files, manifest, layout)
    manifest_data = canonical_bytes(manifest)
    return BuildResult(
        catalogue_data, delta_data, manifest_data, sha256_bytes(catalogue_data),
        sha256_bytes(delta_data), sha256_bytes(manifest_data), manifest["publication_digest"], output,
    )
