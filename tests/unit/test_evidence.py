from __future__ import annotations

import unittest

from modelo.evidence import canonical_json, evidence_id, resolve_pointer


class EvidenceTests(unittest.TestCase):
    def test_canonicalisation_is_deterministic_and_utf16_sorted(self) -> None:
        first = {"\U00010000": 1, "\ue000": 2, "a": [True, None, "x"]}
        second = dict(reversed(tuple(first.items())))
        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertLess(canonical_json(first).index("𐀀"), canonical_json(first).index(""))

    def test_content_address_omits_only_root_id(self) -> None:
        document = {"id": "wrong", "projection": {"id": "retained"}}
        self.assertEqual(evidence_id(document), evidence_id({"projection": {"id": "retained"}}))
        self.assertNotEqual(evidence_id(document), evidence_id({"projection": {}}))

    def test_json_pointer_is_exact_and_does_not_search(self) -> None:
        document = {"a/b": {"~key": ["value"]}}
        self.assertEqual(resolve_pointer(document, "/a~1b/~0key/0"), "value")
        with self.assertRaises(KeyError):
            resolve_pointer(document, "/value")


if __name__ == "__main__":
    unittest.main()
