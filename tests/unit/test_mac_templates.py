from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
OPERATIONS = {"add", "change", "revoke", "move", "batch"}


class MacTemplateTests(unittest.TestCase):
    def test_schema_is_draft_2020_12_and_closed(self) -> None:
        schema = json.loads((ROOT / "schemas/mac.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]["operation"]["enum"]), OPERATIONS)
        self.assertEqual(schema["properties"]["subjects"]["maxItems"], 25)
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


if __name__ == "__main__":
    unittest.main()
