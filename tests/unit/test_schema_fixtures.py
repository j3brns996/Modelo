from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
CASES = ROOT / "tests/fixtures/schema/cases.json"


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
    else:
        raise AssertionError(f"unknown fixture mutation {mutation['op']!r}")
    return changed


class SchemaFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas, cls.registry = _schemas()
        cls.cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]

    def test_every_non_common_schema_has_fixtures(self) -> None:
        expected = set(self.schemas) - {"common.schema.json"}
        actual = {case["schema"] for case in self.cases}
        self.assertEqual(actual, expected)

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
                valid = case["valid"]
            for index, instance in enumerate(valid):
                with self.subTest(schema=case["schema"], valid=index):
                    errors = list(validator.iter_errors(instance))
                    self.assertEqual(errors, [], [error.message for error in errors])
            for mutation in case["invalid"]:
                source = valid[mutation.get("valid_index", 0)]
                instance = _mutate(source, mutation)
                with self.subTest(schema=case["schema"], invalid=mutation["name"]):
                    self.assertNotEqual(list(validator.iter_errors(instance)), [])


if __name__ == "__main__":
    unittest.main()
