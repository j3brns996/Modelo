from __future__ import annotations

import unittest
import sys
from pathlib import Path

from modelo.change import GitError, changed_paths, require_ancestor, resolve_commit, validate_changes

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/fixtures/semantic"))
from repository import Repository  # noqa: E402


class ChangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Repository()

    def tearDown(self) -> None:
        self.repository.close()

    def test_local_git_resolves_named_commits_without_sha_length_assumption(self) -> None:
        self.repository.git("tag", "opaque-base")
        self.assertEqual(resolve_commit(self.repository.root, "opaque-base"), self.repository.base)

    def test_evidence_and_condition_are_immutable(self) -> None:
        evidence = next((self.repository.root / "catalogue/evidence").glob("*.yaml"))
        evidence.write_text(evidence.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        head = self.repository.commit()
        changes = changed_paths(self.repository.root, self.repository.base, head)
        findings = validate_changes(
            changes, evidence_root="catalogue/evidence",
            conditions_root="catalogue/policies/conditions",
            models_root="catalogue/models", offerings_root="catalogue/offerings",
        )
        self.assertIn("EVIDENCE_IMMUTABLE", {finding.code for finding in findings})

    def test_offering_delete_is_allowed_but_model_delete_is_not(self) -> None:
        (self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml").unlink()
        head = self.repository.commit()
        findings = validate_changes(changed_paths(self.repository.root, self.repository.base, head), evidence_root="catalogue/evidence", conditions_root="catalogue/policies/conditions", models_root="catalogue/models", offerings_root="catalogue/offerings")
        self.assertEqual(findings, ())

    def test_base_must_be_ancestor_of_head(self) -> None:
        (self.repository.root / "first.txt").write_text("first\n", encoding="utf-8")
        head = self.repository.commit("first")
        require_ancestor(self.repository.root, self.repository.base, head)
        self.repository.git("checkout", "-qb", "other", self.repository.base)
        (self.repository.root / "unrelated.txt").write_text("x\n", encoding="utf-8")
        unrelated = self.repository.commit("unrelated")
        with self.assertRaises(GitError):
            require_ancestor(self.repository.root, unrelated, head)


if __name__ == "__main__":
    unittest.main()
