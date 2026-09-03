"""Evidence addressing, pointer equality and provenance coverage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from modelo.diagnostics import Diagnostic, Severity
from modelo.schemas import SchemaSet


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonical_json(value: Any) -> str:
    """Serialise Modelo's restricted JSON domain using RFC 8785 key ordering."""

    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(
            f"{_string(key)}:{canonical_json(value[key])}" for key in keys
        ) + "}"
    raise ValueError("value is outside Modelo's canonical JSON domain")


def evidence_id(document: Mapping[str, Any]) -> str:
    envelope = {key: value for key, value in document.items() if key != "id"}
    digest = hashlib.sha256(canonical_json(envelope).encode("utf-8")).hexdigest()
    return f"sha256-{digest}"


def resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    current = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or (token.startswith("0") and token != "0"):
                raise KeyError(pointer)
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise KeyError(pointer)
    return current


def escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


@dataclass(frozen=True, slots=True)
class ExternalFact:
    pointer: str
    value: Any
    freshness_class: str | None


def external_facts(
    instance: Any, schema: Mapping[str, Any], schemas: SchemaSet, pointer: str = ""
) -> tuple[ExternalFact, ...]:
    """Return concrete external leaves selected by schema annotations."""

    facts: list[ExternalFact] = []

    def walk(
        value: Any, node: Mapping[str, Any], base: Mapping[str, Any], at: str
    ) -> None:
        resolved, resolved_base = schemas.resolve(node, base)
        provenance = node.get("x-modelo-provenance", resolved.get("x-modelo-provenance"))
        freshness = node.get(
            "x-modelo-freshness-class", resolved.get("x-modelo-freshness-class")
        )
        if provenance == "external" and not isinstance(value, (dict, list)):
            facts.append(ExternalFact(at, value, freshness if isinstance(freshness, str) else None))
            return
        if isinstance(value, dict):
            properties = resolved.get("properties", {})
            if isinstance(properties, Mapping):
                for key in sorted(value):
                    child = properties.get(key)
                    if child is None:
                        child = resolved.get("additionalProperties")
                    if isinstance(child, Mapping):
                        walk(
                            value[key], child, resolved_base, f"{at}/{escape_pointer(key)}"
                        )
        elif isinstance(value, list):
            items = resolved.get("items")
            if isinstance(items, Mapping):
                for index, child in enumerate(value):
                    walk(child, items, resolved_base, f"{at}/{index}")

    walk(instance, schema, schema, pointer)
    return tuple(facts)


def _diagnostic(code: str, path: str, pointer: str, message: str, remediation: str) -> Diagnostic:
    return Diagnostic(code, Severity.ERROR, path, pointer, message, remediation)


def validate_evidence_links(
    *,
    path: str,
    document: Mapping[str, Any],
    schema: Mapping[str, Any],
    schemas: SchemaSet,
    evidence: Mapping[str, Mapping[str, Any]],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    refs = document.get("evidence_refs")
    if not isinstance(refs, dict):
        refs = {}
    for fact in external_facts(document, schema, schemas):
        reference = refs.get(fact.pointer)
        if not isinstance(reference, dict):
            diagnostics.append(_diagnostic(
                "EVIDENCE_MISSING", path, fact.pointer,
                "externally sourced fact has no exact evidence reference",
                "Add an evidence_refs entry for this fact pointer.",
            ))
            continue
        identifier = reference.get("id")
        record = evidence.get(identifier) if isinstance(identifier, str) else None
        if record is None:
            diagnostics.append(_diagnostic(
                "EVIDENCE_MISSING", path, fact.pointer,
                "referenced evidence record does not exist",
                "Add the content-addressed evidence record or correct the reference.",
            ))
            continue
        projection_pointer = reference.get("projection_pointer")
        try:
            projected = resolve_pointer(record.get("projection"), projection_pointer)
        except (KeyError, IndexError, TypeError):
            diagnostics.append(_diagnostic(
                "EVIDENCE_MISSING", path, fact.pointer,
                "evidence projection pointer does not resolve",
                "Use an explicit pointer into the referenced evidence projection.",
            ))
            continue
        if canonical_json(fact.value) != canonical_json(projected):
            diagnostics.append(_diagnostic(
                "EVIDENCE_VALUE_MISMATCH", path, fact.pointer,
                "fact value differs from its evidence projection",
                "Make the fact and projection canonically equal without transformation.",
            ))
    return tuple(diagnostics)


def validate_content_addresses(
    records: Iterable[tuple[str, Mapping[str, Any]]]
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for path, record in records:
        expected = evidence_id(record)
        actual = record.get("id")
        if actual != expected:
            diagnostics.append(_diagnostic(
                "EVIDENCE_ID_MISMATCH", path, "/id",
                "evidence id is not the SHA-256 of the canonical envelope without id",
                f"Set id and filename to {expected}.",
            ))
    return tuple(diagnostics)


def create_evidence_record(
    source_type: str,
    uri: str,
    observed_at: str,
    projection: Any,
    *,
    schemas: SchemaSet,
    operation: str | None = None,
    partition: str | None = None,
    region: str | None = None,
    retrieved_by: str = "cli",
    scope: dict[str, Any] | None = None,
    visibility: str = "internal",
) -> dict[str, Any]:
    """Construct and schema-validate a content-addressed evidence record."""

    if source_type == "first-party-read-api":
        source: dict[str, Any] = {
            "type": source_type,
            "provider": "aws",
            "service": "bedrock",
            "operation": operation or "",
            "partition": partition or "aws",
            "region": region or "",
            "sanitised_parameters": {},
            "documentation_uri": uri,
        }
    else:
        source = {
            "type": source_type,
            "uri": uri,
        }

    envelope: dict[str, Any] = {
        "source": source,
        "retrieved_by": retrieved_by,
        "observed_at": observed_at,
        "scope": scope if scope is not None else {},
        "projection": projection,
        "visibility": visibility,
    }
    calculated_id = evidence_id(envelope)
    record = {"id": calculated_id, **envelope}
    findings = schemas.validate("evidence.schema.json", record, "<constructed-evidence>")
    if findings:
        details = "; ".join(
            f"{finding.json_pointer or '/'}: {finding.message}" for finding in findings
        )
        raise ValueError(f"invalid evidence record: {details}")
    return record
