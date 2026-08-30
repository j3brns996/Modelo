"""Networkless, change-aware Modelo validation coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from modelo.change import GitError, changed_paths, require_ancestor, resolve_commit, validate_changes, validate_condition_history, with_snapshot
from modelo.config import ConfigError, ModeloConfig, load_config
from modelo.diagnostics import Diagnostic, Severity, sort_diagnostics
from modelo.discovery import DiscoveryError, discover_yaml_files
from modelo.evidence import (
    canonical_json,
    evidence_id,
    external_facts,
    resolve_pointer,
    validate_content_addresses,
    validate_evidence_links,
)
from modelo.freshness import validate_freshness
from modelo.loader import LoadError, load_yaml_mapping
from modelo.schemas import SchemaSet


class CheckSystemError(Exception):
    """Usage or system failure that prevents a validation result."""


@dataclass(slots=True)
class State:
    config: ModeloConfig
    schemas: SchemaSet
    diagnostics: list[Diagnostic]
    models: dict[str, Mapping[str, Any]]
    model_paths: dict[str, str]
    offerings: dict[str, Mapping[str, Any]]
    offering_paths: dict[str, str]
    evidence: dict[str, Mapping[str, Any]]
    evidence_paths: dict[str, str]
    conditions: dict[tuple[str, int], Mapping[str, Any]]
    vendors: dict[str, Mapping[str, Any]]
    services: dict[str, Mapping[str, Any]]
    thresholds: dict[str, int]


def _diag(code: str, path: str, pointer: str, message: str, remediation: str) -> Diagnostic:
    return Diagnostic(code, Severity.ERROR, path, pointer, message, remediation)


def _config_diagnostic(error: ConfigError) -> Diagnostic:
    return _diag(error.code, error.path, error.json_pointer, str(error), error.remediation)


def _load(state: State, path: PurePosixPath) -> Mapping[str, Any] | None:
    try:
        return load_yaml_mapping(state.config.root, path)
    except LoadError as exc:
        state.diagnostics.append(exc.diagnostic)
        return None


def _schema(state: State, name: str, document: Mapping[str, Any], path: str) -> bool:
    findings = state.schemas.validate(name, document, path)
    state.diagnostics.extend(findings)
    return not findings


def _discover(state: State, key: str) -> tuple[PurePosixPath, ...]:
    target = state.config.repository_path(key)
    if not target.exists():
        # Git has no empty-directory objects. An absent optional entity root is
        # therefore the canonical representation of an empty governed set.
        return ()
    try:
        return discover_yaml_files(state.config.root, state.config.paths[key])
    except DiscoveryError as exc:
        state.diagnostics.append(exc.diagnostic)
        return ()


def _relative_parts(path: PurePosixPath, root: PurePosixPath) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return ()


def _identity_mismatch(state: State, path: str, pointer: str, message: str) -> None:
    state.diagnostics.append(_diag(
        "PATH_IDENTITY_MISMATCH", path, pointer, message,
        "Make the governed path and internal identity exactly agree.",
    ))


def _load_state(root: Path) -> State:
    try:
        config = load_config(root)
        schemas = SchemaSet(config.root, config.paths["schemas"])
    except (ConfigError, ValueError, KeyError) as exc:
        if isinstance(exc, ConfigError):
            raise CheckSystemError(exc.render()) from exc
        raise CheckSystemError(str(exc)) from exc
    state = State(config, schemas, [], {}, {}, {}, {}, {}, {}, {}, {}, {}, {})
    config_document = _load(state, PurePosixPath("modelo.yaml"))
    if config_document is not None:
        _schema(state, "modelo.schema.json", config_document, "modelo.yaml")

    governance = config.paths["governance"]
    required = {
        governance / "vendors.yaml": "vendors-registry.schema.json",
        governance / "inference-services.yaml": "inference-services-registry.schema.json",
        governance / "freshness.yaml": "freshness-policy.schema.json",
    }
    for path, schema_name in required.items():
        document = _load(state, path)
        if document is None or not _schema(state, schema_name, document, path.as_posix()):
            continue
        if schema_name == "vendors-registry.schema.json":
            state.vendors = dict(document["vendors"])  # type: ignore[arg-type]
            for key, record in state.vendors.items():
                if record.get("id") != key:
                    _identity_mismatch(state, path.as_posix(), f"/vendors/{key}/id", "vendor id differs from its registry key")
        elif schema_name == "inference-services-registry.schema.json":
            state.services = dict(document["inference_services"])  # type: ignore[arg-type]
            for key, record in state.services.items():
                if record.get("id") != key:
                    _identity_mismatch(state, path.as_posix(), f"/inference_services/{key}/id", "inference-service id differs from its registry key")
        else:
            state.thresholds = dict(document["classes_days"])  # type: ignore[arg-type]

    for path in _discover(state, "models"):
        document = _load(state, path)
        if document is None or not _schema(state, "model.schema.json", document, path.as_posix()):
            continue
        parts = _relative_parts(path, config.paths["models"])
        identifier = document["id"]
        if len(parts) != 1 or parts[0] != f"{identifier}.yaml":
            _identity_mismatch(state, path.as_posix(), "/id", "model id differs from its configured filename")
        if identifier in state.models:
            _identity_mismatch(state, path.as_posix(), "/id", "model identity is duplicated")
        state.models[str(identifier)] = document
        state.model_paths[str(identifier)] = path.as_posix()

    for path in _discover(state, "offerings"):
        document = _load(state, path)
        if document is None or not _schema(state, "offering.schema.json", document, path.as_posix()):
            continue
        parts = _relative_parts(path, config.paths["offerings"])
        identifier = str(document["id"])
        service = str(document["inference_service_id"])
        if len(parts) != 2 or parts != (service, f"{identifier}.yaml"):
            _identity_mismatch(state, path.as_posix(), "/id", "offering identity or inference service differs from its path")
        if identifier in state.offerings:
            _identity_mismatch(state, path.as_posix(), "/id", "offering identity is duplicated")
        state.offerings[identifier] = document
        state.offering_paths[identifier] = path.as_posix()

    for path in _discover(state, "evidence"):
        document = _load(state, path)
        if document is None or not _schema(state, "evidence.schema.json", document, path.as_posix()):
            continue
        identifier = str(document["id"])
        parts = _relative_parts(path, config.paths["evidence"])
        if len(parts) != 1 or parts[0] != f"{identifier}.yaml":
            _identity_mismatch(state, path.as_posix(), "/id", "evidence id differs from its configured filename")
        state.evidence[identifier] = document
        state.evidence_paths[identifier] = path.as_posix()

    for path in _discover(state, "conditions"):
        document = _load(state, path)
        if document is None or not _schema(state, "condition.schema.json", document, path.as_posix()):
            continue
        identifier = str(document["id"])
        version = int(document["version"])
        parts = _relative_parts(path, config.paths["conditions"])
        if len(parts) != 2 or parts != (identifier, f"{version}.yaml"):
            _identity_mismatch(state, path.as_posix(), "/id", "condition id/version differs from its path")
        state.conditions[(identifier, version)] = document
    return state


def _reference_checks(state: State) -> None:
    for identifier, model in state.models.items():
        path = state.model_paths[identifier]
        if model["vendor_id"] not in state.vendors:
            state.diagnostics.append(_diag("UNKNOWN_REFERENCE", path, "/vendor_id", "model vendor does not exist", "Add or reference a governed vendor."))
    for identifier, offering in state.offerings.items():
        path = state.offering_paths[identifier]
        if offering["model_id"] not in state.models:
            state.diagnostics.append(_diag("UNKNOWN_REFERENCE", path, "/model_id", "offering model does not exist", "Reference an existing canonical model."))
        if offering["inference_service_id"] not in state.services:
            state.diagnostics.append(_diag("UNKNOWN_REFERENCE", path, "/inference_service_id", "offering inference service does not exist", "Reference a governed inference service."))
        service_record = state.services.get(offering["inference_service_id"])
        route_ids = {route["id"] for route in offering["routes"]}
        if len(route_ids) != len(offering["routes"]):
            state.diagnostics.append(_diag("PATH_IDENTITY_MISMATCH", path, "/routes", "route ids are not unique within the offering", "Give every route a stable unique internal id."))
        if service_record is not None:
            for index, route in enumerate(offering["routes"]):
                if route["adapter"] != service_record["adapter"]:
                    state.diagnostics.append(_diag(
                        "UNKNOWN_REFERENCE", path, f"/routes/{index}/adapter",
                        "route adapter differs from its inference-service adapter",
                        "Use the adapter governed by the referenced inference service.",
                    ))
        for index, price in enumerate(offering.get("pricing", [])):
            for route_id in price["route_ids"]:
                if route_id not in route_ids:
                    state.diagnostics.append(_diag("UNKNOWN_REFERENCE", path, f"/pricing/{index}/route_ids", "price references an unknown route", "Reference only a route in this offering."))
        for index, reference in enumerate(offering["condition_refs"]):
            key = (reference["id"], reference["version"])
            if key not in state.conditions:
                state.diagnostics.append(_diag("UNKNOWN_REFERENCE", path, f"/condition_refs/{index}", "condition version does not exist", "Reference an existing immutable condition version."))


def _model_evidence(
    state: State, path: str, binding: Mapping[str, Any], model: Mapping[str, Any] | None
) -> None:
    identifier = binding.get("id")
    record = state.evidence.get(identifier) if isinstance(identifier, str) else None
    if record is None:
        state.diagnostics.append(_diag("EVIDENCE_MISSING", path, "/routes", "AWS model binding evidence does not exist", "Reference an explicit evidence record."))
        return
    for field in ("id_pointer", "arn_pointer", "name_pointer", "provider_pointer"):
        pointer = binding.get(field)
        if pointer is None:
            continue
        try:
            resolve_pointer(record["projection"], pointer)
        except (KeyError, IndexError, TypeError):
            state.diagnostics.append(_diag("EVIDENCE_MISSING", path, "/routes", f"AWS {field} does not resolve", "Use an explicit pointer into the selected evidence projection."))
    if model is None:
        return
    vendor = state.vendors.get(model.get("vendor_id"))
    comparisons = (("name_pointer", model.get("name")), ("provider_pointer", vendor.get("name") if vendor else None))
    for field, expected in comparisons:
        try:
            actual = resolve_pointer(record["projection"], binding[field])
        except (KeyError, IndexError, TypeError):
            continue
        if expected is not None and canonical_json(actual) != canonical_json(expected):
            state.diagnostics.append(_diag("EVIDENCE_VALUE_MISMATCH", path, "/routes", f"AWS {field} differs from governed identity", "Use evidence whose reported model and provider names exactly match governed records."))


def _aws_checks(state: State) -> None:
    for identifier, offering in state.offerings.items():
        path = state.offering_paths[identifier]
        model = state.models.get(offering["model_id"])
        for index, route in enumerate(offering["routes"]):
            binding = route["model_binding"]
            if binding["kind"] == "foundation-model":
                evidence_binding = binding["model_evidence"]
                _model_evidence(state, path, evidence_binding, model)
                record = state.evidence.get(evidence_binding["id"])
                if record:
                    values = []
                    for field in ("id_pointer", "arn_pointer"):
                        try:
                            values.append(resolve_pointer(record["projection"], evidence_binding[field]))
                        except (KeyError, IndexError, TypeError):
                            pass
                    if route["reference"] not in values:
                        state.diagnostics.append(_diag("EVIDENCE_VALUE_MISMATCH", path, f"/routes/{index}/reference", "AWS foundation route reference matches neither evidenced model id nor ARN", "Use the exact evidenced foundation model id or AWS-owned ARN."))
            else:
                profile = binding["profile_evidence"]
                profile_record = state.evidence.get(profile["id"])
                if profile_record is None:
                    state.diagnostics.append(_diag("EVIDENCE_MISSING", path, f"/routes/{index}/model_binding/profile_evidence", "AWS profile evidence does not exist", "Reference explicit inference-profile evidence."))
                    continue
                try:
                    profile_value = resolve_pointer(profile_record["projection"], profile["projection_pointer"])
                    if canonical_json(profile_value) != canonical_json(route["reference"]):
                        state.diagnostics.append(_diag("EVIDENCE_VALUE_MISMATCH", path, f"/routes/{index}/reference", "AWS profile reference differs from its explicit evidence projection", "Use the exact evidenced system inference-profile id or ARN."))
                except (KeyError, IndexError, TypeError):
                    state.diagnostics.append(_diag("EVIDENCE_MISSING", path, f"/routes/{index}/model_binding/profile_evidence", "AWS profile projection pointer does not resolve", "Use an explicit profile projection pointer."))
                for destination in binding["destinations"]:
                    evidence_binding = destination["model_evidence"]
                    _model_evidence(state, path, evidence_binding, model)
                    model_record = state.evidence.get(evidence_binding["id"])
                    try:
                        destination_arn = resolve_pointer(profile_record["projection"], destination["destination_pointer"])
                        model_arn = resolve_pointer(model_record["projection"], evidence_binding["arn_pointer"])  # type: ignore[index]
                    except (KeyError, IndexError, TypeError):
                        continue
                    if canonical_json(destination_arn) != canonical_json(model_arn):
                        state.diagnostics.append(_diag("EVIDENCE_VALUE_MISMATCH", path, f"/routes/{index}/model_binding/destinations", "profile destination ARN differs from explicit model evidence", "Use matching explicit profile and foundation-model evidence."))


def _evidence_checks(state: State, as_of: date) -> None:
    state.diagnostics.extend(validate_content_addresses(
        (state.evidence_paths[key], record) for key, record in state.evidence.items()
    ))
    entities: list[tuple[str, Mapping[str, Any], str]] = []
    entities.extend((state.model_paths[key], record, "model.schema.json") for key, record in state.models.items())
    entities.extend((state.offering_paths[key], record, "offering.schema.json") for key, record in state.offerings.items())
    vendor_schema = state.schemas.schema("vendors-registry.schema.json")["properties"]["vendors"]["additionalProperties"]
    for key, record in state.vendors.items():
        entities.append((f"{state.config.paths['governance'].as_posix()}/vendors.yaml", record, "<vendor>"))
    for path, document, schema_name in entities:
        schema = vendor_schema if schema_name == "<vendor>" else state.schemas.schema(schema_name)
        state.diagnostics.extend(validate_evidence_links(path=path, document=document, schema=schema, schemas=state.schemas, evidence=state.evidence))
        facts = external_facts(document, schema, state.schemas)
        references = document.get("evidence_refs", {})
        if isinstance(references, Mapping) and state.thresholds:
            state.diagnostics.extend(validate_freshness(path=path, facts=facts, references=references, evidence=state.evidence, as_of=as_of, thresholds=state.thresholds))


def _validate_state(root: Path, as_of: date) -> State:
    state = _load_state(root)
    _reference_checks(state)
    _evidence_checks(state, as_of)
    _aws_checks(state)
    return state


def check_repository(root: Path, base: str, head: str, as_of: date) -> tuple[Diagnostic, ...]:
    try:
        base_commit = resolve_commit(root, base)
        head_commit = resolve_commit(root, head)
        require_ancestor(root, base_commit, head_commit)
        base_state = with_snapshot(root, base_commit, lambda snapshot: _validate_state(snapshot, as_of))
        head_state = with_snapshot(root, head_commit, lambda snapshot: _validate_state(snapshot, as_of))
        changes = changed_paths(
            root,
            base_commit,
            head_commit,
            tuple(sorted({
                base_state.config.paths["catalogue"].as_posix(),
                head_state.config.paths["catalogue"].as_posix(),
            })),
        )
    except (GitError, CheckSystemError) as exc:
        raise CheckSystemError(str(exc)) from exc
    diagnostics = list(head_state.diagnostics)
    diagnostics.extend(validate_changes(
        changes,
        evidence_root=head_state.config.paths["evidence"].as_posix(),
        conditions_root=head_state.config.paths["conditions"].as_posix(),
        models_root=head_state.config.paths["models"].as_posix(),
        offerings_root=head_state.config.paths["offerings"].as_posix(),
    ))
    try:
        diagnostics.extend(validate_condition_history(
            root,
            head_commit,
            head_state.config.paths["conditions"].as_posix(),
            head_state.config.paths["offerings"].as_posix(),
        ))
    except GitError as exc:
        raise CheckSystemError(str(exc)) from exc
    # A modified record may not silently change logical identity even if a path error
    # in the candidate would otherwise obscure the base comparison.
    for status, path in changes:
        if status != "M":
            continue
        if path in base_state.model_paths.values() and path in head_state.model_paths.values():
            old = next(key for key, value in base_state.model_paths.items() if value == path)
            new = next(key for key, value in head_state.model_paths.items() if value == path)
            if old != new:
                diagnostics.append(_diag("CHANGE_INVALID", path, "/id", "change operation altered model identity", "Use an explicit migration rather than changing identity in place."))
        if path in base_state.offering_paths.values() and path in head_state.offering_paths.values():
            old = next(key for key, value in base_state.offering_paths.items() if value == path)
            new = next(key for key, value in head_state.offering_paths.items() if value == path)
            if old != new:
                diagnostics.append(_diag("CHANGE_INVALID", path, "/id", "change operation altered offering identity", "Use atomic add-destination and revoke-source semantics."))
    return sort_diagnostics(diagnostics)
