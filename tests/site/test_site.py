from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import modelo.build as build_module
from modelo.build import BuildError, _layout, _projection_from_snapshot, recover_candidate
from modelo.change import with_snapshot
from modelo.mac import compute_keys
from modelo.mac import render_adapter_issue_body
from modelo.github_adapter import prepare_github, prepare_github_control
from modelo.platform import (
    TrustedCheckRequest, TrustedControlCheckRequest, _verify_protected_workflow,
    run_trusted_check,
    run_trusted_control_check,
)
from modelo.receipt import canonical_bytes, manifest_entries, publication_digest, sha256_bytes
from modelo.site import (
    DemoBuildRequest,
    FinalBuildRequest,
    ValidationBuildRequest,
    _Resolver,
    _entry,
    _history_html,
    _pricing_rows,
    _route_rows,
    build_demo_site,
    build_final_site,
    build_validation_site,
)


ROOT = Path(__file__).resolve().parents[2]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.links = []; self.ids = set(); self.tables = []
    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs: self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs: self.links.append((attrs["href"], attrs.get("rel", "")))
        if tag == "table": self.tables.append(False)
        if tag == "caption" and self.tables: self.tables[-1] = True


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=root, text=True, capture_output=True, check=True
    ).stdout.strip()


class FinalSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repository"
        shutil.copytree(
            ROOT,
            self.root,
            ignore=shutil.ignore_patterns(".git", "dist", "__pycache__", "*.pyc"),
        )
        shutil.copytree(
            self.root / "tests/fixtures/build/synthetic", self.root / "catalogue",
            dirs_exist_ok=True,
        )
        actors = self.root / "catalogue/governance/actors.yaml"
        actors.parent.mkdir(parents=True, exist_ok=True)
        actors.write_text("version: 1\nagents: {}\n", encoding="utf-8", newline="\n")
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Site fixture")
        git(self.root, "config", "user.email", "site@example.invalid")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base implementation")
        self.base = git(self.root, "rev-parse", "HEAD")
        history_path = self.root / "tests/fixtures/build/synthetic/history.txt"
        history_path.write_text("added\n", encoding="utf-8", newline="\n")
        git(self.root, "add", "."); git(self.root, "commit", "-m", 'add <script>alert("history")</script> marker')
        history_path.write_text("changed\n", encoding="utf-8", newline="\n")
        git(self.root, "add", "."); git(self.root, "commit", "-m", "change history marker")
        history_path.unlink()
        git(self.root, "add", "."); git(self.root, "commit", "-m", "revoke history marker")
        condition = self.root / "catalogue/policies/conditions/test-condition/2.yaml"
        condition.parent.mkdir(parents=True, exist_ok=True)
        condition.write_text(
            "id: test-condition\nversion: 2\ntitle: Second condition\n"
            "description: Synthetic second immutable version.\nowner: Test policy owner\n",
            encoding="utf-8", newline="\n",
        )
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "add synthetic condition")
        self.source = git(self.root, "rev-parse", "HEAD")
        self.tree = git(self.root, "rev-parse", "HEAD^{tree}")
        self.epoch = int(git(self.root, "show", "-s", "--format=%at", self.source))
        layout = _layout(self.root)
        projection = with_snapshot(
            self.root,
            self.source,
            lambda snapshot: _projection_from_snapshot(
                snapshot,
                "synthetic",
                self.source,
                self.tree,
                date(2026, 9, 1),
                layout,
            ),
        )
        catalogue = canonical_bytes(projection)
        delta = canonical_bytes([])
        data = self.root / "dist" / "candidate" / "site" / "data"
        data.mkdir(parents=True)
        (data / "catalogue.json").write_bytes(catalogue)
        (data / "change-delta.json").write_bytes(delta)
        candidate_files = {
            "data/catalogue.json": catalogue,
            "data/change-delta.json": delta,
        }
        manifest = {
            "contract_version": "0.1.0",
            "kind": "candidate",
            "base_commit": self.base,
            "source_commit": self.source,
            "source_tree": self.tree,
            "as_of": "2026-09-01",
            "source_date_epoch": self.epoch,
            "profile": "synthetic",
            "base_url": None,
            "base_path": "/Modelo/",
            "promotion_durability": "fsync-durable",
            "catalogue_path": "data/catalogue.json",
            "change_delta_path": "data/change-delta.json",
            "manifest_path": "data/manifest.json",
            "digest_algorithm": "sha256",
            "publication_digest": publication_digest(candidate_files),
            "files": manifest_entries(candidate_files),
        }
        (data / "manifest.json").write_bytes(canonical_bytes(manifest))
        path = "catalogue/policies/conditions/test-condition/2.yaml"
        delta_record = [{"operation": "add", "path": path, "after": sha256_bytes((self.root / path).read_bytes())}]
        self.expected_delta = canonical_bytes(delta_record)
        payload = json.loads((ROOT / "tests/fixtures/mac/add.json").read_text(encoding="utf-8"))
        payload["subjects"] = [{"kind": "condition", "identity": "test-condition"}]
        payload["dedupe_key"] = "sha256-" + "0" * 64
        payload["idempotency_key"] = "sha256-" + "0" * 64
        payload["dedupe_key"], payload["idempotency_key"] = compute_keys(payload)
        metadata = {
            "contract_version": "0.1.0",
            "repository": {"provider": "github", "host": "github.com", "namespace": "j3brns996", "name": "Modelo"},
            "issue": {"reference": "27", "url": "https://github.com/j3brns996/Modelo/issues/27", "state": "open"},
            "base_sha": self.base, "head_sha": self.source, "head_tree_sha": self.tree,
            "payload": payload, "payload_digest": sha256_bytes(canonical_bytes(payload)),
            "expected_change_delta": delta_record,
        }
        metadata_file = tempfile.NamedTemporaryFile(prefix="modelo-site-metadata-", suffix=".json", delete=False)
        self.metadata_path = Path(metadata_file.name)
        metadata_file.write(canonical_bytes(metadata)); metadata_file.close()
        git(self.root, "commit", "--allow-empty", "-m", "merge MAC 27")
        self.merge = git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.metadata_path.unlink(missing_ok=True)
        self.temporary.cleanup()

    def request(self, *, base_path: str = "/Modelo/", base_url: str | None = None) -> FinalBuildRequest:
        return FinalBuildRequest(
            root=self.root,
            base_commit=self.base,
            source_commit=self.source,
            source_tree=self.tree,
            merge_commit=self.merge,
            merge_tree=self.tree,
            as_of=date(2026, 9, 1),
            source_date_epoch=self.epoch,
            profile="synthetic",
            base_url=base_url or f"https://example.invalid{base_path}",
            base_path=base_path,
            output="dist/final",
            mac_metadata=self.metadata_path,
            publication_capability="public-pages",
        )

    def demo_request(self) -> DemoBuildRequest:
        return DemoBuildRequest(
            root=self.root, source_commit=self.source, source_tree=self.tree,
            as_of=date(2026, 9, 1), source_date_epoch=self.epoch,
            base_url="https://example.invalid/Modelo/", base_path="/Modelo/",
            output="dist/pages",
        )

    def test_demo_is_deterministic_synthetic_and_never_claims_approval(self) -> None:
        git(self.root, "checkout", "--detach", self.source)
        first = build_demo_site(self.demo_request())
        first_bytes = {
            item.relative_to(first.output).as_posix(): item.read_bytes()
            for item in first.output.rglob("*") if item.is_file()
        }
        second = build_demo_site(self.demo_request())
        second_bytes = {
            item.relative_to(second.output).as_posix(): item.read_bytes()
            for item in second.output.rglob("*") if item.is_file()
        }
        self.assertEqual(first_bytes, second_bytes)
        site = first.output / "site"
        manifest = json.loads((site / "data/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["kind"], "demo")
        self.assertEqual(manifest["profile"], "synthetic")
        self.assertEqual((site / "data/change-delta.json").read_bytes(), canonical_bytes([]))
        self.assertNotIn("merge_commit", manifest)
        self.assertNotIn("validation_commit", manifest)
        for page in site.rglob("*.html"):
            rendered = page.read_text(encoding="utf-8")
            self.assertIn("Synthetic demo.", rendered)
            self.assertIn("not an approved enterprise catalogue", rendered)
            self.assertNotIn("Approval merge", rendered)
        offering = (site / "offerings/aws-bedrock/test-offering/index.html").read_text(encoding="utf-8")
        self.assertIn("Demo provenance", offering)
        self.assertIn("not approved for enterprise use", offering)

    def test_demo_rejects_wrong_output_and_dirty_tree(self) -> None:
        git(self.root, "checkout", "--detach", self.source)
        with self.assertRaisesRegex(BuildError, "output must equal configured pages_root"):
            build_demo_site(replace(self.demo_request(), output="dist/final"))
        (self.root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(BuildError, "working tree is dirty"):
            build_demo_site(self.demo_request())

    def test_demo_requires_configured_synthetic_snapshot_date(self) -> None:
        git(self.root, "checkout", "--detach", self.source)
        with self.assertRaisesRegex(BuildError, "configured synthetic fixture snapshot date"):
            build_demo_site(replace(self.demo_request(), as_of=date(2026, 9, 2)))

    def test_demo_rejects_tampered_vendored_runtime(self) -> None:
        git(self.root, "checkout", "--detach", self.source)
        runtime = self.root / "site/assets/vendor/alpine-csp-3.16.3.min.js"
        runtime.write_bytes(runtime.read_bytes() + b"\n")
        git(self.root, "add", runtime.relative_to(self.root).as_posix())
        git(self.root, "commit", "-m", "tamper with browser runtime")
        source = git(self.root, "rev-parse", "HEAD")
        request = replace(
            self.demo_request(),
            source_commit=source,
            source_tree=git(self.root, "rev-parse", "HEAD^{tree}"),
            source_date_epoch=int(git(self.root, "show", "-s", "--format=%at", source)),
        )
        with self.assertRaisesRegex(BuildError, "runtime digest differs"):
            build_demo_site(request)

    def test_exact_inventory_manifest_and_candidate_bytes(self) -> None:
        result = build_final_site(self.request())
        site = result.output / "site"
        manifest = json.loads((site / "data/manifest.json").read_text())
        actual = {
            path.relative_to(site).as_posix()
            for path in site.rglob("*") if path.is_file()
        }
        self.assertEqual(actual, set(manifest["files"]) | {"data/manifest.json"})
        self.assertEqual(
            (site / "data/catalogue.json").read_bytes(),
            (self.root / "dist/candidate/site/data/catalogue.json").read_bytes(),
        )
        self.assertEqual(
            (site / "data/change-delta.json").read_bytes(),
            self.expected_delta,
        )
        self.assertEqual(manifest["merge_commit"], self.merge)
        self.assertEqual(manifest["merge_tree"], self.tree)
        self.assertNotIn("data/manifest.json", manifest["files"])

    def test_rebuild_is_byte_identical(self) -> None:
        first = build_final_site(self.request())
        first_bytes = {
            item.relative_to(first.output).as_posix(): item.read_bytes()
            for item in first.output.rglob("*") if item.is_file()
        }
        second = build_final_site(self.request())
        second_bytes = {
            item.relative_to(second.output).as_posix(): item.read_bytes()
            for item in second.output.rglob("*") if item.is_file()
        }
        self.assertEqual(first_bytes, second_bytes)

    def test_validation_site_binds_exact_test_merge_without_claiming_approval(self) -> None:
        validation = git(
            self.root, "commit-tree", self.tree,
            "-p", self.base, "-p", self.source,
            "-m", "synthetic validation integration",
        )
        git(self.root, "checkout", "--detach", validation)
        request = ValidationBuildRequest(
            root=self.root, base_commit=self.base, source_commit=self.source,
            source_tree=self.tree, validation_commit=validation,
            validation_tree=self.tree, as_of=date(2026, 9, 1),
            source_date_epoch=self.epoch, profile="synthetic",
            base_url="https://example.invalid/Modelo/", base_path="/Modelo/",
            output="dist/validation", mac_metadata=self.metadata_path,
            publication_capability="public-pages",
        )
        result = build_validation_site(request)
        manifest = json.loads(
            (result.output / "site/data/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["kind"], "validation")
        self.assertEqual(manifest["validation_commit"], validation)
        self.assertEqual(manifest["validation_tree"], self.tree)
        self.assertNotIn("merge_commit", manifest)
        home = (result.output / "site/index.html").read_text(encoding="utf-8")
        offering = (
            result.output / "site/offerings/aws-bedrock/test-offering/index.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Validation integration", home)
        self.assertNotIn("Approval merge", home)
        self.assertIn("Validation coordinates", offering)
        self.assertIn("not approval", offering)

        wrong_order = git(
            self.root, "commit-tree", self.tree,
            "-p", self.source, "-p", self.base,
            "-m", "wrong validation parents",
        )
        git(self.root, "checkout", "--detach", wrong_order)
        with self.assertRaisesRegex(BuildError, "exact base and source parents"):
            build_validation_site(replace(request, validation_commit=wrong_order))

    def test_trusted_platform_check_binds_validation_and_writes_detached_receipt(self) -> None:
        validation = git(
            self.root, "commit-tree", self.tree, "-p", self.base, "-p", self.source,
            "-m", "trusted validation integration",
        )
        git(self.root, "checkout", "--detach", validation)
        context = {
            "contract_version": "0.1.0",
            "repository": {"provider": "github", "host": "github.com", "namespace": "j3brns996", "name": "Modelo"},
            "change_request": "29", "base_sha": self.base, "head_sha": self.source,
            "head_tree_sha": self.tree, "validation_sha": validation,
            "validation_tree_sha": self.tree, "as_of": "2026-09-01",
            "source_date_epoch": self.epoch, "profile": "synthetic",
            "base_url": "https://j3brns996.github.io/Modelo/", "base_path": "/Modelo/",
            "publication_capability": "public-pages",
            "workflow_identity": "j3brns996/Modelo/.github/workflows/modelo.yml@main",
            "workflow_sha": self.base, "run_id": "123", "check_name": "modelo/check",
            "gates": {"lock": "success", "schema": "success", "tests": "success", "package": "success"},
        }
        context_path = self.root / "trusted-context.json"
        context_path.write_bytes(canonical_bytes(context))
        git(self.root, "add", "trusted-context.json")
        # The adapter context is external in production; keep this fixture untracked
        # while allowing the trusted builder's clean-tree check to see a clean tree.
        git(self.root, "reset", "--", "trusted-context.json")
        context_path.unlink()
        external = Path(self.temporary.name) / "trusted-context.json"
        external.write_bytes(canonical_bytes(context))
        output = self.root / "dist/receipts/check.json"
        receipt = run_trusted_check(TrustedCheckRequest(
            root=self.root, context=external, mac_metadata=self.metadata_path, output=output,
        ))
        self.assertEqual(receipt["validation_sha"], validation)
        self.assertEqual(receipt["validation_tree_sha"], self.tree)
        self.assertEqual(receipt["ci"]["head_sha"], self.source)
        self.assertEqual(receipt["ci"]["workflow_sha"], self.base)
        self.assertEqual(output.read_bytes(), canonical_bytes(receipt))
        bad = dict(context); bad["workflow_sha"] = self.source
        external.write_bytes(canonical_bytes(bad))
        with self.assertRaisesRegex(BuildError, "workflow SHA"):
            run_trusted_check(TrustedCheckRequest(
                root=self.root, context=external, mac_metadata=self.metadata_path, output=output,
            ))
        bad = dict(context)
        bad["workflow_identity"] = "j3brns996/Modelo/.github/workflows/forged.yml@main"
        external.write_bytes(canonical_bytes(bad))
        with self.assertRaisesRegex(BuildError, "workflow identity"):
            run_trusted_check(TrustedCheckRequest(
                root=self.root, context=external, mac_metadata=self.metadata_path, output=output,
            ))
        external.write_text('{"contract_version":"0.1.0","contract_version":"0.1.0"}\n', encoding="utf-8")
        with self.assertRaisesRegex(BuildError, "strict trusted check context JSON"):
            run_trusted_check(TrustedCheckRequest(
                root=self.root, context=external, mac_metadata=self.metadata_path, output=output,
            ))

    def test_protected_workflow_identity_is_provider_specific_and_exact(self) -> None:
        github = {
            "repository": {
                "adapter": "github", "host": "github.example.invalid",
                "namespace": "platform", "name": "registry",
            },
            "paths": {"github_adapter": ".github", "gitlab_ci": ".gitlab-ci.yml"},
            "project": {"default_branch": "main"},
        }
        github_context = {
            "repository": {
                "provider": "github", "host": "github.example.invalid",
                "namespace": "platform", "name": "registry",
            },
            "workflow_identity": "platform/registry/.github/workflows/modelo.yml@main",
        }
        _verify_protected_workflow(github_context, github)

        gitlab = json.loads(json.dumps(github))
        gitlab["repository"].update({
            "adapter": "gitlab", "host": "gitlab.example.invalid",
            "namespace": "group/subgroup", "name": "catalogue",
        })
        gitlab["project"]["default_branch"] = "stable"
        gitlab_context = {
            "repository": {
                "provider": "gitlab", "host": "gitlab.example.invalid",
                "namespace": "group/subgroup", "name": "catalogue",
            },
            "workflow_identity": "group/subgroup/catalogue/.gitlab-ci.yml@stable",
        }
        _verify_protected_workflow(gitlab_context, gitlab)

        for forged_identity in (
            "other/catalogue/.gitlab-ci.yml@stable",
            "group/subgroup/other/.gitlab-ci.yml@stable",
            "group/subgroup/catalogue/ci/forged.yml@stable",
            "group/subgroup/catalogue/.gitlab-ci.yml@main",
        ):
            forged = {**gitlab_context, "workflow_identity": forged_identity}
            with self.subTest(workflow_identity=forged_identity):
                with self.assertRaisesRegex(BuildError, "workflow identity"):
                    _verify_protected_workflow(forged, gitlab)

        for field, value in (
            ("provider", "github"),
            ("host", "gitlab.invalid"),
            ("namespace", "forged/group"),
            ("name", "forged"),
        ):
            forged_repository = {**gitlab_context["repository"], field: value}
            forged = {**gitlab_context, "repository": forged_repository}
            with self.subTest(repository_field=field):
                with self.assertRaisesRegex(BuildError, "repository identity"):
                    _verify_protected_workflow(forged, gitlab)

        unknown = json.loads(json.dumps(gitlab))
        unknown["repository"]["adapter"] = "unknown"
        with self.assertRaisesRegex(BuildError, "provider is unsupported"):
            _verify_protected_workflow(gitlab_context, unknown)

    def test_github_adapter_binds_issue_pr_and_git_coordinates(self) -> None:
        validation = git(
            self.root, "commit-tree", self.tree, "-p", self.base, "-p", self.source,
            "-m", "adapter validation integration",
        )
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        delta = json.dumps(metadata["expected_change_delta"], sort_keys=True, indent=2)
        body = (
            "## Linked MAC\n\n- Issue: <!-- modelo:mac-issue -->"
            "https://github.com/j3brns996/Modelo/issues/27<!-- /modelo:mac-issue -->\n\n"
            f"- Neutral payload digest: `{metadata['payload_digest']}`\n\n"
            "## Expected change delta\n\n<!-- modelo:change-delta -->\n```json\n"
            + delta + "\n```\n<!-- /modelo:change-delta -->\n"
        )
        event = {
            "repository": {"full_name": "j3brns996/Modelo", "default_branch": "main"},
            "pull_request": {
                "number": 29, "state": "open", "body": body,
                "base": {"sha": self.base, "ref": "main"},
                "head": {"sha": self.source, "repo": {"full_name": "j3brns996/Modelo"}},
            },
        }
        issue = {
            "number": 27, "state": "open",
            "html_url": "https://github.com/j3brns996/Modelo/issues/27",
            "body": render_adapter_issue_body(metadata["payload"], "github"),
        }
        event_path = Path(self.temporary.name) / "event.json"
        issue_path = Path(self.temporary.name) / "issue.json"
        prepared_metadata = Path(self.temporary.name) / "prepared-metadata.json"
        prepared_context = Path(self.temporary.name) / "prepared-context.json"
        event_path.write_bytes(canonical_bytes(event)); issue_path.write_bytes(canonical_bytes(issue))
        prepare_github(
            root=self.root, event_path=event_path, issue_path=issue_path,
            validation_sha=validation, validation_tree=self.tree, as_of=date(2026, 9, 1),
            metadata_output=prepared_metadata, context_output=prepared_context,
        )
        actual_metadata = json.loads(prepared_metadata.read_text(encoding="utf-8"))
        actual_context = json.loads(prepared_context.read_text(encoding="utf-8"))
        self.assertEqual(actual_metadata["expected_change_delta"], metadata["expected_change_delta"])
        self.assertEqual(actual_metadata["payload_digest"], metadata["payload_digest"])
        self.assertEqual(actual_context["head_sha"], self.source)
        self.assertEqual(actual_context["validation_sha"], validation)
        wrong_branch = json.loads(json.dumps(event))
        wrong_branch["pull_request"]["base"]["ref"] = "develop"
        event_path.write_bytes(canonical_bytes(wrong_branch))
        with self.assertRaisesRegex(BuildError, "default branch"):
            prepare_github(
                root=self.root, event_path=event_path, issue_path=issue_path,
                validation_sha=validation, validation_tree=self.tree,
                as_of=date(2026, 9, 1), metadata_output=prepared_metadata,
                context_output=prepared_context,
            )
        duplicate_marker = json.loads(json.dumps(event))
        duplicate_marker["pull_request"]["body"] += (
            "\n- Issue: <!-- modelo:mac-issue -->https://github.com/j3brns996/Modelo/issues/27"
            "<!-- /modelo:mac-issue -->\n"
        )
        event_path.write_bytes(canonical_bytes(duplicate_marker))
        with self.assertRaisesRegex(BuildError, "one same-repository MAC issue"):
            prepare_github(
                root=self.root, event_path=event_path, issue_path=issue_path,
                validation_sha=validation, validation_tree=self.tree,
                as_of=date(2026, 9, 1), metadata_output=prepared_metadata,
                context_output=prepared_context,
            )

    def test_control_plane_mode_is_exact_head_and_human_only(self) -> None:
        git(self.root, "checkout", "--detach", self.source)
        marker = self.root / "docs/control-test.md"
        marker.write_text("synthetic control change\n", encoding="utf-8", newline="\n")
        git(self.root, "add", "docs/control-test.md")
        git(self.root, "commit", "-m", "synthetic control change")
        head = git(self.root, "rev-parse", "HEAD")
        tree = git(self.root, "rev-parse", "HEAD^{tree}")
        validation = git(
            self.root, "commit-tree", tree, "-p", self.source, "-p", head,
            "-m", "control validation integration",
        )
        event = {
            "repository": {"full_name": "j3brns996/Modelo", "default_branch": "main"},
            "pull_request": {
                "number": 30, "state": "open",
                "body": "- Issue: <!-- modelo:control-issue -->https://github.com/j3brns996/Modelo/issues/28<!-- /modelo:control-issue -->",
                "base": {"sha": self.source, "ref": "main"},
                "head": {"sha": head, "repo": {"full_name": "j3brns996/Modelo"}},
            },
        }
        event_path = Path(self.temporary.name) / "control-event.json"
        issue_path = Path(self.temporary.name) / "control-issue.json"
        context_path = Path(self.temporary.name) / "control-context.json"
        event_path.write_bytes(canonical_bytes(event))
        issue_path.write_bytes(canonical_bytes({
            "number": 28, "state": "open",
            "html_url": "https://github.com/j3brns996/Modelo/issues/28",
            "body": "Bootstrap trusted CI, portable skills and launch rehearsal.",
        }))
        prepare_github_control(
            root=self.root, event_path=event_path, issue_path=issue_path,
            validation_sha=validation,
            validation_tree=tree, as_of=date(2026, 9, 1), context_output=context_path,
        )
        git(self.root, "checkout", "--detach", validation)
        output = self.root / "dist/receipts/control-check.json"
        receipt = run_trusted_control_check(TrustedControlCheckRequest(
            root=self.root, context=context_path, output=output,
        ))
        self.assertEqual(receipt["kind"], "control-plane")
        self.assertEqual(receipt["approval_mode"], "human-codeowner-only")
        self.assertEqual(receipt["changed_paths"], ["docs/control-test.md"])
        self.assertEqual(receipt["control_issue"], "28")
        self.assertEqual(receipt["ci"]["workflow_sha"], self.source)

        forged_context = json.loads(context_path.read_text(encoding="utf-8"))
        forged_context["workflow_identity"] = "j3brns996/Modelo/.github/workflows/forged.yml@main"
        context_path.write_bytes(canonical_bytes(forged_context))
        with self.assertRaisesRegex(BuildError, "workflow identity"):
            run_trusted_control_check(TrustedControlCheckRequest(
                root=self.root, context=context_path, output=output,
            ))

        # A control-plane change may never smuggle catalogue data around the
        # MAC issue/payload contract. Mixed changes are rejected fail-closed.
        git(self.root, "checkout", "--detach", head)
        mixed = self.root / "catalogue/mixed-marker.yaml"
        mixed.write_text("marker: rejected\n", encoding="utf-8", newline="\n")
        git(self.root, "add", "catalogue/mixed-marker.yaml")
        git(self.root, "commit", "-m", "synthetic mixed change")
        mixed_head = git(self.root, "rev-parse", "HEAD")
        mixed_tree = git(self.root, "rev-parse", "HEAD^{tree}")
        mixed_validation = git(
            self.root, "commit-tree", mixed_tree, "-p", self.source, "-p", mixed_head,
            "-m", "mixed validation integration",
        )
        event["pull_request"]["head"]["sha"] = mixed_head
        event_path.write_bytes(canonical_bytes(event))
        prepare_github_control(
            root=self.root, event_path=event_path, issue_path=issue_path,
            validation_sha=mixed_validation, validation_tree=mixed_tree,
            as_of=date(2026, 9, 1), context_output=context_path,
        )
        git(self.root, "checkout", "--detach", mixed_validation)
        with self.assertRaisesRegex(BuildError, "forbids catalogue paths"):
            run_trusted_control_check(TrustedControlCheckRequest(
                root=self.root, context=context_path, output=output,
            ))

    def test_final_output_uses_the_configured_build_layout(self) -> None:
        current = _layout(self.root)
        publication = PurePosixPath("publish")
        alternate = replace(
            current,
            candidate_root=PurePosixPath("dist/alternate-candidate"),
            final_root=PurePosixPath("dist/alternate-final"),
            pages_root=PurePosixPath("dist/alternate-pages"),
            target_parent=PurePosixPath("dist"),
            publication_subdir=publication,
            candidate_inventory=tuple(
                publication / path.relative_to(current.publication_subdir)
                for path in current.candidate_inventory
            ),
            writer_lock=PurePosixPath("dist/.alternate-build.lock"),
        )
        request = replace(self.request(), output=alternate.final_root.as_posix())
        with (
            patch("modelo.site._layout", return_value=alternate),
            patch("modelo.build._layout", return_value=alternate),
        ):
            result = build_final_site(request)
        self.assertEqual(result.output, self.root / "dist/alternate-final")
        self.assertTrue((result.output / "publish/index.html").is_file())
        self.assertTrue((result.output / "publish/data/manifest.json").is_file())
        self.assertFalse((result.output / "site").exists())

        real_persist = build_module._persist_journal
        failed = False

        def fail_after_validated_stage(parent, lock, journal, *, initial=False):
            nonlocal failed
            real_persist(parent, lock, journal, initial=initial)
            if journal["phase"] == "validate_stage" and not failed:
                failed = True
                raise OSError("injected alternate-layout crash")

        with (
            patch("modelo.site._layout", return_value=alternate),
            patch("modelo.build._layout", return_value=alternate),
            patch.object(build_module, "_persist_journal", side_effect=fail_after_validated_stage),
            self.assertRaisesRegex(OSError, "alternate-layout crash"),
        ):
            build_final_site(request)
        self.assertFalse((self.root / "dist/.alternate-build.lock").exists())
        self.assertTrue((result.output / "publish/data/manifest.json").is_file())

    def test_project_subpath_links_and_no_javascript_navigation(self) -> None:
        result = build_final_site(self.request())
        site = result.output / "site"
        for html in site.rglob("*.html"):
            text = html.read_text(encoding="utf-8")
            self.assertIn('href="/Modelo/', text)
            self.assertIn('<main id="main"', text)
            self.assertIn('class="skip-link"', text)
            self.assertNotIn("javascript:", text.lower())
            self.assertNotIn(" onclick=", text.lower())

    def test_root_deployment(self) -> None:
        result = build_final_site(self.request(base_path="/", base_url="https://example.invalid/"))
        home = (result.output / "site/index.html").read_text()
        self.assertIn('href="/catalogue/"', home)
        self.assertNotIn('href="//', home)

    def test_missing_mutable_candidate_does_not_affect_trusted_rebuild(self) -> None:
        (self.root / "dist/candidate/site/data/change-delta.json").unlink()
        build_final_site(self.request())

    def test_mutable_candidate_drift_does_not_affect_trusted_rebuild(self) -> None:
        path = self.root / "dist/candidate/site/data/catalogue.json"
        path.write_bytes(path.read_bytes() + b" ")
        build_final_site(self.request())

    def test_merge_tree_must_equal_accepted_source_tree(self) -> None:
        request = self.request()
        bad = replace(request, merge_tree="0" * 40)
        with self.assertRaisesRegex(Exception, "merge tree"):
            build_final_site(bad)

    def test_shallow_history_fails_closed(self) -> None:
        original = subprocess.run
        def shallow(arguments, *args, **kwargs):
            if arguments[:3] == ["git", "rev-parse", "--is-shallow-repository"]:
                return subprocess.CompletedProcess(arguments, 0, "true\n", "")
            return original(arguments, *args, **kwargs)
        from unittest.mock import patch
        with patch("modelo.site.subprocess.run", side_effect=shallow):
            with self.assertRaisesRegex(Exception, "non-shallow"):
                build_final_site(self.request())

    def test_assets_have_no_unsafe_dom_or_remote_dependency(self) -> None:
        assets = (
            ROOT / "site/assets/catalogue.js",
            ROOT / "site/assets/proposal.js",
        )
        for asset in assets:
            javascript = asset.read_text().lower()
            for forbidden in ("innerhtml", "outerhtml", "document.write", "fetch(", "xmlhttprequest"):
                self.assertNotIn(forbidden, javascript, asset)
        base = (ROOT / "site/templates/base.html").read_text()
        self.assertIn("default-src 'none'", base)
        self.assertIn("style-src 'self' $font_style_origin", base)
        self.assertIn("font-src $font_file_origin", base)
        self.assertIn("connect-src 'self' $font_style_origin $font_file_origin", base)
        self.assertIn('href="$font_stylesheet_url"', base)
        self.assertIn('name="referrer" content="no-referrer"', base)
        runtime = (ROOT / "site/assets/vendor/alpine-csp-3.16.3.min.js").read_bytes()
        self.assertEqual(
            sha256_bytes(runtime),
            "sha256:0de89ad5a626c023982c2ed7051ef5fd3cbfa22d012de81fa19005c811bfad4d",
        )
        notices = (ROOT / "site/assets/vendor/THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
        self.assertEqual(notices.count("MIT License"), 2)
        self.assertIn("Caleb Porzio and contributors", notices)
        self.assertIn("Yuxi (Evan) You", notices)

    def test_product_shell_and_rich_synthetic_experience_contract(self) -> None:
        site = build_final_site(self.request()).output / "site"
        home = (site / "index.html").read_text(encoding="utf-8")
        catalogue = (site / "catalogue/index.html").read_text(encoding="utf-8")
        model = (site / "models/test-model/index.html").read_text(encoding="utf-8")
        css = (site / "assets/site.css").read_text(encoding="utf-8")
        for marker in (
            "home-hero", "console-grid", "governance-flow", "history-summary", "start-panel",
            "Browse models", "Available from a provider does not mean approved for your organisation.",
        ):
            self.assertIn(marker, home)
        for page in site.rglob("*.html"):
            rendered = page.read_text(encoding="utf-8")
            self.assertIn('class="site-header"', rendered)
            self.assertIn('class="site-footer"', rendered)
            self.assertIn("fonts.googleapis.com", rendered)
            self.assertIn("fonts.gstatic.com", rendered)
        self.assertIn('data-default-view="grid"', catalogue)
        self.assertIn('data-default-view="grid" data-view="grid"', catalogue)
        self.assertIn('data-view="grid" aria-pressed="true"', catalogue)
        for value in ("chat", "function-calling", "reasoning", "vision", "open-weights", "proprietary"):
            self.assertIn(f'data-value="{value}"', catalogue)
        self.assertIn("Atlas Reasoning", model)
        self.assertIn("128,000", model)
        self.assertIn("Intrinsic evidence", model)
        for contract in ("@media (max-width: 880px)", "@media (max-width: 580px)", ".model-card {", ".fact-grid"):
            self.assertIn(contract, css)
        self.assertIn("textarea[data-proposal-summary]", css)

    def test_catalogue_uses_dedicated_human_readable_model_cards(self) -> None:
        site = build_final_site(self.request()).output / "site"
        catalogue = (site / "catalogue/index.html").read_text(encoding="utf-8")
        css = (site / "assets/site.css").read_text(encoding="utf-8")
        self.assertEqual(catalogue.count("data-model-card"), 22)
        self.assertIn("22 models", catalogue)
        self.assertIn("Current governed catalogue", catalogue)
        self.assertIn("data-catalogue-grid", catalogue)
        self.assertIn("data-catalogue-table", catalogue)
        self.assertIn("model-card__description", catalogue)
        self.assertIn("model-card__facts", catalogue)
        self.assertIn("Nova Micro", catalogue)
        self.assertIn("Command R+", catalogue)
        self.assertIn("Embed v4", catalogue)
        self.assertNotIn("Synthetic example models and offerings</caption>", catalogue)
        self.assertIn('[data-view="grid"] [data-catalogue-table]', css)
        self.assertIn('[data-view="table"] [data-catalogue-grid]', css)

    def test_offering_explains_why_it_is_approved(self) -> None:
        site = build_final_site(self.request()).output / "site"
        offering = (site / "offerings/aws-bedrock/test-offering/index.html").read_text(encoding="utf-8")
        self.assertIn("Why this offering is approved", offering)
        self.assertIn("Approved for synthetic integration testing", offering)

    def test_progressive_explorer_contract_is_accessible_shareable_and_bounded(self) -> None:
        site = build_final_site(self.request()).output / "site"
        catalogue = (site / "catalogue/index.html").read_text(encoding="utf-8")
        javascript = (site / "assets/catalogue.js").read_text(encoding="utf-8")
        for marker in (
            'x-data="catalogueExplorer"', 'aria-live="polite"', "data-active-filters",
            "data-advanced-filters", "data-sort", 'data-view="grid"',
            "data-comparison-dialog", "data-comparison-content",
            'data-comparison-tray role="status" aria-live="polite"',
        ):
            self.assertIn(marker, catalogue)
        self.assertEqual(catalogue.count("data-compare-toggle"), 44)
        self.assertIn('data-search-max="200"', catalogue)
        self.assertIn('data-compare-max="4"', catalogue)
        self.assertIn('data-view-storage-key="modelo.catalogue.view.v1"', catalogue)
        self.assertIn('data-default-view="grid"', catalogue)
        self.assertIn("slice(0, this.compareMax)", javascript)
        self.assertIn("this.comparison.length < this.compareMax", javascript)
        self.assertIn("window.history.replaceState", javascript)
        self.assertIn("window.localStorage.getItem", javascript)
        self.assertIn("window.localStorage.setItem", javascript)
        self.assertLess(javascript.index('parameters.get("view")'), javascript.index("window.localStorage.getItem"))
        self.assertIn("url.searchParams.append", javascript)
        self.assertIn("dataset.searchText", javascript)
        self.assertIn('data-search-text="test-model|Atlas Reasoning|Synthetic reasoning model for governed catalogue demonstrations.|test-vendor', catalogue)
        self.assertIn("document.createElement", javascript)
        self.assertIn("textContent", javascript)
        self.assertLess(catalogue.index("/assets/catalogue.js"), catalogue.index("/assets/vendor/alpine-csp-3.16.3.min.js"))
        self.assertNotIn("<script src=\"http", catalogue)
        propose = (site / "propose/index.html").read_text(encoding="utf-8")
        self.assertIn('/Modelo/assets/proposal.js', propose)
        self.assertNotIn("catalogue.js", propose)
        self.assertNotIn("alpine-csp", propose)
        for page in site.rglob("*.html"):
            if page.relative_to(site).as_posix() in {"catalogue/index.html", "propose/index.html"}:
                continue
            rendered = page.read_text(encoding="utf-8")
            self.assertNotIn("catalogue.js", rendered, page)
            self.assertNotIn("proposal.js", rendered, page)
            self.assertNotIn("alpine-csp", rendered, page)

    def test_search_facets_docs_evidence_footer_and_history_contract(self) -> None:
        site = build_final_site(self.request()).output / "site"
        catalogue = (site / "catalogue/index.html").read_text(encoding="utf-8")
        for facet in ("kind", "vendor", "service", "source-region", "route-type", "capability", "modality", "licence", "lifecycle", "condition"):
            self.assertIn(f'data-filter="{facet}"', catalogue)
        self.assertIn("data-catalogue-row", catalogue)
        model = (site / "models/test-model/index.html").read_text(encoding="utf-8")
        self.assertIn("Intrinsic evidence", model)
        self.assertIn("sha256-", model)
        docs = (site / "docs/index.html").read_text(encoding="utf-8")
        self.assertIn("/Modelo/docs/SPEC.md", docs)
        self.assertIn("/Modelo/docs/contract.yaml", docs)
        home = (site / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'href="https://github.com/j3brns996/Modelo/commit/{self.source}"', home)
        self.assertIn(f'href="https://github.com/j3brns996/Modelo/commit/{self.merge}"', home)
        changes = (site / "changes/index.html").read_text(encoding="utf-8")
        for operation in ("add: ", "change: ", "revoke: "):
            self.assertIn(operation + "tests/fixtures/build/synthetic/history.txt", changes)

    def test_proposal_form_builder_is_scoped_configured_and_noncanonical(self) -> None:
        site = build_final_site(self.request()).output / "site"
        propose_page = (site / "propose/index.html").read_text(encoding="utf-8")

        self.assertIn('<form data-proposal-builder', propose_page)
        for field in (
            'data-field="operation"',
            'data-field="subject-kind"',
            'data-field="subject-identity"',
            'data-field="purpose"',
            'data-field="outcome"',
            'data-field="reason"',
            'data-field="candidate-evidence"',
            'data-field="acceptance"',
        ):
            self.assertIn(field, propose_page)

        for op in ("add", "change"):
            self.assertIn(f'value="{op}"', propose_page)
        operation_control = propose_page.split('id="proposal-operation"', 1)[1].split("</select>", 1)[0]
        for unsupported in ("revoke", "move", "batch"):
            self.assertNotIn(f'value="{unsupported}"', operation_control)
        self.assertEqual(propose_page.count('class="intake-card" rel="noopener noreferrer"'), 5)
        for kind in ("model", "offering", "evidence", "vendor", "inference-service", "condition"):
            self.assertIn(f'value="{kind}"', propose_page)

        for control_id in (
            "proposal-operation",
            "proposal-subject-kind",
            "proposal-subject-identity",
            "proposal-purpose",
            "proposal-requested-outcome",
            "proposal-reason",
            "proposal-candidate-evidence",
            "proposal-acceptance",
            "proposal-summary-output",
        ):
            self.assertIn(f'for="{control_id}"', propose_page)
            self.assertIn(f'id="{control_id}"', propose_page)

        self.assertIn('data-proposal-summary', propose_page)
        self.assertIn('data-copy-summary', propose_page)
        self.assertIn('data-proposal-issue-link', propose_page)
        for status in ("data-proposal-url-status", "data-proposal-copy-status"):
            self.assertIn(status, propose_page)
        self.assertEqual(propose_page.count('role="status" aria-live="polite" aria-atomic="true"'), 2)
        self.assertIn('data-intake-add="https://github.com/j3brns996/Modelo/issues/new?template=mac-add.yml"', propose_page)
        self.assertIn('data-intake-change="https://github.com/j3brns996/Modelo/issues/new?template=mac-change.yml"', propose_page)
        self.assertIn('href="https://github.com/j3brns996/Modelo/issues/new?template=mac-add.yml"', propose_page)
        self.assertIn('rel="noopener noreferrer"', propose_page)
        self.assertIn("non-canonical", propose_page)
        self.assertIn("not a MAC payload", propose_page)
        self.assertNotIn("YAML", propose_page)
        self.assertIn('/Modelo/assets/proposal.js', propose_page)
        self.assertNotIn('/Modelo/assets/catalogue.js', propose_page)
        self.assertNotIn('/Modelo/assets/vendor/alpine-csp-3.16.3.min.js', propose_page)

    def test_proposal_urls_follow_overridden_repository_configuration(self) -> None:
        git(self.root, "checkout", "--detach", self.source)
        config_path = self.root / "modelo.yaml"
        config = config_path.read_text(encoding="utf-8")
        config = config.replace("host: github.com", "host: code.example.invalid")
        config = config.replace("namespace: j3brns996", "namespace: platform")
        config = config.replace("name: Modelo", "name: Registry")
        config = config.replace(
            "web_base: https://github.com/j3brns996/Modelo",
            "web_base: https://code.example.invalid/platform/Registry",
        )
        config = config.replace(
            "add: /issues/new?template=mac-add.yml",
            "add: /tickets/new?intake=add-v2",
        )
        config = config.replace(
            "change: /issues/new?template=mac-change.yml",
            "change: /tickets/new?intake=change-v2",
        )
        config_path.write_text(config, encoding="utf-8", newline="\n")
        git(self.root, "add", "modelo.yaml")
        git(self.root, "commit", "-m", "override configured proposal routes")
        source = git(self.root, "rev-parse", "HEAD")
        request = replace(
            self.demo_request(),
            source_commit=source,
            source_tree=git(self.root, "rev-parse", "HEAD^{tree}"),
            source_date_epoch=int(git(self.root, "show", "-s", "--format=%at", source)),
        )
        page = (build_demo_site(request).output / "site/propose/index.html").read_text(encoding="utf-8")
        add = "https://code.example.invalid/platform/Registry/tickets/new?intake=add-v2"
        change = "https://code.example.invalid/platform/Registry/tickets/new?intake=change-v2"
        self.assertIn(f'data-intake-add="{add}"', page)
        self.assertIn(f'data-intake-change="{change}"', page)
        self.assertNotIn("github.com/j3brns996/Modelo/issues/new", page)

    def test_generated_site_crawl_canonical_fragments_external_rel_and_captions(self) -> None:
        site = build_final_site(self.request()).output / "site"
        emitted = {path.relative_to(site).as_posix() for path in site.rglob("*") if path.is_file()}
        for page in site.rglob("*.html"):
            parser = LinkParser(); parser.feed(page.read_text(encoding="utf-8"))
            self.assertTrue(all(parser.tables), page)
            for href, rel in parser.links:
                if href.startswith("https://"):
                    self.assertEqual(set(rel.split()), {"noopener", "noreferrer"}, (page, href))
                    continue
                local, _, fragment = href.removeprefix("/Modelo/").partition("#")
                if href.startswith("#"):
                    local, fragment = page.relative_to(site).as_posix(), href[1:]
                target = local + "index.html" if local.endswith("/") else local
                if not target: target = "index.html"
                self.assertIn(target, emitted, (page, href))
                if fragment:
                    target_parser = LinkParser(); target_parser.feed((site / target).read_text(encoding="utf-8"))
                    self.assertIn(fragment, target_parser.ids)

    def test_private_profile_requires_explicit_restricted_capability(self) -> None:
        with self.assertRaisesRegex(BuildError, "restricted capability"):
            build_final_site(replace(self.request(), profile="private"))

    def test_malicious_values_are_inert(self) -> None:
        rendered = _history_html([{"url": "https://example.invalid/x", "sha": "a" * 40, "date": "2026-09-01", "subject": '<script>alert("x")</script>', "changes": ['add: <img src=x onerror=alert(1)>']}])
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        site = build_final_site(self.request()).output / "site"
        generated = b"\n".join(path.read_bytes() for path in site.rglob("*") if path.is_file())
        self.assertNotIn(b'<script>alert("history")</script>', generated)
        self.assertIn(b'&lt;script&gt;alert(&quot;history&quot;)&lt;/script&gt;', generated)

    def test_synthetic_generated_bytes_fail_on_private_canary_in_history(self) -> None:
        import modelo.site as site_module
        canary = "MODELO_PRIVATE_CANARY"
        with patch.object(site_module, "_history", return_value=[{
            "sha": "a" * 40, "date": "2026-09-01", "subject": canary,
            "changes": ["add: harmless"], "url": "https://example.invalid/commit",
        }]):
            with self.assertRaisesRegex(BuildError, "private leakage"):
                build_final_site(self.request())

    def test_missing_and_extra_generated_inventory_fail_exactly(self) -> None:
        import modelo.site as site_module
        real = site_module._site_files
        for mode in ("missing", "extra"):
            with self.subTest(mode=mode):
                def changed(*args, selected=mode, **kwargs):
                    files = real(*args, **kwargs)
                    if selected == "missing": files.pop("index.html")
                    else: files["undeclared.txt"] = b"extra\n"
                    return files
                with patch.object(site_module, "_site_files", side_effect=changed):
                    with self.assertRaisesRegex(BuildError, "inventory mismatch"):
                        build_final_site(self.request())

    def test_disjoint_final_tree_rebuild_is_byte_identical(self) -> None:
        first = build_final_site(self.request())
        snapshot = {
            path.relative_to(first.output).as_posix(): path.read_bytes()
            for path in first.output.rglob("*") if path.is_file()
        }
        with tempfile.TemporaryDirectory(prefix="modelo-disjoint-final-") as temporary:
            displaced = Path(temporary) / "first-final-tree"
            first.output.rename(displaced)
            second = build_final_site(self.request())
            rebuilt = {
                path.relative_to(second.output).as_posix(): path.read_bytes()
                for path in second.output.rglob("*") if path.is_file()
            }
            self.assertEqual(rebuilt, snapshot)

    def test_github_gitlab_root_subpath_and_route_collision(self) -> None:
        routes = {
            "home": "/", "catalogue": "/catalogue/", "model": "/models/{model_id}/",
            "offering": "/offerings/{inference_service_id}/{offering_id}/", "changes": "/changes/",
            "process": "/process/", "propose": "/propose/", "docs": "/docs/", "not_found": "/404.html",
            "asset_css": "/assets/site.css", "asset_catalogue_js": "/assets/catalogue.js",
            "asset_proposal_js": "/assets/proposal.js",
            "asset_alpine": "/assets/vendor/alpine-csp-3.16.3.min.js",
            "asset_third_party_notices": "/assets/vendor/THIRD-PARTY-NOTICES.md",
            "catalogue_data": "/data/catalogue.json", "change_delta_data": "/data/change-delta.json",
            "manifest_data": "/data/manifest.json", "schemas_data": "/data/schemas/",
            "human_specification": "/docs/SPEC.md", "machine_contract": "/docs/contract.yaml",
        }
        for base_url, base_path in (("https://example.invalid/", "/"), ("https://example.invalid/group/project/", "/group/project/")):
            resolver = _Resolver(base_url, base_path, routes, {"web_base": "https://gitlab.com/group/project", "web_routes": {"commit": "/-/commit/{commit_sha}"}})
            self.assertEqual(resolver.site("catalogue"), base_path + "catalogue/")
            self.assertEqual(resolver.repository_url("commit", commit_sha="a" * 40), "https://gitlab.com/group/project/-/commit/" + "a" * 40)
        broken = dict(routes); broken["process"] = broken["catalogue"]
        with self.assertRaisesRegex(BuildError, "collide"):
            _Resolver("https://example.invalid/", "/", broken, {"web_base": "https://github.com/o/r", "web_routes": {"commit": "/commit/{commit_sha}"}})

    def test_final_recovery_crash_injection_across_every_shared_phase(self) -> None:
        baseline = build_final_site(self.request())
        baseline_bytes = {
            path.relative_to(baseline.output).as_posix(): path.read_bytes()
            for path in baseline.output.rglob("*") if path.is_file()
        }
        real_persist = build_module._persist_journal
        for selected in build_module.PHASES:
            with self.subTest(phase=selected):
                raised = False
                def crash(parent, lock, journal, *, initial=False):
                    nonlocal raised
                    real_persist(parent, lock, journal, initial=initial)
                    if journal["phase"] == selected and not raised:
                        raised = True
                        raise KeyboardInterrupt("simulated process death")
                with patch.object(build_module, "_persist_journal", side_effect=crash):
                    with self.assertRaises(KeyboardInterrupt):
                        build_final_site(self.request())
                if selected == "lock":
                    with self.assertRaisesRegex(BuildError, "initial-lock recovery"):
                        recover_candidate(self.root)
                    current = {
                        path.relative_to(baseline.output).as_posix(): path.read_bytes()
                        for path in baseline.output.rglob("*") if path.is_file()
                    }
                    self.assertEqual(current, baseline_bytes, selected)
                    (self.root / "dist/.modelo-build.lock").unlink()
                    continue
                self.assertIn(recover_candidate(self.root), {
                    build_module.RecoveryOutcome.ROLLED_BACK,
                    build_module.RecoveryOutcome.COMMITTED,
                })
                self.assertFalse((self.root / "dist/.modelo-build.lock").exists())
                current = {
                    path.relative_to(baseline.output).as_posix(): path.read_bytes()
                    for path in baseline.output.rglob("*") if path.is_file()
                }
                self.assertEqual(current, baseline_bytes, selected)


class RegionViewTests(unittest.TestCase):
    def test_direct_route_has_no_destination_region(self) -> None:
        offering = {"routes": [{"id": "direct", "source_region": "eu-west-2", "reference": "test.model-v1", "model_binding": {"kind": "foundation-model", "model_evidence": {"id": "e"}}}]}
        html = _route_rows(offering, {})
        self.assertIn("eu-west-2", html)
        self.assertIn("None", html)

    def test_profile_destinations_come_from_bound_evidence(self) -> None:
        offering = {"routes": [{"id": "profile", "source_region": "eu-west-2", "reference": "eu.test.model-v1", "model_binding": {"kind": "system-inference-profile", "profile_evidence": {"id": "profile"}, "destinations": [{"destination_pointer": "/models/0/modelArn", "model_evidence": {"id": "east"}}, {"destination_pointer": "/models/1/modelArn", "model_evidence": {"id": "west"}}]}}]}
        evidence = {"east": {"source": {"region": "eu-central-1"}}, "west": {"source": {"region": "eu-west-1"}}}
        html = _route_rows(offering, evidence)
        self.assertIn("eu-west-2", html)
        self.assertIn("eu-central-1, eu-west-1", html)

    def test_same_profile_two_source_regions_keep_distinct_routes_prices_and_destinations(self) -> None:
        offering = {
            "routes": [
                {"id": "profile-uk", "source_region": "eu-west-2", "reference": "global.test.profile-v1", "model_binding": {"kind": "system-inference-profile", "profile_evidence": {"id": "p-uk"}, "destinations": [{"destination_pointer": "/models/0/modelArn", "model_evidence": {"id": "uk-destination"}}]}},
                {"id": "profile-us", "source_region": "us-east-1", "reference": "global.test.profile-v1", "model_binding": {"kind": "system-inference-profile", "profile_evidence": {"id": "p-us"}, "destinations": [{"destination_pointer": "/models/0/modelArn", "model_evidence": {"id": "us-destination"}}]}},
            ],
            "pricing": [
                {"dimension": "input", "amount": "1.00", "currency": "USD", "quantity": 1000000, "unit": "token", "route_ids": ["profile-uk"]},
                {"dimension": "input", "amount": "2.00", "currency": "USD", "quantity": 1000000, "unit": "token", "route_ids": ["profile-us"]},
            ],
        }
        evidence = {
            "uk-destination": {"source": {"region": "eu-west-1"}},
            "us-destination": {"source": {"region": "us-west-2"}},
        }
        routes = _route_rows(offering, evidence)
        prices = _pricing_rows(offering)
        self.assertEqual(routes.count("global.test.profile-v1"), 2)
        for value in ("eu-west-2", "eu-west-1", "us-east-1", "us-west-2"):
            self.assertIn(value, routes)
        self.assertIn("1.00", prices); self.assertIn("profile-uk", prices)
        self.assertIn("2.00", prices); self.assertIn("profile-us", prices)


if __name__ == "__main__":
    unittest.main()
