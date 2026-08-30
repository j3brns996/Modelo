from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from modelo.mac import (
    MAX_ADAPTER_OVERHEAD_BYTES,
    MAX_BODY_BYTES,
    MAX_RENDERED_PAYLOAD_BYTES,
    MacError,
    compute_keys,
    extract_adapter_issue_payload,
    extract_issue_payload,
    payload_digest,
    render_adapter_issue_body,
    render_issue_body,
    validate_payload,
    with_computed_keys,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/mac"


class MacTests(unittest.TestCase):
    def fixtures(self) -> dict[str, dict[str, object]]:
        return {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(FIXTURES.glob("*.json"))
        }

    def test_all_operation_fixtures_validate_with_exact_hashes(self) -> None:
        fixtures = self.fixtures()
        self.assertEqual(set(fixtures), {"add", "change", "revoke", "move", "batch"})
        for operation, payload in fixtures.items():
            with self.subTest(operation=operation):
                self.assertEqual(validate_payload(payload), payload)
                self.assertEqual(payload["operation"], operation)
                self.assertEqual(compute_keys(payload), (payload["dedupe_key"], payload["idempotency_key"]))
                self.assertRegex(payload_digest(payload), r"^sha256-[0-9a-f]{64}$")

    def test_github_and_gitlab_transports_round_trip_to_identical_objects(self) -> None:
        for name, payload in self.fixtures().items():
            github = render_issue_body(payload, "github")
            gitlab = render_issue_body(payload, "gitlab")
            with self.subTest(operation=name):
                self.assertNotEqual(github, gitlab)
                self.assertEqual(extract_issue_payload(github), payload)
                self.assertEqual(extract_issue_payload(gitlab), payload)
                self.assertEqual(
                    extract_adapter_issue_payload(render_adapter_issue_body(payload, "github"), "github"),
                    payload,
                )
                self.assertEqual(
                    extract_adapter_issue_payload(render_adapter_issue_body(payload, "gitlab"), "gitlab"),
                    payload,
                )

    def test_request_id_is_omitted_from_both_keys(self) -> None:
        payload = self.fixtures()["add"]
        changed = deepcopy(payload)
        changed["request_id"] = "00000000-0000-4000-8000-000000000099"
        changed = with_computed_keys(changed)
        self.assertEqual(compute_keys(payload), compute_keys(changed))
        self.assertNotEqual(payload_digest(payload), payload_digest(changed))

    def test_evidence_changes_idempotency_but_not_reservation(self) -> None:
        payload = self.fixtures()["change"]
        changed = deepcopy(payload)
        changed["candidate_evidence"][0]["digest"] = "sha256-" + "9" * 64
        changed = with_computed_keys(changed)
        self.assertEqual(payload["dedupe_key"], changed["dedupe_key"])
        self.assertNotEqual(payload["idempotency_key"], changed["idempotency_key"])

    def test_subject_order_does_not_change_reservation_key(self) -> None:
        payload = self.fixtures()["batch"]
        changed = deepcopy(payload)
        changed["subjects"].reverse()
        changed = with_computed_keys(changed)
        self.assertEqual(payload["dedupe_key"], changed["dedupe_key"])
        self.assertNotEqual(payload["idempotency_key"], changed["idempotency_key"])

    def test_semantic_constraints_fail_closed(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []
        add = self.fixtures()["add"]
        bad = deepcopy(add)
        bad["subjects"].append(deepcopy(bad["subjects"][0]))
        cases.append(("duplicate subject", bad))
        bad = deepcopy(add)
        bad["batch_scope"] = {}
        cases.append(("batch field on add", bad))
        move = self.fixtures()["move"]
        bad = deepcopy(move)
        bad["subjects"][1]["role"] = "source"
        cases.append(("two move sources", bad))
        revoke = self.fixtures()["revoke"]
        bad = deepcopy(revoke)
        bad["subjects"][0]["kind"] = "model"
        cases.append(("revoke model", bad))
        batch = self.fixtures()["batch"]
        bad = deepcopy(batch)
        bad["subjects"] = bad["subjects"] * 13
        cases.append(("batch over 25", bad))
        bad = deepcopy(add)
        bad["candidate_evidence"][0]["uri"] = "http://example.invalid/not-https"
        cases.append(("non-https evidence", bad))
        bad = deepcopy(add)
        bad["candidate_evidence"][0]["observed_at"] = "2026-99-99T12:00:00Z"
        cases.append(("impossible timestamp", bad))
        for identity in ("Uppercase", "not portable", "café"):
            bad = deepcopy(add)
            bad["subjects"][0]["identity"] = identity
            cases.append((f"non-canonical identity {identity!r}", bad))
        bad = deepcopy(add)
        bad["reason"] = "line one\nline two"
        cases.append(("control character in text", bad))
        for name, payload in cases:
            with self.subTest(name=name), self.assertRaises(MacError):
                validate_payload(payload, verify_hashes=False)

    def test_hash_mismatch_and_unknown_field_fail(self) -> None:
        payload = self.fixtures()["add"]
        for mutation in ("hash", "unknown"):
            changed = deepcopy(payload)
            if mutation == "hash":
                changed["dedupe_key"] = "sha256-" + "f" * 64
            else:
                changed["approval"] = True
            with self.subTest(mutation=mutation), self.assertRaises(MacError):
                validate_payload(changed)

    def test_transport_rejects_ambiguous_or_tampered_content(self) -> None:
        payload = self.fixtures()["add"]
        body = render_issue_body(payload, "github")
        cases = {
            "missing marker": body.replace("<!-- modelo:mac-payload:start -->", ""),
            "duplicate marker": body + "\n<!-- modelo:mac-payload:start -->\n",
            "wrong digest": body.replace(payload_digest(payload), "sha256-" + "f" * 64),
            "oversized": "x" * (MAX_BODY_BYTES + 1),
            "duplicate key": body.replace('"schema_version": "0.1",', '"schema_version": "0.1",\n  "schema_version": "0.1",'),
        }
        for name, candidate in cases.items():
            with self.subTest(name=name), self.assertRaises(MacError):
                extract_issue_payload(candidate)

    def test_helpers_do_not_mutate_callers(self) -> None:
        payload = self.fixtures()["batch"]
        before = deepcopy(payload)
        validate_payload(payload)
        compute_keys(payload)
        render_issue_body(payload, "github")
        self.assertEqual(payload, before)

    def test_aggregate_render_bound_accepts_large_valid_payload(self) -> None:
        payload = deepcopy(self.fixtures()["add"])
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
        rendered_size = len(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        )
        self.assertGreater(rendered_size, 60_000)
        self.assertLessEqual(rendered_size, MAX_RENDERED_PAYLOAD_BYTES)
        for adapter in ("github", "gitlab"):
            body = render_adapter_issue_body(payload, adapter)
            self.assertLessEqual(len(body.encode("utf-8")), MAX_BODY_BYTES)
            self.assertEqual(extract_adapter_issue_payload(body, adapter), payload)
        canonical_body = render_issue_body(payload, "github")
        self.assertLessEqual(len(canonical_body.encode("utf-8")), MAX_BODY_BYTES)
        self.assertLessEqual(
            len(canonical_body.encode("utf-8")) - rendered_size,
            MAX_ADAPTER_OVERHEAD_BYTES,
        )

    def test_aggregate_render_bound_rejects_oversized_payload(self) -> None:
        payload = deepcopy(self.fixtures()["add"])
        payload["acceptance"] = [f"criterion-{index}-" + "a" * 2_000 for index in range(25)]
        payload["candidate_evidence"] = [
            {
                "uri": "https://example.invalid/" + "e" * 1_900 + f"/{index}",
                "observed_at": "2026-08-30T12:00:00Z",
                "digest": "sha256-" + f"{index:064x}",
            }
            for index in range(25)
        ]
        with self.assertRaisesRegex(MacError, "rendered canonical payload exceeds"):
            with_computed_keys(payload)


if __name__ == "__main__":
    unittest.main()
