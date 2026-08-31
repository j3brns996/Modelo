from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urljoin
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from modelo.evidence import canonical_json


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
CASES = ROOT / "tests/fixtures/schema/cases.json"
MAC_FIXTURES = ROOT / "tests/fixtures/mac"

REQUIRED_FIXED_PUBLICATION_FILES = {
    "404.html",
    "assets/catalogue.js",
    "assets/site.css",
    "assets/vendor/alpine-csp-3.16.3.min.js",
    "assets/vendor/THIRD-PARTY-NOTICES.md",
    "catalogue/index.html",
    "changes/index.html",
    "data/catalogue.json",
    "data/change-delta.json",
    "docs/index.html",
    "docs/SPEC.md",
    "docs/contract.yaml",
    "index.html",
    "process/index.html",
    "propose/index.html",
}
REQUIRED_PUBLICATION_FILES = REQUIRED_FIXED_PUBLICATION_FILES | {
    *(f"schemas/{path.relative_to(SCHEMAS).as_posix()}" for path in SCHEMAS.rglob("*.schema.json")),
}


def _schemas() -> tuple[dict[str, dict[str, Any]], Registry[Any]]:
    documents: dict[str, dict[str, Any]] = {}
    registry: Registry[Any] = Registry()
    for path in sorted(SCHEMAS.rglob("*.schema.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(document)
        documents[path.relative_to(SCHEMAS).as_posix()] = document
        registry = registry.with_resource(document["$id"], Resource.from_contents(document))
    return documents, registry


def _mutate(instance: Any, mutation: dict[str, Any]) -> Any:
    changed = copy.deepcopy(instance)
    parent = changed
    for component in mutation["path"][:-1]:
        parent = parent[component]
    key = mutation["path"][-1]
    if mutation["op"] == "remove":
        del parent[key]
    elif mutation["op"] == "set":
        parent[key] = mutation["value"]
    elif mutation["op"] == "rename":
        parent[mutation["value"]] = parent.pop(key)
    elif mutation["op"] == "repeat":
        parent[key] = mutation["value"] * mutation["count"]
    elif mutation["op"] == "duplicate_first":
        parent[key].append(copy.deepcopy(parent[key][0]))
    else:
        raise AssertionError(f"unknown fixture mutation {mutation['op']!r}")
    return changed


def _flatten_errors(errors: list[Any]) -> list[Any]:
    flattened: list[Any] = []
    pending = list(errors)
    while pending:
        error = pending.pop()
        flattened.append(error)
        pending.extend(error.context)
    return flattened


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _canonical_receipt_bytes(value: dict[str, Any]) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _mac_metadata_errors(
    envelope: dict[str, Any],
    flags: dict[str, str],
    computed_delta: list[dict[str, Any]],
    *,
    base_registries: dict[str, dict[str, Any]] | None = None,
    head_registries: dict[str, dict[str, Any]] | None = None,
    head_offering_paths: set[str] | None = None,
) -> set[str]:
    errors: set[str] = set()
    repository = envelope["repository"]
    issue = envelope["issue"]
    issue_prefix = (
        f"https://{repository['host']}/{repository['namespace']}/{repository['name']}/issues/"
        if repository["provider"] == "github"
        else f"https://{repository['host']}/{repository['namespace']}/{repository['name']}/-/issues/"
    )
    if issue["url"] != issue_prefix + issue["reference"]:
        errors.add("issue-repository")
    for name, flag, field in (
        ("base", "base_commit", "base_sha"),
        ("head", "source_commit", "head_sha"),
        ("head-tree", "source_tree", "head_tree_sha"),
    ):
        if flags[flag] != envelope[field]:
            errors.add(name)
    digest = "sha256:" + hashlib.sha256(_canonical_receipt_bytes(envelope["payload"])).hexdigest()
    if digest != envelope["payload_digest"]:
        errors.add("payload-digest")
    expected_delta = _sort_delta(envelope["expected_change_delta"])
    if expected_delta != _sort_delta(computed_delta):
        errors.add("computed-delta")

    payload = envelope["payload"]
    subjects = payload["subjects"]
    operation = payload["item_operation"] if payload["operation"] == "batch" else payload["operation"]
    registry_paths = {
        "vendor": "catalogue/governance/vendors.yaml",
        "inference-service": "catalogue/governance/inference-services.yaml",
    }

    def path_for(subject: dict[str, str]) -> str:
        kind, identity = subject["kind"], subject["identity"]
        if kind == "model":
            return f"catalogue/models/{identity}.yaml"
        if kind == "offering":
            return f"*/{identity}.yaml"
        if kind == "evidence":
            return f"catalogue/evidence/{identity}.yaml"
        if kind == "vendor":
            return "catalogue/governance/vendors.yaml"
        if kind == "inference-service":
            return "catalogue/governance/inference-services.yaml"
        return f"catalogue/policies/conditions/{identity}.yaml"

    def path_matches(subject: dict[str, str], path: str) -> bool:
        expected = path_for(subject)
        return (
            path.startswith("catalogue/offerings/") and path.endswith(expected[1:])
            if expected.startswith("*/")
            else path == expected
        )

    if payload["operation"] == "move":
        source = next((item for item in subjects if item.get("role") == "source"), None)
        destination = next((item for item in subjects if item.get("role") == "destination"), None)
        if source is None or destination is None or len(expected_delta) != 1:
            errors.add("operation-subjects")
        else:
            delta = expected_delta[0]
            if (
                delta["operation"] != "move"
                or not path_matches(source, delta["source"]["path"])
                or not path_matches(destination, delta["destination"]["path"])
            ):
                errors.add("operation-subjects")
            if delta["source"].get("replacement") != delta["destination"]["path"]:
                errors.add("move-replacement")
    else:
        registry_subjects = [item for item in subjects if item["kind"] in registry_paths]
        ordinary_subjects = [item for item in subjects if item["kind"] not in registry_paths]
        registry_delta = [
            item for item in expected_delta
            if item.get("path") in set(registry_paths.values())
        ]
        ordinary_delta = [item for item in expected_delta if item not in registry_delta]
        if registry_subjects or registry_delta:
            if base_registries is None or head_registries is None:
                errors.add("registry-context")
            else:
                for kind, registry_path in registry_paths.items():
                    claimed = {
                        item["identity"] for item in registry_subjects if item["kind"] == kind
                    }
                    base_map = base_registries.get(kind, {})
                    head_map = head_registries.get(kind, {})
                    transitions: dict[str, str] = {}
                    for key in set(base_map) | set(head_map):
                        if key not in base_map:
                            transitions[key] = "add"
                        elif key not in head_map:
                            transitions[key] = "delete"
                        elif canonical_json(base_map[key]) != canonical_json(head_map[key]):
                            transitions[key] = "change"
                    changed = set(transitions)
                    if claimed != changed:
                        errors.add("registry-subjects")
                    if "delete" in transitions.values():
                        errors.add("registry-deletion")
                    if any(value != operation for value in transitions.values()):
                        errors.add("registry-operation")
                    matching_delta = [item for item in registry_delta if item["path"] == registry_path]
                    if bool(changed) != (len(matching_delta) == 1):
                        errors.add("registry-subjects")
        if len(ordinary_delta) != len(ordinary_subjects):
            errors.add("operation-subjects")
        else:
            unmatched = list(ordinary_delta)
            for subject in ordinary_subjects:
                match = next(
                    (item for item in unmatched if item["operation"] == operation and path_matches(subject, item["path"])),
                    None,
                )
                if match is None:
                    errors.add("operation-subjects")
                    break
                unmatched.remove(match)
            if unmatched:
                errors.add("operation-subjects")
        if operation == "revoke":
            for delta in ordinary_delta:
                replacement = delta.get("replacement")
                if replacement is not None and (
                    replacement == delta["path"]
                    or head_offering_paths is None
                    or replacement not in head_offering_paths
                ):
                    errors.add("revoke-replacement")
    return errors


def _read_mac_metadata_contract(path: Path, after_read: Any = None) -> dict[str, Any]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("CI cannot enforce non-symlink metadata input")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not hasattr(before, "st_mtime_ns") or not hasattr(before, "st_ctime_ns"):
            raise RuntimeError("CI cannot enforce nanosecond metadata identity")
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("metadata input must be a regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, 262145 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > 262144:
                raise ValueError("metadata input exceeds 262144 bytes")
        if after_read is not None:
            after_read()
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise ValueError("metadata input changed while read")
    finally:
        os.close(descriptor)

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_number(value: str) -> Any:
        raise ValueError(f"non-integer JSON number {value!r}")

    document = json.loads(
        b"".join(chunks).decode("utf-8", errors="strict"),
        object_pairs_hook=pairs,
        parse_float=reject_number,
        parse_constant=reject_number,
    )
    if not isinstance(document, dict):
        raise ValueError("metadata root must be a JSON object")
    return document


def _canonical_site_url_matches(url: str, base_path: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname == parsed.hostname.lower()
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
        and parsed.query == ""
        and parsed.fragment == ""
        and "%" not in parsed.path
        and all(segment not in {".", ".."} for segment in parsed.path.split("/"))
        and parsed.path == base_path
        and url.endswith("/")
    )


def _source_epoch_errors(explicit_epoch: int, source_author_epoch: int) -> set[str]:
    return set() if explicit_epoch == source_author_epoch else {"source-author-epoch"}


def _output_path_errors(
    kind: str,
    output: str,
    candidate_root: str,
    final_root: str,
    *,
    is_symlink: bool = False,
    input_roots: tuple[str, ...] = ("catalogue", "schemas", "tests", "site", "tooling"),
) -> set[str]:
    errors: set[str] = set()
    expected = candidate_root if kind == "candidate" else final_root
    path = PurePosixPath(output)
    if output != expected:
        errors.add("output-root")
    if path.is_absolute() or ".." in path.parts or is_symlink:
        errors.add("output-safety")
    if any(path == PurePosixPath(root) or PurePosixPath(root) in path.parents for root in input_roots):
        errors.add("output-inside-input")
    return errors


def _sort_delta(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {"add": 0, "change": 1, "revoke": 2, "move": 3}

    def key(item: dict[str, Any]) -> tuple[Any, ...]:
        if item["operation"] == "move":
            primary = item["source"]["path"]
            destination = item["destination"]["path"]
            before = item["source"].get("before", "")
            after = item["destination"].get("after", "")
        else:
            primary = item["path"]
            destination = ""
            before = item.get("before", "")
            after = item.get("after", "")
        return (
            rank[item["operation"]],
            primary.encode(),
            destination.encode(),
            before,
            after,
            canonical_json(item).encode("utf-8"),
        )

    return sorted(value, key=key)


def _agent_paths_allowed(paths: list[str]) -> bool:
    prefixes = ("catalogue/models/", "catalogue/offerings/", "catalogue/evidence/")
    return bool(paths) and all(path.startswith(prefixes) for path in paths)


def _expected_manifest_files(projection: dict[str, Any]) -> set[str]:
    detail = {
        *(f"models/{model['id']}/index.html" for model in projection["models"]),
        *(
            f"offerings/{offering['inference_service_id']}/{offering['id']}/index.html"
            for offering in projection["offerings"]
        ),
    }
    return REQUIRED_PUBLICATION_FILES | detail


def _manifest_completeness_errors(
    files: dict[str, Any], projection: dict[str, Any]
) -> dict[str, set[str]]:
    expected = _expected_manifest_files(projection)
    actual = set(files)
    return {"missing": expected - actual, "unexpected": actual - expected}


def _trusted_context(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": check["repository"],
        "current_base_sha": check["base_sha"],
        "current_head_sha": check["head_sha"],
        "current_head_tree_sha": check["head_tree_sha"],
        "as_of": check["as_of"],
        "source_date_epoch": check["source_date_epoch"],
        "profile": check["profile"],
        "base_url": check["base_url"],
        "base_path": check["base_path"],
        "mac_issue": check["mac_issue"],
        "mac_payload_digest": check["mac_payload_digest"],
        "change_delta": check["change_delta"],
        "artifacts": check["artifacts"],
        "tool_digest": check["tool_digest"],
        "lock_digest": check["lock_digest"],
        "actors_registry_digest": check["actors_registry_digest"],
        "ci": check["ci"],
    }


def _trusted_check_correlation_errors(check: dict[str, Any], trusted: dict[str, Any]) -> set[str]:
    errors: set[str] = set()
    internal = {
        "check-ci-head": (check["ci"]["head_sha"], check["head_sha"]),
        "check-ci-provider": (check["ci"]["provider"], check["repository"]["provider"]),
        "check-ci-name": (check["ci"]["check"], "modelo/check"),
        "check-ci-result": (check["ci"]["result"], "success"),
    }
    errors.update(name for name, values in internal.items() if values[0] != values[1])
    correlations = {
        "trusted-repository": (check["repository"], trusted["repository"]),
        "trusted-base": (check["base_sha"], trusted["current_base_sha"]),
        "trusted-head": (check["head_sha"], trusted["current_head_sha"]),
        "trusted-head-tree": (check["head_tree_sha"], trusted["current_head_tree_sha"]),
        "trusted-as-of": (check["as_of"], trusted["as_of"]),
        "trusted-epoch": (check["source_date_epoch"], trusted["source_date_epoch"]),
        "trusted-profile": (check["profile"], trusted["profile"]),
        "trusted-base-url": (check["base_url"], trusted["base_url"]),
        "trusted-base-path": (check["base_path"], trusted["base_path"]),
        "trusted-mac-issue": (check["mac_issue"], trusted["mac_issue"]),
        "trusted-mac-payload": (check["mac_payload_digest"], trusted["mac_payload_digest"]),
        "trusted-delta": (check["change_delta"], trusted["change_delta"]),
        "trusted-artifacts": (check["artifacts"], trusted["artifacts"]),
        "trusted-tool": (check["tool_digest"], trusted["tool_digest"]),
        "trusted-lock": (check["lock_digest"], trusted["lock_digest"]),
        "trusted-actors": (check["actors_registry_digest"], trusted["actors_registry_digest"]),
        "trusted-ci": (check["ci"], trusted["ci"]),
    }
    errors.update(name for name, values in correlations.items() if values[0] != values[1])
    return errors


def _release_correlation_errors(
    check: dict[str, Any], release: dict[str, Any], trusted: dict[str, Any]
) -> set[str]:
    errors = _trusted_check_correlation_errors(check, trusted)
    pairs = {
        "repository": (check["repository"], release["repository"]),
        "base": (check["base_sha"], release["base_sha"]),
        "source": (check["head_sha"], release["source_sha"]),
        "ci-head": (check["head_sha"], release["ci"]["head_sha"]),
        "approval-head": (check["head_sha"], release["approval"]["approved_head_sha"]),
        "head-tree": (check["head_tree_sha"], release["head_tree_sha"]),
        "merge-tree": (release["head_tree_sha"], release["merge_tree_sha"]),
        "as-of": (check["as_of"], release["as_of"]),
        "epoch": (check["source_date_epoch"], release["source_date_epoch"]),
        "profile": (check["profile"], release["profile"]),
        "base-url": (check["base_url"], release["base_url"]),
        "base-path": (check["base_path"], release["base_path"]),
        "delta": (check["change_delta"], release["change_delta"]),
        "catalogue": (check["artifacts"]["catalogue"], release["artifacts"]["catalogue"]),
        "tool": (check["tool_digest"], release["tool_digest"]),
        "lock": (check["lock_digest"], release["lock_digest"]),
        "actors": (check["actors_registry_digest"], release["approval"]["actors_registry_digest"]),
        "ci-provider": (check["ci"]["provider"], release["ci"]["provider"]),
        "workflow": (check["ci"]["workflow_identity"], release["ci"]["workflow_identity"]),
        "workflow-sha": (check["ci"]["workflow_sha"], release["ci"]["workflow_sha"]),
        "workflow-gates": (check["ci"]["gates"], release["ci"]["gates"]),
        "ci-run": (check["ci"]["run_id"], release["ci"]["run_id"]),
        "ci-check": (check["ci"]["check"], release["ci"]["check"]),
        "ci-result": (check["ci"]["result"], release["ci"]["result"]),
    }
    errors.update(name for name, values in pairs.items() if values[0] != values[1])
    expected_digest = "sha256:" + hashlib.sha256(_canonical_receipt_bytes(check)).hexdigest()
    if release["accepted_check_receipt_digest"] != expected_digest:
        errors.add("check-digest")
    for name in ("publication", "manifest"):
        if check["artifacts"][name]["path"] != release["artifacts"][name]["path"]:
            errors.add(f"{name}-path")
    return errors


class SchemaFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas, cls.registry = _schemas()
        cls.cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]

    def test_every_non_common_schema_has_fixtures(self) -> None:
        expected = set(self.schemas) - {"common.schema.json"}
        actual = {case["schema"] for case in self.cases}
        mac_fixtures = sorted(MAC_FIXTURES.glob("*.json"))
        self.assertEqual(
            {path.stem for path in mac_fixtures},
            {"add", "batch", "change", "move", "revoke"},
        )
        mac_validator = Draft202012Validator(
            self.schemas["mac.schema.json"],
            registry=self.registry,
            format_checker=FormatChecker(),
        )
        for path in mac_fixtures:
            instance = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(schema="mac.schema.json", fixture=path.name):
                errors = list(mac_validator.iter_errors(instance))
                self.assertEqual(errors, [], [error.message for error in errors])
        actual.add("mac.schema.json")
        self.assertEqual(actual, expected)

    def test_all_schema_references_resolve(self) -> None:
        identifiers = {document["$id"] for document in self.schemas.values()}
        for name, document in self.schemas.items():
            for node in _walk_json(document):
                if "$ref" not in node:
                    continue
                target = urljoin(document["$id"], node["$ref"]).split("#", 1)[0]
                with self.subTest(schema=name, reference=node["$ref"]):
                    self.assertIn(target, identifiers)

    def test_patterns_do_not_use_ambiguous_terminal_dollar_anchor(self) -> None:
        for name, document in self.schemas.items():
            for node in _walk_json(document):
                if "pattern" not in node:
                    continue
                with self.subTest(schema=name, pattern=node["pattern"]):
                    self.assertFalse(node["pattern"].endswith("$"))

    def test_valid_and_invalid_fixtures(self) -> None:
        for case in self.cases:
            schema = self.schemas[case["schema"]]
            validator = Draft202012Validator(
                schema,
                registry=self.registry,
                format_checker=FormatChecker(),
            )
            if "valid_source" in case:
                valid = [
                    yaml.safe_load((ROOT / case["valid_source"]).read_text(encoding="utf-8"))
                ]
            else:
                valid = copy.deepcopy(case["valid"])
            for mutation in case.get("valid_mutations", []):
                valid.append(
                    _mutate(valid[mutation.get("valid_index", 0)], mutation)
                )
            for index, instance in enumerate(valid):
                with self.subTest(schema=case["schema"], valid=index):
                    errors = list(validator.iter_errors(instance))
                    self.assertEqual(errors, [], [error.message for error in errors])
            for mutation in case["invalid"]:
                self.assertIn("expect", mutation, mutation["name"])
                source = valid[mutation.get("valid_index", 0)]
                instance = _mutate(source, mutation)
                with self.subTest(schema=case["schema"], invalid=mutation["name"]):
                    errors = _flatten_errors(list(validator.iter_errors(instance)))
                    expected_keyword, expected_path = mutation["expect"]
                    matching = [
                        error
                        for error in errors
                        if error.validator == expected_keyword
                        and list(error.absolute_path) == expected_path
                    ]
                    self.assertNotEqual(
                        matching,
                        [],
                        [
                            {
                                "keyword": error.validator,
                                "path": list(error.absolute_path),
                                "message": error.message,
                            }
                            for error in errors
                        ],
                    )

    def test_launch_wire_schemas_are_closed_and_non_recursive(self) -> None:
        manifest = self.schemas["build-manifest.schema.json"]
        files = manifest["properties"]["files"]
        self.assertEqual(manifest["additionalProperties"], False)
        self.assertEqual(files["required"], ["data/catalogue.json", "data/change-delta.json"])
        self.assertIn(
            {"not": {"const": "data/manifest.json"}},
            files["propertyNames"]["allOf"],
        )
        self.assertEqual(
            self.schemas["check-receipt.schema.json"]["properties"]["change_delta"]["$ref"],
            "release-receipt.schema.json#/$defs/changeDeltaList",
        )
        self.assertEqual(
            self.schemas["release-receipt.schema.json"]["properties"]["change_delta"]["$ref"],
            "#/$defs/changeDeltaList",
        )
        metadata = self.schemas["mac-metadata.schema.json"]
        self.assertEqual(metadata["additionalProperties"], False)
        self.assertEqual(metadata["properties"]["payload"]["$ref"], "mac.schema.json")
        self.assertEqual(
            metadata["properties"]["expected_change_delta"]["$ref"],
            "release-receipt.schema.json#/$defs/changeDeltaList",
        )
        self.assertEqual(metadata["properties"]["expected_change_delta"]["maxItems"], 25)

    def test_modelo_removes_legacy_publication_path_and_disables_agent_approval(self) -> None:
        config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("publication_profiles", config["paths"])
        self.assertNotIn("site_output", config["paths"])
        approval = config["platform"]["optional_capabilities"]["agent_approval"]
        self.assertIs(approval["enabled"], False)
        self.assertEqual(approval["registry"], config["paths"]["actors_registry"])
        self.assertEqual(
            config["platform"]["required_capabilities"]["trusted_pipeline"]["gitlab"],
            "protected_pipeline_policy_if_available_otherwise_protected_branch_adapter",
        )

    def test_catalogue_output_cannot_publish_actor_registry(self) -> None:
        output = self.schemas["catalogue-output.schema.json"]
        self.assertNotIn("actors", output["properties"])
        self.assertEqual(output["additionalProperties"], False)

    def test_check_receipt_digest_is_canonical_bytes_plus_one_lf(self) -> None:
        case = next(case for case in self.cases if case["schema"] == "check-receipt.schema.json")
        receipt = case["valid"][0]
        reordered = dict(reversed(list(receipt.items())))
        exact = _canonical_receipt_bytes(receipt)
        self.assertEqual(exact, _canonical_receipt_bytes(reordered))
        self.assertTrue(exact.endswith(b"\n"))
        self.assertFalse(exact.endswith(b"\n\n"))
        digest = hashlib.sha256(exact).hexdigest()
        self.assertEqual(digest, hashlib.sha256(_canonical_receipt_bytes(reordered)).hexdigest())
        self.assertNotEqual(digest, hashlib.sha256(exact[:-1]).hexdigest())

    def test_change_delta_permutations_have_one_canonical_order(self) -> None:
        digest = "sha256:" + "a" * 64
        values = [
            {"operation": "revoke", "path": "catalogue/offerings/x/z.yaml", "before": digest},
            {"operation": "add", "path": "catalogue/models/b.yaml", "after": digest},
            {"operation": "change", "path": "catalogue/models/a.yaml", "before": digest, "after": digest},
        ]
        expected = _sort_delta(values)
        self.assertEqual(expected, _sort_delta(list(reversed(values))))
        self.assertEqual([item["operation"] for item in expected], ["add", "change", "revoke"])
        self.assertEqual(_canonical_receipt_bytes({"change_delta": expected}), _canonical_receipt_bytes({"change_delta": _sort_delta(values[1:] + values[:1])}))

    def test_change_delta_sort_is_total_when_declared_keys_tie(self) -> None:
        digest = "sha256:" + "a" * 64
        tied = [
            {
                "operation": "move",
                "source": {
                    "operation": "revoke", "path": "catalogue/offerings/aws-bedrock/a.yaml",
                    "before": digest, "reason": "First admissible reason.",
                    "effective_at": "2026-08-30T14:00:00Z",
                },
                "destination": {
                    "operation": "add", "path": "catalogue/offerings/aws-bedrock/b.yaml",
                    "after": digest,
                },
            },
            {
                "operation": "move",
                "source": {
                    "operation": "revoke", "path": "catalogue/offerings/aws-bedrock/a.yaml",
                    "before": digest, "reason": "Second admissible reason.",
                    "effective_at": "2026-08-30T15:00:00Z",
                    "replacement": "catalogue/offerings/aws-bedrock/b.yaml",
                },
                "destination": {
                    "operation": "add", "path": "catalogue/offerings/aws-bedrock/b.yaml",
                    "after": digest,
                },
            },
        ]
        release_case = next(
            case for case in self.cases if case["schema"] == "release-receipt.schema.json"
        )
        release = copy.deepcopy(release_case["valid"][0])
        release["change_delta"] = tied
        validator = Draft202012Validator(
            self.schemas["release-receipt.schema.json"],
            registry=self.registry,
            format_checker=FormatChecker(),
        )
        self.assertEqual(list(validator.iter_errors(release)), [])
        self.assertEqual(_sort_delta(tied), _sort_delta(list(reversed(tied))))

    def test_documented_package_build_command_is_supported_by_pinned_uv(self) -> None:
        config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        command = "uv build --offline --no-cache"
        self.assertEqual(config["toolchain"]["package_build"], command)
        self.assertIn(command, (ROOT / "README.md").read_text(encoding="utf-8"))
        version = subprocess.run(
            ["uv", "--version"], check=True, capture_output=True, text=True
        )
        self.assertEqual(version.stdout.split()[:2], ["uv", "0.11.33"])
        help_result = subprocess.run(
            ["uv", "build", "--help"], check=True, capture_output=True, text=True
        )
        self.assertIn("--offline", help_result.stdout)
        self.assertIn("--no-cache", help_result.stdout)

    def test_catalogue_sort_contract_covers_unordered_arrays(self) -> None:
        contract = yaml.safe_load((ROOT / "docs/contract.yaml").read_text(encoding="utf-8"))
        self.assertEqual(
            contract["build"]["catalogue_sort_keys"],
            {
                "models": ["id", "canonical_json_bytes"],
                "offerings": ["inference_service_id", "id", "canonical_json_bytes"],
                "evidence": ["id", "canonical_json_bytes"],
                "conditions": ["id", "version", "canonical_json_bytes"],
                "routes": ["id", "canonical_json_bytes"],
                "route_destinations": ["destination_pointer", "canonical_json_bytes"],
                "pricing": ["dimension", "unit", "quantity", "amount", "currency", "sorted_route_ids", "canonical_json_bytes"],
                "condition_refs": ["id", "version", "canonical_json_bytes"],
                "id_arrays": "ascii_id",
                "total_tie_breaker": "canonical_json_bytes",
            },
        )
        self.assertTrue(contract["build"]["semantic_evidence_projection_arrays_preserve_source_order"])

    def test_t6_manifest_completeness_has_exact_fixed_and_derived_inventory(self) -> None:
        contract = yaml.safe_load((ROOT / "docs/contract.yaml").read_text(encoding="utf-8"))
        manifest_schema = self.schemas["build-manifest.schema.json"]
        self.assertEqual(manifest_schema["x-modelo-executable-completeness-owner"], "candidate:T5;validation:T8;final:T6;demo:Pages")
        self.assertEqual(
            manifest_schema["x-modelo-executable-completeness"],
            "candidate_files_exact_catalogue_plus_change_delta;validation_final_and_demo_files_equal_contract_fixed_union_all_source_commit_schemas_union_projection_derived_excluding_manifest",
        )
        configured = set(contract["build"]["manifest_required_fixed_files"])
        self.assertEqual(configured, REQUIRED_FIXED_PUBLICATION_FILES)
        configured_schemas = {
            path for path in REQUIRED_PUBLICATION_FILES if path.startswith("schemas/")
        }
        source_schemas = {
            f"schemas/{path.relative_to(SCHEMAS).as_posix()}"
            for path in SCHEMAS.rglob("*.schema.json")
        }
        self.assertEqual(configured_schemas, source_schemas)
        self.assertEqual(contract["build"]["candidate_manifest_completeness_executable_owner"], "t5")
        self.assertEqual(contract["build"]["final_manifest_completeness_executable_owner"], "t6")
        site_contract = (ROOT / "docs/site-contract.md").read_text(encoding="utf-8")
        self.assertIn("`data/change-delta.json`", site_contract)
        self.assertIn("every schema file", site_contract)
        self.assertNotIn("currently 17", site_contract)
        self.assertNotIn("sixteen schema", site_contract)
        projection = {
            "models": [{"id": "model-a"}, {"id": "model-b"}],
            "offerings": [
                {"inference_service_id": "aws-bedrock", "id": "offer-a"}
            ],
        }
        expected = _expected_manifest_files(projection)
        self.assertIn("models/model-a/index.html", expected)
        self.assertIn("offerings/aws-bedrock/offer-a/index.html", expected)
        complete = {path: {} for path in expected}
        self.assertEqual(_manifest_completeness_errors(complete, projection), {"missing": set(), "unexpected": set()})
        for missing in sorted(expected):
            with self.subTest(missing=missing):
                errors = _manifest_completeness_errors(
                    {path: {} for path in expected - {missing}}, projection
                )
                self.assertEqual(errors["missing"], {missing})
        errors = _manifest_completeness_errors(
            {path: {} for path in expected | {"unexpected.html"}}, projection
        )
        self.assertEqual(errors["unexpected"], {"unexpected.html"})
        self.assertNotIn("data/manifest.json", expected)

    def test_t5_candidate_manifest_inventory_is_exact(self) -> None:
        config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        build = config["build"]
        self.assertEqual(build["implemented_kinds"], ["candidate", "demo", "final"])
        self.assertEqual(build["final_cli_arguments"], ["merge_commit", "merge_tree", "publication_capability"])
        self.assertEqual(
            set(build["candidate_output_inventory"]),
            {
                "site/data/catalogue.json",
                "site/data/change-delta.json",
                "site/data/manifest.json",
            },
        )
        self.assertEqual(
            set(build["candidate_manifest_files"]),
            {"data/catalogue.json", "data/change-delta.json"},
        )
        manifest = next(
            case["valid"][0]
            for case in self.cases
            if case["schema"] == "build-manifest.schema.json"
        )
        self.assertEqual(set(manifest["files"]), set(build["candidate_manifest_files"]))
        self.assertEqual(manifest["change_delta_path"], "data/change-delta.json")
        self.assertEqual(
            config["publication"]["profiles"]["synthetic"]["source"],
            "tests/fixtures/build/synthetic",
        )
        self.assertEqual(
            config["publication"]["profiles"]["synthetic"]["as_of"],
            "2026-08-30",
        )

    def test_t5_required_inputs_and_commands_align_cross_document(self) -> None:
        config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        contract = yaml.safe_load((ROOT / "docs/contract.yaml").read_text(encoding="utf-8"))
        required = {
            "kind", "base_commit", "source_commit", "source_tree", "as_of",
            "source_date_epoch", "mac_metadata", "profile", "base_path", "output",
        }
        self.assertEqual(set(config["build"]["required_cli_arguments"]), required)
        self.assertEqual(set(contract["build"]["candidate_cli_required_flags"]), required)
        self.assertEqual(
            set(contract["build"]["final_cli_required_flags"]),
            {
                "kind", "base_commit", "source_commit", "source_tree",
                "merge_commit", "merge_tree", "as_of", "source_date_epoch",
                "mac_metadata", "profile", "publication_capability", "base_url", "base_path", "output",
            },
        )
        self.assertEqual(config["paths"]["mac_metadata_schema"], "schemas/mac-metadata.schema.json")
        command = config["toolchain"]["clean_clone"]["build"]
        for flag in (
            "--kind", "--base-commit", "--source-commit", "--source-tree", "--as-of",
            "--source-date-epoch", "--mac-metadata", "--profile", "--base-path", "--output",
        ):
            self.assertIn(flag, command)
        for path in (ROOT / "README.md", ROOT / "SPEC.md", ROOT / "docs/implementation-plan.md"):
            with self.subTest(path=path.name):
                self.assertIn("--base-commit", path.read_text(encoding="utf-8"))
        build = config["build"]
        self.assertEqual(
            _output_path_errors(
                "candidate", build["candidate_root"],
                build["candidate_root"], build["final_root"],
            ),
            set(),
        )
        self.assertEqual(
            _output_path_errors(
                "final", build["final_root"],
                build["candidate_root"], build["final_root"],
            ),
            set(),
        )
        adversarial = (
            ("candidate", "dist/other", False, "output-root"),
            ("candidate", "../candidate", False, "output-safety"),
            ("candidate", "/tmp/candidate", False, "output-safety"),
            ("candidate", "dist/candidate", True, "output-safety"),
            ("candidate", "catalogue/output", False, "output-inside-input"),
        )
        for kind, output, symlink, expected in adversarial:
            with self.subTest(output=output, symlink=symlink):
                self.assertIn(
                    expected,
                    _output_path_errors(
                        kind, output, build["candidate_root"], build["final_root"],
                        is_symlink=symlink,
                    ),
                )

    def test_validated_mac_metadata_correlates_exact_inputs_and_delta(self) -> None:
        envelope = next(
            case["valid"][0]
            for case in self.cases
            if case["schema"] == "mac-metadata.schema.json"
        )
        flags = {
            "base_commit": envelope["base_sha"],
            "source_commit": envelope["head_sha"],
            "source_tree": envelope["head_tree_sha"],
        }
        self.assertEqual(
            _mac_metadata_errors(envelope, flags, envelope["expected_change_delta"]), set()
        )
        mutations = {
            "base": ("flag", "base_commit", "0" * 40),
            "head": ("flag", "source_commit", "0" * 40),
            "head-tree": ("flag", "source_tree", "0" * 40),
            "issue-repository": ("envelope", ["issue", "url"], "https://github.com/other/Repo/issues/22"),
            "payload-digest": ("envelope", ["payload_digest"], "sha256:" + "0" * 64),
            "operation-subjects": ("envelope", ["payload", "subjects", 0, "identity"], "other-model"),
            "computed-delta": ("computed", [0, "after"], "sha256:" + "0" * 64),
        }
        for expected, (target_kind, path, value) in mutations.items():
            changed_envelope = copy.deepcopy(envelope)
            changed_flags = copy.deepcopy(flags)
            changed_delta = copy.deepcopy(envelope["expected_change_delta"])
            if target_kind == "flag":
                changed_flags[path] = value
            else:
                target = changed_delta if target_kind == "computed" else changed_envelope
                for component in path[:-1]:
                    target = target[component]
                target[path[-1]] = value
            with self.subTest(expected=expected):
                self.assertIn(
                    expected,
                    _mac_metadata_errors(changed_envelope, changed_flags, changed_delta),
                )
        wrong_operation = copy.deepcopy(envelope)
        wrong_operation["payload"]["operation"] = "change"
        wrong_operation["payload_digest"] = "sha256:" + hashlib.sha256(
            _canonical_receipt_bytes(wrong_operation["payload"])
        ).hexdigest()
        self.assertIn(
            "operation-subjects",
            _mac_metadata_errors(wrong_operation, flags, envelope["expected_change_delta"]),
        )
        wrong_path = copy.deepcopy(envelope)
        wrong_path["expected_change_delta"][0]["path"] = "catalogue/models/other.yaml"
        errors = _mac_metadata_errors(wrong_path, flags, envelope["expected_change_delta"])
        self.assertIn("operation-subjects", errors)
        self.assertIn("computed-delta", errors)

    def test_registry_subjects_are_derived_from_keyed_document_diff(self) -> None:
        base = next(
            case["valid"][0] for case in self.cases
            if case["schema"] == "mac-metadata.schema.json"
        )
        digest_a = "sha256:" + "a" * 64
        digest_b = "sha256:" + "b" * 64
        delta = [{
            "operation": "change",
            "path": "catalogue/governance/vendors.yaml",
            "before": digest_a,
            "after": digest_b,
        }]
        flags = {
            "base_commit": base["base_sha"],
            "source_commit": base["head_sha"],
            "source_tree": base["head_tree_sha"],
        }

        def envelope_for(identities: list[str]) -> dict[str, Any]:
            envelope = copy.deepcopy(base)
            payload = json.loads((MAC_FIXTURES / "batch.json").read_text(encoding="utf-8"))
            payload["subjects"] = [
                {"kind": "vendor", "identity": identity} for identity in identities
            ]
            envelope["payload"] = payload
            envelope["payload_digest"] = "sha256:" + hashlib.sha256(
                _canonical_receipt_bytes(payload)
            ).hexdigest()
            envelope["expected_change_delta"] = copy.deepcopy(delta)
            return envelope

        base_maps = {"vendor": {}, "inference-service": {}}
        head_maps = {
            "vendor": {"vendor-a": {"name": "A"}, "vendor-b": {"name": "B"}},
            "inference-service": {},
        }
        batch = envelope_for(["vendor-a", "vendor-b"])
        metadata_validator = Draft202012Validator(
            self.schemas["mac-metadata.schema.json"],
            registry=self.registry,
            format_checker=FormatChecker(),
        )
        self.assertEqual(list(metadata_validator.iter_errors(batch)), [])
        self.assertEqual(
            _mac_metadata_errors(
                batch, flags, delta,
                base_registries=base_maps, head_registries=head_maps,
            ),
            set(),
        )
        changed_maps_base = {
            "vendor": {"vendor-a": {"name": "Old A"}, "vendor-b": {"name": "Old B"}},
            "inference-service": {},
        }
        changed_maps_head = {
            "vendor": {"vendor-a": {"name": "A"}, "vendor-b": {"name": "B"}},
            "inference-service": {},
        }
        self.assertIn(
            "registry-operation",
            _mac_metadata_errors(
                batch, flags, delta,
                base_registries=changed_maps_base,
                head_registries=changed_maps_head,
            ),
        )
        changed_batch = copy.deepcopy(batch)
        changed_batch["payload"]["item_operation"] = "change"
        changed_batch["payload_digest"] = "sha256:" + hashlib.sha256(
            _canonical_receipt_bytes(changed_batch["payload"])
        ).hexdigest()
        self.assertEqual(
            _mac_metadata_errors(
                changed_batch, flags, delta,
                base_registries=changed_maps_base,
                head_registries=changed_maps_head,
            ),
            set(),
        )
        deleted_maps = {
            "vendor": {"vendor-b": {"name": "B"}}, "inference-service": {}
        }
        self.assertIn(
            "registry-deletion",
            _mac_metadata_errors(
                changed_batch, flags, delta,
                base_registries=changed_maps_head, head_registries=deleted_maps,
            ),
        )
        for identities in (["vendor-a"], ["vendor-a", "vendor-b", "vendor-c"]):
            with self.subTest(identities=identities):
                self.assertIn(
                    "registry-subjects",
                    _mac_metadata_errors(
                        envelope_for(list(identities)), flags, delta,
                        base_registries=base_maps, head_registries=head_maps,
                    ),
                )
        claim_a_change_b = envelope_for(["vendor-a"])
        self.assertIn(
            "registry-subjects",
            _mac_metadata_errors(
                claim_a_change_b, flags, delta,
                base_registries=base_maps,
                head_registries={
                    "vendor": {"vendor-b": {"name": "B"}},
                    "inference-service": {},
                },
            ),
        )
        unclaimed = copy.deepcopy(base)
        unclaimed["expected_change_delta"] = copy.deepcopy(delta)
        self.assertIn(
            "registry-subjects",
            _mac_metadata_errors(
                unclaimed, flags, delta,
                base_registries=base_maps,
                head_registries={
                    "vendor": {"vendor-a": {"name": "A"}},
                    "inference-service": {},
                },
            ),
        )
        service = envelope_for(["service-a"])
        service["payload"]["subjects"] = [
            {"kind": "inference-service", "identity": "service-a"}
        ]
        service["payload_digest"] = "sha256:" + hashlib.sha256(
            _canonical_receipt_bytes(service["payload"])
        ).hexdigest()
        service_delta = [{
            "operation": "change",
            "path": "catalogue/governance/inference-services.yaml",
            "before": digest_a,
            "after": digest_b,
        }]
        service["expected_change_delta"] = service_delta
        self.assertEqual(
            _mac_metadata_errors(
                service, flags, service_delta,
                base_registries={"vendor": {}, "inference-service": {}},
                head_registries={
                    "vendor": {},
                    "inference-service": {"service-a": {"name": "Service A"}},
                },
            ),
            set(),
        )

    def test_mac_metadata_ingestion_is_bounded_strict_json_read_once(self) -> None:
        config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        ingestion = config["build"]["mac_metadata_ingestion"]
        self.assertEqual(
            ingestion,
            {
                "cli_value": "explicit_file_path",
                "file_type": "regular_non_symlink",
                "max_bytes": 262144,
                "encoding": "strict_utf8",
                "format": "strict_json_object_not_yaml",
                "duplicate_keys": "reject",
                "non_finite_numbers": "reject",
                "floating_point_numbers": "reject",
                "open_strategy": "nofollow_required_in_ci",
                "read_strategy": "once_from_single_open_descriptor",
                "mutation_check": "fstat_before_after_device_inode_mode_type_size_mtime_ns_ctime_ns_equal",
                "incapable_ci": "fail_closed",
                "local_candidate_accepting_durability": False,
                "outside_repository_temp_path": "allowed",
                "network_read": False,
                "validation_order": ["file_boundary", "json_parse", "schema", "semantic_correlations"],
            },
        )
        valid = next(
            case["valid"][0] for case in self.cases
            if case["schema"] == "mac-metadata.schema.json"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regular = root / "valid.json"
            regular.write_text(json.dumps(valid), encoding="utf-8")
            self.assertEqual(_read_mac_metadata_contract(regular), valid)
            original_bytes = regular.read_bytes()
            original_mtime = regular.stat().st_mtime_ns

            def same_size_rewrite_with_restored_mtime() -> None:
                original_ctime = regular.stat().st_ctime_ns
                changed = bytearray(original_bytes)
                changed[-2] = ord(" ") if changed[-2] != ord(" ") else ord("\t")
                regular.write_bytes(bytes(changed))
                os.utime(regular, ns=(original_mtime, original_mtime))
                deadline = time.monotonic() + 2.0
                while regular.stat().st_ctime_ns == original_ctime and time.monotonic() < deadline:
                    time.sleep(0.001)
                    os.utime(regular, ns=(original_mtime, original_mtime))
                self.assertNotEqual(regular.stat().st_ctime_ns, original_ctime)

            with self.assertRaises(ValueError):
                _read_mac_metadata_contract(regular, same_size_rewrite_with_restored_mtime)
            regular.write_bytes(original_bytes)
            symlink = root / "link.json"
            symlink.symlink_to(regular)
            invalid: list[tuple[str, bytes | None]] = [
                ("link.json", None),
                ("large.json", b"{" + b" " * 262144 + b"}"),
                ("utf8.json", b"{\"x\":\xff}"),
                ("yaml.json", b"key: value\n"),
                ("duplicate.json", b"{\"x\":1,\"x\":2}"),
                ("nan.json", b"{\"x\":NaN}"),
                ("float.json", b"{\"x\":1.5}"),
                ("array.json", b"[]"),
            ]
            for name, content in invalid:
                path = root / name
                if content is not None:
                    path.write_bytes(content)
                with self.subTest(name=name), self.assertRaises((OSError, ValueError, UnicodeError, json.JSONDecodeError)):
                    _read_mac_metadata_contract(path)

    def test_source_epoch_is_explicit_but_frozen_to_source_author_time(self) -> None:
        config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        determinism = config["determinism"]
        self.assertEqual(
            determinism["source_date_epoch"],
            "required_equal_exact_source_commit_author_timestamp",
        )
        self.assertIs(determinism["source_date_epoch_environment_read"], False)
        self.assertEqual(determinism["arbitrary_override"], "forbidden")
        self.assertEqual(determinism["final_source_commit"], "accepted_head")
        self.assertTrue(determinism["merge_timestamp_receipt_only"])
        self.assertEqual(_source_epoch_errors(100, 100), set())
        self.assertEqual(_source_epoch_errors(101, 100), {"source-author-epoch"})
        for path in (
            ROOT / "SPEC.md", ROOT / "README.md", ROOT / "docs/contract.yaml",
            ROOT / "docs/implementation-plan.md", ROOT / "docs/site-contract.md",
        ):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("SOURCE_DATE_EPOCH", text)
            self.assertNotIn("recorded explicit override", text)

    def test_revoke_and_move_annotations_are_envelope_only_and_exact(self) -> None:
        base = next(
            case["valid"][0]
            for case in self.cases
            if case["schema"] == "mac-metadata.schema.json"
        )
        flags = {
            "base_commit": base["base_sha"],
            "source_commit": base["head_sha"],
            "source_tree": base["head_tree_sha"],
        }
        digest_a = "sha256:" + "a" * 64
        digest_b = "sha256:" + "b" * 64
        cases = [
            (
                "revoke",
                json.loads((MAC_FIXTURES / "revoke.json").read_text(encoding="utf-8")),
                [{"operation": "revoke", "path": "catalogue/offerings/aws-bedrock/bedrock-example-model.yaml", "before": digest_a, "reason": "Governance withdrawal.", "effective_at": "2026-08-30T14:00:00Z"}],
                [0, "reason"],
                "Different reason.",
            ),
            (
                "move",
                json.loads((MAC_FIXTURES / "move.json").read_text(encoding="utf-8")),
                [{"operation": "move", "source": {"operation": "revoke", "path": "catalogue/offerings/aws-bedrock/bedrock-example-old.yaml", "before": digest_a, "reason": "Identity moved.", "effective_at": "2026-08-30T14:00:00Z", "replacement": "catalogue/offerings/aws-bedrock/bedrock-example-new.yaml"}, "destination": {"operation": "add", "path": "catalogue/offerings/aws-bedrock/bedrock-example-new.yaml", "after": digest_b}}],
                [0, "source", "effective_at"],
                "2026-08-30T15:00:00Z",
            ),
        ]
        for name, payload, delta, mutation_path, value in cases:
            envelope = copy.deepcopy(base)
            envelope["payload"] = payload
            envelope["payload_digest"] = "sha256:" + hashlib.sha256(
                _canonical_receipt_bytes(payload)
            ).hexdigest()
            envelope["expected_change_delta"] = delta
            self.assertEqual(_mac_metadata_errors(envelope, flags, delta), set())
            changed = copy.deepcopy(delta)
            target = changed
            for component in mutation_path[:-1]:
                target = target[component]
            target[mutation_path[-1]] = value
            with self.subTest(name=name):
                self.assertIn("computed-delta", _mac_metadata_errors(envelope, flags, changed))

    def test_move_and_revoke_replacements_are_exact_and_resolvable(self) -> None:
        base = next(
            case["valid"][0] for case in self.cases
            if case["schema"] == "mac-metadata.schema.json"
        )
        flags = {
            "base_commit": base["base_sha"],
            "source_commit": base["head_sha"],
            "source_tree": base["head_tree_sha"],
        }
        digest = "sha256:" + "a" * 64
        move = copy.deepcopy(base)
        move["payload"] = json.loads((MAC_FIXTURES / "move.json").read_text(encoding="utf-8"))
        move["payload_digest"] = "sha256:" + hashlib.sha256(
            _canonical_receipt_bytes(move["payload"])
        ).hexdigest()
        move_delta = [{
            "operation": "move",
            "source": {
                "operation": "revoke",
                "path": "catalogue/offerings/aws-bedrock/bedrock-example-old.yaml",
                "before": digest,
                "reason": "Identity moved.",
                "effective_at": "2026-08-30T14:00:00Z",
                "replacement": "catalogue/offerings/aws-bedrock/bedrock-example-new.yaml",
            },
            "destination": {
                "operation": "add",
                "path": "catalogue/offerings/aws-bedrock/bedrock-example-new.yaml",
                "after": digest,
            },
        }]
        move["expected_change_delta"] = move_delta
        self.assertEqual(_mac_metadata_errors(move, flags, move_delta), set())
        for replacement in (None, "catalogue/offerings/aws-bedrock/arbitrary.yaml"):
            changed = copy.deepcopy(move_delta)
            if replacement is None:
                changed[0]["source"].pop("replacement")
            else:
                changed[0]["source"]["replacement"] = replacement
            changed_envelope = copy.deepcopy(move)
            changed_envelope["expected_change_delta"] = changed
            self.assertIn("move-replacement", _mac_metadata_errors(changed_envelope, flags, changed))

        revoke = copy.deepcopy(base)
        revoke["payload"] = json.loads((MAC_FIXTURES / "revoke.json").read_text(encoding="utf-8"))
        revoke["payload_digest"] = "sha256:" + hashlib.sha256(
            _canonical_receipt_bytes(revoke["payload"])
        ).hexdigest()
        revoked_path = "catalogue/offerings/aws-bedrock/bedrock-example-model.yaml"
        replacement_path = "catalogue/offerings/aws-bedrock/bedrock-example-new.yaml"
        revoke_delta = [{
            "operation": "revoke", "path": revoked_path, "before": digest,
            "reason": "Governance withdrawal.", "effective_at": "2026-08-30T14:00:00Z",
        }]
        revoke["expected_change_delta"] = revoke_delta
        self.assertEqual(
            _mac_metadata_errors(revoke, flags, revoke_delta, head_offering_paths=set()), set()
        )
        valid = copy.deepcopy(revoke_delta)
        valid[0]["replacement"] = replacement_path
        valid_envelope = copy.deepcopy(revoke)
        valid_envelope["expected_change_delta"] = valid
        self.assertEqual(
            _mac_metadata_errors(
                valid_envelope, flags, valid, head_offering_paths={replacement_path}
            ),
            set(),
        )
        for replacement, head_paths in (
            (revoked_path, {revoked_path}),
            (replacement_path, set()),
        ):
            changed = copy.deepcopy(revoke_delta)
            changed[0]["replacement"] = replacement
            changed_envelope = copy.deepcopy(revoke)
            changed_envelope["expected_change_delta"] = changed
            self.assertIn(
                "revoke-replacement",
                _mac_metadata_errors(
                    changed_envelope, flags, changed, head_offering_paths=head_paths
                ),
            )

    def test_canonical_base_url_and_path_pairs(self) -> None:
        for url, path in (
            ("https://example.invalid/", "/"),
            ("https://example.invalid/Modelo/", "/Modelo/"),
        ):
            with self.subTest(url=url, path=path):
                self.assertTrue(_canonical_site_url_matches(url, path))
        for url, path in (
            ("https://example.invalid/Other/", "/Modelo/"),
            ("https://user@example.invalid/Modelo/", "/Modelo/"),
            ("https://example.invalid:443/Modelo/", "/Modelo/"),
            ("https://example.invalid/Modelo/?x=1", "/Modelo/"),
            ("https://example.invalid/Modelo", "/Modelo/"),
            ("https://example.invalid/../Modelo/", "/../Modelo/"),
        ):
            with self.subTest(url=url, path=path):
                self.assertFalse(_canonical_site_url_matches(url, path))

    def test_release_fixture_correlates_with_accepted_check_fixture(self) -> None:
        by_schema = {case["schema"]: case for case in self.cases}
        check = by_schema["check-receipt.schema.json"]["valid"][0]
        release = by_schema["release-receipt.schema.json"]["valid"][0]
        equalities = {
            "repository": (check["repository"], release["repository"]),
            "check provider": (check["repository"]["provider"], check["ci"]["provider"]),
            "release provider": (release["repository"]["provider"], release["ci"]["provider"]),
            "base": (check["base_sha"], release["base_sha"]),
            "head": (check["head_sha"], release["source_sha"]),
            "ci head": (check["head_sha"], release["ci"]["head_sha"]),
            "approval head": (check["head_sha"], release["approval"]["approved_head_sha"]),
            "tree": (check["head_tree_sha"], release["head_tree_sha"]),
            "merge tree": (release["head_tree_sha"], release["merge_tree_sha"]),
            "as-of": (check["as_of"], release["as_of"]),
            "epoch": (check["source_date_epoch"], release["source_date_epoch"]),
            "profile": (check["profile"], release["profile"]),
            "base URL": (check["base_url"], release["base_url"]),
            "base path": (check["base_path"], release["base_path"]),
            "delta": (check["change_delta"], release["change_delta"]),
            "catalogue": (check["artifacts"]["catalogue"], release["artifacts"]["catalogue"]),
            "tool": (check["tool_digest"], release["tool_digest"]),
            "lock": (check["lock_digest"], release["lock_digest"]),
            "actors": (check["actors_registry_digest"], release["approval"]["actors_registry_digest"]),
            "workflow": (check["ci"]["workflow_identity"], release["ci"]["workflow_identity"]),
            "workflow SHA": (check["ci"]["workflow_sha"], release["ci"]["workflow_sha"]),
            "workflow gates": (check["ci"]["gates"], release["ci"]["gates"]),
            "ci run": (check["ci"]["run_id"], release["ci"]["run_id"]),
            "ci check": (check["ci"]["check"], release["ci"]["check"]),
            "ci result": (check["ci"]["result"], release["ci"]["result"]),
        }
        for name, (accepted, final) in equalities.items():
            with self.subTest(name=name):
                self.assertEqual(accepted, final)
        self.assertEqual(
            release["accepted_check_receipt_digest"],
            "sha256:" + hashlib.sha256(_canonical_receipt_bytes(check)).hexdigest(),
        )
        trusted = _trusted_context(check)
        self.assertEqual(_trusted_check_correlation_errors(check, trusted), set())
        self.assertEqual(_release_correlation_errors(check, release, trusted), set())

    def test_trusted_check_correlations_reject_digest_recomputed_drift(self) -> None:
        by_schema = {case["schema"]: case for case in self.cases}
        original = by_schema["check-receipt.schema.json"]["valid"][0]
        release = by_schema["release-receipt.schema.json"]["valid"][0]
        trusted = _trusted_context(original)
        mutations = {
            "trusted-head": (["head_sha"], "0" * 40),
            "trusted-repository": (["repository", "provider"], "gitlab"),
        }
        for expected, (path, value) in mutations.items():
            check = copy.deepcopy(original)
            target = check
            for component in path[:-1]:
                target = target[component]
            target[path[-1]] = value
            if expected == "trusted-head":
                check["ci"]["head_sha"] = value
            else:
                check["ci"]["provider"] = value
            changed_release = copy.deepcopy(release)
            changed_release["accepted_check_receipt_digest"] = (
                "sha256:" + hashlib.sha256(_canonical_receipt_bytes(check)).hexdigest()
            )
            with self.subTest(expected=expected):
                self.assertIn(expected, _release_correlation_errors(check, changed_release, trusted))

    def test_trusted_check_correlations_reject_result_and_current_base_drift(self) -> None:
        check = next(
            case["valid"][0]
            for case in self.cases
            if case["schema"] == "check-receipt.schema.json"
        )
        trusted = _trusted_context(check)
        failed = copy.deepcopy(check)
        failed["ci"]["result"] = "failure"
        self.assertIn("check-ci-result", _trusted_check_correlation_errors(failed, trusted))
        advanced = copy.deepcopy(trusted)
        advanced["current_base_sha"] = "0" * 40
        self.assertIn("trusted-base", _trusted_check_correlation_errors(check, advanced))

    def test_trusted_check_correlations_reject_internal_head_and_provider_mismatch(self) -> None:
        check = next(
            case["valid"][0]
            for case in self.cases
            if case["schema"] == "check-receipt.schema.json"
        )
        trusted = _trusted_context(check)
        wrong_head = copy.deepcopy(check)
        wrong_head["ci"]["head_sha"] = "0" * 40
        self.assertIn("check-ci-head", _trusted_check_correlation_errors(wrong_head, trusted))
        wrong_provider = copy.deepcopy(check)
        wrong_provider["ci"]["provider"] = "gitlab"
        self.assertIn("check-ci-provider", _trusted_check_correlation_errors(wrong_provider, trusted))

    def test_release_correlations_fail_independently(self) -> None:
        by_schema = {case["schema"]: case for case in self.cases}
        check = by_schema["check-receipt.schema.json"]["valid"][0]
        release = by_schema["release-receipt.schema.json"]["valid"][0]
        mutations = {
            "repository": (["repository", "name"], "Other"),
            "base": (["base_sha"], "0" * 40),
            "source": (["source_sha"], "0" * 40),
            "ci-head": (["ci", "head_sha"], "0" * 40),
            "approval-head": (["approval", "approved_head_sha"], "0" * 40),
            "merge-tree": (["merge_tree_sha"], "0" * 40),
            "epoch": (["source_date_epoch"], 1),
            "base-url": (["base_url"], "https://example.invalid/Other/"),
            "delta": (["change_delta", 0, "path"], "catalogue/models/other.yaml"),
            "catalogue": (["artifacts", "catalogue", "sha256"], "sha256:" + "0" * 64),
            "tool": (["tool_digest"], "sha256:" + "0" * 64),
            "actors": (["approval", "actors_registry_digest"], "sha256:" + "0" * 64),
            "workflow": (["ci", "workflow_identity"], "untrusted"),
            "ci-run": (["ci", "run_id"], "999"),
            "check-digest": (["accepted_check_receipt_digest"], "sha256:" + "0" * 64),
            "manifest-path": (["artifacts", "manifest", "path"], "site/other.json"),
        }
        for expected, (path, value) in mutations.items():
            changed = copy.deepcopy(release)
            target = changed
            for component in path[:-1]:
                target = target[component]
            target[path[-1]] = value
            with self.subTest(expected=expected):
                self.assertIn(expected, _release_correlation_errors(check, changed, _trusted_context(check)))

    def test_agent_approval_requires_every_path_to_be_data_only(self) -> None:
        self.assertTrue(_agent_paths_allowed(["catalogue/models/a.yaml", "catalogue/evidence/sha256-a.yaml"]))
        self.assertFalse(_agent_paths_allowed([]))
        for control_path in (
            "schemas/model.schema.json",
            "modelo.yaml",
            "tooling/modelo/src/modelo/build.py",
            ".github/workflows/modelo.yml",
            "docs/contract.yaml",
        ):
            with self.subTest(path=control_path):
                self.assertFalse(_agent_paths_allowed(["catalogue/models/a.yaml", control_path]))

    def test_contract_assigns_all_cross_document_checks_to_t8(self) -> None:
        contract = yaml.safe_load((ROOT / "docs/contract.yaml").read_text(encoding="utf-8"))
        self.assertEqual(
            self.schemas["check-receipt.schema.json"]["x-modelo-executable-correlations"],
            [
                "ci.head_sha==head_sha",
                "ci.provider==repository.provider",
                "receipt_fields==trusted_t8_inputs",
            ],
        )
        self.assertEqual(
            set(contract["validation"]["t8_check_receipt_correlations"]),
            {
                "repository_identity",
                "base_head_and_head_tree",
                "as_of_source_epoch_profile_base_url_and_base_path",
                "mac_payload_and_canonical_change_delta",
                "named_artifact_paths_and_digests",
                "tool_and_lock_digests",
                "actors_registry_digest_and_actor_eligibility",
                "trusted_ci_provider_workflow_run_check_result_and_exact_head",
            },
        )
        self.assertEqual(
            set(contract["validation"]["t8_trusted_input_equality"]),
            {
                "repository", "current_base_sha", "current_head_sha",
                "current_head_tree_sha", "as_of", "source_date_epoch", "profile",
                "base_url", "base_path", "mac_issue", "mac_payload_digest",
                "canonical_change_delta", "named_artifacts_and_digests",
                "tool_digest", "lock_digest", "actors_registry_digest",
                "ci_provider", "workflow_identity", "run_id", "check_name",
                "success_result",
            },
        )
        self.assertEqual(
            set(contract["validation"]["t8_internal_receipt_equalities"]),
            {"ci_head_equals_top_level_head", "ci_provider_equals_repository_provider"},
        )
        self.assertEqual(
            set(contract["validation"]["postmerge_publication"]["final_only_digest_exceptions"]),
            {"publication", "manifest"},
        )
        self.assertTrue(contract["approval"]["agent_approval"]["every_changed_path_must_match_allowlist"])

    def test_atomic_publication_contract_is_ordered_and_not_overclaimed(self) -> None:
        config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        build = config["build"]
        self.assertEqual(
            set(build["required_cli_arguments"]),
            {"kind", "base_commit", "source_commit", "source_tree", "as_of", "source_date_epoch", "mac_metadata", "profile", "base_path", "output"},
        )
        self.assertEqual(set(build["final_cli_arguments"]), {"merge_commit", "merge_tree", "publication_capability"})
        self.assertIs(build["ambient_git_or_environment_inference"], False)
        self.assertEqual(build["lock_acquire"], "exclusive_create_or_fail_fast")
        self.assertEqual(build["target_parent"], "dist")
        self.assertEqual(build["staging_name"], "target_name_dot_128_bit_csprng_hex_dot_staging")
        self.assertEqual(build["backup_name"], "target_name_dot_same_128_bit_csprng_hex_dot_backup")
        self.assertEqual(build["atomic_publish"], "per_rename_same_filesystem_only")
        self.assertEqual(
            build["promotion_state_machine"],
            ["lock", "stage", "fsync_stage", "validate_stage", "backup_old", "promote_new", "fsync_parent", "verify_target", "remove_backup", "unlock"],
        )
        self.assertEqual(build["crash_recovery"], "explicit_recover_from_journal_or_fail_closed_on_ambiguity")


if __name__ == "__main__":
    unittest.main()
