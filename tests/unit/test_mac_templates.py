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
            "^[a-z0-9](?:[a-z0-9._:/@+\\-]*[a-z0-9])?(?![\\s\\S])",
        )
        self.assertEqual(
            schema["$defs"]["text"]["pattern"],
            "^[^\\u0000-\\u0020\\u007f-\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000](?:[^\\u0000-\\u001f\\u007f-\\u009f]*[^\\u0000-\\u0020\\u007f-\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000])?(?![\\s\\S])",
        )
        for definition in ("subject", "batchScope", "candidateEvidence"):
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])

    def test_security_patterns_never_use_ambiguous_dollar_anchor(self) -> None:
        schema = json.loads((ROOT / "schemas/mac.schema.json").read_text(encoding="utf-8"))

        def patterns(value: object) -> list[str]:
            if isinstance(value, dict):
                found = [value["pattern"]] if isinstance(value.get("pattern"), str) else []
                for child in value.values():
                    found.extend(patterns(child))
                return found
            if isinstance(value, list):
                return [pattern for child in value for pattern in patterns(child)]
            return []

        security_patterns = patterns(schema)
        self.assertTrue(security_patterns)
        for pattern in security_patterns:
            with self.subTest(pattern=pattern):
                self.assertNotIn("$", pattern)
                self.assertTrue(pattern.endswith("(?![\\s\\S])"))

    def test_github_issue_forms_are_valid_and_operation_specific(self) -> None:
        paths = sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("mac-*.yml"))
        self.assertEqual({path.stem.removeprefix("mac-") for path in paths}, OPERATIONS)
        for path in paths:
            operation = path.stem.removeprefix("mac-")
            form = yaml.safe_load(path.read_text(encoding="utf-8"))
            with self.subTest(operation=operation):
                self.assertEqual(set(form), {"name", "description", "title", "body"})
                fields = [item for item in form["body"] if item["type"] != "markdown"]
                self.assertNotIn("mac_payload", {item["id"] for item in fields})
                self.assertNotIn("payload_digest", {item["id"] for item in fields})
                request_type = next(item for item in fields if item["id"] == "request_type")
                self.assertEqual(request_type["type"], "dropdown")
                self.assertEqual(request_type["attributes"]["options"], [operation])
                self.assertTrue(request_type["validations"]["required"])
                for required in ("purpose", "requested_outcome", "reason", "acceptance"):
                    self.assertIn(required, {item["id"] for item in fields})
                self.assertNotIn("labels", form)

        add_form = yaml.safe_load(
            (ROOT / ".github/ISSUE_TEMPLATE/mac-add.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(add_form["name"], "Add a catalogue record")

    def test_github_issue_forms_explain_the_request_in_plain_language(self) -> None:
        expected = {
            "add": "Add something new",
            "change": "Update an existing record",
            "revoke": "Withdraw an approved offering",
            "move": "Replace an offering identity",
            "batch": "Submit several related changes",
        }
        for operation, heading in expected.items():
            form = yaml.safe_load(
                (ROOT / f".github/ISSUE_TEMPLATE/mac-{operation}.yml").read_text(encoding="utf-8")
            )
            rendered = "\n".join(
                item.get("attributes", {}).get("value", "")
                for item in form["body"] if item["type"] == "markdown"
            )
            with self.subTest(operation=operation):
                self.assertIn(heading, rendered)
                self.assertIn("What happens next", rendered)
                self.assertNotIn("Change details (JSON)", rendered)
                self.assertNotIn("Change fingerprint", rendered)

    def test_github_issue_form_common_fields_match_the_trusted_compiler(self) -> None:
        common = {
            "request_type": ("Modelo MAC request type", True),
            "purpose": ("Purpose", True),
            "requested_outcome": ("Requested outcome", True),
            "reason": ("Why is this needed?", True),
            "candidate_evidence": ("Supporting observations", False),
            "acceptance": ("Acceptance checks", True),
        }
        specific = {
            "add": {"subject_kind": "Subject type", "subject_identity": "Subject identity"},
            "change": {"subject_kind": "Subject type", "subject_identity": "Subject identity"},
            "revoke": {"subject_identity": "Offering identity"},
            "move": {
                "source_identity": "Current offering identity",
                "destination_identity": "Replacement offering identity",
            },
            "batch": {
                "item_operation": "Batch change type",
                "subject_kind": "Subject type",
                "subject_identities": "Subject identities",
                "source_type": "Evidence source type",
                "source_url": "Evidence source URL",
                "scope_ref": "Opaque scope reference",
                "partition": "Provider partition",
                "region": "Source region",
                "inference_service": "Inference service",
            },
        }
        for operation, operation_fields in specific.items():
            form = yaml.safe_load(
                (ROOT / f".github/ISSUE_TEMPLATE/mac-{operation}.yml").read_text(encoding="utf-8")
            )
            fields = {
                item["id"]: item for item in form["body"]
                if item["type"] != "markdown"
            }
            with self.subTest(operation=operation):
                self.assertEqual(set(fields), set(common) | set(operation_fields) | {"final_checks"})
                for field_id, (label, required) in common.items():
                    self.assertEqual(fields[field_id]["attributes"]["label"], label)
                    self.assertIs(fields[field_id]["validations"]["required"], required)
                for field_id, label in operation_fields.items():
                    self.assertEqual(fields[field_id]["attributes"]["label"], label)
                    self.assertTrue(fields[field_id]["validations"]["required"])
                self.assertEqual(fields["final_checks"]["attributes"]["label"], "Before submitting")
                self.assertTrue(all(
                    option["required"]
                    for option in fields["final_checks"]["attributes"]["options"]
                ))

        batch_description = next(
            item["attributes"]["description"]
            for item in yaml.safe_load(
                (ROOT / ".github/ISSUE_TEMPLATE/mac-batch.yml").read_text(encoding="utf-8")
            )["body"]
            if item.get("id") == "subject_kind"
        )
        self.assertIn("Revoke batches support offerings only", batch_description)

    def test_github_issue_contact_link_is_derived_from_site_config(self) -> None:
        repository = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        chooser = yaml.safe_load(
            (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
        )
        expected = (
            repository["site"]["base_url"].rstrip("/")
            + repository["site"]["routes"]["process"]
        )
        self.assertEqual(len(chooser["contact_links"]), 1)
        self.assertEqual(chooser["contact_links"][0]["url"], expected)

    def test_pull_request_templates_lead_with_decision_and_evidence(self) -> None:
        mac = (ROOT / ".github/PULL_REQUEST_TEMPLATE/mac.md").read_text(encoding="utf-8")
        control = (ROOT / ".github/PULL_REQUEST_TEMPLATE/control.md").read_text(encoding="utf-8")
        for heading in ("Decision requested", "Why this should change", "Evidence", "Reviewer decision"):
            self.assertIn(heading, mac)
        for heading in ("Outcome", "Why now", "Risk and rollback", "Verification", "Reviewer decision"):
            self.assertIn(heading, control)
        self.assertNotIn("Bootstrap exception", control)

    def test_control_issue_form_captures_outcome_scope_risk_and_acceptance(self) -> None:
        form = yaml.safe_load(
            (ROOT / ".github/ISSUE_TEMPLATE/control-change.yml").read_text(encoding="utf-8")
        )
        fields = {
            item["id"]: item for item in form["body"] if item["type"] != "markdown"
        }
        self.assertEqual(
            set(fields), {"problem", "outcome", "scope", "risk", "acceptance", "final_checks"}
        )
        for field in ("problem", "outcome", "scope", "risk", "acceptance"):
            self.assertTrue(fields[field]["validations"]["required"])
        self.assertNotIn("Request type", {
            item["attributes"].get("label") for item in form["body"]
            if item["type"] != "markdown"
        })

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
        body = self.fill_gitlab_template("add", payload)
        self.assertLessEqual(len(body.encode("utf-8")), MAX_BODY_BYTES)
        self.assertEqual(extract_adapter_issue_payload(body, "gitlab"), payload)

    def test_change_request_templates_have_identical_neutral_contract(self) -> None:
        github = (ROOT / ".github/PULL_REQUEST_TEMPLATE/mac.md").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab/merge_request_templates/MAC.md").read_text(encoding="utf-8")
        self.assertEqual(github, gitlab)
        for required in ("Issue:", "Neutral payload digest:", "Affected logical identities:"):
            self.assertIn(required, github)
        self.assertIn("assertions, not evidence", github)

    def test_later_slices_add_only_the_declared_bootstrap_surfaces(self) -> None:
        self.assertTrue((ROOT / ".github/workflows/modelo.yml").is_file())
        self.assertTrue((ROOT / ".agents/skills").is_dir())
        self.assertEqual(
            {path.relative_to(ROOT / "catalogue").as_posix() for path in (ROOT / "catalogue").rglob("*") if path.is_file()},
            set(),
        )
        self.assertTrue((ROOT / "site").is_dir())

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

    def test_schema_and_module_true_end_of_input_parity_corpus(self) -> None:
        schema = json.loads((ROOT / "schemas/mac.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        separators = {
            "lf": "\n",
            "cr": "\r",
            "line-separator": "\u2028",
            "paragraph-separator": "\u2029",
        }

        for separator_name, separator in separators.items():
            for placement in ("leading", "trailing"):
                text_value = separator + "value" if placement == "leading" else "value" + separator
                uri_value = (
                    separator + "https://example.invalid/path"
                    if placement == "leading"
                    else "https://example.invalid/path" + separator
                )
                cases = (
                    ("reason", "add", ("reason",), text_value),
                    ("purpose", "add", ("purpose",), text_value),
                    (
                        "scope_ref",
                        "batch",
                        ("batch_scope", "observation_scope", "scope_ref"),
                        text_value,
                    ),
                    (
                        "candidate_uri",
                        "add",
                        ("candidate_evidence", 0, "uri"),
                        uri_value,
                    ),
                )
                for field, fixture, path, value in cases:
                    payload = self.fixtures()[fixture]
                    target: object = payload
                    for segment in path[:-1]:
                        target = target[segment]  # type: ignore[index]
                    target[path[-1]] = value  # type: ignore[index]

                    schema_accepts = not list(validator.iter_errors(payload))
                    try:
                        validate_payload(payload, verify_hashes=False)
                        module_accepts = True
                    except ValueError:
                        module_accepts = False
                    with self.subTest(
                        separator=separator_name,
                        placement=placement,
                        field=field,
                    ):
                        self.assertFalse(schema_accepts)
                        self.assertFalse(module_accepts)
                        self.assertEqual(schema_accepts, module_accepts)


if __name__ == "__main__":
    unittest.main()
