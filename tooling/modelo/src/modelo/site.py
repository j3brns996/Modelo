"""Deterministic final static-site projection and durable publisher."""

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
    BuildError, BuildRequest, _layout, _publish, _safe_url,
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
    def __init__(self, base_url: str, base_path: str, site_routes: Mapping[str, str], repository: Mapping[str, Any]) -> None:
        _safe_url(base_url, base_path)
        parsed = urlsplit(base_url)
        if parsed.path != base_path:
            raise BuildError("final base URL path must equal normalised base path")
        self.base_url = base_url
        self.base_path = base_path
        self.site_routes = dict(site_routes)
        self.repository = repository
        self._validate_routes()

    def _validate_routes(self) -> None:
        expected_directories = {"home", "catalogue", "model", "offering", "changes", "process", "propose", "docs"}
        expected_files = {"not_found", "asset_css", "asset_js", "catalogue_data", "change_delta_data", "manifest_data", "schemas_data", "human_specification", "machine_contract"}
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


def _navigation(resolver: _Resolver) -> str:
    labels = (("catalogue", "Catalogue"), ("changes", "Changes"), ("process", "Process"), ("propose", "Propose"), ("docs", "Docs"))
    return "".join('<a href="' + escape(resolver.site(key), quote=True) + '">' + label + "</a>" for key, label in labels)


def _page(root: Path, source: str, templates_path: str, resolver: _Resolver, request: FinalBuildRequest, name: str, title: str, content: str, route: str, route_values: Mapping[str, str] | None = None) -> bytes:
    base = _template(root, source, templates_path, "base")
    values = {
        "canonical_url": escape(resolver.canonical(route, **dict(route_values or {})), quote=True),
        "asset_css_url": escape(resolver.site("asset_css"), quote=True),
        "asset_js_url": escape(resolver.site("asset_js"), quote=True),
        "title": escape(title), "navigation": _navigation(resolver), "content": content,
        "home_url": escape(resolver.site("home"), quote=True),
        "source_commit_url": escape(resolver.repository_url("commit", commit_sha=request.source_commit), quote=True),
        "merge_commit_url": escape(resolver.repository_url("commit", commit_sha=request.merge_commit), quote=True),
        "source_commit_short": escape(request.source_commit[:12]), "as_of": request.as_of.isoformat(),
        "merge_commit_short": escape(request.merge_commit[:12]),
    }
    return (_substitute(base, values, name) + "\n").encode("utf-8")


