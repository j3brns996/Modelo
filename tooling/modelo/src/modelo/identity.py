"""ModelRelease identity profile; no provider lookups or approval authority."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from modelo.evidence import evidence_id, resolve_pointer

ENTITY_PROFILE = "0.3.0"
AWS_MODEL_NAMESPACE = "aws.bedrock.foundation-model"
BOUND_STATUSES = frozenset({"verified", "vendor-asserted", "provider-mapped"})


def canonical_urn(kind: str, identifier: str) -> str:
    if kind not in {"model-release", "offering"} or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", identifier
    ) or len(identifier) > 128:
        raise ValueError("canonical URN requires a supported kind and internal ID")
    return f"urn:modelo:{kind}:{identifier}"


def release_precision(model: Mapping[str, Any]) -> str:
    return model.get("release", {}).get("precision", "named-release")


def has_provider_claim(model: Mapping[str, Any], value: Any) -> bool:
    return any(
        claim["namespace"] == AWS_MODEL_NAMESPACE
        and claim["value"] == value
        and claim["relation"] == "identifies"
        and claim["status"] in BOUND_STATUSES
        for claim in model.get("identity_claims", [])
    )


def migrate_bound_model(
    model: Mapping[str, Any], evidence: Mapping[str, Any], *,
    id_pointer: str, reviewed_model_id: str,
) -> dict[str, Any]:
    """Return a local draft from an explicitly reviewed API-to-model binding.

    Never search names, infer equivalence, modify evidence, or write history.
    Caller must validate the complete draft through the ordinary MAC workflow.
    """
    if reviewed_model_id != model["id"]:
        raise ValueError("reviewed model ID differs from the migration target")
    if evidence.get("id") != evidence_id(evidence):
        raise ValueError("migration evidence content address is invalid")
    source = evidence.get("source", {})
    if (source.get("type"), source.get("provider"), source.get("service")) != (
        "first-party-read-api", "aws", "bedrock"
    ) or source.get("operation") not in {"GetFoundationModel", "ListFoundationModels"}:
        raise ValueError("migration requires explicit Bedrock model API evidence")
    value = resolve_pointer(evidence["projection"], id_pointer)
    if not isinstance(value, str) or not value:
        raise ValueError("model ID pointer must select a nonempty string")
    result = deepcopy(dict(model))
    result["canonical_urn"] = canonical_urn("model-release", str(model["id"]))
    claim = dict(namespace=AWS_MODEL_NAMESPACE, value=value, relation="identifies", status="provider-mapped")
    claims = result.setdefault("identity_claims", [])
    keys = [(item["namespace"], item["value"], item["relation"]) for item in claims]
    if len(keys) != len(set(keys)):
        raise ValueError("migration cannot resolve duplicate identity claim tuples")
    key = (claim["namespace"], claim["value"], claim["relation"])
    if key in keys:
        # Migration is not a status review or an evidence refresh. Preserve both.
        return result
    index = len(claims)
    claims.append(claim)
    result["evidence_refs"][f"/identity_claims/{index}/value"] = {
        "id": evidence["id"], "projection_pointer": id_pointer,
    }
    return result


def migrate_offering(offering: Mapping[str, Any]) -> dict[str, Any]:
    """Classify existing explicit binding kinds without asserting immutability."""
    result = deepcopy(dict(offering))
    for route in result["routes"]:
        if "source_region" not in route:
            raise ValueError("migration supports only explicit AWS route bindings")
        kind = route.get("model_binding", {}).get("kind")
        if kind not in {"foundation-model", "system-inference-profile"}:
            raise ValueError("unsupported route binding; do not infer selector semantics")
        selector = "provider-model-id" if kind == "foundation-model" else "inference-profile"
        if route.get("selector_type", selector) != selector:
            raise ValueError("migration cannot overwrite an existing selector claim")
        route["selector_type"] = selector
    return result
