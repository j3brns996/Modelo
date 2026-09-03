from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/fixtures/semantic"))
from repository import Repository  # noqa: E402


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "modelo", *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_version_is_deterministic(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "modelo 0.1.1\n")
        self.assertEqual(result.stderr, "")

    def test_help_and_future_command_help_succeed(self) -> None:
        for arguments in (
            (), ("check", "--help"), ("build", "--help"), ("config", "site", "--help"),
            ("platform", "github-intake", "--help"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)

    def test_site_configuration_has_one_machine_readable_owner(self) -> None:
        result = self.run_cli("config", "site")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            '{"base_path":"/Modelo/","base_url":"https://j3brns996.github.io/Modelo/","synthetic_as_of":"2026-09-01"}\n',
        )
        lines = self.run_cli("config", "site", "--format", "lines")
        self.assertEqual(
            lines.stdout,
            "https://j3brns996.github.io/Modelo/\n/Modelo/\n2026-09-01\n",
        )

    def test_final_build_requires_merge_coordinates_metadata_and_publication_capability(self) -> None:
        result = self.run_cli(
            "build", "--kind", "final", "--base-commit", "a" * 40,
            "--source-commit", "b" * 40, "--source-tree", "c" * 40,
            "--as-of", "2026-08-30", "--source-date-epoch", "0",
            "--mac-metadata", "metadata.json", "--profile", "synthetic",
            "--base-url", "https://example.invalid/Modelo/", "--base-path", "/Modelo/",
            "--output", "dist/final",
            "--publication-capability", "public-pages",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("final build requires --merge-commit and --merge-tree", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        result = self.run_cli(
            "build", "--kind", "final", "--base-commit", "a" * 40,
            "--source-commit", "b" * 40, "--source-tree", "c" * 40,
            "--merge-commit", "d" * 40, "--merge-tree", "c" * 40,
            "--as-of", "2026-08-30", "--source-date-epoch", "0",
            "--mac-metadata", "metadata.json", "--profile", "synthetic",
            "--base-url", "https://example.invalid/Modelo/", "--base-path", "/Modelo/",
            "--output", "dist/final",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("publication-capability", result.stderr)

    def test_demo_build_rejects_mac_and_private_profile_before_git_access(self) -> None:
        common = (
            "build", "--kind", "demo", "--base-commit", "a" * 40,
            "--source-commit", "a" * 40, "--source-tree", "b" * 40,
            "--as-of", "2026-08-30", "--source-date-epoch", "0",
            "--base-url", "https://example.invalid/Modelo/", "--base-path", "/Modelo/",
            "--output", "dist/pages",
        )
        private = self.run_cli(*common, "--profile", "private")
        self.assertEqual(private.returncode, 2)
        self.assertIn("fixes publication profile to synthetic", private.stderr)
        metadata = self.run_cli(*common, "--profile", "synthetic", "--mac-metadata", "metadata.json")
        self.assertEqual(metadata.returncode, 2)
        self.assertIn("does not accept --mac-metadata", metadata.stderr)

    def test_recover_command_is_exposed(self) -> None:
        result = self.run_cli("recover", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)

    def test_check_succeeds_for_exact_local_commits(self) -> None:
        repository = Repository()
        self.addCleanup(repository.close)
        result = subprocess.run(
            [sys.executable, "-m", "modelo", "--root", str(repository.root), "check", "--base", repository.base, "--head", repository.base, "--as-of", "2026-09-01"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_check_json_is_deterministic_and_has_only_contracted_fields(self) -> None:
        repository = Repository()
        self.addCleanup(repository.close)
        path = repository.root / "catalogue/models/test-model.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("vendor_id: test-vendor", "vendor_id: absent"), encoding="utf-8", newline="\n")
        head = repository.commit()
        command = [sys.executable, "-m", "modelo", "--root", str(repository.root), "check", "--base", repository.base, "--head", head, "--as-of", "2026-09-01", "--format", "json"]
        first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(first.returncode, 1)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, "")
        import json
        payload = json.loads(first.stdout)
        self.assertTrue(payload)
        self.assertEqual(set(payload[0]), {"code", "severity", "path", "json_pointer", "message", "remediation"})
        text_command = command[:-2]
        text_first = subprocess.run(text_command, cwd=ROOT, text=True, capture_output=True, check=False)
        text_second = subprocess.run(text_command, cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual((text_first.returncode, text_first.stdout), (1, text_second.stdout))

    def test_invalid_date_and_git_object_are_system_errors(self) -> None:
        for arguments in (("check", "--base", "x", "--head", "y", "--as-of", "2026-02-30"), ("check", "--base", "x", "--head", "y", "--as-of", "2026-08-30")):
            result = self.run_cli(*arguments)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)

    def test_missing_arguments_fail_as_usage(self) -> None:
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("required", result.stderr)

    def test_commands_do_not_mutate_repository(self) -> None:
        protected = [
            ROOT / name for name in ("modelo.yaml", "VERSION", "pyproject.toml", "uv.lock")
        ]
        before = {path: path.read_bytes() for path in protected}
        self.run_cli("--version")
        self.run_cli("check", "--base", "b", "--head", "h", "--as-of", "2026-08-30")
        after = {path: path.read_bytes() for path in protected}
        self.assertEqual(before, after)

    def test_dev_evidence_create_inline_and_file_output(self) -> None:
        result = self.run_cli(
            "dev", "evidence-create",
            "--source-type", "official-provider-documentation",
            "--uri", "https://example.invalid/doc",
            "--observed-at", "2026-09-01T00:00:00Z",
            "--projection", '{"providerName": "AWS"}',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["id"].startswith("sha256-"))
        self.assertEqual(data["source"]["uri"], "https://example.invalid/doc")
        self.assertEqual(data["projection"], {"providerName": "AWS"})

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            proj_file = tmp_path / "proj.json"
            proj_file.write_text('{"providerName": "AWS"}', encoding="utf-8")
            out_file = tmp_path / "evidence.json"
            res_file = self.run_cli(
                "dev", "evidence-create",
                "--source-type", "official-provider-documentation",
                "--uri", "https://example.invalid/doc",
                "--observed-at", "2026-09-01T00:00:00Z",
                "--projection", str(proj_file),
                "--output", str(out_file),
            )
            self.assertEqual(res_file.returncode, 0, res_file.stderr)
            self.assertEqual(res_file.stdout, "")
            out_data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(out_data["projection"], {"providerName": "AWS"})

    def test_dev_mac_init_inline_and_validation_error(self) -> None:
        digest = "sha256-" + "a" * 64
        result = self.run_cli(
            "dev", "mac-init",
            "--operation", "add",
            "--purpose", "Add test model for CLI test",
            "--subjects", '[{"kind": "model", "identity": "test-model"}]',
            "--requested-outcome", "Add record",
            "--reason", "New model available",
            "--candidate-evidence", f'[{{\"uri\": \"https://example.invalid/doc\", \"observed_at\": \"2026-09-01T00:00:00Z\", \"digest\": \"{digest}\"}}]',
            "--acceptance", '["criterion 1"]',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["operation"], "add")
        self.assertTrue(payload["dedupe_key"].startswith("sha256-"))

        bad_result = self.run_cli(
            "dev", "mac-init",
            "--operation", "invalid_operation",
            "--purpose", "Purpose",
            "--subjects", "[]",
            "--requested-outcome", "Outcome",
            "--reason", "Reason",
            "--candidate-evidence", "[]",
            "--acceptance", "[]",
        )
        self.assertEqual(bad_result.returncode, 2)
        self.assertEqual(bad_result.stdout, "")
        self.assertIn("modelo:", bad_result.stderr)
        self.assertNotIn("Traceback", bad_result.stderr)


if __name__ == "__main__":
    unittest.main()

