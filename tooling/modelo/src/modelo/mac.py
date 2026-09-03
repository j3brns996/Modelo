"""Platform-neutral move/add/change (MAC) payload handling.

The Git-provider adapters may transport these objects, but they do not own
their meaning.  This module is deliberately networkless and parses only the
bounded canonical-JSON block emitted by :func:`render_issue_body`.  JSON is a
YAML-compatible subset and avoids introducing a second YAML trust boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from jsonschema import FormatChecker


Adapter = Literal["github", "gitlab"]
MAX_BODY_BYTES = 65_536
MAX_ADAPTER_OVERHEAD_BYTES = 4_096
MAX_RENDERED_PAYLOAD_BYTES = MAX_BODY_BYTES - MAX_ADAPTER_OVERHEAD_BYTES
MAX_DEPTH = 12
MAX_NODES = 500
PAYLOAD_START = "<!-- modelo:mac-payload:start -->"
PAYLOAD_END = "<!-- modelo:mac-payload:end -->"
INTAKE_START = "<!-- modelo:intake-generated-start -->"
INTAKE_END = "<!-- modelo:intake-generated-end -->"
_HASH_PATTERN = re.compile(r"^sha256-[0-9a-f]{64}$")
_IDENTITY_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._:/@+-]*[a-z0-9])?$")
_HOST_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HTTPS_PATTERN = re.compile(
    rf"^https://(?:{_HOST_LABEL}\.)*{_HOST_LABEL}(?:[/?#][\u0021-\u007e]*)?$"
)
_FORMAT_CHECKER = FormatChecker()
_KINDS = {"model", "offering", "evidence", "vendor", "inference-service", "condition"}
_OPERATIONS = {"add", "change", "revoke", "move", "batch"}
_ITEM_OPERATIONS = {"add", "change", "revoke"}
_TOP_LEVEL_FIELDS = {
    "schema_version",
    "request_id",
    "operation",
    "item_operation",
    "purpose",
    "subjects",
    "batch_scope",
    "requested_outcome",
    "reason",
    "candidate_evidence",
    "acceptance",
    "dedupe_key",
    "idempotency_key",
}


class MacError(ValueError):
    """A deterministic neutral-MAC contract failure."""

    code = "MAC_INVALID"


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MacError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _measure(value: Any) -> tuple[int, int]:
    maximum_depth = 0
    nodes = 0
    pending = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        nodes += 1
        maximum_depth = max(maximum_depth, depth)
        if nodes > MAX_NODES or maximum_depth > MAX_DEPTH:
            return maximum_depth, nodes
        if isinstance(item, Mapping):
            pending.extend((child, depth + 1) for pair in item.items() for child in pair)
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return maximum_depth, nodes


def _mapping(value: Any, name: str, allowed: set[str], required: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise MacError(f"{name} must be an object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise MacError(f"{name} contains unknown fields: {sorted(unknown)}")
    if missing:
        raise MacError(f"{name} is missing fields: {sorted(missing)}")
    return value


def _text(value: Any, name: str, *, maximum: int = 2_048) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise MacError(f"{name} must be a non-empty trimmed string of at most {maximum} characters")
    if any(ord(character) < 32 or 0x7F <= ord(character) <= 0x9F for character in value):
        raise MacError(f"{name} contains a control character")
    return value


def _identity(value: Any, name: str) -> str:
    text = _text(value, name, maximum=256)
    if not _IDENTITY_PATTERN.fullmatch(text):
        raise MacError(
            f"{name} must be a lowercase ASCII canonical identifier using "
            "letters, digits, dot, underscore, colon, slash, at, plus or hyphen"
        )
    return text


def _https(value: Any, name: str) -> str:
    text = _text(value, name)
    if not _HTTPS_PATTERN.fullmatch(text) or not _FORMAT_CHECKER.conforms(text, "uri"):
        raise MacError(
            f"{name} must be an ASCII https URI with a DNS-style host, no user information "
            "or explicit port; path, query and fragment are permitted"
        )
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port is not None
    ):
        raise MacError(f"{name} violates the https URI policy")
    return text


def _hash(value: Any, name: str) -> str:
    text = _text(value, name, maximum=71)
    if not _HASH_PATTERN.fullmatch(text):
        raise MacError(f"{name} must be a lowercase sha256 digest")
    return text


def _canonical_json(value: Any) -> bytes:
    """Return RFC 8785-compatible bytes for the MAC schema's JSON subset.

    All schema keys are fixed ASCII strings and the schema contains no JSON
    numbers, the two areas where a generic ``sort_keys`` serialiser can differ
    from JCS.  Non-finite or numeric extensions are rejected by validation.
    """

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MacError(f"payload is not canonical JSON data: {exc}") from exc


def _digest(value: Any) -> str:
    return "sha256-" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _validate_subjects(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    raw = payload.get("subjects")
    if not isinstance(raw, list) or not raw or len(raw) > 25:
        raise MacError("subjects must contain between 1 and 25 items")
    subjects: list[dict[str, str]] = []
    reservations: set[tuple[str, str]] = set()
    for index, item in enumerate(raw):
        subject = _mapping(item, f"subjects[{index}]", {"kind", "identity", "role"}, {"kind", "identity"})
        kind = _text(subject["kind"], f"subjects[{index}].kind", maximum=32)
        identity = _identity(subject["identity"], f"subjects[{index}].identity")
        if kind not in _KINDS:
            raise MacError(f"subjects[{index}].kind is unsupported")
        reservation = (kind, identity)
        if reservation in reservations:
            raise MacError("subjects contain a duplicate logical identity")
        reservations.add(reservation)
        normalised = {"kind": kind, "identity": identity}
        if "role" in subject:
            role = _text(subject["role"], f"subjects[{index}].role", maximum=11)
            if role not in {"source", "destination"}:
                raise MacError(f"subjects[{index}].role is unsupported")
            normalised["role"] = role
        subjects.append(normalised)
    return subjects


def _validate_batch_scope(value: Any) -> dict[str, Any]:
    scope = _mapping(
        value,
        "batch_scope",
        {"source", "observation_scope", "inference_service_id"},
        {"source", "observation_scope", "inference_service_id"},
    )
    source = _mapping(scope["source"], "batch_scope.source", {"type", "uri"}, {"type", "uri"})
    source_type = _text(source["type"], "batch_scope.source.type", maximum=32)
    if source_type not in {"first-party-read-api", "official-documentation"}:
        raise MacError("batch_scope.source.type is unsupported")
    observation = _mapping(
        scope["observation_scope"],
        "batch_scope.observation_scope",
        {"scope_ref", "partition", "region"},
        {"scope_ref", "partition", "region"},
    )
    return {
        "source": {"type": source_type, "uri": _https(source["uri"], "batch_scope.source.uri")},
        "observation_scope": {
            key: _text(observation[key], f"batch_scope.observation_scope.{key}", maximum=256)
            for key in ("scope_ref", "partition", "region")
        },
        "inference_service_id": _identity(
            scope["inference_service_id"], "batch_scope.inference_service_id"
        ),
    }


def _validate_evidence(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 25:
        raise MacError("candidate_evidence must be an array of at most 25 items")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        evidence = _mapping(
            item,
            f"candidate_evidence[{index}]",
            {"uri", "observed_at", "digest"},
            {"uri", "observed_at", "digest"},
        )
        observed_at = _text(evidence["observed_at"], f"candidate_evidence[{index}].observed_at", maximum=40)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", observed_at):
            raise MacError(f"candidate_evidence[{index}].observed_at must be an RFC3339 UTC timestamp")
        try:
            parsed_time = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MacError(f"candidate_evidence[{index}].observed_at is not a real timestamp") from exc
        if parsed_time.tzinfo != timezone.utc:
            raise MacError(f"candidate_evidence[{index}].observed_at must use UTC")
        result.append(
            {
                "uri": _https(evidence["uri"], f"candidate_evidence[{index}].uri"),
                "observed_at": observed_at,
                "digest": _hash(evidence["digest"], f"candidate_evidence[{index}].digest"),
            }
        )
    return result


def validate_payload(payload: Mapping[str, Any], *, verify_hashes: bool = True) -> dict[str, Any]:
    """Validate and return a detached, normalised neutral MAC payload."""

    value = _mapping(
        payload,
        "payload",
        _TOP_LEVEL_FIELDS,
        {
            "schema_version",
            "request_id",
            "operation",
            "purpose",
            "subjects",
            "requested_outcome",
            "reason",
            "candidate_evidence",
            "acceptance",
            "dedupe_key",
            "idempotency_key",
        },
    )
    if value["schema_version"] != "0.1":
        raise MacError("schema_version must equal '0.1'")
    request_id = _text(value["request_id"], "request_id", maximum=36)
    try:
        if str(UUID(request_id)) != request_id:
            raise ValueError
    except ValueError as exc:
        raise MacError("request_id must be a canonical lowercase UUID") from exc
    operation = _text(value["operation"], "operation", maximum=8)
    if operation not in _OPERATIONS:
        raise MacError("operation is unsupported")
    subjects = _validate_subjects(value)
    roles = [subject.get("role") for subject in subjects]
    item_operation: str | None = None
    batch_scope: dict[str, Any] | None = None
    if operation == "batch":
        if "item_operation" not in value or "batch_scope" not in value:
            raise MacError("batch requires item_operation and batch_scope")
        item_operation = _text(value["item_operation"], "item_operation", maximum=6)
        if item_operation not in _ITEM_OPERATIONS:
            raise MacError("item_operation is unsupported")
        batch_scope = _validate_batch_scope(value["batch_scope"])
        if item_operation == "revoke" and any(subject["kind"] != "offering" for subject in subjects):
            raise MacError("batch revoke supports offering subjects only")
        if any(role is not None for role in roles):
            raise MacError("batch subjects cannot have roles")
    else:
        if "item_operation" in value or "batch_scope" in value:
            raise MacError("only batch may contain item_operation or batch_scope")
        if operation == "move":
            if len(subjects) != 2 or any(subject["kind"] != "offering" for subject in subjects):
                raise MacError("move requires exactly two offering subjects")
            if sorted(roles) != ["destination", "source"]:
                raise MacError("move requires exactly one source and one destination")
        else:
            if len(subjects) != 1 or any(role is not None for role in roles):
                raise MacError("non-batch add/change/revoke requires one subject without a role")
            if operation == "revoke" and subjects[0]["kind"] != "offering":
                raise MacError("revoke supports offering subjects only")

    acceptance_raw = value["acceptance"]
    if not isinstance(acceptance_raw, list) or not acceptance_raw or len(acceptance_raw) > 25:
        raise MacError("acceptance must contain between 1 and 25 criteria")
    acceptance = [_text(item, f"acceptance[{index}]") for index, item in enumerate(acceptance_raw)]

    result: dict[str, Any] = {
        "schema_version": "0.1",
        "request_id": request_id,
        "operation": operation,
        "purpose": _text(value["purpose"], "purpose", maximum=160),
        "subjects": subjects,
        "requested_outcome": _text(value["requested_outcome"], "requested_outcome"),
        "reason": _text(value["reason"], "reason"),
        "candidate_evidence": _validate_evidence(value["candidate_evidence"]),
        "acceptance": acceptance,
        "dedupe_key": _hash(value["dedupe_key"], "dedupe_key"),
        "idempotency_key": _hash(value["idempotency_key"], "idempotency_key"),
    }
    if item_operation is not None:
        result["item_operation"] = item_operation
    if batch_scope is not None:
        result["batch_scope"] = batch_scope
    rendered_payload_bytes = len(
        json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True).encode("utf-8")
    )
    if rendered_payload_bytes > MAX_RENDERED_PAYLOAD_BYTES:
        raise MacError(
            f"rendered canonical payload exceeds {MAX_RENDERED_PAYLOAD_BYTES} bytes"
        )
    if verify_hashes:
        expected_dedupe, expected_idempotency = compute_keys(result)
        if result["dedupe_key"] != expected_dedupe:
            raise MacError("dedupe_key does not match the canonical reservation input")
        if result["idempotency_key"] != expected_idempotency:
            raise MacError("idempotency_key does not match the canonical complete intent")
    return deepcopy(result)


def compute_keys(payload: Mapping[str, Any]) -> tuple[str, str]:
    """Compute contract-defined dedupe and idempotency keys."""

    value = validate_payload(payload, verify_hashes=False)
    effective_operation = value.get("item_operation", value["operation"])
    reservations = sorted(
        ({"kind": subject["kind"], "identity": subject["identity"]} for subject in value["subjects"]),
        key=lambda item: (item["kind"], item["identity"]),
    )
    dedupe_input = {
        "effective_operation": effective_operation,
        "purpose": value["purpose"],
        "reservations": reservations,
    }
    intent = {
        key: deepcopy(item)
        for key, item in value.items()
        if key not in {"request_id", "dedupe_key", "idempotency_key"}
    }
    return _digest(dedupe_input), _digest(intent)


def with_computed_keys(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Replace placeholder hashes and return a fully validated payload."""

    candidate = deepcopy(dict(payload))
    placeholder = "sha256-" + "0" * 64
    candidate["dedupe_key"] = placeholder
    candidate["idempotency_key"] = placeholder
    dedupe_key, idempotency_key = compute_keys(candidate)
    candidate["dedupe_key"] = dedupe_key
    candidate["idempotency_key"] = idempotency_key
    return validate_payload(candidate)


