"""Stable, deterministic diagnostics shared by Modelo validation stages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from typing import Iterable


BASELINE_CODES = frozenset(
    {
        "YAML_PARSE_ERROR",
        "YAML_DUPLICATE_KEY",
        "YAML_ALIAS_OR_ANCHOR",
        "YAML_CUSTOM_TAG",
        "YAML_MULTI_DOCUMENT",
        "YAML_INVALID_ROOT",
        "YAML_LIMIT_EXCEEDED",
        "FILE_OR_PATH_ERROR",
        "SCHEMA_VIOLATION",
        "PATH_IDENTITY_MISMATCH",
        "UNKNOWN_REFERENCE",
        "EVIDENCE_MISSING",
        "EVIDENCE_VALUE_MISMATCH",
        "EVIDENCE_ID_MISMATCH",
        "EVIDENCE_IMMUTABLE",
        "EVIDENCE_STALE",
        "EVIDENCE_FUTURE",
        "CHANGE_INVALID",
        "MAC_INVALID",
        "BUILD_NONDETERMINISTIC",
        "RELEASE_RECEIPT_INVALID",
        "PLATFORM_CONTROL_MISSING",
    }
)


class Severity(StrEnum):
    """Severity values available in the v0.1 diagnostic contract."""

    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One immutable, machine-readable validation finding."""

    code: str
    severity: Severity
    path: str
    json_pointer: str
    message: str
    remediation: str

    def __post_init__(self) -> None:
        if self.code not in BASELINE_CODES:
            raise ValueError(f"diagnostic code is not in the v0.1 contract: {self.code!r}")
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be a Severity")
        for field_name in ("path", "json_pointer", "message", "remediation"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
        if not self.path:
            raise ValueError("diagnostic path must not be empty")
        if self.json_pointer and not self.json_pointer.startswith("/"):
            raise ValueError("json_pointer must be empty or start with '/'")
        if not self.message:
            raise ValueError("diagnostic message must not be empty")
        if not self.remediation:
            raise ValueError("diagnostic remediation must not be empty")

    def to_dict(self) -> dict[str, str]:
        """Return the exact six-field public representation."""

        return {
            "code": self.code,
            "severity": self.severity.value,
            "path": self.path,
            "json_pointer": self.json_pointer,
            "message": self.message,
            "remediation": self.remediation,
        }


def sort_diagnostics(diagnostics: Iterable[Diagnostic]) -> tuple[Diagnostic, ...]:
    """Return diagnostics in a stable order independent of traversal order."""

    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.path,
                item.json_pointer,
                item.code,
                item.severity.value,
                item.message,
                item.remediation,
            ),
        )
    )


def diagnostics_json(diagnostics: Iterable[Diagnostic]) -> str:
    """Serialise a deterministic diagnostic snapshot with a trailing newline."""

    payload = [item.to_dict() for item in sort_diagnostics(diagnostics)]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
