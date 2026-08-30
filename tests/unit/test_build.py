from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
import subprocess
import tarfile
from unittest.mock import patch
import yaml

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

    def changed_publication(self, result):
        catalogue = json.loads(result.catalogue_bytes)
        catalogue["as_of"] = "2026-08-29"
        files = {
            "data/catalogue.json": canonical_bytes(catalogue),
            "data/change-delta.json": result.change_delta_bytes,
        }
        manifest = json.loads(result.manifest_bytes)
        manifest["files"] = manifest_entries(files)
        manifest["publication_digest"] = publication_digest(files)
        return files, manifest

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
            {"profile": "not-configured"},
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
        __import__("shutil").copytree(backup, parent / f"candidate.{token}.staging")
        layout = build_module._layout(self.repository.root)
        old = build_module._candidate_inventory(self.repository.root, backup, layout)
        new = deepcopy(old)
        (parent / ".modelo-build.lock").write_bytes(canonical_bytes(
            build_module._record("backup_old", "candidate", token, old, new)
        ))
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
        new_files, new_manifest = self.changed_publication(result)
        real_write = build_module._persist_journal
        for phase in (
            "lock", "stage", "fsync_stage", "validate_stage", "backup_old",
            "promote_new", "fsync_parent", "verify_target", "remove_backup",
        ):
            with self.subTest(phase=phase):
                def injected(parent, lock, journal, *, initial=False, selected=phase):
                    if journal["phase"] == selected:
                        raise OSError(f"injected {selected}")
                    return real_write(parent, lock, journal, initial=initial)
                with patch.object(build_module, "_persist_journal", side_effect=injected), self.assertRaises(OSError):
                    build_module._publish(
                        self.repository.root, result.output, new_files, new_manifest,
                        build_module._layout(self.repository.root),
                    )
                current = {
                    path.relative_to(result.output).as_posix(): path.read_bytes()
                    for path in result.output.rglob("*") if path.is_file()
                }
                self.assertEqual(current, old)
                self.assertFalse((result.output.parent / ".modelo-build.lock").exists())

        def fail_unlock(parent, lock, journal, *, initial=False):
            if journal["phase"] == "unlock":
                raise OSError("injected unlock")
            return real_write(parent, lock, journal, initial=initial)

        with patch.object(build_module, "_persist_journal", side_effect=fail_unlock):
            build_module._publish(
                self.repository.root, result.output, new_files, new_manifest,
                build_module._layout(self.repository.root),
            )
        self.assertEqual(
            result.output.joinpath("site/data/catalogue.json").read_bytes(),
            new_files["data/catalogue.json"],
        )
        self.assertFalse((result.output.parent / ".modelo-build.lock").exists())

    def test_partial_backup_deletion_never_replaces_complete_new_with_partial_old(self) -> None:
        result = build_candidate(self.request())
        files, manifest = self.changed_publication(result)
        layout = build_module._layout(self.repository.root)
        real_unlink = Path.unlink
        failed = False

        def injected(path, *args, **kwargs):
            nonlocal failed
            if ".backup" in str(path) and path.is_file() and not failed:
                real_unlink(path, *args, **kwargs)
                failed = True
                raise OSError("injected partial deletion")
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", injected):
            build_module._publish(self.repository.root, result.output, files, manifest, layout)
        self.assertEqual(result.output.joinpath("site/data/catalogue.json").read_bytes(), files["data/catalogue.json"])
        self.assertFalse((result.output.parent / ".modelo-build.lock").exists())

    def test_recovery_rejects_symlink_and_impossible_lock_state_without_mutation(self) -> None:
        result = build_candidate(self.request())
        layout = build_module._layout(self.repository.root)
        parent = result.output.parent
        old = build_module._candidate_inventory(self.repository.root, result.output, layout)
        token = "2" * 32
        backup = parent / f"candidate.{token}.backup"
        shutil_copy = __import__("shutil").copytree
        shutil_copy(result.output, backup)
        catalogue = backup / "site/data/catalogue.json"
        catalogue.unlink()
        catalogue.symlink_to(result.output / "site/data/catalogue.json")
        lock = parent / ".modelo-build.lock"
        lock.write_bytes(canonical_bytes(build_module._record("remove_backup", "candidate", token, old, old)))
        before = result.output.joinpath("site/data/catalogue.json").read_bytes()
        with self.assertRaises(BuildError):
            recover_candidate(self.repository.root)
        self.assertEqual(result.output.joinpath("site/data/catalogue.json").read_bytes(), before)
        self.assertTrue(lock.exists())
        lock.unlink()
        __import__("shutil").rmtree(backup)

        token = "3" * 32
        staging = parent / f"candidate.{token}.staging"
        shutil_copy(result.output, staging)
        lock.write_bytes(canonical_bytes(build_module._record("lock", "candidate", token, old, old)))
        with self.assertRaises(BuildError):
            recover_candidate(self.repository.root)
        self.assertTrue(result.output.is_dir())
        self.assertTrue(staging.is_dir())
        self.assertTrue(lock.exists())
        lock.unlink(); __import__("shutil").rmtree(staging)

    def test_staging_and_backup_name_collisions_retry_without_touching_collision(self) -> None:
        result = build_candidate(self.request())
        files, manifest = self.changed_publication(result)
        parent = result.output.parent
        first, second = "4" * 32, "5" * 32
        collision = parent / f"candidate.{first}.backup"
        collision.write_text("owned by another process", encoding="utf-8")
        with patch.object(build_module.secrets, "token_hex", side_effect=(first, second)):
            build_module._publish(
                self.repository.root, result.output, files, manifest,
                build_module._layout(self.repository.root),
            )
        self.assertEqual(collision.read_text(encoding="utf-8"), "owned by another process")

    def test_corrupt_journal_digest_fails_without_mutation(self) -> None:
        result = build_candidate(self.request())
        layout = build_module._layout(self.repository.root)
        inventory = build_module._candidate_inventory(self.repository.root, result.output, layout)
        record = build_module._record("lock", "candidate", "6" * 32, inventory, inventory)
        record["record_digest"] = "sha256:" + "0" * 64
        lock = result.output.parent / ".modelo-build.lock"
        lock.write_bytes(canonical_bytes(record))
        before = result.output.joinpath("site/data/catalogue.json").read_bytes()
        with self.assertRaises(BuildError):
            recover_candidate(self.repository.root)
        self.assertEqual(result.output.joinpath("site/data/catalogue.json").read_bytes(), before)
        self.assertTrue(lock.exists())

    def test_configured_gitlab_issue_route_is_used_without_provider_inference(self) -> None:
        document = yaml.safe_load((self.repository.root / "modelo.yaml").read_text(encoding="utf-8"))
        document["repository"].update({
            "adapter": "gitlab", "host": "gitlab.example.invalid", "namespace": "catalogues",
            "name": "portable", "web_base": "https://gitlab.example.invalid/catalogues/portable",
        })
        document["repository"]["web_routes"]["issue"] = "/work-items/{issue_number}"
        (self.repository.root / "modelo.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n"
        )
        layout = build_module._layout(self.repository.root)
        envelope = json.loads(self.metadata_path.read_bytes())
        envelope["repository"] = {
            "provider": "gitlab", "host": "gitlab.example.invalid",
            "namespace": "catalogues", "name": "portable",
        }
        envelope["issue"]["url"] = "https://gitlab.example.invalid/catalogues/portable/work-items/21"
        build_module._metadata_semantics(
            envelope, self.request(), list(envelope["expected_change_delta"]), layout
        )
        envelope["issue"]["url"] = "https://gitlab.example.invalid/catalogues/portable/-/issues/21"
        with self.assertRaises(BuildError):
            build_module._metadata_semantics(
                envelope, self.request(), list(envelope["expected_change_delta"]), layout
            )

    def test_git_archive_and_filesystem_faults_are_stable_build_errors(self) -> None:
        messages = []
        for detail in ("first path", "different errno and path"):
            with patch.object(build_module.subprocess, "run", side_effect=OSError(detail)):
                with self.assertRaises(BuildError) as caught:
                    build_candidate(self.request())
            messages.append(str(caught.exception))
        self.assertEqual(messages, ["local Git validation failed"] * 2)
        with patch.object(build_module, "with_snapshot", side_effect=tarfile.ReadError("bad archive")):
            with self.assertRaisesRegex(BuildError, r"^build system error \(ReadError\)$"):
                build_candidate(self.request())

    def test_relocated_configured_catalogue_roots_build_successfully(self) -> None:
        repository = Repository()
        self.addCleanup(repository.close)
        document = yaml.safe_load((repository.root / "modelo.yaml").read_text(encoding="utf-8"))
        replacements = {
            "catalogue": "records", "models": "records/models",
            "offerings": "records/offerings", "evidence": "records/evidence",
            "governance": "records/governance", "actors_registry": "records/governance/actors.yaml",
            "conditions": "records/policies/conditions",
        }
        document["paths"].update(replacements)
        (repository.root / "modelo.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n"
        )
        (repository.root / "catalogue").rename(repository.root / "records")
        base = repository.commit("relocate configured catalogue")
        condition = repository.root / "records/policies/conditions/test-condition/2.yaml"
        condition.write_text(
            "id: test-condition\nversion: 2\ntitle: Second condition\n"
            "description: Synthetic second immutable version.\nowner: Test policy owner\n",
            encoding="utf-8", newline="\n",
        )
        head = repository.commit("add relocated condition")
        tree = repository.git("rev-parse", f"{head}^{{tree}}").strip()
        epoch = int(repository.git("show", "-s", "--format=%at", head).strip())
        relative = "records/policies/conditions/test-condition/2.yaml"
        delta = [{"operation": "add", "path": relative, "after": sha256_bytes(condition.read_bytes())}]
        payload = json.loads((ROOT / "tests/fixtures/mac/add.json").read_text(encoding="utf-8"))
        payload["subjects"] = [{"kind": "condition", "identity": "test-condition"}]
        payload["dedupe_key"] = payload["idempotency_key"] = "sha256-" + "0" * 64
        payload["dedupe_key"], payload["idempotency_key"] = compute_keys(payload)
        envelope = {
            "contract_version": "0.1.0",
            "repository": {"provider": "github", "host": "github.com", "namespace": "j3brns", "name": "Modelo"},
            "issue": {"reference": "21", "url": "https://github.com/j3brns/Modelo/issues/21", "state": "open"},
            "base_sha": base, "head_sha": head, "head_tree_sha": tree,
            "payload": payload, "payload_digest": sha256_bytes(canonical_bytes(payload)),
            "expected_change_delta": delta,
        }
        descriptor, metadata_name = tempfile.mkstemp(prefix="modelo-relocated-", suffix=".json")
        os.close(descriptor)
        metadata = Path(metadata_name)
        self.addCleanup(metadata.unlink, missing_ok=True)
        metadata.write_bytes(canonical_bytes(envelope))
        result = build_candidate(BuildRequest(
            root=repository.root, kind="candidate", base_commit=base, source_commit=head,
            source_tree=tree, as_of=date(2026, 8, 30), source_date_epoch=epoch,
            mac_metadata=metadata, profile="synthetic", base_url=None,
            base_path="/Modelo/", output="dist/candidate",
        ))
        self.assertTrue(result.output.joinpath("site/data/manifest.json").is_file())

    def test_configured_output_overlap_fails_before_mutation(self) -> None:
        document = yaml.safe_load((self.repository.root / "modelo.yaml").read_text(encoding="utf-8"))
        document["build"].update({
            "candidate_root": "tests/candidate", "target_parent": "tests",
            "writer_lock": "tests/.modelo-build.lock",
        })
        (self.repository.root / "modelo.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n"
        )
        with self.assertRaisesRegex(BuildError, "overlaps a configured input"):
            build_module._layout(self.repository.root)
        self.assertFalse((self.repository.root / "tests/candidate").exists())
        self.assertFalse((self.repository.root / "tests/.modelo-build.lock").exists())

    def test_old_absent_crash_matrix_rolls_back_precommit_and_forward_postcommit(self) -> None:
        result = build_candidate(self.request())
        layout = build_module._layout(self.repository.root)
        parent = result.output.parent
        source = Path(tempfile.mkdtemp(prefix="modelo-complete-candidate-")) / "candidate"
        __import__("shutil").copytree(result.output, source)
        self.addCleanup(__import__("shutil").rmtree, source.parent, ignore_errors=True)
        inventory = build_module._candidate_inventory(self.repository.root, result.output, layout)
        __import__("shutil").rmtree(result.output)
        lock = parent / ".modelo-build.lock"
        cases = (
            ("lock", "7" * 32, "none", False),
            ("backup_old", "8" * 32, "staging", False),
            ("promote_new", "9" * 32, "target", False),
            ("remove_backup", "a" * 32, "target", True),
            ("unlock", "b" * 32, "target", True),
        )
        for phase, token, location, committed in cases:
            with self.subTest(phase=phase):
                if result.output.exists():
                    __import__("shutil").rmtree(result.output)
                staging = parent / f"candidate.{token}.staging"
                if location == "staging":
                    __import__("shutil").copytree(source, staging)
                elif location == "target":
                    __import__("shutil").copytree(source, result.output)
                lock.write_bytes(canonical_bytes(
                    build_module._record(phase, "candidate", token, None, inventory)
                ))
                recover_candidate(self.repository.root)
                self.assertEqual(result.output.exists(), committed)
                self.assertFalse(staging.exists())
                self.assertFalse(lock.exists())

    def test_old_present_crash_matrix_restores_precommit_and_retains_committed_new(self) -> None:
        result = build_candidate(self.request())
        layout = build_module._layout(self.repository.root)
        parent = result.output.parent
        old_source = Path(tempfile.mkdtemp(prefix="modelo-old-candidate-")) / "candidate"
        __import__("shutil").copytree(result.output, old_source)
        old_inventory = build_module._candidate_inventory(self.repository.root, result.output, layout)
        files, manifest = self.changed_publication(result)
        build_module._publish(self.repository.root, result.output, files, manifest, layout)
        new_source = Path(tempfile.mkdtemp(prefix="modelo-new-candidate-")) / "candidate"
        __import__("shutil").copytree(result.output, new_source)
        new_inventory = build_module._candidate_inventory(self.repository.root, result.output, layout)
        self.addCleanup(__import__("shutil").rmtree, old_source.parent, ignore_errors=True)
        self.addCleanup(__import__("shutil").rmtree, new_source.parent, ignore_errors=True)
        lock = parent / ".modelo-build.lock"
        cases = (
            ("lock", "c" * 32, "old", "none", "none"),
            ("stage", "d" * 32, "old", "new", "none"),
            ("fsync_stage", "e" * 32, "old", "new", "none"),
            ("validate_stage", "f" * 32, "old", "new", "none"),
            ("backup_old", "1" * 31 + "0", "old", "new", "none"),
            ("promote_new", "2" * 31 + "0", "none", "new", "old"),
            ("fsync_parent", "3" * 31 + "0", "new", "none", "old"),
            ("verify_target", "4" * 31 + "0", "new", "none", "old"),
        )
        for phase, token, target_kind, staging_kind, backup_kind in cases:
            with self.subTest(phase=phase):
                for path in parent.glob("candidate.*"):
                    if path.is_dir():
                        __import__("shutil").rmtree(path)
                    else:
                        path.unlink()
                if result.output.exists():
                    __import__("shutil").rmtree(result.output)
                staging = parent / f"candidate.{token}.staging"
                backup = parent / f"candidate.{token}.backup"
                sources = {"old": old_source, "new": new_source}
                if target_kind != "none":
                    __import__("shutil").copytree(sources[target_kind], result.output)
                if staging_kind != "none":
                    __import__("shutil").copytree(sources[staging_kind], staging)
                if backup_kind != "none":
                    __import__("shutil").copytree(sources[backup_kind], backup)
                lock.write_bytes(canonical_bytes(build_module._record(
                    phase, "candidate", token, old_inventory, new_inventory
                )))
                recover_candidate(self.repository.root)
                self.assertEqual(
                    build_module._candidate_inventory(self.repository.root, result.output, layout),
                    old_inventory,
                )
                self.assertFalse(staging.exists()); self.assertFalse(backup.exists()); self.assertFalse(lock.exists())

        token = "5" * 31 + "0"
        __import__("shutil").rmtree(result.output)
        __import__("shutil").copytree(new_source, result.output)
        backup = parent / f"candidate.{token}.backup"
        __import__("shutil").copytree(old_source, backup)
        lock.write_bytes(canonical_bytes(build_module._record(
            "remove_backup", "candidate", token, old_inventory, new_inventory
        )))
        recover_candidate(self.repository.root)
        self.assertEqual(
            build_module._candidate_inventory(self.repository.root, result.output, layout), new_inventory
        )
        self.assertFalse(backup.exists()); self.assertFalse(lock.exists())


if __name__ == "__main__":
    unittest.main()
