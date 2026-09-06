"""Deterministic, non-accepting method-equivalence assessment validation."""

from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from modelo.schemas import SchemaSet

MAPPING_PATH = "docs/assurance/nist-ai-rmf-mapping.yaml"
DISCLAIMER = "Supports selected NIST AI RMF outcomes; not a certification; not a complete organisational AI-system inventory."


def reverse_mapping(document: Mapping[str, Any]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for item in document["mappings"]:
        for artefact in item["artefacts"]:
            reverse.setdefault(artefact, []).append(item["id"])
    return {key: sorted(set(reverse[key])) for key in sorted(reverse)}


def validate_mapping(root: Path, document: Mapping[str, Any], *, as_of: date) -> tuple[str, ...]:
    schemas = SchemaSet(root, PurePosixPath("schemas"))
    errors = [finding.message for finding in schemas.validate("nist-ai-rmf-mapping.schema.json", document, MAPPING_PATH)]
    if errors:
        return tuple(errors)
    ids = [item["id"] for item in document["mappings"]]
    if len(ids) != len(set(ids)):
        errors.append("mapping outcomes must be unique")
    for item in document["mappings"]:
        expected_source = "https://airc.nist.gov/airmf-resources/airmf/5-sec-core/" if item["id"] == "GOVERN-1.6" else "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf"
        if item["source"] != expected_source:
            errors.append("source does not own the selected NIST outcome")
        if item["current_level"] == "O":
            errors.append("this non-operating repository profile cannot assert operating equivalence; a separately governed operating assessment profile is required")
        if item["action"] != (None if item["id"] == "GOVERN-1.6" else item["id"]):
            errors.append("action and outcome identity differ")
        for relative in item["artefacts"]:
            path = PurePosixPath(relative)
            if path.is_absolute() or ".." in path.parts or not root.joinpath(*path.parts).is_file():
                errors.append(f"missing or unsafe authoritative artefact: {relative}")
        for assessment in item["operating_assessments"]:
            start, end = date.fromisoformat(assessment["period_start"]), date.fromisoformat(assessment["period_end"])
            if not start <= end <= as_of:
                errors.append("operating assessment must cover an actual elapsed period")
    # Shape and dates cannot prove truth. Independent assessment must inspect
    # the cited population, findings, operating evidence and remediation.
    return tuple(sorted(errors))