def payload_digest(payload: Mapping[str, Any]) -> str:
    """Hash a complete, valid neutral payload for issue/change binding."""

    return _digest(validate_payload(payload))


def render_issue_body(payload: Mapping[str, Any], adapter: Adapter) -> str:
    """Render a bounded, stable issue-body transport for either Git provider."""

    if adapter not in {"github", "gitlab"}:
        raise MacError("unsupported Git-provider adapter")
    value = validate_payload(payload)
    pretty = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
    body = (
        f"## Neutral MAC payload ({adapter})\n\n"
        f"{PAYLOAD_START}\n```json\n{pretty}\n```\n{PAYLOAD_END}\n\n"
        f"<!-- modelo:mac-payload-digest {payload_digest(value)} -->\n"
    )
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise MacError(f"rendered issue body exceeds {MAX_BODY_BYTES} bytes")
    return body


def render_adapter_issue_body(payload: Mapping[str, Any], adapter: Adapter) -> str:
    """Render the provider-native filled fields represented by checked-in templates."""

    if adapter not in {"github", "gitlab"}:
        raise MacError("unsupported Git-provider adapter")
    value = validate_payload(payload)
    pretty = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
    digest = payload_digest(value)
    if adapter == "github":
        body = (
            f"### Neutral MAC payload\n\n```json\n{pretty}\n```\n\n"
            f"### Neutral payload digest\n\n{digest}\n"
        )
    else:
        body = (
            f"# MAC request\n\n```json\n{pretty}\n```\n\n"
            f"Neutral payload digest: `{digest}`\n"
        )
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise MacError(f"rendered adapter issue body exceeds {MAX_BODY_BYTES} bytes")
    return body


