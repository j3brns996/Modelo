"""Provider-neutral compilation of bounded guided MAC issue fields."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from modelo.mac import MAX_BODY_BYTES, MacError, payload_digest, with_computed_keys
from modelo.receipt import canonical_bytes, sha256_bytes


INTAKE_START = "<!-- modelo:intake-generated-start -->"
INTAKE_END = "<!-- modelo:intake-generated-end -->"
INTAKE_RESULT = "<!-- modelo:intake-result -->"

_HEADING = re.compile(r"(?m)^### ([^\n]{1,80})\n\n")
_FIELD_ORDER = (
    "request_type",
    "item_operation",
    "subject_kind",
    "subject_identity",
    "offering_identity",
    "source_identity",
    "destination_identity",
    "subject_identities",
    "purpose",
    "requested_outcome",
    "reason",
    "source_type",
    "source_url",
    "scope_ref",
    "partition",
    "region",
    "inference_service",
    "candidate_evidence",
    "acceptance",
    "final_checks",
)
_FIELD_LABELS = {
    "Batch change type": "item_operation",
    "Subject type": "subject_kind",
    "Subject identity": "subject_identity",
    "Offering identity": "offering_identity",
    "Current offering identity": "source_identity",
    "Replacement offering identity": "destination_identity",
    "Subject identities": "subject_identities",
    "Purpose": "purpose",
    "Requested outcome": "requested_outcome",
    "Why is this needed?": "reason",
    "Evidence source type": "source_type",
    "Evidence source URL": "source_url",
    "Opaque scope reference": "scope_ref",
    "Provider partition": "partition",
    "Source region": "region",
    "Inference service": "inference_service",
    "Supporting observations": "candidate_evidence",
    "Acceptance checks": "acceptance",
    "Before submitting": "final_checks",
}
_DISPLAY_LABELS = {field: label for label, field in _FIELD_LABELS.items()}
_DISPLAY_LABELS["request_type"] = "Request type"
_COMMON_FIELDS = {
    "request_type",
    "purpose",
    "requested_outcome",
    "reason",
    "candidate_evidence",
    "acceptance",
    "final_checks",
}
_OPERATION_FIELDS = {
    "add": {"subject_kind", "subject_identity"},
    "change": {"subject_kind", "subject_identity"},
    "revoke": {"offering_identity"},
    "move": {"source_identity", "destination_identity"},
    "batch": {
        "item_operation",
        "subject_kind",
        "subject_identities",
        "source_type",
        "source_url",
        "scope_ref",
        "partition",
        "region",
        "inference_service",
    },
}


@dataclass(frozen=True, slots=True)
class GuidedIntakeResult:
    valid: bool
    issue_body: str
    comment_body: str
    payload: dict[str, Any] | None


def _without_generated_intake(body: str) -> str:
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError(f"issue body exceeds {MAX_BODY_BYTES} bytes")
    start = body.find(INTAKE_START)
    end = body.find(INTAKE_END)
    if start < 0 and end < 0:
        return body.rstrip()
    if (
        start < 0
        or end < start
        or body.find(INTAKE_START, start + 1) >= 0
        or body.find(INTAKE_END, end + 1) >= 0
    ):
        raise ValueError("issue contains an ambiguous generated intake block")
    if body[end + len(INTAKE_END):].strip():
        raise ValueError("generated intake block must be the final issue section")
    return body[:start].rstrip()


def _issue_sections(body: str, request_labels: tuple[str, ...]) -> dict[str, str]:
    labels = dict(_FIELD_LABELS)
    labels.update((label, "request_type") for label in request_labels)
    matches = [match for match in _HEADING.finditer(body) if match.group(1) in labels]
    sections: dict[str, str] = {}
    previous_rank = -1
    ranks = {field: index for index, field in enumerate(_FIELD_ORDER)}
    for index, match in enumerate(matches):
        field = labels[match.group(1)]
        if field in sections:
            raise MacError("guided proposal contains a duplicate field heading")
        rank = ranks[field]
        if rank < previous_rank:
            raise MacError("guided proposal field headings are out of order")
        previous_rank = rank
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[field] = body[match.end():end].strip()
    return sections


def _answer(
    sections: dict[str, str], field: str, *, plain: bool = False,
    display_label: str | None = None,
) -> str:
    value = sections.get(field, "").strip()
    if not value or value == "_No response_":
        raise MacError(
            f"guided proposal is missing {display_label or _DISPLAY_LABELS[field]}"
        )
    return " ".join(value.split()) if plain else value


def _lines(
    sections: dict[str, str], field: str, *, required: bool = True,
) -> list[str]:
    value = sections.get(field, "").strip()
    if not value or value == "_No response_":
        if required:
            raise MacError(f"guided proposal is missing {_DISPLAY_LABELS[field]}")
        return []
    values = [" ".join(line.split()) for line in value.splitlines() if line.strip()]
    if required and not values:
        raise MacError(f"guided proposal is missing {_DISPLAY_LABELS[field]}")
    return values


def _candidate_evidence(sections: dict[str, str]) -> list[dict[str, str]]:
    records = []
    for line in _lines(sections, "candidate_evidence", required=False):
        parts = line.split(" | ")
        if len(parts) != 3:
            raise MacError(
                "each supporting observation must contain URL | UTC time | sha256- digest"
            )
        records.append({"uri": parts[0], "observed_at": parts[1], "digest": parts[2]})
    return records


def _compile_payload(
    sections: dict[str, str], issue_url: str, request_label: str,
) -> dict[str, Any]:
    operation = _answer(sections, "request_type", display_label=request_label)
    if operation not in _OPERATION_FIELDS:
        raise MacError("guided proposal has an unsupported request type")
    inapplicable = set(sections) - _COMMON_FIELDS - _OPERATION_FIELDS[operation]
    if inapplicable:
        field = min(inapplicable, key=_FIELD_ORDER.index)
        raise MacError(
            f"guided proposal field heading {_DISPLAY_LABELS[field]} is not valid for {operation}"
        )
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "request_id": str(uuid5(NAMESPACE_URL, issue_url)),
        "operation": operation,
        "purpose": _answer(sections, "purpose", plain=True),
        "requested_outcome": _answer(sections, "requested_outcome", plain=True),
        "reason": _answer(sections, "reason", plain=True),
        "candidate_evidence": _candidate_evidence(sections),
        "acceptance": _lines(sections, "acceptance"),
    }
    if operation in {"add", "change"}:
        payload["subjects"] = [{
            "kind": _answer(sections, "subject_kind"),
            "identity": _answer(sections, "subject_identity"),
        }]
    elif operation == "revoke":
        payload["subjects"] = [{
            "kind": "offering",
            "identity": _answer(sections, "offering_identity"),
        }]
    elif operation == "move":
        payload["subjects"] = [
            {
                "kind": "offering",
                "identity": _answer(sections, "source_identity"),
                "role": "source",
            },
            {
                "kind": "offering",
                "identity": _answer(sections, "destination_identity"),
                "role": "destination",
            },
        ]
    else:
        kind = _answer(sections, "subject_kind")
        payload["item_operation"] = _answer(sections, "item_operation")
        payload["subjects"] = [
            {"kind": kind, "identity": identity}
            for identity in _lines(sections, "subject_identities")
        ]
        payload["batch_scope"] = {
            "source": {
                "type": _answer(sections, "source_type"),
                "uri": _answer(sections, "source_url"),
            },
            "observation_scope": {
                "scope_ref": _answer(sections, "scope_ref"),
                "partition": _answer(sections, "partition"),
                "region": _answer(sections, "region"),
            },
            "inference_service_id": _answer(sections, "inference_service"),
        }
    return with_computed_keys(payload)


def _intake_issue_body(
    source: str, payload: dict[str, Any], provider_name: str,
) -> str:
    pretty = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
    body = (
        source + "\n\n" + INTAKE_START + "\n"
        + f"<!-- modelo:intake-source {sha256_bytes(source.encode('utf-8'))} -->\n"
        + f"### Change details (JSON)\n\n```json\n{pretty}\n```\n\n"
        + f"### Change fingerprint\n\n{payload_digest(payload)}\n"
        + INTAKE_END + "\n"
    )
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise MacError(f"generated proposal exceeds the {provider_name} issue body limit")
    return body


def _intake_comment(payload: dict[str, Any], change_request_name: str) -> str:
    identities = ", ".join(
        f"{item['kind']}:{item['identity']}" for item in payload["subjects"]
    )
    digest = sha256_bytes(canonical_bytes(payload))
    return (
        INTAKE_RESULT + "\n## Proposal ready\n\n"
        "Modelo validated the guided answers and generated the canonical request above. "
        "This is still a proposal, not approval.\n\n"
        f"### Copy into the {change_request_name}\n\n"
        f"- Neutral payload digest: `{digest}`\n"
        f"- Operation: `{payload['operation']}`\n"
        f"- Affected logical identities: {identities}\n\n"
        "Next: add the governed records and admissible evidence on a topic branch, then "
        f"open the MAC {change_request_name}.\n"
    )


def compile_guided_intake(
    *, body: str, issue_url: str, request_labels: tuple[str, ...],
    provider_name: str, change_request_name: str,
) -> GuidedIntakeResult:
    """Compile recognized form headings while leaving prose headings inside answers intact."""
    had_generated = INTAKE_START in body or INTAKE_END in body
    source = _without_generated_intake(body)
    try:
        sections = _issue_sections(source, request_labels)
    except MacError as exc:
        if not had_generated and not any(
            f"### {label}\n\n" in source for label in request_labels
        ):
            raise ValueError("issue is not a supported guided proposal") from exc
        sections = {}
        compile_error: MacError | None = exc
    else:
        compile_error = None
    if "request_type" not in sections and compile_error is None:
        if not had_generated:
            raise ValueError("issue is not a supported guided proposal")
        compile_error = MacError(f"guided proposal is missing {request_labels[0]}")
    try:
        if compile_error is not None:
            raise compile_error
        payload = _compile_payload(sections, issue_url, request_labels[0])
        issue_body = _intake_issue_body(source, payload, provider_name)
        comment_body = _intake_comment(payload, change_request_name)
    except (MacError, ValueError) as exc:
        message = str(exc).splitlines()[0]
        comment = (
            INTAKE_RESULT + "\n## Proposal needs attention\n\n"
            + message + ". Update the issue fields and Modelo will check them again.\n"
        )
        return GuidedIntakeResult(False, source + "\n", comment, None)
    return GuidedIntakeResult(True, issue_body, comment_body, payload)
