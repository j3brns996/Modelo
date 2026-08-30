from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
CASES = ROOT / "tests/fixtures/schema/cases.json"
MAC_FIXTURES = ROOT / "tests/fixtures/mac"


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


if __name__ == "__main__":
    unittest.main()
