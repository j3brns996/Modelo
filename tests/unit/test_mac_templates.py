from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from modelo.mac import (
    MAX_ADAPTER_OVERHEAD_BYTES,
    MAX_BODY_BYTES,
    extract_adapter_issue_payload,
    payload_digest,
    with_computed_keys,
    validate_payload,
)


ROOT = Path(__file__).resolve().parents[2]
OPERATIONS = {"add", "change", "revoke", "move", "batch"}


class MacTemplateTests(unittest.TestCase):
    def fixtures(self) -> dict[str, dict[str, object]]:
        return {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((ROOT / "tests/fixtures/mac").glob("*.json"))
        }

    def fill_github_form(self, operation: str, payload: dict[str, object]) -> str:
        path = ROOT / f".github/ISSUE_TEMPLATE/mac-{operation}.yml"
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        pretty = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        sections: list[str] = []
        for item in form["body"]:
            if item["type"] == "textarea" and item["id"] == "mac_payload":
                sections.append(f"### {item['attributes']['label']}\n\n```json\n{pretty}\n```")
            elif item["type"] == "input" and item["id"] == "payload_digest":
                sections.append(f"### {item['attributes']['label']}\n\n{payload_digest(payload)}")
            elif item["type"] == "checkboxes":
                choices = "\n".join(f"- [x] {choice['label']}" for choice in item["attributes"]["options"])
                sections.append(f"### {item['attributes']['label']}\n\n{choices}")
        return "\n\n".join(sections) + "\n"

    def fill_gitlab_template(self, operation: str, payload: dict[str, object]) -> str:
        path = ROOT / f".gitlab/issue_templates/MAC-{operation.title()}.md"
        text = path.read_text(encoding="utf-8")
        pretty = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        text, count = re.subn(r"(?ms)```json\n[\s\S]*?\n```", f"```json\n{pretty}\n```", text)
        self.assertEqual(count, 1)
        return text.replace("Neutral payload digest: `sha256-...`", f"Neutral payload digest: `{payload_digest(payload)}`")

    def test_schema_is_draft_2020_12_and_closed(self) -> None:
        schema = json.loads((ROOT / "schemas/mac.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]["operation"]["enum"]), OPERATIONS)
        self.assertEqual(schema["properties"]["subjects"]["maxItems"], 25)
        self.assertEqual(
            schema["$defs"]["identity"]["pattern"],
            "^[a-z0-9](?:[a-z0-9._:/@+\\-]*[a-z0-9])?$",
        )
        self.assertEqual(
            schema["$defs"]["text"]["pattern"],
            "^[^\\u0000-\\u0020\\u007f-\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000](?:[^\\u0000-\\u001f\\u007f-\\u009f]*[^\\u0000-\\u0020\\u007f-\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000])?$",
        )
        for definition in ("subject", "batchScope", "candidateEvidence"):
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])

    def test_github_issue_forms_are_valid_and_operation_specific(self) -> None:
        paths = sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("mac-*.yml"))
        self.assertEqual({path.stem.removeprefix("mac-") for path in paths}, OPERATIONS)
        for path in paths:
            operation = path.stem.removeprefix("mac-")
            form = yaml.safe_load(path.read_text(encoding="utf-8"))
            with self.subTest(operation=operation):
                self.assertEqual(set(form), {"name", "description", "title", "body"})
                textareas = [item for item in form["body"] if item["type"] == "textarea"]
                self.assertEqual([item["id"] for item in textareas], ["mac_payload"])
                self.assertEqual(textareas[0]["attributes"]["render"], "json")
                self.assertTrue(textareas[0]["validations"]["required"])
                self.assertIn(f'"operation": "{operation}"', textareas[0]["attributes"]["placeholder"])
                inputs = [item for item in form["body"] if item["type"] == "input"]
                self.assertEqual([item["id"] for item in inputs], ["payload_digest"])
                self.assertTrue(inputs[0]["validations"]["required"])
                self.assertNotIn("labels", form)

    def test_actual_filled_github_forms_round_trip(self) -> None:
        for operation, payload in self.fixtures().items():
            body = self.fill_github_form(operation, payload)
            with self.subTest(operation=operation):
                self.assertLessEqual(len(body.encode("utf-8")), MAX_BODY_BYTES)
                self.assertEqual(extract_adapter_issue_payload(body, "github"), payload)
                rendered_payload = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                self.assertLessEqual(
                    len(body.encode("utf-8")) - len(rendered_payload.encode("utf-8")),
                    MAX_ADAPTER_OVERHEAD_BYTES,
                )

    def test_gitlab_templates_are_operation_specific_and_inert(self) -> None:
        paths = sorted((ROOT / ".gitlab/issue_templates").glob("MAC-*.md"))
        self.assertEqual({path.stem.removeprefix("MAC-").lower() for path in paths}, OPERATIONS)
        for path in paths:
            operation = path.stem.removeprefix("MAC-").lower()
            text = path.read_text(encoding="utf-8")
            with self.subTest(operation=operation):
                self.assertIn(f'"operation": "{operation}"', text)
                self.assertIn("```json", text)
                self.assertIn("Neutral payload digest: `sha256-...`", text)
                self.assertNotIn("/label", text)
                self.assertNotIn("curl ", text)

    def test_actual_filled_gitlab_templates_round_trip(self) -> None:
        for operation, payload in self.fixtures().items():
            body = self.fill_gitlab_template(operation, payload)
            with self.subTest(operation=operation):
                self.assertLessEqual(len(body.encode("utf-8")), MAX_BODY_BYTES)
                self.assertEqual(extract_adapter_issue_payload(body, "gitlab"), payload)
                rendered_payload = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                self.assertLessEqual(
                    len(body.encode("utf-8")) - len(rendered_payload.encode("utf-8")),
                    MAX_ADAPTER_OVERHEAD_BYTES,
                )

    def test_near_limit_payload_round_trips_through_actual_templates(self) -> None:
        payload = self.fixtures()["add"]
        payload["acceptance"] = [f"criterion-{index}-" + "a" * 1_960 for index in range(25)]
        payload["candidate_evidence"] = [
            {
                "uri": "https://example.invalid/" + "e" * 900 + f"/{index}",
                "observed_at": "2026-08-30T12:00:00Z",
                "digest": "sha256-" + f"{index:064x}",
            }
            for index in range(10)
        ]
        payload = with_computed_keys(payload)
        for adapter, body in (
            ("github", self.fill_github_form("add", payload)),
            ("gitlab", self.fill_gitlab_template("add", payload)),
        ):
            with self.subTest(adapter=adapter):
                self.assertLessEqual(len(body.encode("utf-8")), MAX_BODY_BYTES)
                self.assertEqual(extract_adapter_issue_payload(body, adapter), payload)

    def test_change_request_templates_have_identical_neutral_contract(self) -> None:
        github = (ROOT / ".github/PULL_REQUEST_TEMPLATE/mac.md").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab/merge_request_templates/MAC.md").read_text(encoding="utf-8")
        self.assertEqual(github, gitlab)
        for required in ("Issue:", "Neutral payload digest:", "Affected logical identities:"):
            self.assertIn(required, github)
        self.assertIn("assertions, not evidence", github)

    def test_t7_does_not_add_workflows_site_skills_or_catalogue(self) -> None:
        for relative in (".github/workflows", "site", ".agents/skills", "catalogue"):
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_schema_and_module_text_parity_corpus(self) -> None:
        schema = json.loads((ROOT / "schemas/mac.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        base = self.fixtures()["add"]
        cases = (
            ("", False),
            ("plain", True),
            ("two words", True),
            ("internal\u00a0space", True),
            ("Unicode café", True),
            (" leading", False),
            ("trailing ", False),
            ("\u00a0leading-nbsp", False),
            ("trailing-nbsp\u00a0", False),
            ("\u1680leading-ogham", False),
            ("trailing-em-space\u2003", False),
            ("line\nbreak", False),
            ("tab\tinside", False),
            ("c1\u0085control", False),
            ("delete\u007fcontrol", False),
            ("a" * 2_048, True),
            ("a" * 2_049, False),
        )
        for value, expected in cases:
            payload = json.loads(json.dumps(base))
            payload["reason"] = value
            schema_accepts = not list(validator.iter_errors(payload))
            try:
                validate_payload(payload, verify_hashes=False)
                module_accepts = True
            except ValueError:
                module_accepts = False
            with self.subTest(value=repr(value)):
                self.assertEqual(schema_accepts, expected)
                self.assertEqual(module_accepts, expected)
                self.assertEqual(schema_accepts, module_accepts)

    def test_schema_and_module_https_uri_parity_corpus(self) -> None:
        schema = json.loads((ROOT / "schemas/mac.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        cases = (
            ("https://example.invalid", True),
            ("https://docs.example.invalid/path/to/item", True),
            ("https://example.invalid/path?key=value&other=2#section", True),
            ("https://EXAMPLE.invalid/Path", True),
            ("https://127.0.0.1/resource", True),
            ("http://example.invalid/path", False),
            ("HTTPS://example.invalid/path", False),
            ("https://user@example.invalid/path", False),
            ("https://user:secret@example.invalid/path", False),
            ("https://example.invalid:443/path", False),
            ("https://[2001:db8::1]/path", False),
            ("https://example_invalid/path", False),
            ("https://example.invalid./path", False),
            ("https:///missing-host", False),
            ("https://example.invalid/a path", False),
            ("https://example.invalid/café", False),
            ("https://example.invalid/line\nbreak", False),
            ("https://example.invalid/" + "a" * 2_024, True),
            ("https://example.invalid/" + "a" * 2_025, False),
        )
        for uri, expected in cases:
            for fixture, pointer in (("add", "candidate"), ("batch", "source")):
                payload = self.fixtures()[fixture]
                if pointer == "candidate":
                    payload["candidate_evidence"][0]["uri"] = uri
                else:
                    payload["batch_scope"]["source"]["uri"] = uri
                schema_accepts = not list(validator.iter_errors(payload))
                try:
                    validate_payload(payload, verify_hashes=False)
                    module_accepts = True
                except ValueError:
                    module_accepts = False
                with self.subTest(uri=uri, pointer=pointer):
                    self.assertEqual(schema_accepts, expected)
                    self.assertEqual(module_accepts, expected)
                    self.assertEqual(schema_accepts, module_accepts)


if __name__ == "__main__":
    unittest.main()
