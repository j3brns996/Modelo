"""Canonical projection, delta and receipt primitives.

These functions are deliberately provider-neutral and side-effect free.  Every
digest returned here covers the exact bytes emitted by the corresponding
canonical encoder, including its single trailing LF.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Iterable, Mapping

from modelo.evidence import canonical_json


def canonical_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def sort_change_delta(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rank = {"add": 0, "change": 1, "revoke": 2, "move": 3}

    def key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        operation = item["operation"]
        if operation == "move":
            source = item["source"]
            destination_record = item["destination"]
            primary = source["path"]
            destination = destination_record["path"]
            before = source.get("before", "")
            after = destination_record.get("after", "")
        else:
            primary = item["path"]
            destination = ""
            before = item.get("before", "")
            after = item.get("after", "")
        return (
            rank[operation],
            primary.encode("utf-8"),
            destination.encode("utf-8"),
            str(before).encode("utf-8"),
            str(after).encode("utf-8"),
            canonical_json(dict(item)).encode("utf-8"),
        )

    return [deepcopy(dict(item)) for item in sorted(items, key=key)]


def change_delta_bytes(items: Iterable[Mapping[str, Any]]) -> bytes:
    return canonical_bytes(sort_change_delta(items))


def _canonical_tie(value: Mapping[str, Any]) -> bytes:
    return canonical_json(dict(value)).encode("utf-8")


def _rewrite_index_pointers(
    references: Mapping[str, Any], component: str, old_to_new: Mapping[int, int]
) -> dict[str, Any]:
    prefix = f"/{component}/"
    rewritten: dict[str, Any] = {}
    for pointer, reference in references.items():
        changed = pointer
        if pointer.startswith(prefix):
            remainder = pointer[len(prefix):]
            token, separator, suffix = remainder.partition("/")
            if token.isdigit() and int(token) in old_to_new:
                changed = f"{prefix}{old_to_new[int(token)]}"
                if separator:
                    changed += "/" + suffix
        if changed in rewritten:
            raise ValueError("sorting creates duplicate evidence pointer")
        rewritten[changed] = deepcopy(reference)
    return rewritten


def _sort_with_index(values: list[dict[str, Any]], key) -> tuple[list[dict[str, Any]], dict[int, int]]:
    indexed = list(enumerate(values))
    indexed.sort(key=lambda pair: (*key(pair[1]), _canonical_tie(pair[1])))
    return ([deepcopy(value) for _, value in indexed], {old: new for new, (old, _) in enumerate(indexed)})


def _normalise_model(value: Mapping[str, Any]) -> dict[str, Any]:
    model = deepcopy(dict(value))
    for field in ("capabilities", "modalities"):
        if field in model:
            model[field] = sorted(model[field], key=lambda item: item.encode("ascii"))
    return model


def _normalise_offering(value: Mapping[str, Any]) -> dict[str, Any]:
    offering = deepcopy(dict(value))
    references = dict(offering.get("evidence_refs", {}))
    routes, route_map = _sort_with_index(
        list(offering["routes"]), lambda item: (item["id"].encode("ascii"),)
    )
    for route in routes:
        binding = route.get("model_binding", {})
        if binding.get("kind") == "system-inference-profile":
            binding["destinations"] = sorted(
                binding["destinations"],
                key=lambda item: (
                    item["destination_pointer"].encode("utf-8"),
                    _canonical_tie(item),
                ),
            )
    offering["routes"] = routes
    references = _rewrite_index_pointers(references, "routes", route_map)
    if "pricing" in offering:
        for price in offering["pricing"]:
            price["route_ids"] = sorted(price["route_ids"], key=lambda item: item.encode("ascii"))
        prices, price_map = _sort_with_index(
            list(offering["pricing"]),
            lambda item: (
                item["dimension"].encode("utf-8"),
                item["unit"].encode("utf-8"),
                item["quantity"].encode("utf-8"),
                item["amount"].encode("utf-8"),
                item["currency"].encode("utf-8"),
                "\0".join(item["route_ids"]).encode("utf-8"),
            ),
        )
        offering["pricing"] = prices
        references = _rewrite_index_pointers(references, "pricing", price_map)
    offering["condition_refs"] = sorted(
        offering["condition_refs"],
        key=lambda item: (item["id"].encode("ascii"), item["version"], _canonical_tie(item)),
    )
    if references or "evidence_refs" in offering:
        offering["evidence_refs"] = references
    return offering


def catalogue_projection(
    *,
    contract_version: str,
    source_commit: str,
    source_tree: str,
    as_of: str,
    profile: str,
    models: Iterable[Mapping[str, Any]],
    offerings: Iterable[Mapping[str, Any]],
    evidence: Iterable[Mapping[str, Any]],
    conditions: Iterable[Mapping[str, Any]],
    vendors: Mapping[str, Any],
    inference_services: Mapping[str, Any],
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    normal_models = [_normalise_model(item) for item in models]
    normal_offerings = [_normalise_offering(item) for item in offerings]
    return {
        "contract_version": contract_version,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "as_of": as_of,
        "profile": profile,
        "models": sorted(normal_models, key=lambda item: (item["id"].encode("ascii"), _canonical_tie(item))),
        "offerings": sorted(normal_offerings, key=lambda item: (item["inference_service_id"].encode("ascii"), item["id"].encode("ascii"), _canonical_tie(item))),
        "evidence": sorted((deepcopy(dict(item)) for item in evidence), key=lambda item: (item["id"].encode("ascii"), _canonical_tie(item))),
        "conditions": sorted((deepcopy(dict(item)) for item in conditions), key=lambda item: (item["id"].encode("ascii"), item["version"], _canonical_tie(item))),
        "vendors": deepcopy(dict(vendors)),
        "inference_services": deepcopy(dict(inference_services)),
        "freshness": deepcopy(dict(freshness)),
    }


def publication_digest(files: Mapping[str, bytes]) -> str:
    records = bytearray()
    for path in sorted(files, key=lambda item: item.encode("utf-8")):
        data = files[path]
        records.extend(path.encode("utf-8"))
        records.extend(b"\0")
        records.extend(sha256_bytes(data).encode("ascii"))
        records.extend(b"\0")
        records.extend(str(len(data)).encode("ascii"))
        records.extend(b"\n")
    return sha256_bytes(bytes(records))


def manifest_entries(files: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    media = {".json": "application/json; charset=utf-8"}
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(files, key=lambda item: item.encode("utf-8")):
        suffix = ".json" if path.endswith(".json") else ""
        result[path] = {
            "sha256": sha256_bytes(files[path]),
            "size": len(files[path]),
            "media_type": media.get(suffix, "application/octet-stream"),
        }
    return result
