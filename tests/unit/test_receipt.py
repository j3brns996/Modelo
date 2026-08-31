from __future__ import annotations

import hashlib
import itertools
import unittest

from modelo.receipt import (
    canonical_bytes, catalogue_projection, change_delta_bytes, manifest_entries, publication_digest,
    sha256_bytes, sort_change_delta,
)


class ReceiptTests(unittest.TestCase):
    def test_canonical_bytes_have_one_lf_and_tampering_changes_digest(self) -> None:
        value = {"z": 1, "a": "é"}
        encoded = canonical_bytes(value)
        self.assertEqual(encoded, b'{"a":"\xc3\xa9","z":1}\n')
        self.assertNotEqual(sha256_bytes(encoded), sha256_bytes(encoded[:-1]))

    def test_delta_permutations_are_byte_identical(self) -> None:
        digest = "sha256:" + "a" * 64
        values = [
            {"operation": "change", "path": "catalogue/models/b.yaml", "before": digest, "after": digest},
            {"operation": "add", "path": "catalogue/models/a.yaml", "after": digest},
            {"operation": "revoke", "path": "catalogue/offerings/x/c.yaml", "before": digest, "reason": "x", "effective_at": "2026-08-30T00:00:00Z"},
        ]
        outputs = {change_delta_bytes(permutation) for permutation in itertools.permutations(values)}
        self.assertEqual(len(outputs), 1)
        self.assertEqual([item["operation"] for item in sort_change_delta(values)], ["add", "change", "revoke"])

    def test_publication_digest_is_exact_and_order_independent(self) -> None:
        files = {"b": b"two", "a": b"one"}
        reversed_files = dict(reversed(list(files.items())))
        self.assertEqual(publication_digest(files), publication_digest(reversed_files))
        records = (
            b"a\0" + sha256_bytes(b"one").encode() + b"\0" + b"3\n"
            + b"b\0" + sha256_bytes(b"two").encode() + b"\0" + b"3\n"
        )
        self.assertEqual(publication_digest(files), "sha256:" + hashlib.sha256(records).hexdigest())
        entries = manifest_entries(files)
        self.assertEqual(entries["a"]["size"], 3)

    def test_projection_sorts_routes_and_rewrites_fact_pointers(self) -> None:
        offering = {
            "id": "o", "inference_service_id": "svc", "model_id": "m",
            "routes": [
                {"id": "z", "source_region": "us-east-1", "reference": "z", "model_binding": {}},
                {"id": "a", "source_region": "eu-west-2", "reference": "a", "model_binding": {}},
            ],
            "condition_refs": [{"id": "z", "version": 2}, {"id": "a", "version": 1}],
            "pricing": [
                {"dimension": "output", "unit": "token", "quantity": 1000, "amount": "2", "currency": "USD", "route_ids": ["z", "a"]},
                {"dimension": "input", "unit": "token", "quantity": 1, "amount": "1", "currency": "USD", "route_ids": ["a"]},
            ],
            "evidence_refs": {
                "/routes/0/reference": {"id": "e", "projection_pointer": "/z"},
                "/pricing/0/amount": {"id": "e", "projection_pointer": "/price"},
            },
        }
        projection = catalogue_projection(
            contract_version="0.1.0", source_commit="a" * 40, source_tree="b" * 40,
            as_of="2026-08-30", profile="synthetic", models=[], offerings=[offering],
            evidence=[{"id": "e", "projection": {"ordered": [2, 1]}}], conditions=[],
            vendors={"vendors": {}}, inference_services={"inference_services": {}},
            freshness={"classes_days": {}},
        )
        normal = projection["offerings"][0]
        self.assertEqual([route["id"] for route in normal["routes"]], ["a", "z"])
        self.assertIn("/routes/1/reference", normal["evidence_refs"])
        self.assertEqual([price["dimension"] for price in normal["pricing"]], ["input", "output"])
        self.assertIn("/pricing/1/amount", normal["evidence_refs"])
        self.assertEqual(projection["evidence"][0]["projection"]["ordered"], [2, 1])

    def test_two_source_region_profile_permutation_is_byte_identical(self) -> None:
        def offering(order):
            routes_by_id = {
                "eu-route": {
                    "id": "eu-route", "source_region": "eu-west-2",
                    "reference": "global.test.profile-v1",
                    "model_binding": {
                        "kind": "system-inference-profile",
                        "profile_evidence": {"id": "e-eu", "projection_pointer": "/profileId", "type_pointer": "/type", "status_pointer": "/status", "destinations_pointer": "/models"},
                        "destinations": [{"destination_pointer": "/models/0/modelArn", "model_evidence": {"id": "m-eu", "arn_pointer": "/modelArn", "name_pointer": "/modelName", "provider_pointer": "/providerName"}}],
                    },
                },
                "us-route": {
                    "id": "us-route", "source_region": "us-east-1",
                    "reference": "global.test.profile-v1",
                    "model_binding": {
                        "kind": "system-inference-profile",
                        "profile_evidence": {"id": "e-us", "projection_pointer": "/profileId", "type_pointer": "/type", "status_pointer": "/status", "destinations_pointer": "/models"},
                        "destinations": [{"destination_pointer": "/models/1/modelArn", "model_evidence": {"id": "m-us", "arn_pointer": "/modelArn", "name_pointer": "/modelName", "provider_pointer": "/providerName"}}],
                    },
                },
            }
            routes = [routes_by_id[identifier] for identifier in order]
            return {
                "id": "o", "inference_service_id": "svc", "model_id": "m",
                "routes": routes,
                "pricing": [{"dimension": "input", "unit": "token", "quantity": 1, "amount": "1", "currency": "USD", "route_ids": list(reversed(order))}],
                "condition_refs": [],
                "evidence_refs": {
                    f"/routes/{index}/reference": {
                        "id": routes_by_id[identifier]["model_binding"]["profile_evidence"]["id"],
                        "projection_pointer": "/profileId",
                    }
                    for index, identifier in enumerate(order)
                },
            }

        common = {
            "contract_version": "0.1.0", "source_commit": "a" * 40,
            "source_tree": "b" * 40, "as_of": "2026-08-30", "profile": "synthetic",
            "models": [], "evidence": [], "conditions": [],
            "vendors": {"vendors": {}},
            "inference_services": {"inference_services": {}},
            "freshness": {"classes_days": {}},
        }
        first = catalogue_projection(offerings=[offering(["eu-route", "us-route"])], **common)
        second = catalogue_projection(offerings=[offering(["us-route", "eu-route"])], **common)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        normal = first["offerings"][0]
        self.assertEqual([route["id"] for route in normal["routes"]], ["eu-route", "us-route"])
        self.assertEqual(normal["pricing"][0]["route_ids"], ["eu-route", "us-route"])
        self.assertEqual(normal["evidence_refs"]["/routes/0/reference"]["id"], "e-eu")
        self.assertEqual(normal["evidence_refs"]["/routes/1/reference"]["id"], "e-us")


if __name__ == "__main__":
    unittest.main()