def _parse_json_payload(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_object_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(MacError(f"invalid JSON value {token}")),
        )
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise MacError(f"invalid MAC JSON: {exc}") from exc
    depth, nodes = _measure(value)
    if depth > MAX_DEPTH or nodes > MAX_NODES:
        raise MacError("MAC payload exceeds depth or node limits")
    return validate_payload(value)


def _bounded_body(body: str) -> None:
    if not isinstance(body, str) or len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise MacError(f"issue body exceeds {MAX_BODY_BYTES} bytes")


def extract_adapter_issue_payload(body: str, adapter: Adapter) -> dict[str, Any]:
    """Recover a payload from the actual filled GitHub or GitLab template shape."""

    _bounded_body(body)
    if adapter == "github":
        starts = [match.start() for match in re.finditer(re.escape(INTAKE_START), body)]
        ends = [match.start() for match in re.finditer(re.escape(INTAKE_END), body)]
        if starts or ends:
            if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
                raise MacError("generated intake block is ambiguous")
            if body[ends[0] + len(INTAKE_END):].strip():
                raise MacError("generated intake block is not final")
            source_digests = re.findall(
                r"<!-- modelo:intake-source (sha256:[0-9a-f]{64}) -->",
                body[starts[0]:ends[0]],
            )
            source = body[:starts[0]].rstrip()
            actual = "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
            if source_digests != [actual]:
                raise MacError("guided proposal human fields changed after payload generation")
        payload_matches = re.findall(
            r"(?ms)^### (?:Neutral MAC payload|Change details \(JSON\))\n\n```json\n([\s\S]*?)\n```(?:\n|$)", body
        )
        digest_matches = re.findall(
            r"(?m)^### (?:Neutral payload digest|Change fingerprint)\n\n(sha256-[0-9a-f]{64})$", body
        )
    elif adapter == "gitlab":
        payload_matches = re.findall(r"(?ms)^```json\n([\s\S]*?)\n```(?:\n|$)", body)
        digest_matches = re.findall(
            r"(?m)^Neutral payload digest: `(sha256-[0-9a-f]{64})`$", body
        )
    else:
        raise MacError("unsupported Git-provider adapter")
    if len(payload_matches) != 1 or len(digest_matches) != 1:
        raise MacError("adapter issue body must contain one MAC payload and one digest field")
    payload = _parse_json_payload(payload_matches[0])
    if digest_matches[0] != payload_digest(payload):
        raise MacError("declared adapter payload digest does not match the canonical payload")
    return payload


