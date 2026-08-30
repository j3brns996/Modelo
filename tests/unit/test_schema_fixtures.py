from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
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

REQUIRED_PUBLICATION_FILES = {
    "404.html",
    "assets/catalogue.js",
    "assets/site.css",
    "catalogue/index.html",
    "changes/index.html",
    "data/catalogue.json",
    "docs/index.html",
    "index.html",
    "process/index.html",
    "propose/index.html",
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
        self.assertEqual(files["required"], ["data/catalogue.json"])
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

    def test_modelo_removes_legacy_publication_path_and_disables_agent_approval(self) -> None:
        config = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("publication_profiles", config["paths"])
        self.assertNotIn("site_output", config["paths"])
        approval = config["platform"]["optional_capabilities"]["agent_approval"]
        self.assertIs(approval["enabled"], False)
        self.assertEqual(approval["registry"], config["paths"]["actors_registry"])
        self.assertEqual(
            config["platform"]["required_capabilities"]["trusted_pipeline"]["gitlab"],
            "pipeline_execution_policy_or_equivalent",
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
        self.assertEqual(manifest_schema["x-modelo-executable-completeness-owner"], "T6")
        self.assertEqual(
            manifest_schema["x-modelo-executable-completeness"],
            "files_keys_equal_contract_fixed_union_projection_derived_excluding_manifest",
        )
        configured = set(contract["build"]["manifest_required_fixed_files"])
        self.assertEqual(configured, REQUIRED_PUBLICATION_FILES)
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
            {"kind", "source_commit", "source_tree", "as_of", "source_date_epoch", "mac_metadata", "profile", "base_path", "output"},
        )
        self.assertEqual(set(build["final_required_cli_arguments"]), {"merge_commit", "merge_tree"})
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
