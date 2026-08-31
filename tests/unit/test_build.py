from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import sys
import subprocess
import tarfile
from unittest.mock import patch
import yaml

import modelo.build as build_module
from modelo.build import BuildError, BuildRequest, build_candidate, recover_candidate
from modelo.evidence import evidence_id
from modelo.mac import compute_keys
from modelo.receipt import canonical_bytes, manifest_entries, publication_digest, sha256_bytes
from modelo.validators import check_repository

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
            "repository": {"provider": "github", "host": "github.com", "namespace": "j3brns996", "name": "Modelo"},
            "issue": {"reference": "21", "url": "https://github.com/j3brns996/Modelo/issues/21", "state": "open"},
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

    def test_two_source_region_profile_repository_orders_produce_identical_candidate(self) -> None:
        def evidence_path(repository, identifier):
            return repository.root / "catalogue/evidence" / f"{identifier}.yaml"

        def write_evidence(repository, record):
            identifier = evidence_id(record)
            document = {"id": identifier, **record}
            evidence_path(repository, identifier).write_text(
                yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n"
            )
            return identifier

        def make(order):
            repository = Repository()
            self.addCleanup(repository.close)
            eu_model_id = "sha256-3cc6bbaee52dff309202c8aed63c219a8277199cadafdbeeac3b0e2c91c746fb"
            eu_model = yaml.safe_load(
                evidence_path(repository, eu_model_id).read_text(encoding="utf-8")
            )
            us_model = deepcopy(eu_model)
            us_model.pop("id")
            us_model["source"].update(region="us-east-1")
            us_model["source"]["sanitised_parameters"] = {
                "modelIdentifier": "test.model-v1"
            }
            us_model["scope"]["region"] = "us-east-1"
            us_model["projection"]["modelArn"] = (
                "arn:aws:bedrock:us-east-1::foundation-model/test.model-v1"
            )
            us_model_id = write_evidence(repository, us_model)

            model_ids = {"eu": eu_model_id, "us": us_model_id}
            regions = {"eu": "eu-west-2", "us": "us-east-1"}
            model_arns = {
                "eu": "arn:aws:bedrock:eu-west-2::foundation-model/test.model-v1",
                "us": "arn:aws:bedrock:us-east-1::foundation-model/test.model-v1",
            }
            profile_ids = {}
            for key in ("eu", "us"):
                profile_ids[key] = write_evidence(repository, {
                    "source": {
                        "type": "first-party-read-api", "provider": "aws",
                        "service": "bedrock", "operation": "GetInferenceProfile",
                        "partition": "aws", "region": regions[key],
                        "sanitised_parameters": {
                            "inferenceProfileIdentifier": "global.test.profile-v1"
                        },
                        "documentation_uri": "https://example.invalid/aws-profile-api",
                    },
                    "retrieved_by": "cli", "observed_at": "2026-08-01T00:00:00Z",
                    "scope": {"scope_ref": f"synthetic-{key}", "region": regions[key]},
                    "projection": {
                        "profileId": "global.test.profile-v1", "type": "SYSTEM_DEFINED",
                        "status": "ACTIVE", "models": [{"modelArn": model_arns[key]}],
                    },
                    "visibility": "public",
                })

            prices = {
                "eu": {"dimension": "input", "unit": "token", "quantity": 1000000, "amount": "1.00", "currency": "USD"},
                "us": {"dimension": "input", "unit": "token", "quantity": 1000000, "amount": "2.00", "currency": "USD"},
            }
            price_evidence_id = write_evidence(repository, {
                "source": {
                    "type": "official-provider-documentation",
                    "uri": "https://example.invalid/aws-pricing",
                },
                "retrieved_by": "manual", "observed_at": "2026-08-29T00:00:00Z",
                "scope": {}, "projection": {"prices": prices}, "visibility": "public",
            })

            routes = {}
            for key in ("eu", "us"):
                routes[key] = {
                    "id": f"{key}-route", "source_region": regions[key],
                    "reference": "global.test.profile-v1",
                    "model_binding": {
                        "kind": "system-inference-profile",
                        "profile_evidence": {
                            "id": profile_ids[key], "projection_pointer": "/profileId",
                            "type_pointer": "/type", "status_pointer": "/status",
                            "destinations_pointer": "/models",
                        },
                        "destinations": [{
                            "destination_pointer": "/models/0/modelArn",
                            "model_evidence": {
                                "id": model_ids[key], "arn_pointer": "/modelArn",
                                "name_pointer": "/modelName",
                                "provider_pointer": "/providerName",
                            },
                        }],
                    },
                }
            offering = {
                "id": "test-offering", "inference_service_id": "aws-bedrock",
                "model_id": "test-model", "routes": [routes[key] for key in order],
                "pricing": [
                    {**prices[key], "route_ids": [f"{key}-route"]}
                    for key in reversed(order)
                ],
                "condition_refs": [{"id": "test-condition", "version": 1}],
                "evidence_refs": {},
            }
            for index, key in enumerate(order):
                offering["evidence_refs"][f"/routes/{index}/reference"] = {
                    "id": profile_ids[key], "projection_pointer": "/profileId",
                }
            for index, key in enumerate(reversed(order)):
                for field in ("dimension", "unit", "quantity", "amount", "currency"):
                    offering["evidence_refs"][f"/pricing/{index}/{field}"] = {
                        "id": price_evidence_id,
                        "projection_pointer": f"/prices/{key}/{field}",
                    }
            offering_path = (
                repository.root
                / "catalogue/offerings/aws-bedrock/test-offering.yaml"
            )
            offering_path.write_text(
                yaml.safe_dump(offering, sort_keys=False), encoding="utf-8", newline="\n"
            )
            synthetic = repository.root / "tests/fixtures/build/synthetic"
            shutil.rmtree(synthetic)
            shutil.copytree(repository.root / "catalogue", synthetic)
            head = repository.commit("two regional routes")
            self.assertEqual(
                check_repository(
                    repository.root, repository.base, head, date(2026, 8, 30)
                ),
                (),
            )
            projection = build_module._projection_from_snapshot(
                repository.root, "synthetic", "a" * 40, "b" * 40,
                date(2026, 8, 30), build_module._layout(repository.root),
            )
            return canonical_bytes(projection), projection

        forward_bytes, forward = make(("eu", "us"))
        reverse_bytes, reverse = make(("us", "eu"))
        self.assertEqual(forward_bytes, reverse_bytes)
        normal = forward["offerings"][0]
        self.assertEqual(
            [route["id"] for route in normal["routes"]], ["eu-route", "us-route"]
        )
        self.assertEqual(
            normal["evidence_refs"]["/routes/0/reference"]["id"],
            normal["routes"][0]["model_binding"]["profile_evidence"]["id"],
        )
        self.assertEqual(
            [price["route_ids"] for price in normal["pricing"]],
            [["eu-route"], ["us-route"]],
        )
        self.assertEqual(forward, reverse)

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
                expected_error = BuildError if phase == "stage" else OSError
                with patch.object(build_module, "_persist_journal", side_effect=injected), self.assertRaises(expected_error):
                    build_module._publish(
                        self.repository.root, result.output, new_files, new_manifest,
                        build_module._layout(self.repository.root),
                    )
                current = {
                    path.relative_to(result.output).as_posix(): path.read_bytes()
                    for path in result.output.rglob("*") if path.is_file()
                }
                self.assertEqual(current, old)
                lock = result.output.parent / ".modelo-build.lock"
                self.assertEqual(lock.exists(), phase == "stage")
                if lock.exists():
                    lock.unlink()

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

    def test_failed_final_lock_deletion_fsync_never_reports_success(self) -> None:
        result = build_candidate(self.request())
        files, manifest = self.changed_publication(result)
        layout = build_module._layout(self.repository.root)
        lock = result.output.parent / ".modelo-build.lock"
        real_fsync = build_module._fsync_dir

        def injected(path):
            if path == result.output.parent and not lock.exists():
                raise OSError("injected final parent fsync")
            return real_fsync(path)

        with patch.object(build_module, "_fsync_dir", side_effect=injected), self.assertRaises(OSError):
            build_module._publish(self.repository.root, result.output, files, manifest, layout)
        self.assertEqual(result.output.joinpath("site/data/catalogue.json").read_bytes(), files["data/catalogue.json"])
        self.assertFalse(lock.exists())

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

    def test_old_inventory_is_read_only_after_durable_exclusive_lock(self) -> None:
        result = build_candidate(self.request())
        real_inventory = build_module._candidate_inventory
        observed = []

        def inspected(root, target, layout):
            if target == result.output:
                observed.append((result.output.parent / ".modelo-build.lock").is_file())
            return real_inventory(root, target, layout)

        with patch.object(build_module, "_candidate_inventory", side_effect=inspected):
            build_candidate(self.request())
        self.assertTrue(observed)
        self.assertTrue(all(observed))

    def test_backup_rename_has_no_placeholder_window(self) -> None:
        result = build_candidate(self.request())
        files, manifest = self.changed_publication(result)
        real_replace = build_module._rename_noreplace
        observed = []

        def inspected(source, destination):
            source_path, destination_path = Path(source), Path(destination)
            if source_path == result.output and destination_path.name.endswith(".backup"):
                observed.append(not destination_path.exists() and not destination_path.is_symlink())
            return real_replace(source, destination)

        with patch.object(build_module, "_rename_noreplace", side_effect=inspected):
            build_module._publish(
                self.repository.root, result.output, files, manifest,
                build_module._layout(self.repository.root),
            )
        self.assertEqual(observed, [True])

    def test_durable_commit_journal_fault_rolls_forward_as_success(self) -> None:
        result = build_candidate(self.request())
        files, manifest = self.changed_publication(result)
        real_persist = build_module._persist_journal
        raised = False

        def persisted_then_failed(parent, lock, journal, *, initial=False):
            nonlocal raised
            real_persist(parent, lock, journal, initial=initial)
            if journal["phase"] == "remove_backup" and not raised:
                raised = True
                raise OSError("injected after durable commit journal")

        with patch.object(build_module, "_persist_journal", side_effect=persisted_then_failed):
            build_module._publish(
                self.repository.root, result.output, files, manifest,
                build_module._layout(self.repository.root),
            )
        self.assertTrue(raised)
        self.assertEqual(result.output.joinpath("site/data/catalogue.json").read_bytes(), files["data/catalogue.json"])
        self.assertFalse((result.output.parent / ".modelo-build.lock").exists())

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

    def test_condition_and_offering_composite_subject_aliases_are_rejected(self) -> None:
        layout = build_module._layout(self.repository.root)
        condition_envelope = json.loads(self.metadata_path.read_bytes())
        condition_envelope["payload"]["subjects"][0]["identity"] = "policies/conditions/test-condition"
        condition_envelope["payload"]["dedupe_key"] = condition_envelope["payload"]["idempotency_key"] = "sha256-" + "0" * 64
        condition_envelope["payload"]["dedupe_key"], condition_envelope["payload"]["idempotency_key"] = compute_keys(condition_envelope["payload"])
        condition_envelope["payload_digest"] = sha256_bytes(canonical_bytes(condition_envelope["payload"]))
        with self.assertRaises(BuildError):
            build_module._metadata_semantics(
                condition_envelope, self.request(), list(condition_envelope["expected_change_delta"]), layout
            )

        base = self.head
        offering_path = "catalogue/offerings/aws-bedrock/test-offering.yaml"
        offering = self.repository.root / offering_path
        before = offering.read_bytes()
        offering.write_bytes(before + b"# representation-only change\n")
        head = self.repository.commit("change offering representation")
        tree = self.repository.git("rev-parse", f"{head}^{{tree}}").strip()
        payload = json.loads((ROOT / "tests/fixtures/mac/change.json").read_text(encoding="utf-8"))
        payload["subjects"] = [{"kind": "offering", "identity": "aws-bedrock/test-offering"}]
        payload["dedupe_key"] = payload["idempotency_key"] = "sha256-" + "0" * 64
        payload["dedupe_key"], payload["idempotency_key"] = compute_keys(payload)
        delta = [{
            "operation": "change", "path": offering_path,
            "before": sha256_bytes(before), "after": sha256_bytes(offering.read_bytes()),
        }]
        envelope = {
            "contract_version": "0.1.0",
            "repository": {"provider": "github", "host": "github.com", "namespace": "j3brns996", "name": "Modelo"},
            "issue": {"reference": "21", "url": "https://github.com/j3brns996/Modelo/issues/21", "state": "open"},
            "base_sha": base, "head_sha": head, "head_tree_sha": tree,
            "payload": payload, "payload_digest": sha256_bytes(canonical_bytes(payload)),
            "expected_change_delta": delta,
        }
        request = self.request(
            base_commit=base, source_commit=head, source_tree=tree,
            source_date_epoch=int(self.repository.git("show", "-s", "--format=%at", head).strip()),
        )
        with self.assertRaises(BuildError):
            build_module._metadata_semantics(envelope, request, delta, layout)
        payload["subjects"][0]["identity"] = "test-offering"
        payload["dedupe_key"] = payload["idempotency_key"] = "sha256-" + "0" * 64
        payload["dedupe_key"], payload["idempotency_key"] = compute_keys(payload)
        envelope["payload_digest"] = sha256_bytes(canonical_bytes(payload))
        build_module._metadata_semantics(envelope, request, delta, layout)

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
            "repository": {"provider": "github", "host": "github.com", "namespace": "j3brns996", "name": "Modelo"},
            "issue": {"reference": "21", "url": "https://github.com/j3brns996/Modelo/issues/21", "state": "open"},
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
            "candidate_root": "tests/candidate", "validation_root": "tests/validation",
            "final_root": "tests/final", "pages_root": "tests/pages",
            "target_parent": "tests",
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
            ("stage", "7" * 31 + "0", "staging", False),
            ("fsync_stage", "7" * 31 + "1", "staging", False),
            ("validate_stage", "7" * 31 + "2", "staging", False),
            ("backup_old", "8" * 32, "staging", False),
            ("promote_new", "9" * 32, "target", False),
            ("fsync_parent", "9" * 31 + "0", "target", False),
            ("verify_target", "9" * 31 + "1", "target", False),
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

    def test_journal_phase_semantics_and_uncaptured_lock_fail_closed(self) -> None:
        result = build_candidate(self.request())
        layout = build_module._layout(self.repository.root)
        inventory = build_module._candidate_inventory(self.repository.root, result.output, layout)
        lock = result.output.parent / ".modelo-build.lock"
        before = {
            path.relative_to(result.output).as_posix(): path.read_bytes()
            for path in result.output.rglob("*") if path.is_file()
        }
        for phase in build_module.PHASES:
            with self.subTest(phase=phase):
                record = build_module._record(phase, "candidate", "c" * 32, inventory, inventory)
                record["sequence"] = (record["sequence"] + 1) % len(build_module.PHASES)
                body = {key: value for key, value in record.items() if key != "record_digest"}
                record["record_digest"] = sha256_bytes(canonical_bytes(body))
                with self.assertRaisesRegex(BuildError, "phase/sequence"):
                    build_module._validate_record(record, layout)

        for sequence in (False, True):
            record = build_module._record("lock", "candidate", "c" * 32, None, inventory)
            record["sequence"] = sequence
            body = {key: value for key, value in record.items() if key != "record_digest"}
            record["record_digest"] = sha256_bytes(canonical_bytes(body))
            with self.assertRaisesRegex(BuildError, "phase/sequence"):
                build_module._validate_record(record, layout)

        for old in (inventory, None):
            with self.subTest(lock_old=old is not None):
                record = build_module._record("lock", "candidate", "c" * 32, old, inventory)
                lock.write_bytes(canonical_bytes(record))
                with self.assertRaises(BuildError):
                    recover_candidate(self.repository.root)
                self.assertEqual(
                    {
                        path.relative_to(result.output).as_posix(): path.read_bytes()
                        for path in result.output.rglob("*") if path.is_file()
                    },
                    before,
                )
                self.assertEqual(lock.read_bytes(), canonical_bytes(record))
                lock.unlink()

    def test_recovery_never_unlinks_even_hard_linked_journal_temporary(self) -> None:
        result = build_candidate(self.request())
        layout = build_module._layout(self.repository.root)
        inventory = build_module._candidate_inventory(self.repository.root, result.output, layout)
        __import__("shutil").rmtree(result.output)
        parent = result.output.parent
        lock = parent / ".modelo-build.lock"
        record = build_module._record("lock", "candidate", "d" * 32, None, inventory)
        lock.write_bytes(canonical_bytes(record))
        temporary = parent / f".{lock.name}.{record['token']}.0.tmp"
        os.link(lock, temporary)
        # A pathname could be swapped after any identity read.  Recovery has no
        # unlink path at all, so the attempted TOCTOU callback is never reached.
        with patch.object(Path, "unlink", side_effect=AssertionError("unsafe unlink attempted")) as unlink:
            with self.assertRaisesRegex(BuildError, "ambiguous build recovery journal temporary"):
                recover_candidate(self.repository.root)
        unlink.assert_not_called()
        self.assertTrue(lock.exists()); self.assertTrue(temporary.exists())
        temporary.unlink(); lock.unlink()

    def test_normal_journal_replace_consumes_temporary_without_hard_link_acquisition(self) -> None:
        with patch.object(os, "link", side_effect=AssertionError("hard-link acquisition attempted")):
            result = build_candidate(self.request())
        self.assertTrue(result.output.is_dir())
        self.assertEqual(
            list(result.output.parent.glob("..modelo-build.lock.*.tmp")), []
        )

    def test_failed_journal_replace_retains_ambiguous_temp_and_complete_target(self) -> None:
        result = build_candidate(self.request())
        files, manifest = self.changed_publication(result)
        layout = build_module._layout(self.repository.root)
        before = {
            path.relative_to(result.output).as_posix(): path.read_bytes()
            for path in result.output.rglob("*") if path.is_file()
        }
        real_replace = os.replace

        def fail_journal_replace(source, destination):
            if str(source).endswith(".tmp") and Path(destination).name == ".modelo-build.lock":
                raise OSError("injected before journal replace")
            return real_replace(source, destination)

        with patch.object(os, "replace", side_effect=fail_journal_replace):
            with self.assertRaisesRegex(BuildError, "explicit recovery required"):
                build_module._publish(self.repository.root, result.output, files, manifest, layout)
        self.assertEqual(
            {
                path.relative_to(result.output).as_posix(): path.read_bytes()
                for path in result.output.rglob("*") if path.is_file()
            },
            before,
        )
        lock = result.output.parent / ".modelo-build.lock"
        temporaries = list(result.output.parent.glob("..modelo-build.lock.*.tmp"))
        self.assertTrue(lock.exists()); self.assertEqual(len(temporaries), 1)
        temporaries[0].unlink(); lock.unlink()

    def test_foreign_journal_temporaries_are_ambiguous_and_never_removed(self) -> None:
        result = build_candidate(self.request())
        layout = build_module._layout(self.repository.root)
        inventory = build_module._candidate_inventory(self.repository.root, result.output, layout)
        parent = result.output.parent
        lock = parent / ".modelo-build.lock"
        record = build_module._record("stage", "candidate", "e" * 32, inventory, inventory)
        raw = canonical_bytes(record)
        for index, kind in enumerate(("foreign-bytes", "forged-record", "symlink", "directory"), start=999):
            with self.subTest(kind=kind):
                lock.write_bytes(raw)
                temporary = parent / f".{lock.name}.{record['token']}.{index}.tmp"
                if kind == "foreign-bytes":
                    temporary.write_bytes(b"foreign")
                elif kind == "forged-record":
                    temporary.write_bytes(raw)
                elif kind == "symlink":
                    temporary.symlink_to(lock)
                else:
                    temporary.mkdir()
                before = {
                    path.relative_to(result.output).as_posix(): path.read_bytes()
                    for path in result.output.rglob("*") if path.is_file()
                }
                with self.assertRaisesRegex(BuildError, "ambiguous build recovery journal temporary"):
                    recover_candidate(self.repository.root)
                self.assertEqual(lock.read_bytes(), raw)
                self.assertTrue(temporary.exists() or temporary.is_symlink())
                self.assertEqual(
                    {
                        path.relative_to(result.output).as_posix(): path.read_bytes()
                        for path in result.output.rglob("*") if path.is_file()
                    },
                    before,
                )
                if temporary.is_dir() and not temporary.is_symlink():
                    temporary.rmdir()
                else:
                    temporary.unlink()
                lock.unlink()

    def test_old_absent_caught_failure_matrix_is_restart_safe(self) -> None:
        result = build_candidate(self.request())
        files, manifest = self.changed_publication(result)
        layout = build_module._layout(self.repository.root)
        __import__("shutil").rmtree(result.output)
        real_persist = build_module._persist_journal
        phases = (
            "lock", "stage", "fsync_stage", "validate_stage", "backup_old",
            "promote_new", "fsync_parent", "verify_target", "remove_backup",
        )
        for phase in phases:
            with self.subTest(phase=phase):
                def injected(parent, lock, journal, *, initial=False, selected=phase):
                    if journal["phase"] == selected:
                        raise OSError(f"injected {selected}")
                    return real_persist(parent, lock, journal, initial=initial)
                with patch.object(build_module, "_persist_journal", side_effect=injected), self.assertRaises(OSError):
                    build_module._publish(self.repository.root, result.output, files, manifest, layout)
                self.assertFalse(result.output.exists())
                self.assertFalse((result.output.parent / ".modelo-build.lock").exists())

    def test_partial_off_path_staging_and_backup_cleanup_resume(self) -> None:
        result = build_candidate(self.request())
        layout = build_module._layout(self.repository.root)
        parent = result.output.parent
        old = build_module._candidate_inventory(self.repository.root, result.output, layout)
        files, manifest = self.changed_publication(result)
        build_module._publish(self.repository.root, result.output, files, manifest, layout)
        new = build_module._candidate_inventory(self.repository.root, result.output, layout)
        new_source = Path(tempfile.mkdtemp(prefix="modelo-partial-new-")) / "candidate"
        __import__("shutil").copytree(result.output, new_source)
        self.addCleanup(__import__("shutil").rmtree, new_source.parent, ignore_errors=True)
        # Resume a precommit rollback after old was restored and deletion of
        # the off-path new staging tree had already begun.
        old_source = Path(tempfile.mkdtemp(prefix="modelo-partial-old-")) / "candidate"
        build_candidate(self.request())
        __import__("shutil").copytree(result.output, old_source)
        self.addCleanup(__import__("shutil").rmtree, old_source.parent, ignore_errors=True)
        token = "6" * 31 + "0"
        staging = parent / f"candidate.{token}.staging"
        __import__("shutil").copytree(new_source, staging)
        (staging / "site/data/catalogue.json").unlink()
        (parent / ".modelo-build.lock").write_bytes(canonical_bytes(
            build_module._record("verify_target", "candidate", token, old, new)
        ))
        recover_candidate(self.repository.root)
        self.assertFalse(staging.exists())
        self.assertEqual(build_module._candidate_inventory(self.repository.root, result.output, layout), old)
        # Resume committed cleanup after backup deletion had partially run.
        token = "6" * 31 + "1"
        build_module._publish(self.repository.root, result.output, files, manifest, layout)
        backup = parent / f"candidate.{token}.backup"
        __import__("shutil").copytree(old_source, backup)
        (backup / "site/data/change-delta.json").unlink()
        (parent / ".modelo-build.lock").write_bytes(canonical_bytes(
            build_module._record("remove_backup", "candidate", token, old, new)
        ))
        self.assertIs(recover_candidate(self.repository.root), build_module.RecoveryOutcome.COMMITTED)
        self.assertFalse(backup.exists())
        self.assertEqual(build_module._candidate_inventory(self.repository.root, result.output, layout), new)


if __name__ == "__main__":
    unittest.main()
