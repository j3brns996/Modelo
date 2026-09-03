"""Deterministic validation/final static-site projection and durable publisher."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from string import Template
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urlsplit

from modelo.build import (
    BuildError, BuildRequest, _layout, _projection_from_snapshot, _publish, _safe_url,
    _walk_regular_tree, rebuild_candidate_inputs, recover_candidate,
)
from modelo.change import with_snapshot
from modelo.config import load_config
from modelo.receipt import canonical_bytes, publication_digest, sha256_bytes
from modelo.schemas import SchemaSet


_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_PRIVATE_CANARY = b"MODELO_PRIVATE_CANARY"


@dataclass(frozen=True, slots=True)
class FinalBuildRequest:
    root: Path
    base_commit: str
    source_commit: str
    source_tree: str
    merge_commit: str
    merge_tree: str
    as_of: date
    source_date_epoch: int
    profile: str
    base_url: str
    base_path: str
    output: str
    mac_metadata: Path
    publication_capability: str


@dataclass(frozen=True, slots=True)
class ValidationBuildRequest:
    root: Path
    base_commit: str
    source_commit: str
    source_tree: str
    validation_commit: str
    validation_tree: str
    as_of: date
    source_date_epoch: int
    profile: str
    base_url: str
    base_path: str
    output: str
    mac_metadata: Path
    publication_capability: str


@dataclass(frozen=True, slots=True)
class DemoBuildRequest:
    root: Path
    source_commit: str
    source_tree: str
    as_of: date
    source_date_epoch: int
    base_url: str
    base_path: str
    output: str


@dataclass(frozen=True, slots=True)
class _SiteBuildRequest:
    kind: str
    root: Path
    base_commit: str
    source_commit: str
    source_tree: str
    integration_commit: str
    integration_tree: str
    as_of: date
    source_date_epoch: int
    profile: str
    base_url: str
    base_path: str
    output: str
    mac_metadata: Path | None
    publication_capability: str


@dataclass(frozen=True, slots=True)
class FinalBuildResult:
    output: Path
    manifest_bytes: bytes
    publication_digest: str
    file_count: int


def _git(root: Path, *arguments: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", *arguments], cwd=root, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=not binary, check=False,
    )
    if result.returncode:
        raise BuildError("local Git command failed while building final site")
    return result.stdout


def _canonical_commit(root: Path, value: str, label: str) -> str:
    resolved = str(_git(root, "rev-parse", "--verify", f"{value}^{{commit}}")).strip()
    if value != resolved or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise BuildError(f"{label} must be a complete canonical commit SHA")
    return resolved


def _blob(root: Path, commit: str, path: str) -> bytes:
    if not path or path.startswith("/") or ".." in PurePosixPath(path).parts:
        raise BuildError("unsafe committed input path")
    mode = str(_git(root, "ls-tree", commit, "--", path)).split()
    if len(mode) < 3 or mode[0] not in {"100644", "100755"} or mode[1] != "blob":
        raise BuildError(f"committed site input is missing or not a regular blob: {path}")
    return bytes(_git(root, "show", f"{commit}:{path}", binary=True))


def _entry(data: bytes, path: str = "") -> dict[str, Any]:
    suffix = PurePosixPath(path).suffix
    media = {
        ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".md": "text/markdown; charset=utf-8", ".yaml": "application/yaml; charset=utf-8",
    }.get(suffix, "application/json; charset=utf-8")
    return {"sha256": sha256_bytes(data), "size": len(data), "media_type": media}


class _Resolver:
    def __init__(self, base_url: str, base_path: str, site_routes: Mapping[str, str], repository: Mapping[str, Any], fonts: Mapping[str, Any] | None = None) -> None:
        _safe_url(base_url, base_path)
        parsed = urlsplit(base_url)
        if parsed.path != base_path:
            raise BuildError("final base URL path must equal normalised base path")
        self.base_url = base_url
        self.base_path = base_path
        self.site_routes = dict(site_routes)
        self.repository = repository
        self.fonts = dict(fonts or {})
        self._validate_routes()

    def _validate_routes(self) -> None:
        expected_directories = {"home", "catalogue", "model", "offering", "changes", "process", "propose", "docs"}
        expected_files = {
            "not_found", "asset_css", "asset_catalogue_js", "asset_proposal_js", "asset_alpine",
            "asset_third_party_notices", "catalogue_data", "change_delta_data",
            "manifest_data", "schemas_data", "human_specification", "machine_contract",
        }
        if set(self.site_routes) != expected_directories | expected_files:
            raise BuildError("configured site route inventory is incomplete or contains extras")
        rendered: dict[str, str] = {}
        samples = {"model_id": "sample-model", "inference_service_id": "sample-service", "offering_id": "sample-offering"}
        for key, route in self.site_routes.items():
            if not isinstance(route, str) or not route.startswith("/") or "//" in route or ".." in PurePosixPath(route).parts:
                raise BuildError(f"configured site route {key!r} is not canonical")
            placeholders = set(re.findall(r"\{([a-z][a-z0-9_]*)\}", route))
            if route.count("{") != len(placeholders) or route.count("}") != len(placeholders) or not placeholders <= set(samples):
                raise BuildError(f"configured site route {key!r} has invalid placeholders")
            if key in expected_directories and not route.endswith("/"):
                raise BuildError(f"configured directory route {key!r} needs a trailing slash")
            if key in expected_files and key != "schemas_data" and route.endswith("/"):
                raise BuildError(f"configured file route {key!r} must not have a trailing slash")
            if key == "schemas_data" and not route.endswith("/"):
                raise BuildError("configured schema route needs a trailing slash")
            concrete = route
            for name in placeholders:
                concrete = concrete.replace("{" + name + "}", samples[name])
            if concrete in rendered:
                raise BuildError(f"configured site routes {rendered[concrete]!r} and {key!r} collide")
            rendered[concrete] = key

    def site(self, key: str, **values: str) -> str:
        try:
            route = self.site_routes[key]
        except KeyError as exc:
            raise BuildError(f"unknown configured site route {key!r}") from exc
        for name, value in values.items():
            if not _ID.fullmatch(value):
                raise BuildError(f"unsafe route value for {name}")
            route = route.replace("{" + name + "}", quote(value, safe=""))
        if "{" in route or "}" in route:
            raise BuildError(f"unresolved configured site route {key!r}")
        return self.base_path + route.lstrip("/")

    def canonical(self, key: str, **values: str) -> str:
        local = self.site(key, **values)
        return self.base_url.removesuffix(self.base_path) + local

    def output_path(self, key: str, **values: str) -> str:
        route = self.site_routes[key]
        for name, value in values.items():
            route = route.replace("{" + name + "}", value)
        if "{" in route or "}" in route:
            raise BuildError(f"unresolved configured output route {key!r}")
        relative = route.lstrip("/")
        if key == "schemas_data":
            return relative
        return (relative + "index.html") if route.endswith("/") else relative

    def repository_url(self, key: str, **values: str) -> str:
        try:
            route = self.repository["web_routes"][key]
        except (KeyError, TypeError) as exc:
            raise BuildError(f"unknown configured repository route {key!r}") from exc
        for name, value in values.items():
            if not value or any(char in value for char in "{}\r\n"):
                raise BuildError("unsafe repository route value")
            route = route.replace("{" + name + "}", quote(value, safe=""))
        if "{" in route or "}" in route or not route.startswith("/"):
            raise BuildError(f"unresolved configured repository route {key!r}")
        return str(self.repository["web_base"]).rstrip("/") + route


def _template(root: Path, source: str, templates_path: str, name: str) -> Template:
    raw = _blob(root, source, f"{templates_path}/{name}.html")
    try:
        return Template(raw.decode("utf-8", "strict"))
    except UnicodeError as exc:
        raise BuildError(f"template {name!r} is not strict UTF-8") from exc


def _substitute(template: Template, values: Mapping[str, str], name: str) -> str:
    try:
        rendered = template.substitute(values)
    except (KeyError, ValueError) as exc:
        raise BuildError(f"template {name!r} has a missing or invalid placeholder") from exc
    if "\r" in rendered:
        raise BuildError(f"template {name!r} rendered CR line endings")
    return rendered


def _markdown(raw: bytes) -> str:
    try:
        lines = raw.decode("utf-8", "strict").splitlines()
    except UnicodeError as exc:
        raise BuildError("site content is not strict UTF-8") from exc
    output: list[str] = []
    paragraph: list[str] = []
    def flush() -> None:
        if paragraph:
            output.append("<p>" + escape(" ".join(paragraph)) + "</p>")
            paragraph.clear()
    for line in lines:
        if not line.strip():
            flush()
        elif line.startswith("## "):
            flush(); output.append("<h2>" + escape(line[3:]) + "</h2>")
        elif line.startswith("# "):
            flush(); output.append("<h2>" + escape(line[2:]) + "</h2>")
        else:
            paragraph.append(line.strip())
    flush()
    return "\n".join(output)


def _tags(values: Iterable[Any]) -> str:
    return " ".join(f'<span class="tag">{escape(str(value))}</span>' for value in values)


def _evidence_region(evidence: Mapping[str, Mapping[str, Any]], identifier: str) -> str:
    try:
        region = evidence[identifier]["source"]["region"]
    except (KeyError, TypeError) as exc:
        raise BuildError("bound destination evidence lacks a source Region") from exc
    if not isinstance(region, str):
        raise BuildError("bound destination evidence has an invalid source Region")
    return region


def _route_rows(offering: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]) -> str:
    rows: list[str] = []
    for route in offering.get("routes", []):
        binding = route["model_binding"]
        kind = binding["kind"]
        destinations: list[str] = []
        if kind == "system-inference-profile":
            destinations = sorted({
                _evidence_region(evidence, item["model_evidence"]["id"])
                for item in binding["destinations"]
            })
        rows.append(
            "<tr><td><code>" + escape(route["id"]) + "</code></td><td>" +
            escape(route["source_region"]) + "</td><td>" + escape(kind) +
            "</td><td><code>" + escape(route["reference"]) + "</code></td><td>" +
            (", ".join(map(escape, destinations)) if destinations else '<span class="muted">None</span>') +
            "</td></tr>"
        )
    return '<table><caption>Callable provider routes</caption><thead><tr><th>Route</th><th>Source Region</th><th>Route type</th><th>Reference</th><th>Destination Regions</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"


def _pricing_rows(offering: Mapping[str, Any]) -> str:
    rows = []
    for price in offering.get("pricing", []):
        rows.append("<tr><td>" + escape(price["dimension"]) + "</td><td>" + escape(price["amount"]) + " " + escape(price["currency"]) + "</td><td>" + escape(str(price["quantity"])) + " " + escape(price["unit"]) + "</td><td>" + _tags(price["route_ids"]) + "</td></tr>")
    if not rows:
        return '<p class="muted">No pricing facts are published for this offering.</p>'
    return '<table><caption>Published pricing facts</caption><thead><tr><th>Dimension</th><th>Amount</th><th>Unit</th><th>Routes</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"


def _history(root: Path, merge: str, source_path: str, resolver: _Resolver) -> list[dict[str, Any]]:
    if str(_git(root, "rev-parse", "--is-shallow-repository")).strip() != "false":
        raise BuildError("final site requires complete non-shallow first-parent history")
    commits = str(_git(root, "rev-list", "--first-parent", "--reverse", merge)).splitlines()
    if not commits or commits[-1] != merge:
        raise BuildError("cannot establish complete first-parent history")
    result: list[dict[str, Any]] = []
    for commit in commits:
        parents = str(_git(root, "show", "-s", "--format=%P", commit)).split()
        args = ["diff-tree", "--no-commit-id", "--name-status", "-r", "--no-renames"]
        if parents:
            args.extend([parents[0], commit, "--", source_path])
        else:
            args.extend(["--root", commit, "--", source_path])
        changes = []
        for line in str(_git(root, *args)).splitlines():
            status, separator, path = line.partition("\t")
            if not separator or status not in {"A", "M", "D"}:
                raise BuildError("history contains an ambiguous or unsupported path delta")
            changes.append({"A": "add", "M": "change", "D": "revoke"}[status] + ": " + path)
        if changes:
            timestamp = int(str(_git(root, "show", "-s", "--format=%at", commit)).strip())
            subject = str(_git(root, "show", "-s", "--format=%s", commit)).rstrip("\n")
            result.append({
                "sha": commit, "date": datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat(),
                "subject": subject, "changes": sorted(changes, key=lambda value: value.encode("utf-8")),
                "url": resolver.repository_url("commit", commit_sha=commit),
            })
    return list(reversed(result))


def _history_html(history: Iterable[Mapping[str, Any]]) -> str:
    items = []
    for entry in history:
        changes = "".join("<li>" + escape(item) + "</li>" for item in entry["changes"])
        items.append('<article class="card"><h2><a rel="noopener noreferrer" href="' + escape(entry["url"], quote=True) + '"><code>' + escape(entry["sha"][:12]) + "</code></a></h2><p><time datetime=\"" + escape(entry["date"], quote=True) + '\">' + escape(entry["date"]) + "</time> · " + escape(entry["subject"]) + "</p><ul>" + changes + "</ul></article>")
    return '<div class="cards">' + "".join(items) + "</div>" if items else '<p class="muted">No catalogue changes are present in first-parent history.</p>'


def _history_summary_html(history: Iterable[Mapping[str, Any]]) -> str:
    items = []
    for entry in history:
        items.append(
            '<article class="history-card"><div><time datetime="' + escape(entry["date"], quote=True) + '">'
            + escape(entry["date"]) + '</time><span>' + str(len(entry["changes"])) + ' changed paths</span></div><h3>'
            + escape(entry["subject"]) + '</h3><a rel="noopener noreferrer" href="'
            + escape(entry["url"], quote=True) + '"><code>' + escape(entry["sha"][:12])
            + '</code><span aria-hidden="true">→</span></a></article>'
        )
    return '<div class="history-summary">' + "".join(items) + "</div>" if items else '<p class="muted">No catalogue changes are present in first-parent history.</p>'


def _navigation(resolver: _Resolver, current: str) -> str:
    labels = (
        ("catalogue", "Explore"), ("process", "Governance"),
        ("changes", "Changes"), ("propose", "Contribute"), ("docs", "Reference"),
    )
    return "".join(
        '<a href="' + escape(resolver.site(key), quote=True) + '"'
        + (' aria-current="page"' if key == current else "") + ">" + label + "</a>"
        for key, label in labels
    )


def _page(root: Path, source: str, templates_path: str, resolver: _Resolver, request: _SiteBuildRequest, name: str, title: str, content: str, route: str, route_values: Mapping[str, str] | None = None) -> bytes:
    base = _template(root, source, templates_path, "base")
    try:
        font_stylesheet = str(resolver.fonts["stylesheet_url"])
        font_style_origin = str(resolver.fonts["style_origin"])
        font_file_origin = str(resolver.fonts["file_origin"])
    except KeyError as exc:
        raise BuildError("configured site font contract is incomplete") from exc
    values = {
        "canonical_url": escape(resolver.canonical(route, **dict(route_values or {})), quote=True),
        "asset_css_url": escape(resolver.site("asset_css"), quote=True),
        "asset_third_party_notices_url": escape(resolver.site("asset_third_party_notices"), quote=True),
        "font_stylesheet_url": escape(font_stylesheet, quote=True),
        "font_style_origin": escape(font_style_origin, quote=True),
        "font_file_origin": escape(font_file_origin, quote=True),
        "scripts": (
            '<script src="' + escape(resolver.site("asset_catalogue_js"), quote=True) + '" defer></script>\n  '
            '<script src="' + escape(resolver.site("asset_alpine"), quote=True) + '" defer></script>'
            if name == "catalogue" else
            '<script src="' + escape(resolver.site("asset_proposal_js"), quote=True) + '" defer></script>'
            if name == "propose" else ""
        ),
        "title": escape(title), "navigation": _navigation(resolver, route), "content": content,
        "page_name": escape(name, quote=True),
        "home_url": escape(resolver.site("home"), quote=True),
        "catalogue_url": escape(resolver.site("catalogue"), quote=True),
        "process_url": escape(resolver.site("process"), quote=True),
        "docs_url": escape(resolver.site("docs"), quote=True),
        "repository_url": escape(str(resolver.repository["web_base"]), quote=True),
        "source_commit_url": escape(resolver.repository_url("commit", commit_sha=request.source_commit), quote=True),
        "status_banner": (
            '<aside class="status-banner" role="status"><span class="status-banner__dot" aria-hidden="true"></span><strong>Synthetic demo.</strong>'
            "<span>This is test data, not an approved enterprise catalogue.</span></aside>"
            if request.kind == "demo" else ""
        ),
        "integration_label": (
            "Approval merge" if request.kind == "final" else
            ("Validation integration" if request.kind == "validation" else "Demo source")
        ),
        "integration_commit_url": escape(resolver.repository_url("commit", commit_sha=request.integration_commit), quote=True),
        "source_commit_short": escape(request.source_commit[:12]), "as_of": request.as_of.isoformat(),
        "integration_commit_short": escape(request.integration_commit[:12]),
    }
    return (_substitute(base, values, name) + "\n").encode("utf-8")


def _site_files(root: Path, request: _SiteBuildRequest, catalogue_raw: bytes, delta_raw: bytes, catalogue: Mapping[str, Any], document: Mapping[str, Any]) -> dict[str, bytes]:
    all_routes = dict(document["site"]["routes"])
    all_routes.update({key + "_data": value for key, value in document["site"]["data_routes"].items()})
    all_routes.update(document["site"]["asset_routes"])
    all_routes.update(document["site"]["document_routes"])
    resolver = _Resolver(request.base_url, request.base_path, all_routes, document["repository"], document["site"]["fonts"])
    templates_path = document["paths"]["site_templates"]
    templates = {name: _template(root, request.source_commit, templates_path, name) for name in ("home", "catalogue", "model", "offering", "changes", "process", "propose", "docs", "404")}
    evidence = {item["id"]: item for item in catalogue["evidence"]}
    offerings_by_model: dict[str, list[Mapping[str, Any]]] = {}
    for item in catalogue["offerings"]:
        offerings_by_model.setdefault(item["model_id"], []).append(item)
    history = _history(root, request.integration_commit, document["publication"]["profiles"][request.profile]["source"], resolver)
    metrics = (
        ("Models", len(catalogue["models"])), ("Offerings", len(catalogue["offerings"])),
        ("Evidence", len(catalogue["evidence"])), ("Conditions", len(catalogue["conditions"])),
    )
    summary = '<div class="console-grid">' + "".join(
        '<div><span>' + label + '</span><strong>' + str(value) + "</strong></div>"
        for label, value in metrics
    ) + "</div><div class=\"console-foot\"><span>profile</span><code>" + escape(request.profile) + "</code><span>as_of</span><code>" + request.as_of.isoformat() + "</code></div>"
    governance_flow = '<ol class="governance-flow"><li><span>01</span><strong>Find the facts</strong><p>Read the provider source and record when and where the facts were seen.</p></li><li><span>02</span><strong>Keep the proof</strong><p>Link each published claim to a fixed, content-addressed evidence record.</p></li><li><span>03</span><strong>Make a decision</strong><p>Review the proposed change and explain why the offering should be approved.</p></li><li><span>04</span><strong>Publish exactly</strong><p>Build the reviewed Git revision once and publish those exact files.</p></li></ol>'
    home_content = _substitute(templates["home"], {
        "summary": summary, "governance_flow": governance_flow,
        "recent_changes": _history_summary_html(history[:3]),
        "catalogue_url": escape(resolver.site("catalogue"), quote=True),
        "process_url": escape(resolver.site("process"), quote=True),
        "propose_url": escape(resolver.site("propose"), quote=True),
        "docs_url": escape(resolver.site("docs"), quote=True),
    }, "home")
    rows = []
    cards = []
    def attributes(values: Mapping[str, Iterable[Any] | Any]) -> str:
        parts = []
        for key, value in values.items():
            items = value if isinstance(value, (list, tuple, set)) else [value]
            parts.append(' data-' + key + '="' + escape("|".join(str(item) for item in items), quote=True) + '"')
        return "".join(parts)
    for model in catalogue["models"]:
        model_name = str(model.get("name", model["id"]))
        model_url = resolver.site("model", model_id=model["id"])
        model_offerings = offerings_by_model.get(model["id"], [])
        services = sorted({item["inference_service_id"] for item in model_offerings})
        source_regions = sorted({route["source_region"] for item in model_offerings for route in item["routes"]})
        attrs = attributes({
            "key": f'model:{model["id"]}', "name": model_name, "kind": "model",
            "search-text": [model["id"], model_name, model.get("description", ""), model.get("vendor_id", ""), *model.get("capabilities", []), *model.get("modalities", []), model.get("licensing", ""), model.get("lifecycle", ""), *services, *source_regions],
            "vendor": model.get("vendor_id", ""), "capability": model.get("capabilities", []),
            "service": services, "source-region": source_regions,
            "modality": model.get("modalities", []), "licence": model.get("licensing", ""),
            "lifecycle": model.get("lifecycle", ""), "model-id": model["id"],
            "model-name": model_name, "model-url": model_url,
            "compare-capabilities": ", ".join(model.get("capabilities", [])),
            "compare-modalities": ", ".join(model.get("modalities", [])),
            "compare-context": model.get("context_window", ""),
            "compare-licence": model.get("licensing", ""),
            "compare-lifecycle": model.get("lifecycle", ""),
        })
        rows.append(
            '<tr class="catalogue-row catalogue-row--model" data-catalogue-row data-catalogue-item' + attrs + '><td class="catalogue-kind" data-label="Kind"><span>Model</span></td><td class="catalogue-primary" data-label="Name"><a href="'
            + escape(model_url, quote=True) + '">' + escape(model_name) + '</a><code>' + escape(model["id"]) + '</code></td><td class="catalogue-owner" data-label="Vendor">'
            + escape(model.get("vendor_id", "")) + '</td><td class="catalogue-signals" data-label="Capabilities">'
            + _tags(model.get("capabilities", []))
            + ('<span class="context-stat"><small>Context</small><strong>' + f'{model["context_window"]:,}' + "</strong></span>" if model.get("context_window") else "")
            + '</td><td class="catalogue-action" data-label="Action"><button class="button button--small" type="button" data-compare-toggle '
            + 'x-on:click="toggleComparison" aria-pressed="false" hidden>Compare</button></td></tr>'
        )
        initials = "".join(part[0].upper() for part in model.get("vendor_id", "model").split("-")[:2] if part)
        offering_summary = (
            '<span class="model-card__availability model-card__availability--approved">' + str(len(model_offerings))
            + (' approved offering' if len(model_offerings) == 1 else ' approved offerings') + '</span>' + _tags(services)
            if model_offerings else '<span class="model-card__availability">No approved offering</span>'
        )
        facts = []
        if model.get("context_window"):
            facts.append('<div><span>Context</span><strong>' + f'{model["context_window"]:,}' + '</strong></div>')
        if model.get("lifecycle"):
            facts.append('<div><span>Lifecycle</span><strong>' + escape(model["lifecycle"].title()) + '</strong></div>')
        if model.get("licensing"):
            facts.append('<div><span>Licence</span><strong>' + escape(model["licensing"].replace("-", " ").title()) + '</strong></div>')
        cards.append(
            '<article class="model-card" data-model-card data-catalogue-card data-catalogue-item' + attrs + '>'
            + '<div class="model-card__heading"><span class="model-card__mark" aria-hidden="true">' + escape(initials) + '</span><div><p>'
            + escape(model.get("vendor_id", "")) + '</p><h2><a href="' + escape(model_url, quote=True) + '">' + escape(model_name) + '</a></h2></div>'
            + '<button class="model-card__save" type="button" aria-label="Compare ' + escape(model_name, quote=True) + '" data-compare-toggle x-on:click="toggleComparison" aria-pressed="false" hidden>Compare</button></div>'
            + '<p class="model-card__description">' + escape(model.get("description", "No description has been published for this model.")) + '</p>'
            + '<div class="model-card__tags">' + _tags(model.get("capabilities", [])) + _tags(model.get("modalities", [])) + '</div>'
            + ('<div class="model-card__facts">' + "".join(facts) + '</div>' if facts else '')
            + '<div class="model-card__footer"><div>' + offering_summary + '</div><a href="' + escape(model_url, quote=True) + '">View model <span aria-hidden="true">→</span></a></div></article>'
        )
    for offering in catalogue["offerings"]:
        model = next(item for item in catalogue["models"] if item["id"] == offering["model_id"])
        attrs = attributes({"key": f'offering:{offering["inference_service_id"]}:{offering["id"]}', "name": offering["id"], "kind": "offering", "search-text": [offering["id"], offering["model_id"], model.get("vendor_id", ""), offering["inference_service_id"], *[route["source_region"] for route in offering["routes"]], *[route["model_binding"]["kind"] for route in offering["routes"]], *model.get("capabilities", []), *model.get("modalities", []), *[item["id"] for item in offering.get("condition_refs", [])]], "vendor": model.get("vendor_id", ""), "service": offering["inference_service_id"], "source-region": [route["source_region"] for route in offering["routes"]], "route-type": [route["model_binding"]["kind"] for route in offering["routes"]], "capability": model.get("capabilities", []), "modality": model.get("modalities", []), "licence": model.get("licensing", ""), "lifecycle": model.get("lifecycle", ""), "condition": [item["id"] for item in offering.get("condition_refs", [])]})
        rows.append('<tr class="catalogue-row catalogue-row--offering" data-catalogue-row data-catalogue-item' + attrs + '><td class="catalogue-kind" data-label="Kind"><span>Offering</span></td><td class="catalogue-primary" data-label="Name"><a href="' + escape(resolver.site("offering", inference_service_id=offering["inference_service_id"], offering_id=offering["id"]), quote=True) + '">' + escape(offering["id"]) + '</a><code>' + escape(offering["model_id"]) + '</code></td><td class="catalogue-owner" data-label="Service">' + escape(offering["inference_service_id"]) + '</td><td class="catalogue-signals" data-label="Source regions">' + _tags(route["source_region"] for route in offering["routes"]) + '</td><td class="catalogue-action" data-label="Action"><span class="muted">View route →</span></td></tr>')
    filter_fields = (
        ("kind", "Type", "basic"), ("vendor", "Vendor", "basic"),
        ("service", "Service", "basic"), ("source-region", "Source Region", "basic"),
        ("capability", "Capability", "basic"), ("route-type", "Route type", "advanced"),
        ("modality", "Modality", "advanced"), ("licence", "Licence", "advanced"),
        ("lifecycle", "Lifecycle", "advanced"), ("condition", "Condition", "advanced"),
    )
    controls: dict[str, list[str]] = {"basic": [], "advanced": []}
    for key, label, group in filter_fields:
        present = sorted({
            item
            for html in rows
            for match in re.findall(r' data-' + re.escape(key) + r'="([^"]*)"', html)
            for item in match.split("|") if item
        })
        if not present:
            continue
        options = "".join(
            '<button class="filter-chip" type="button" data-filter="' + key
            + '" data-filter-label="' + escape(label, quote=True) + '" data-value="'
            + escape(value, quote=True) + '" aria-pressed="false" x-on:click="toggleFilter">'
            + escape(value.replace("-", " ").title() if key == "kind" else value) + "</button>"
            for value in present
        )
        controls[group].append(
            '<fieldset class="filter-group"><legend>' + escape(label)
            + '</legend><div class="filter-options">' + options + "</div></fieldset>"
        )
    caption = "Catalogue models and offerings"
    catalogue_note = (
        '<strong>Documentation-backed examples.</strong> These 22 models demonstrate the catalogue experience. They are observations, not enterprise approvals; only an offering grants permission to consume a model.'
        if request.kind == "demo" else '<strong>Current governed catalogue.</strong> Model facts describe what exists. An approved offering explains whether and how the organisation may use it.'
    )
    enhancement = document["site"]["progressive_enhancement"]
    catalogue_content = _substitute(templates["catalogue"], {
        "basic_filter_controls": '<div class="filter-groups">' + "".join(controls["basic"]) + "</div>",
        "advanced_filter_controls": '<div class="filter-groups">' + "".join(controls["advanced"]) + "</div>",
        "search_max_length": str(enhancement["search_max_length"]),
        "comparison_max_models": str(enhancement["comparison_max_models"]),
        "view_storage_key": escape(enhancement["view_storage_key"], quote=True),
        "default_view": escape(enhancement["default_view"], quote=True),
        "model_count": str(len(catalogue["models"])),
        "catalogue_note": catalogue_note,
        "table_view_pressed": "true" if enhancement["default_view"] == "table" else "false",
        "grid_view_pressed": "true" if enhancement["default_view"] == "grid" else "false",
        "catalogue_cards": '<div class="model-grid" data-catalogue-grid>' + "".join(cards) + '</div>',
        "catalogue_rows": '<table data-catalogue-table><caption>' + caption + '</caption><thead><tr><th>Kind</th><th>Name</th><th>Owner/service</th><th>Signals</th><th>Action</th></tr></thead><tbody data-catalogue-body>' + "".join(rows) + "</tbody></table>",
    }, "catalogue")
    history_content = _substitute(templates["changes"], {"history": _history_html(history)}, "changes")
    content_path = document["paths"]["site_content"]
    process_content = _substitute(templates["process"], {"body": _markdown(_blob(root, request.source_commit, content_path + "/process.md"))}, "process")
    intake = document["repository"]["web_routes"]["mac_intake"]
    intake_links = "".join('<a class="intake-card" rel="noopener noreferrer" href="' + escape(str(document["repository"]["web_base"]).rstrip("/") + intake[key], quote=True) + '"><span>' + escape(key.title()) + '</span><small>Open governed request</small><b aria-hidden="true">→</b></a>' for key in ("add", "change", "revoke", "move", "batch"))
    web_base_url = str(document["repository"]["web_base"]).rstrip("/")
    propose_content = _substitute(templates["propose"], {
        "body": _markdown(_blob(root, request.source_commit, content_path + "/propose.md")),
        "intake_links": intake_links,
        "intake_add_url": escape(web_base_url + intake["add"], quote=True),
        "intake_change_url": escape(web_base_url + intake["change"], quote=True),
    }, "propose")
    docs_links = '<div class="reference-grid"><a href="' + escape(resolver.site("human_specification"), quote=True) + '"><strong>Human specification</strong><span>Rationale and invariants</span></a><a href="' + escape(resolver.site("machine_contract"), quote=True) + '"><strong>Machine contract</strong><span>Compact executable context</span></a><a href="' + escape(resolver.site("schemas_data") + "model.schema.json", quote=True) + '"><strong>Model schema</strong><span>Canonical model shape</span></a><a href="' + escape(resolver.site("schemas_data") + "offering.schema.json", quote=True) + '"><strong>Offering schema</strong><span>Consumption approval shape</span></a></div><div class="clone-command"><span>Clean clone</span><code>git clone ' + escape(str(document["repository"]["web_base"]) + ".git") + "</code></div>"
    docs_content = _substitute(templates["docs"], {"body": _markdown(_blob(root, request.source_commit, content_path + "/docs.md")), "documentation_links": docs_links}, "docs")
    not_found_content = _substitute(templates["404"], {"home_url": escape(resolver.site("home"), quote=True)}, "404")
    page_specs = {
        resolver.output_path("home"): ("home", "Modelo", home_content, "home"),
        resolver.output_path("catalogue"): ("catalogue", "Catalogue", catalogue_content, "catalogue"),
        resolver.output_path("changes"): ("changes", "Changes", history_content, "changes"),
        resolver.output_path("process"): ("process", "Process", process_content, "process"),
        resolver.output_path("propose"): ("propose", "Propose", propose_content, "propose"),
        resolver.output_path("docs"): ("docs", "Documentation", docs_content, "docs"),
        resolver.output_path("not_found"): ("404", "Page not found", not_found_content, "not_found"),
    }
    files = {path: _page(root, request.source_commit, templates_path, resolver, request, name, title, content, route) for path, (name, title, content, route) in page_specs.items()}
    for model in catalogue["models"]:
        model_refs = sorted({reference["id"] for reference in model.get("evidence_refs", {}).values()})
        facts = '<dl class="fact-grid"><div><dt>Identifier</dt><dd><code>' + escape(model["id"]) + "</code></dd></div><div><dt>Vendor</dt><dd>" + escape(model.get("vendor_id", "")) + "</dd></div><div><dt>Context window</dt><dd>" + (f'{model["context_window"]:,}' if model.get("context_window") else "Not stated") + "</dd></div><div><dt>Licence</dt><dd>" + escape(model.get("licensing", "Not stated")) + "</dd></div><div><dt>Capabilities</dt><dd>" + (_tags(model.get("capabilities", [])) or "Not stated") + "</dd></div><div><dt>Modalities</dt><dd>" + (_tags(model.get("modalities", [])) or "Not stated") + "</dd></div></dl>"
        links = "".join('<a class="related-card" href="' + escape(resolver.site("offering", inference_service_id=o["inference_service_id"], offering_id=o["id"]), quote=True) + '"><span><strong>' + escape(o["id"]) + '</strong><small>' + escape(o["inference_service_id"]) + '</small></span><b aria-hidden="true">→</b></a>' for o in offerings_by_model.get(model["id"], [])) or '<p class="empty-state">No approved offering is published for this model.</p>'
        content = _substitute(templates["model"], {
            "model_name": escape(model.get("name", model["id"])),
            "model_description": escape(model.get("description", "No description published.")),
            "model_facts": facts, "offering_links": '<div class="related-grid">' + links + "</div>",
            "model_status": '<span class="status-pill status-pill--' + escape(model.get("lifecycle", "unknown"), quote=True) + '">' + escape(model.get("lifecycle", "Unspecified").title()) + "</span>",
            "evidence_summary": '<p class="evidence-count"><strong>' + str(len(model_refs)) + '</strong><span>bound fact references</span></p><p>Every externally sourced field links to a content-addressed evidence projection.</p><div class="evidence-ids">' + (_tags(model_refs) or "None") + "</div>",
        }, "model")
        files[resolver.output_path("model", model_id=model["id"])] = _page(root, request.source_commit, templates_path, resolver, request, "model", model.get("name", model["id"]), content, "model", {"model_id": model["id"]})
    releases_url = str(document["repository"]["web_base"]).rstrip("/") + document["repository"]["web_routes"]["releases"]
    for offering in catalogue["offerings"]:
        if request.kind == "final":
            approval = '<section class="coordinate-card"><span class="status-pill">Approved</span><h2>Approval coordinates</h2><dl><dt>Accepted source</dt><dd><code>' + escape(request.source_commit[:12]) + '</code></dd><dt>Accepted tree</dt><dd><code>' + escape(request.source_tree[:12]) + '</code></dd><dt>Merge</dt><dd><a rel="noopener noreferrer" href="' + escape(resolver.repository_url("commit", commit_sha=request.integration_commit), quote=True) + '"><code>' + escape(request.integration_commit[:12]) + '</code></a></dd></dl><p><a rel="noopener noreferrer" href="' + escape(releases_url, quote=True) + '">Find release receipts</a></p></section>'
        elif request.kind == "validation":
            approval = '<section class="coordinate-card"><span class="status-pill status-pill--validation">Validation</span><h2>Validation coordinates</h2><dl><dt>Source</dt><dd><code>' + escape(request.source_commit[:12]) + '</code></dd><dt>Tree</dt><dd><code>' + escape(request.source_tree[:12]) + '</code></dd><dt>Integration</dt><dd><a rel="noopener noreferrer" href="' + escape(resolver.repository_url("commit", commit_sha=request.integration_commit), quote=True) + '"><code>' + escape(request.integration_commit[:12]) + '</code></a></dd></dl><p>Validation is not approval.</p></section>'
        else:
            approval = '<section class="coordinate-card"><span class="status-pill status-pill--synthetic">Synthetic</span><h2>Demo provenance</h2><dl><dt>Source</dt><dd><a rel="noopener noreferrer" href="' + escape(resolver.repository_url("commit", commit_sha=request.source_commit), quote=True) + '"><code>' + escape(request.source_commit[:12]) + '</code></a></dd><dt>Tree</dt><dd><code>' + escape(request.source_tree[:12]) + '</code></dd></dl><p>Synthetic fixture only, not approved for enterprise use.</p></section>'
        refs = sorted({reference["id"] for reference in offering.get("evidence_refs", {}).values()})
        conditions = [f'{item["id"]}@{item["version"]}' for item in offering.get("condition_refs", [])]
        content = _substitute(templates["offering"], {"offering_name": escape(offering["id"]), "approval": approval, "approval_rationale": escape(offering["approval_rationale"]), "route_table": _route_rows(offering, evidence), "pricing_table": _pricing_rows(offering), "conditions_evidence": '<dl class="fact-grid"><div><dt>Conditions</dt><dd>' + (_tags(conditions) or "None") + '</dd></div><div><dt>Evidence</dt><dd>' + (_tags(refs) or "None") + "</dd></div></dl>"}, "offering")
        path = resolver.output_path("offering", inference_service_id=offering["inference_service_id"], offering_id=offering["id"])
        files[path] = _page(root, request.source_commit, templates_path, resolver, request, "offering", offering["id"], content, "offering", {"inference_service_id": offering["inference_service_id"], "offering_id": offering["id"]})
    files[resolver.output_path("asset_css")] = _blob(root, request.source_commit, document["paths"]["site_assets"] + "/site.css")
    files[resolver.output_path("asset_catalogue_js")] = _blob(root, request.source_commit, document["paths"]["site_assets"] + "/catalogue.js")
    files[resolver.output_path("asset_proposal_js")] = _blob(root, request.source_commit, document["paths"]["site_assets"] + "/proposal.js")
    enhancement = document["site"]["progressive_enhancement"]
    alpine = _blob(root, request.source_commit, document["paths"]["site_assets"] + "/" + enhancement["runtime_source"])
    if sha256_bytes(alpine) != enhancement["runtime_sha256"]:
        raise BuildError("vendored Alpine CSP runtime digest differs from modelo.yaml")
    files[resolver.output_path("asset_alpine")] = alpine
    files[resolver.output_path("asset_third_party_notices")] = _blob(root, request.source_commit, document["paths"]["site_assets"] + "/" + enhancement["licence_source"])
    files[resolver.output_path("catalogue_data")] = catalogue_raw
    files[resolver.output_path("change_delta_data")] = delta_raw
    files[resolver.output_path("human_specification")] = _blob(root, request.source_commit, document["paths"]["human_specification"])
    files[resolver.output_path("machine_contract")] = _blob(root, request.source_commit, document["paths"]["machine_contract"])
    schemas_root = document["paths"]["schemas"]
    schema_paths = str(_git(root, "ls-tree", "-r", "--name-only", request.source_commit, "--", schemas_root)).splitlines()
    if not schema_paths or any(not path.endswith(".json") for path in schema_paths):
        raise BuildError("committed schema inventory is empty or contains undeclared file types")
    for path in schema_paths:
        relative = PurePosixPath(path).relative_to(schemas_root)
        files[(PurePosixPath(resolver.output_path("schemas_data")) / relative).as_posix()] = _blob(root, request.source_commit, path)
    return files


def _expected_paths(document: Mapping[str, Any], catalogue: Mapping[str, Any], schema_paths: Iterable[str]) -> set[str]:
    fixed = set(document["build"]["final_fixed_files"])
    schemas_root = document["paths"]["schemas"]
    schema_route = document["site"]["data_routes"]["schemas"].lstrip("/")
    fixed.update(schema_route + PurePosixPath(path).relative_to(schemas_root).as_posix() for path in schema_paths)
    def emitted(route: str, **values: str) -> str:
        for name, value in values.items():
            route = route.replace("{" + name + "}", value)
        return route.lstrip("/") + ("index.html" if route.endswith("/") else "")
    routes = document["site"]["routes"]
    fixed.update(emitted(routes["model"], model_id=item["id"]) for item in catalogue["models"])
    fixed.update(
        emitted(
            routes["offering"], inference_service_id=item["inference_service_id"],
            offering_id=item["id"],
        ) for item in catalogue["offerings"]
    )
    return fixed


def _tree_inventory(path: Path) -> dict[str, dict[str, Any]]:
    return {
        relative: _entry(data, relative)
        for relative, data in _walk_regular_tree(path).items()
    }


def build_final_site(request: FinalBuildRequest) -> FinalBuildResult:
    return _build_site(_SiteBuildRequest(
        kind="final", root=request.root, base_commit=request.base_commit,
        source_commit=request.source_commit, source_tree=request.source_tree,
        integration_commit=request.merge_commit, integration_tree=request.merge_tree,
        as_of=request.as_of, source_date_epoch=request.source_date_epoch,
        profile=request.profile, base_url=request.base_url, base_path=request.base_path,
        output=request.output, mac_metadata=request.mac_metadata,
        publication_capability=request.publication_capability,
    ))


def build_validation_site(request: ValidationBuildRequest) -> FinalBuildResult:
    return _build_site(_SiteBuildRequest(
        kind="validation", root=request.root, base_commit=request.base_commit,
        source_commit=request.source_commit, source_tree=request.source_tree,
        integration_commit=request.validation_commit,
        integration_tree=request.validation_tree, as_of=request.as_of,
        source_date_epoch=request.source_date_epoch, profile=request.profile,
        base_url=request.base_url, base_path=request.base_path, output=request.output,
        mac_metadata=request.mac_metadata,
        publication_capability=request.publication_capability,
    ))


def build_demo_site(request: DemoBuildRequest) -> FinalBuildResult:
    return _build_site(_SiteBuildRequest(
        kind="demo", root=request.root, base_commit=request.source_commit,
        source_commit=request.source_commit, source_tree=request.source_tree,
        integration_commit=request.source_commit, integration_tree=request.source_tree,
        as_of=request.as_of, source_date_epoch=request.source_date_epoch,
        profile="synthetic", base_url=request.base_url, base_path=request.base_path,
        output=request.output, mac_metadata=None,
        publication_capability="public-pages",
    ))


def _build_site(request: _SiteBuildRequest) -> FinalBuildResult:
    root = request.root.resolve()
    load_config(root)
    if request.kind not in {"demo", "validation", "final"}:
        raise BuildError("unknown site publication kind")
    if request.profile not in {"synthetic", "private"}:
        raise BuildError("unknown publication profile")
    allowed_capabilities = {"public-pages", "restricted-artifact", "access-controlled-pages"}
    if request.publication_capability not in allowed_capabilities:
        raise BuildError("unknown publication capability")
    if request.profile == "private" and request.publication_capability not in {
        "restricted-artifact", "access-controlled-pages"
    }:
        raise BuildError("private publication requires an explicit restricted capability")
    if not request.base_url:
        raise BuildError(f"{request.kind} build requires an explicit canonical HTTPS base URL")
    base = _canonical_commit(root, request.base_commit, "base commit")
    source = _canonical_commit(root, request.source_commit, "source commit")
    integration = _canonical_commit(root, request.integration_commit, f"{request.kind} integration commit")
    layout = with_snapshot(root, source, lambda snapshot: _layout(snapshot))
    document = _committed_yaml_config(root, source, "modelo.yaml")
    configured_output = {
        "demo": layout.pages_root,
        "validation": layout.validation_root,
        "final": layout.final_root,
    }[request.kind]
    if request.output != configured_output.as_posix():
        output_key = "pages_root" if request.kind == "demo" else f"{request.kind}_root"
        raise BuildError(f"{request.kind} output must equal configured {output_key}")
    if str(_git(root, "rev-parse", f"{source}^{{tree}}")).strip() != request.source_tree:
        raise BuildError("source tree does not match source commit")
    actual_integration_tree = str(_git(root, "rev-parse", f"{integration}^{{tree}}")).strip()
    if actual_integration_tree != request.integration_tree or request.integration_tree != request.source_tree:
        coordinate = "merge tree" if request.kind == "final" else "validation tree"
        raise BuildError(f"{coordinate} must equal both the explicit integration tree and source tree")
    if request.kind == "validation":
        parents = str(_git(root, "rev-list", "--parents", "-n", "1", integration)).split()
        if parents != [integration, base, source]:
            raise BuildError("validation commit must have exact base and source parents in that order")
    if str(_git(root, "rev-parse", "HEAD")).strip() != integration:
        raise BuildError(f"checked-out HEAD differs from explicit {request.kind} integration commit")
    if str(_git(root, "status", "--porcelain=v1", "--untracked-files=all")).strip():
        raise BuildError("working tree is dirty")
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, integration], cwd=root).returncode:
        raise BuildError(f"base commit is not an ancestor of {request.kind} integration commit")
    author_epoch = int(str(_git(root, "show", "-s", "--format=%at", source)).strip())
    if request.source_date_epoch != author_epoch:
        raise BuildError("source date epoch differs from accepted source commit author time")
    if request.kind == "demo":
        try:
            configured_as_of = date.fromisoformat(document["publication"]["profiles"]["synthetic"]["as_of"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BuildError("configured synthetic fixture snapshot date is invalid") from exc
        if request.as_of != configured_as_of:
            raise BuildError("demo as-of must equal configured synthetic fixture snapshot date")
        catalogue = with_snapshot(
            root, source,
            lambda snapshot: _projection_from_snapshot(
                snapshot, request.profile, source, request.source_tree,
                request.as_of, layout,
            ),
        )
        catalogue_raw = canonical_bytes(catalogue)
        delta_raw = canonical_bytes([])
    else:
        if request.mac_metadata is None:
            raise BuildError(f"{request.kind} build requires validated MAC metadata")
        catalogue_raw, delta_raw, catalogue = rebuild_candidate_inputs(BuildRequest(
            root=root, kind="candidate", base_commit=base, source_commit=source,
            source_tree=request.source_tree, as_of=request.as_of,
            source_date_epoch=request.source_date_epoch, mac_metadata=request.mac_metadata,
            profile=request.profile, base_url=None, base_path=request.base_path,
            output=layout.candidate_root.as_posix(),
        ))
    files = _site_files(root, request, catalogue_raw, delta_raw, catalogue, document)
    schemas_root = document["paths"]["schemas"]
    schema_paths = str(_git(root, "ls-tree", "-r", "--name-only", source, "--", schemas_root)).splitlines()
    expected = _expected_paths(document, catalogue, schema_paths)
    if set(files) != expected:
        missing = sorted(expected - set(files)); extra = sorted(set(files) - expected)
        raise BuildError(f"final site inventory mismatch; missing={missing!r}; extra={extra!r}")
    if request.profile == "synthetic" and any(_PRIVATE_CANARY in data for data in files.values()):
        raise BuildError("synthetic publication contains a private leakage canary")
    entries = {path: _entry(data, path) for path, data in files.items()}
    manifest: dict[str, Any] = {
        "contract_version": "0.1.0", "kind": request.kind, "base_commit": base,
        "source_commit": source, "source_tree": request.source_tree,
        "as_of": request.as_of.isoformat(), "source_date_epoch": request.source_date_epoch,
        "profile": request.profile, "base_url": request.base_url, "base_path": request.base_path,
        "promotion_durability": "fsync-durable",
        "catalogue_path": layout.catalogue_path.as_posix(),
        "change_delta_path": layout.change_delta_path.as_posix(),
        "manifest_path": layout.manifest_path.as_posix(),
        "digest_algorithm": "sha256", "publication_digest": publication_digest(files), "files": entries,
    }
    if request.kind == "validation":
        manifest.update({
            "validation_commit": integration,
            "validation_tree": request.integration_tree,
        })
    elif request.kind == "final":
        manifest.update({"merge_commit": integration, "merge_tree": request.integration_tree})
    findings = with_snapshot(
        root, source,
        lambda snapshot: SchemaSet(snapshot, layout.schemas).validate(
            layout.build_manifest_schema, manifest, layout.manifest_path.as_posix()
        ),
    )
    if findings:
        raise BuildError(f"{request.kind} manifest violates schema: {findings[0].message}")
    manifest_raw = canonical_bytes(manifest)
    output = root.joinpath(*configured_output.parts)
    _publish(root, output, files, manifest, layout)
    expected_physical = {
        (layout.publication_subdir / path).as_posix(): entry
        for path, entry in entries.items()
    }
    expected_physical[(layout.publication_subdir / layout.manifest_path).as_posix()] = _entry(
        manifest_raw, layout.manifest_path.as_posix()
    )
    if _tree_inventory(output) != expected_physical:
        raise BuildError(f"{request.kind} publication verification failed after promotion")
    return FinalBuildResult(output, manifest_raw, manifest["publication_digest"], len(files))


def _committed_yaml_config(root: Path, commit: str, path: str) -> dict[str, Any]:
    """Load configuration exclusively from one immutable Git blob."""
    from modelo.loader import load_yaml_mapping
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="modelo-config-") as raw:
        temporary = Path(raw)
        target = temporary / "config.yaml"
        target.write_bytes(_blob(root, commit, path))
        return dict(load_yaml_mapping(temporary, PurePosixPath("config.yaml")))


def recover_final_site(root: Path) -> Any:
    """Explicitly recover the journal-selected candidate or final publication."""
    return recover_candidate(root.resolve())
