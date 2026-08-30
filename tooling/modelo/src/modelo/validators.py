"""Networkless, change-aware Modelo validation coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
import re
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
        route_ids = {route["id"] for route in offering["routes"]}
        if len(route_ids) != len(offering["routes"]):
            state.diagnostics.append(_diag("PATH_IDENTITY_MISMATCH", path, "/routes", "route ids are not unique within the offering", "Give every route a stable unique internal id."))
        for index, price in enumerate(offering.get("pricing", [])):
            for route_id in price["route_ids"]:
                if route_id not in route_ids:
                    state.diagnostics.append(_diag("UNKNOWN_REFERENCE", path, f"/pricing/{index}/route_ids", "price references an unknown route", "Reference only a route in this offering."))
        for index, reference in enumerate(offering["condition_refs"]):
            key = (reference["id"], reference["version"])
            if key not in state.conditions:
                state.diagnostics.append(_diag("UNKNOWN_REFERENCE", path, f"/condition_refs/{index}", "condition version does not exist", "Reference an existing immutable condition version."))


_AWS_ARN = re.compile(
    r"^arn:(aws|aws-cn|aws-us-gov):bedrock:([^:]+)::"
    r"(foundation-model|inference-profile)/"
    r"[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){1,3}"
    r"(?::[a-z0-9-]{1,63}){0,2}$"
)


def _aws_arn_scope(value: Any) -> tuple[str, str, str] | None:
    if not isinstance(value, str):
        return None
    match = _AWS_ARN.fullmatch(value)
    if match is None:
        return None
    return match.group(1), match.group(2), match.group(3)


def _aws_api_source(
    state: State,
    path: str,
    pointer: str,
    record: Mapping[str, Any],
    *,
    operations: tuple[str, ...],
    region: str,
) -> Mapping[str, Any] | None:
    operation_label = " or ".join(operations)
    source = record.get("source")
    if not isinstance(source, Mapping) or source.get("type") != "first-party-read-api":
        state.diagnostics.append(_diag(
            "EVIDENCE_VALUE_MISMATCH", path, pointer,
            "AWS route binding requires first-party read-API evidence",
            f"Use AWS Bedrock {operation_label} evidence observed in {region}.",
        ))
        return None
    expected = {
        "provider": "aws", "service": "bedrock", "region": region,
    }
    for field, value in expected.items():
        if source.get(field) != value:
            state.diagnostics.append(_diag(
                "EVIDENCE_VALUE_MISMATCH", path, pointer,
                f"AWS route evidence {field} does not match its invocation binding",
                f"Use {operation_label} evidence from AWS Bedrock in {region}.",
            ))
    if source.get("operation") not in operations:
        state.diagnostics.append(_diag(
            "EVIDENCE_VALUE_MISMATCH", path, pointer,
            "AWS route evidence operation does not match its binding kind",
            f"Use {operation_label} evidence from AWS Bedrock in {region}.",
        ))
    partition = source.get("partition")
    coherent = (
        (partition == "aws-cn" and region.startswith("cn-"))
        or (partition == "aws-us-gov" and region.startswith("us-gov-"))
        or (
            partition == "aws"
            and not region.startswith("cn-")
            and not region.startswith("us-gov-")
        )
    )
    if not coherent:
        state.diagnostics.append(_diag(
            "EVIDENCE_VALUE_MISMATCH", path, pointer,
            "AWS partition and Region are incoherent",
            "Use aws-cn with cn-*, aws-us-gov with us-gov-*, and aws for other Regions.",
        ))
    return source


def _aws_arn_matches_source(
    state: State,
    path: str,
    pointer: str,
    value: Any,
    source: Mapping[str, Any] | None,
    *,
    resource: str,
    required: bool = False,
) -> None:
    scope = _aws_arn_scope(value)
    if scope is None:
        if required:
            state.diagnostics.append(_diag(
                "EVIDENCE_VALUE_MISMATCH", path, pointer,
                "AWS evidence value is not a canonical supported ARN",
                f"Use a canonical AWS-owned Bedrock {resource} ARN.",
            ))
        return
    if source is None:
        return
    partition, region, kind = scope
    if kind != resource or partition != source.get("partition") or region != source.get("region"):
        state.diagnostics.append(_diag(
            "EVIDENCE_VALUE_MISMATCH", path, pointer,
            "AWS ARN partition, Region or resource type differs from its evidence source",
            "Use an ARN whose partition, Region and resource type match the bound API evidence.",
        ))


def _model_evidence(
    state: State, path: str, binding_pointer: str, binding: Mapping[str, Any],
    model: Mapping[str, Any] | None, *, expected_region: str | None = None,
) -> None:
    identifier = binding.get("id")
    record = state.evidence.get(identifier) if isinstance(identifier, str) else None
    if record is None:
        state.diagnostics.append(_diag("EVIDENCE_MISSING", path, binding_pointer, "AWS model binding evidence does not exist", "Reference an explicit evidence record."))
        return
    source = _aws_api_source(
        state, path, binding_pointer, record,
        operations=("GetFoundationModel", "ListFoundationModels"),
        region=expected_region or str(record.get("source", {}).get("region", "")),
    )
    for field in ("id_pointer", "arn_pointer", "name_pointer", "provider_pointer"):
        projection_pointer = binding.get(field)
        if projection_pointer is None:
            continue
        try:
            resolve_pointer(record["projection"], projection_pointer)
        except (KeyError, IndexError, TypeError):
            state.diagnostics.append(_diag("EVIDENCE_MISSING", path, binding_pointer, f"AWS {field} does not resolve", "Use an explicit pointer into the selected evidence projection."))
    try:
        model_arn = resolve_pointer(record["projection"], binding["arn_pointer"])
    except (KeyError, IndexError, TypeError):
        model_arn = None
    _aws_arn_matches_source(
        state, path, binding_pointer, model_arn, source, resource="foundation-model",
        required=True,
    )
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
            state.diagnostics.append(_diag("EVIDENCE_VALUE_MISMATCH", path, binding_pointer, f"AWS {field} differs from governed identity", "Use evidence whose reported model and provider names exactly match governed records."))


def _aws_offering_checks(
    state: State, offering: Mapping[str, Any], path: str
) -> None:
    model = state.models.get(offering["model_id"])
    semantic_routes: set[tuple[str, str, str]] = set()
    for index, route in enumerate(offering["routes"]):
        route_pointer = f"/routes/{index}"
        source_region = str(route["source_region"])
        binding = route["model_binding"]
        semantic_key = (source_region, str(binding["kind"]), str(route["reference"]))
        if semantic_key in semantic_routes:
            state.diagnostics.append(_diag(
                "PATH_IDENTITY_MISMATCH", path, route_pointer,
                "AWS route duplicates an existing invocation coordinate",
                "Keep one route per source Region, binding kind and provider reference.",
            ))
        semantic_routes.add(semantic_key)
        if binding["kind"] == "foundation-model":
            evidence_binding = binding["model_evidence"]
            _model_evidence(
                state, path, f"{route_pointer}/model_binding/model_evidence",
                evidence_binding, model, expected_region=source_region,
            )
            record = state.evidence.get(evidence_binding["id"])
            if record:
                source = _aws_api_source(
                    state, path, f"{route_pointer}/source_region", record,
                    operations=("GetFoundationModel", "ListFoundationModels"),
                    region=source_region,
                )
                _aws_arn_matches_source(
                    state, path, f"{route_pointer}/reference", route["reference"],
                    source, resource="foundation-model",
                )
                values = []
                matching_pointers: set[str] = set()
                for field in ("id_pointer", "arn_pointer"):
                    try:
                        value = resolve_pointer(record["projection"], evidence_binding[field])
                        values.append(value)
                        if canonical_json(value) == canonical_json(route["reference"]):
                            matching_pointers.add(str(evidence_binding[field]))
                    except (KeyError, IndexError, TypeError):
                        pass
                if route["reference"] not in values:
                    state.diagnostics.append(_diag("EVIDENCE_VALUE_MISMATCH", path, f"{route_pointer}/reference", "AWS foundation route reference matches neither evidenced model id nor ARN", "Use the exact evidenced foundation model id or AWS-owned ARN."))
                fact_reference = offering.get("evidence_refs", {}).get(
                    f"{route_pointer}/reference"
                )
                if (
                    not isinstance(fact_reference, Mapping)
                    or fact_reference.get("id") != evidence_binding["id"]
                    or fact_reference.get("projection_pointer") not in matching_pointers
                ):
                    state.diagnostics.append(_diag(
                        "EVIDENCE_VALUE_MISMATCH", path,
                        f"{route_pointer}/reference",
                        "AWS route fact reference is not its explicit model binding evidence",
                        "Use the bound model evidence ID and the exact matching ID or ARN pointer.",
                    ))
        else:
            profile = binding["profile_evidence"]
            profile_record = state.evidence.get(profile["id"])
            if profile_record is None:
                state.diagnostics.append(_diag("EVIDENCE_MISSING", path, f"{route_pointer}/model_binding/profile_evidence", "AWS profile evidence does not exist", "Reference explicit inference-profile evidence."))
                continue
            profile_source = _aws_api_source(
                state, path, f"{route_pointer}/source_region", profile_record,
                operations=("GetInferenceProfile", "ListInferenceProfiles"),
                region=source_region,
            )
            _aws_arn_matches_source(
                state, path, f"{route_pointer}/reference", route["reference"],
                profile_source, resource="inference-profile",
            )
            fact_reference = offering.get("evidence_refs", {}).get(
                f"{route_pointer}/reference"
            )
            if (
                not isinstance(fact_reference, Mapping)
                or fact_reference.get("id") != profile["id"]
                or fact_reference.get("projection_pointer")
                != profile["projection_pointer"]
            ):
                state.diagnostics.append(_diag(
                    "EVIDENCE_VALUE_MISMATCH", path,
                    f"{route_pointer}/reference",
                    "AWS route fact reference is not its explicit profile binding evidence",
                    "Use the bound profile evidence ID and exact profile reference pointer.",
                ))
            try:
                profile_value = resolve_pointer(profile_record["projection"], profile["projection_pointer"])
                if canonical_json(profile_value) != canonical_json(route["reference"]):
                    state.diagnostics.append(_diag("EVIDENCE_VALUE_MISMATCH", path, f"{route_pointer}/reference", "AWS profile reference differs from its explicit evidence projection", "Use the exact evidenced system inference-profile id or ARN."))
            except (KeyError, IndexError, TypeError):
                state.diagnostics.append(_diag("EVIDENCE_MISSING", path, f"{route_pointer}/model_binding/profile_evidence", "AWS profile projection pointer does not resolve", "Use an explicit profile projection pointer."))
            for field, expected in (("type_pointer", "SYSTEM_DEFINED"), ("status_pointer", "ACTIVE")):
                try:
                    actual = resolve_pointer(profile_record["projection"], profile[field])
                except (KeyError, IndexError, TypeError):
                    state.diagnostics.append(_diag(
                        "EVIDENCE_MISSING", path,
                        f"{route_pointer}/model_binding/profile_evidence/{field}",
                        f"AWS profile {field} does not resolve",
                        "Bind the explicit profile type and status projections.",
                    ))
                else:
                    if actual != expected:
                        state.diagnostics.append(_diag(
                            "EVIDENCE_VALUE_MISMATCH", path,
                            f"{route_pointer}/model_binding/profile_evidence/{field}",
                            f"AWS callable system profile must report {expected}",
                            f"Use a profile whose first-party evidence reports {expected}.",
                        ))
            try:
                projected_destinations = resolve_pointer(
                    profile_record["projection"], profile["destinations_pointer"]
                )
                if not isinstance(projected_destinations, list):
                    raise TypeError("profile destinations are not an array")
            except (KeyError, IndexError, TypeError):
                projected_destinations = None
                state.diagnostics.append(_diag(
                    "EVIDENCE_MISSING", path,
                    f"{route_pointer}/model_binding/profile_evidence/destinations_pointer",
                    "AWS profile destinations pointer does not resolve to an array",
                    "Bind the complete first-party profile destination array.",
                ))
            bound_destination_arns: list[Any] = []
            for destination_index, destination in enumerate(binding["destinations"]):
                evidence_binding = destination["model_evidence"]
                model_record = state.evidence.get(evidence_binding["id"])
                destination_pointer = (
                    f"{route_pointer}/model_binding/destinations/{destination_index}"
                )
                expected_region = None
                try:
                    destination_arn = resolve_pointer(
                        profile_record["projection"], destination["destination_pointer"]
                    )
                    destination_scope = _aws_arn_scope(destination_arn)
                    if destination_scope is not None:
                        expected_region = destination_scope[1]
                except (KeyError, IndexError, TypeError):
                    destination_arn = None
                else:
                    bound_destination_arns.append(destination_arn)
                _model_evidence(
                    state, path, destination_pointer, evidence_binding, model,
                    expected_region=expected_region,
                )
                if model_record is None:
                    continue
                destination_source = model_record.get("source")
                _aws_arn_matches_source(
                    state, path, destination_pointer, destination_arn,
                    destination_source if isinstance(destination_source, Mapping) else None,
                    resource="foundation-model", required=True,
                )
                try:
                    model_arn = resolve_pointer(model_record["projection"], evidence_binding["arn_pointer"])
                except (KeyError, IndexError, TypeError):
                    continue
                if canonical_json(destination_arn) != canonical_json(model_arn):
                    state.diagnostics.append(_diag("EVIDENCE_VALUE_MISMATCH", path, destination_pointer, "profile destination ARN differs from explicit model evidence", "Use matching explicit profile and foundation-model evidence."))
            if projected_destinations is not None:
                projected_arns = [
                    item.get("modelArn") if isinstance(item, Mapping) else None
                    for item in projected_destinations
                ]
                destinations_base = profile["destinations_pointer"]
                expected_pointers = {
                    f"{destinations_base}/{index}/modelArn"
                    for index in range(len(projected_destinations))
                }
                actual_pointers = [
                    destination["destination_pointer"]
                    for destination in binding["destinations"]
                ]
                if (
                    any(value is None for value in projected_arns)
                    or len(actual_pointers) != len(set(actual_pointers))
                    or set(actual_pointers) != expected_pointers
                    or sorted(map(canonical_json, projected_arns))
                    != sorted(map(canonical_json, bound_destination_arns))
                ):
                    state.diagnostics.append(_diag(
                        "EVIDENCE_VALUE_MISMATCH", path,
                        f"{route_pointer}/model_binding/destinations",
                        "AWS profile destination bindings are not a complete one-to-one projection",
                        "Bind every and only destination model ARN reported by the selected profile evidence.",
                    ))


def _aws_checks(state: State) -> None:
    for identifier, offering in state.offerings.items():
        path = state.offering_paths[identifier]
        service = state.services.get(offering["inference_service_id"])
        if service is None:
            # The unknown-service finding is authoritative. Do not guess a
            # provider adapter and cascade provider-specific diagnostics.
            continue
        adapter = service.get("adapter")
        if adapter == "aws-bedrock":
            _aws_offering_checks(state, offering, path)
        else:
            state.diagnostics.append(_diag(
                "UNKNOWN_REFERENCE", path, "/inference_service_id",
                "inference-service adapter has no implemented validator",
                "Use a service whose governed adapter is implemented.",
            ))


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
            base_commit,
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