def _site_files(root: Path, request: FinalBuildRequest, catalogue_raw: bytes, delta_raw: bytes, catalogue: Mapping[str, Any], document: Mapping[str, Any]) -> dict[str, bytes]:
    all_routes = dict(document["site"]["routes"])
    all_routes.update({key + "_data": value for key, value in document["site"]["data_routes"].items()})
    all_routes.update(document["site"]["asset_routes"])
    all_routes.update(document["site"]["document_routes"])
    resolver = _Resolver(request.base_url, request.base_path, all_routes, document["repository"])
    templates_path = document["paths"]["site_templates"]
    templates = {name: _template(root, request.source_commit, templates_path, name) for name in ("home", "catalogue", "model", "offering", "changes", "process", "propose", "docs", "404")}
    evidence = {item["id"]: item for item in catalogue["evidence"]}
    offerings_by_model: dict[str, list[Mapping[str, Any]]] = {}
    for item in catalogue["offerings"]:
        offerings_by_model.setdefault(item["model_id"], []).append(item)
    history = _history(root, request.merge_commit, document["publication"]["profiles"][request.profile]["source"], resolver)
    summary = '<div class="cards"><section class="card"><strong>' + str(len(catalogue["models"])) + '</strong><br>Models</section><section class="card"><strong>' + str(len(catalogue["offerings"])) + "</strong><br>Offerings</section></div>"
    home_content = _substitute(templates["home"], {"summary": summary, "recent_changes": _history_html(history[:3])}, "home")
    rows = []
    def attributes(values: Mapping[str, Iterable[Any] | Any]) -> str:
        parts = []
        for key, value in values.items():
            items = value if isinstance(value, (list, tuple, set)) else [value]
            parts.append(' data-' + key + '="' + escape("|".join(str(item) for item in items), quote=True) + '"')
        return "".join(parts)
    for model in catalogue["models"]:
        attrs = attributes({"kind": "model", "vendor": model.get("vendor_id", ""), "capability": model.get("capabilities", []), "modality": model.get("modalities", []), "licence": model.get("licensing", ""), "lifecycle": model.get("lifecycle", "")})
        rows.append('<tr data-catalogue-row' + attrs + '><td>Model</td><td><a href="' + escape(resolver.site("model", model_id=model["id"]), quote=True) + '">' + escape(model.get("name", model["id"])) + "</a></td><td>" + escape(model.get("vendor_id", "")) + "</td><td>" + _tags(model.get("capabilities", [])) + "</td></tr>")
    for offering in catalogue["offerings"]:
        model = next(item for item in catalogue["models"] if item["id"] == offering["model_id"])
        attrs = attributes({"kind": "offering", "vendor": model.get("vendor_id", ""), "service": offering["inference_service_id"], "source-region": [route["source_region"] for route in offering["routes"]], "route-type": [route["model_binding"]["kind"] for route in offering["routes"]], "capability": model.get("capabilities", []), "modality": model.get("modalities", []), "licence": model.get("licensing", ""), "lifecycle": model.get("lifecycle", ""), "condition": [item["id"] for item in offering.get("condition_refs", [])]})
        rows.append('<tr data-catalogue-row' + attrs + '><td>Offering</td><td><a href="' + escape(resolver.site("offering", inference_service_id=offering["inference_service_id"], offering_id=offering["id"]), quote=True) + '">' + escape(offering["id"]) + "</a></td><td>" + escape(offering["inference_service_id"]) + "</td><td>" + _tags(route["source_region"] for route in offering["routes"]) + "</td></tr>")
    filter_fields = (("vendor", "Vendor"), ("service", "Service"), ("source-region", "Source Region"), ("route-type", "Route type"), ("capability", "Capability"), ("modality", "Modality"), ("licence", "Licence"), ("lifecycle", "Lifecycle"), ("condition", "Condition"))
    controls = []
    for key, label in filter_fields:
        present = sorted({
            item
            for html in rows
            for match in re.findall(r' data-' + re.escape(key) + r'="([^"]*)"', html)
            for item in match.split("|") if item
        })
        controls.append('<label for="filter-' + key + '">' + label + '</label><select id="filter-' + key + '" data-filter="' + key + '"><option value="">All</option>' + "".join('<option value="' + escape(value, quote=True) + '">' + escape(value) + '</option>' for value in present) + '</select>')
    catalogue_content = _substitute(templates["catalogue"], {"filter_controls": "".join(controls), "catalogue_rows": '<table><caption>Approved models and offerings</caption><thead><tr><th>Kind</th><th>Name</th><th>Owner/service</th><th>Capabilities/Source Regions</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"}, "catalogue")
    history_content = _substitute(templates["changes"], {"history": _history_html(history)}, "changes")
    content_path = document["paths"]["site_content"]
    process_content = _substitute(templates["process"], {"body": _markdown(_blob(root, request.source_commit, content_path + "/process.md"))}, "process")
    intake = document["repository"]["web_routes"]["mac_intake"]
    intake_links = "".join('<li><a rel="noopener noreferrer" href="' + escape(str(document["repository"]["web_base"]).rstrip("/") + intake[key], quote=True) + '">' + escape(key.title()) + " request</a></li>" for key in ("add", "change", "revoke", "move", "batch"))
    propose_content = _substitute(templates["propose"], {"body": _markdown(_blob(root, request.source_commit, content_path + "/propose.md")), "intake_links": intake_links}, "propose")
    docs_links = '<ul><li><a href="' + escape(resolver.site("human_specification"), quote=True) + '">Human specification</a></li><li><a href="' + escape(resolver.site("machine_contract"), quote=True) + '">Machine contract</a></li><li><a href="' + escape(resolver.site("schemas_data") + "model.schema.json", quote=True) + '">Model schema</a></li><li><a href="' + escape(resolver.site("schemas_data") + "offering.schema.json", quote=True) + '">Offering schema</a></li></ul><pre><code>git clone ' + escape(str(document["repository"]["web_base"]) + ".git") + "</code></pre>"
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
        facts = '<dl><dt>Identifier</dt><dd><code>' + escape(model["id"]) + "</code></dd><dt>Vendor</dt><dd>" + escape(model.get("vendor_id", "")) + "</dd><dt>Capabilities</dt><dd>" + _tags(model.get("capabilities", [])) + "</dd><dt>Modalities</dt><dd>" + _tags(model.get("modalities", [])) + "</dd><dt>Intrinsic evidence</dt><dd>" + (_tags(model_refs) or "None") + "</dd></dl>"
        links = "".join('<li><a href="' + escape(resolver.site("offering", inference_service_id=o["inference_service_id"], offering_id=o["id"]), quote=True) + '">' + escape(o["id"]) + "</a></li>" for o in offerings_by_model.get(model["id"], [])) or "<li>None</li>"
        content = _substitute(templates["model"], {"model_name": escape(model.get("name", model["id"])), "model_description": escape(model.get("description", "No description published.")), "model_facts": facts, "offering_links": "<ul>" + links + "</ul>"}, "model")
        files[resolver.output_path("model", model_id=model["id"])] = _page(root, request.source_commit, templates_path, resolver, request, "model", model.get("name", model["id"]), content, "model", {"model_id": model["id"]})
    releases_url = str(document["repository"]["web_base"]).rstrip("/") + document["repository"]["web_routes"]["releases"]
    for offering in catalogue["offerings"]:
        approval = '<section class="card"><h2>Approval coordinates</h2><dl><dt>Accepted source</dt><dd><code>' + escape(request.source_commit) + '</code></dd><dt>Accepted tree</dt><dd><code>' + escape(request.source_tree) + '</code></dd><dt>Merge commit</dt><dd><a rel="noopener noreferrer" href="' + escape(resolver.repository_url("commit", commit_sha=request.merge_commit), quote=True) + '"><code>' + escape(request.merge_commit) + '</code></a></dd></dl><p><a rel="noopener noreferrer" href="' + escape(releases_url, quote=True) + '">Discover protected releases and detached receipts</a>. No approval receipt is embedded in this site.</p></section>'
        refs = sorted({reference["id"] for reference in offering.get("evidence_refs", {}).values()})
        conditions = [f'{item["id"]}@{item["version"]}' for item in offering.get("condition_refs", [])]
        content = _substitute(templates["offering"], {"offering_name": escape(offering["id"]), "approval": approval, "route_table": _route_rows(offering, evidence), "pricing_table": _pricing_rows(offering), "conditions_evidence": "<p>Conditions: " + (_tags(conditions) or "None") + "</p><p>Evidence: " + (_tags(refs) or "None") + "</p>"}, "offering")
        path = resolver.output_path("offering", inference_service_id=offering["inference_service_id"], offering_id=offering["id"])
        files[path] = _page(root, request.source_commit, templates_path, resolver, request, "offering", offering["id"], content, "offering", {"inference_service_id": offering["inference_service_id"], "offering_id": offering["id"]})
    files[resolver.output_path("asset_css")] = _blob(root, request.source_commit, document["paths"]["site_assets"] + "/site.css")
    files[resolver.output_path("asset_js")] = _blob(root, request.source_commit, document["paths"]["site_assets"] + "/catalogue.js")
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
    root = request.root.resolve()
    load_config(root)
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
        raise BuildError("final build requires an explicit canonical HTTPS base URL")
    base = _canonical_commit(root, request.base_commit, "base commit")
    source = _canonical_commit(root, request.source_commit, "source commit")
    merge = _canonical_commit(root, request.merge_commit, "merge commit")
    layout = with_snapshot(root, source, lambda snapshot: _layout(snapshot))
    if request.output != layout.final_root.as_posix():
        raise BuildError("final output must equal configured final_root")
    if str(_git(root, "rev-parse", f"{source}^{{tree}}")).strip() != request.source_tree:
        raise BuildError("source tree does not match source commit")
    actual_merge_tree = str(_git(root, "rev-parse", f"{merge}^{{tree}}")).strip()
    if actual_merge_tree != request.merge_tree or request.merge_tree != request.source_tree:
        raise BuildError("merge tree must equal both the explicit merge tree and accepted source tree")
    if str(_git(root, "rev-parse", "HEAD")).strip() != merge:
        raise BuildError("checked-out HEAD differs from explicit merge commit")
    if str(_git(root, "status", "--porcelain=v1", "--untracked-files=all")).strip():
        raise BuildError("working tree is dirty")
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, merge], cwd=root).returncode:
        raise BuildError("base commit is not an ancestor of merge commit")
    author_epoch = int(str(_git(root, "show", "-s", "--format=%at", source)).strip())
    if request.source_date_epoch != author_epoch:
        raise BuildError("source date epoch differs from accepted source commit author time")
    catalogue_raw, delta_raw, catalogue = rebuild_candidate_inputs(BuildRequest(
        root=root, kind="candidate", base_commit=base, source_commit=source,
        source_tree=request.source_tree, as_of=request.as_of,
        source_date_epoch=request.source_date_epoch, mac_metadata=request.mac_metadata,
        profile=request.profile, base_url=None, base_path=request.base_path,
        output=layout.candidate_root.as_posix(),
    ))
    document = _committed_yaml_config(root, source, "modelo.yaml")
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
    manifest = {
        "contract_version": "0.1.0", "kind": "final", "base_commit": base,
        "source_commit": source, "source_tree": request.source_tree,
        "merge_commit": merge, "merge_tree": request.merge_tree,
        "as_of": request.as_of.isoformat(), "source_date_epoch": request.source_date_epoch,
        "profile": request.profile, "base_url": request.base_url, "base_path": request.base_path,
        "promotion_durability": "fsync-durable",
        "catalogue_path": layout.catalogue_path.as_posix(),
        "change_delta_path": layout.change_delta_path.as_posix(),
        "manifest_path": layout.manifest_path.as_posix(),
        "digest_algorithm": "sha256", "publication_digest": publication_digest(files), "files": entries,
    }
    findings = with_snapshot(
        root, source,
        lambda snapshot: SchemaSet(snapshot, layout.schemas).validate(
            layout.build_manifest_schema, manifest, layout.manifest_path.as_posix()
        ),
    )
    if findings:
        raise BuildError(f"final manifest violates schema: {findings[0].message}")
    manifest_raw = canonical_bytes(manifest)
    output = root.joinpath(*layout.final_root.parts)
    _publish(root, output, files, manifest, layout)
    expected_physical = {
        (layout.publication_subdir / path).as_posix(): entry
        for path, entry in entries.items()
    }
    expected_physical[(layout.publication_subdir / layout.manifest_path).as_posix()] = _entry(
        manifest_raw, layout.manifest_path.as_posix()
    )
    if _tree_inventory(output) != expected_physical:
        raise BuildError("final publication verification failed after promotion")
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
