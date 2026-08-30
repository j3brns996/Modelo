from __future__ import annotations

import unittest
import sys
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from modelo.change import GitError, changed_paths, require_ancestor, resolve_commit, validate_changes, validate_condition_history

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

    def test_mixed_offering_changes_are_exactly_one_atomic_move(self) -> None:
        roots = dict(evidence_root="catalogue/evidence", conditions_root="catalogue/policies/conditions", models_root="catalogue/models", offerings_root="catalogue/offerings")
        prefix = "catalogue/offerings/aws-bedrock/"
        cases = (
            (("D", prefix + "a.yaml"), ("A", prefix + "b.yaml")),
            (("A", prefix + "a.yaml"), ("A", prefix + "b.yaml")),
            (("D", prefix + "a.yaml"), ("D", prefix + "b.yaml")),
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(validate_changes(changes, **roots), ())
        rejected = (
            (("D", prefix + "a.yaml"), ("A", prefix + "b.yaml"), ("A", prefix + "c.yaml")),
            (("D", prefix + "a.yaml"), ("D", prefix + "b.yaml"), ("A", prefix + "c.yaml")),
            (("D", prefix + "a.yaml"), ("D", prefix + "b.yaml"), ("A", prefix + "c.yaml"), ("A", prefix + "d.yaml")),
        )
        for changes in rejected:
            with self.subTest(changes=changes):
                self.assertIn("CHANGE_INVALID", {finding.code for finding in validate_changes(changes, **roots)})

    def test_condition_history_detects_mutation_and_changed_reintroduction(self) -> None:
        condition = self.repository.root / "catalogue/policies/conditions/test-condition/1.yaml"
        original = condition.read_text(encoding="utf-8")
        condition.write_text(original.replace("Synthetic condition", "Mutated condition"), encoding="utf-8", newline="\n")
        mutated = self.repository.commit("mutate condition")
        self.assertIn("CHANGE_INVALID", {finding.code for finding in validate_condition_history(self.repository.root, mutated, "catalogue/policies/conditions", "catalogue/offerings")})
        condition.unlink()
        offering = self.repository.root / "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering_text = offering.read_text(encoding="utf-8")
        offering.write_text(offering_text.replace("condition_refs:\n  - id: test-condition\n    version: 1", "condition_refs: []"), encoding="utf-8", newline="\n")
        deleted = self.repository.commit("delete condition")
        condition.parent.mkdir(parents=True, exist_ok=True)
        condition.write_text(original.replace("Synthetic condition", "Reintroduced condition"), encoding="utf-8", newline="\n")
        offering.write_text(offering_text, encoding="utf-8", newline="\n")
        reintroduced = self.repository.commit("reintroduce condition")
        self.assertIn("CHANGE_INVALID", {finding.code for finding in validate_condition_history(self.repository.root, reintroduced, "catalogue/policies/conditions", "catalogue/offerings")})
        self.assertNotEqual(deleted, reintroduced)

    def test_condition_history_fails_closed_when_clone_is_shallow(self) -> None:
        with TemporaryDirectory(prefix="modelo-shallow-") as temporary:
            shallow = Path(temporary) / "repository"
            subprocess.run(
                ["git", "clone", "-q", "--depth", "1", f"file://{self.repository.root}", str(shallow)],
                check=True, capture_output=True, text=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=shallow, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            with self.assertRaisesRegex(GitError, "shallow"):
                validate_condition_history(shallow, head, "catalogue/policies/conditions", "catalogue/offerings")


if __name__ == "__main__":
    unittest.main()
