"""Calendar-day evidence freshness validation."""

from __future__ import annotations

from datetime import date, timezone
from typing import Iterable, Mapping

from modelo.diagnostics import Diagnostic, Severity
from modelo.evidence import ExternalFact
from modelo.schemas import parse_rfc3339


def parse_as_of(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("as-of must use YYYY-MM-DD")
    return parsed


def observed_utc_date(value: str) -> date:
    parsed = parse_rfc3339(value)
    return parsed.astimezone(timezone.utc).date()


def validate_freshness(
    *,
    path: str,
    facts: Iterable[ExternalFact],
    references: Mapping[str, object],
    evidence: Mapping[str, Mapping[str, object]],
    as_of: date,
    thresholds: Mapping[str, int],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for fact in facts:
        if fact.freshness_class is None:
            continue
        reference = references.get(fact.pointer)
        if not isinstance(reference, dict) or not isinstance(reference.get("id"), str):
            continue
        record = evidence.get(reference["id"])
        if record is None or not isinstance(record.get("observed_at"), str):
            continue
        try:
            observed = observed_utc_date(record["observed_at"])
        except ValueError:
            continue
        age = (as_of - observed).days
        if age < 0:
            diagnostics.append(Diagnostic(
                "EVIDENCE_FUTURE", Severity.ERROR, path, fact.pointer,
                "evidence observation is in the future relative to as-of",
                "Use evidence observed no later than the explicit as-of date.",
            ))
        elif age > thresholds[fact.freshness_class]:
            diagnostics.append(Diagnostic(
                "EVIDENCE_STALE", Severity.ERROR, path, fact.pointer,
                f"evidence is {age} calendar days old; maximum is {thresholds[fact.freshness_class]}",
                "Refresh the evidence and migrate the fact reference through MAC review.",
            ))
    return tuple(diagnostics)
