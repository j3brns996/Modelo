from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys
import subprocess
from unittest.mock import patch

import modelo.build as build_module
from modelo.build import BuildError, BuildRequest, build_candidate, recover_candidate
from modelo.mac import compute_keys
from modelo.receipt import canonical_bytes, manifest_entries, publication_digest, sha256_bytes

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/fixtures/semantic"))
from repository import Repository  # noqa: E402


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Repository()
        self.addCleanup(self.repository.close)
        condition = self.repository.root / "catalogue/policies/conditions/test-condition/2.yaml"
        condition.parent.mkdir(parents=True, exist_ok=True)
        condition.write_text(
            "id: test-condition\nversion: 2\ntitle: Second condition\n"
            "description: Synthetic second immutable version.\nowner: Test policy owner\n",
            encoding="utf-8", newline="\n",
        )
        self.head = self.repository.commit("add condition")
        self.tree = self.repository.git("rev-parse", f"{self.head}^{{tree}}").strip()
        self.epoch = int(self.repository.git("show", "-s", "--format=%at", self.head).strip())
        path = "catalogue/policies/conditions/test-condition/2.yaml"
        raw = (self.repository.root / path).read_bytes()
        delta = [{"operation": "add", "path": path, "after": sha256_bytes(raw)}]
        payload = json.loads((ROOT / "tests/fixtures/mac/add.json").read_text(encoding="utf-8"))
        payload["subjects"] = [{"kind": "condition", "identity": "test-condition"}]
        payload["dedupe_key"] = "sha256-" + "0" * 64
        payload["idempotency_key"] = "sha256-" + "0" * 64
        payload["dedupe_key"], payload["idempotency_key"] = compute_keys(payload)
        metadata = {
            "contract_version": "0.1.0",
            "repository": {"provider": "github", "host": "github.com", "namespace": "j3brns", "name": "Modelo"},
            "issue": {"reference": "21", "url": "https://github.com/j3brns/Modelo/issues/21", "state": "open"},
            "base_sha": self.repository.base, "head_sha": self.head, "head_tree_sha": self.tree,
            "payload": payload, "payload_digest": sha256_bytes(canonical_bytes(payload)),
            "expected_change_delta": delta,
        }
        temporary = tempfile.NamedTemporaryFile(prefix="modelo-metadata-", suffix=".json", delete=False)
        self.metadata_path = Path(temporary.name)
        temporary.write(canonical_bytes(metadata)); temporary.close()
        self.addCleanup(self.metadata_path.unlink, missing_ok=True)

    def request(self, **changes) -> BuildRequest:
        values = {
            "root": self.repository.root, "kind": "candidate",
            "base_commit": self.repository.base, "source_commit": self.head,
            "source_tree": self.tree, "as_of": date(2026, 8, 30),
            "source_date_epoch": self.epoch, "mac_metadata": self.metadata_path,
            "profile": "synthetic", "base_url": None, "base_path": "/Modelo/",
            "output": "dist/candidate",
        }
        values.update(changes)
        return BuildRequest(**values)

    def test_two_builds_are_byte_identical_and_exact_inventory(self) -> None:
        first = build_candidate(self.request())
        first_files = {
            path.relative_to(first.output).as_posix(): path.read_bytes()
            for path in first.output.rglob("*") if path.is_file()
        }
        second = build_candidate(self.request())
        second_files = {
            path.relative_to(second.output).as_posix(): path.read_bytes()
            for path in second.output.rglob("*") if path.is_file()
        }
        self.assertEqual(first_files, second_files)
        self.assertEqual(set(first_files), {
            "site/data/catalogue.json", "site/data/change-delta.json", "site/data/manifest.json",
        })
        manifest = json.loads(first_files["site/data/manifest.json"])
        self.assertEqual(set(manifest["files"]), {"data/catalogue.json", "data/change-delta.json"})
        self.assertNotIn("actors", json.loads(first.catalogue_bytes))

    def test_wrong_correlations_and_paths_fail_closed(self) -> None:
        cases = (
            {"base_commit": "0" * 40}, {"source_tree": "0" * 40},
            {"source_date_epoch": self.epoch + 1}, {"output": "dist/elsewhere"},
            {"base_url": "http://example.invalid/Modelo/"}, {"base_path": "/../"},
            {"kind": "final", "output": "dist/final"},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(BuildError):
                build_candidate(self.request(**changes))

    def test_metadata_tamper_dirty_tree_and_concurrent_writer_fail(self) -> None:
        original = self.metadata_path.read_bytes()
        changed = bytearray(original); changed[-2] = ord(" ")
        self.metadata_path.write_bytes(changed)
        with self.assertRaises(BuildError):
            build_candidate(self.request())
        self.metadata_path.write_bytes(original)
        dirty = self.repository.root / "unexpected.txt"; dirty.write_text("dirty", encoding="utf-8")
        with self.assertRaises(BuildError):
            build_candidate(self.request())
        dirty.unlink()
        lock = self.repository.root / "dist/.modelo-build.lock"
        lock.parent.mkdir(exist_ok=True); lock.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(BuildError):
            build_candidate(self.request())

    def test_explicit_recovery_restores_verified_backup(self) -> None:
        result = build_candidate(self.request())
        parent = result.output.parent
        token = "1" * 32
        backup = parent / f"candidate.{token}.backup"
        result.output.rename(backup)
        (parent / ".modelo-build.lock").write_bytes(canonical_bytes({
            "version": 1, "phase": "backup_old", "target": "candidate", "token": token,
        }))
        recover_candidate(self.repository.root)
        self.assertTrue(result.output.is_dir())
        self.assertFalse(backup.exists())
        self.assertFalse((parent / ".modelo-build.lock").exists())

    def test_exact_candidate_cli_succeeds_without_ambient_inputs(self) -> None:
        command = [
            sys.executable, "-m", "modelo", "--root", str(self.repository.root), "build",
            "--kind", "candidate", "--base-commit", self.repository.base,
            "--source-commit", self.head, "--source-tree", self.tree,
            "--as-of", "2026-08-30", "--source-date-epoch", str(self.epoch),
            "--mac-metadata", str(self.metadata_path), "--profile", "synthetic",
            "--no-base-url", "--base-path", "/Modelo/", "--output", "dist/candidate",
        ]
        result = subprocess.run(
            command, cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_injected_transition_failures_preserve_complete_old_target(self) -> None:
        result = build_candidate(self.request())
        old = {
            path.relative_to(result.output).as_posix(): path.read_bytes()
            for path in result.output.rglob("*") if path.is_file()
        }
        old_manifest = json.loads(old["site/data/manifest.json"])
        new_files = {
            "data/catalogue.json": old["site/data/catalogue.json"][:-1] + b" \n",
            "data/change-delta.json": old["site/data/change-delta.json"],
        }
        new_manifest = deepcopy(old_manifest)
        new_manifest["files"] = manifest_entries(new_files)
        new_manifest["publication_digest"] = publication_digest(new_files)
        real_write = build_module._write_journal
        for phase in ("lock", "stage", "fsync_stage", "validate_stage", "backup_old", "promote_new", "fsync_parent", "verify_target"):
            with self.subTest(phase=phase):
                def injected(descriptor, journal, *, selected=phase):
                    if journal["phase"] == selected:
                        raise OSError(f"injected {selected}")
                    return real_write(descriptor, journal)
                with patch.object(build_module, "_write_journal", side_effect=injected), self.assertRaises(OSError):
                    build_module._publish(self.repository.root, result.output, new_files, new_manifest)
                current = {
                    path.relative_to(result.output).as_posix(): path.read_bytes()
                    for path in result.output.rglob("*") if path.is_file()
                }
                self.assertEqual(current, old)
                self.assertFalse((result.output.parent / ".modelo-build.lock").exists())


if __name__ == "__main__":
    unittest.main()