def extract_issue_payload(body: str) -> dict[str, Any]:
    """Recover and validate one canonical payload block from an issue body."""

    _bounded_body(body)
    start_pattern = re.compile(rf"(?m)^{re.escape(PAYLOAD_START)}$")
    end_pattern = re.compile(rf"(?m)^{re.escape(PAYLOAD_END)}$")
    starts = list(start_pattern.finditer(body))
    ends = list(end_pattern.finditer(body))
    if len(starts) != 1 or len(ends) != 1 or ends[0].start() <= starts[0].end():
        raise MacError("issue body must contain exactly one ordered MAC payload marker pair")
    block = body[starts[0].end() : ends[0].start()].strip()
    match = re.fullmatch(r"```json\n([\s\S]+)\n```", block)
    if match is None:
        raise MacError("MAC payload marker must contain exactly one fenced JSON object")
    payload = _parse_json_payload(match.group(1))
    marker_pattern = re.compile(r"(?m)^<!-- modelo:mac-payload-digest (sha256-[0-9a-f]{64}) -->$")
    markers = marker_pattern.findall(body)
    if markers != [payload_digest(payload)]:
        raise MacError("issue body must contain one matching canonical payload digest marker")
    return payload


def init_mac_payload(
    operation: str,
    purpose: str,
    subjects: list[dict[str, Any]],
    requested_outcome: str,
    reason: str,
    candidate_evidence: list[dict[str, Any]],
    acceptance: list[str],
    item_operation: str | None = None,
    batch_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Initialize a MAC payload with a canonical UUID request_id, compute keys, and validate."""

    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "request_id": str(uuid4()),
        "operation": operation,
        "purpose": purpose,
        "subjects": subjects,
        "requested_outcome": requested_outcome,
        "reason": reason,
        "candidate_evidence": candidate_evidence,
        "acceptance": acceptance,
    }
    if item_operation is not None:
        payload["item_operation"] = item_operation
    if batch_scope is not None:
        payload["batch_scope"] = batch_scope

    return with_computed_keys(payload)

