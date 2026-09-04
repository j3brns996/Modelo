from __future__ import annotations

import json
import shutil
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
        self.assertEqual(result.stdout, "modelo 0.1.2\n")
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

    def test_dev_evidence_create_valid_api_record(self) -> None:
        result = self.run_cli(
            "dev", "evidence-create",
            "--source-type", "first-party-read-api",
            "--uri", "https://example.invalid/api",
            "--observed-at", "2026-09-01T00:00:00Z",
            "--projection", '{"modelName": "API Model"}',
            "--provider", "aws",
            "--service", "bedrock",
            "--operation", "GetFoundationModel",
            "--partition", "aws",
            "--region", "us-east-1",
            "--sanitised-parameters", '{"modelIdentifier": "model-1"}',
            "--retrieved-by", "mcp",
            "--visibility", "public",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["source"]["operation"], "GetFoundationModel")
        self.assertEqual(record["source"]["region"], "us-east-1")
        self.assertEqual(record["source"]["provider"], "aws")
        self.assertEqual(record["source"]["service"], "bedrock")
        self.assertEqual(
            record["source"]["sanitised_parameters"],
            {"modelIdentifier": "model-1"},
        )
        self.assertEqual(record["retrieved_by"], "mcp")
        self.assertEqual(record["visibility"], "public")

        null_parameters = list(result.args[3:])
        parameter_index = null_parameters.index("--sanitised-parameters")
        null_parameters[parameter_index + 1] = "null"
        null_result = self.run_cli(*null_parameters)
        self.assertEqual(null_result.returncode, 0, null_result.stderr)
        self.assertIsNone(json.loads(null_result.stdout)["source"]["sanitised_parameters"])

    def test_dev_evidence_create_rejects_invalid_records_without_output(self) -> None:
        base = (
            "dev", "evidence-create",
            "--source-type", "official-provider-documentation",
            "--uri", "https://example.invalid/doc",
            "--observed-at", "2026-09-01T00:00:00Z",
            "--projection", '{"providerName": "AWS"}',
        )
        cases = (
            ("URI", ("--uri", "http://example.invalid/doc")),
            ("timestamp", ("--observed-at", "2026-02-30T00:00:00Z")),
            ("retriever", ("--retrieved-by", "browser")),
            ("visibility", ("--visibility", "secret")),
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for index, (name, override) in enumerate(cases):
                arguments = list(base)
                if override[0] in arguments:
                    option = arguments.index(override[0])
                    arguments[option + 1] = override[1]
                else:
                    arguments.extend(override)
                output = tmp_path / f"existing-{index}.json"
                output.write_text("preserve me\n", encoding="utf-8")
                result = self.run_cli(*arguments, "--output", str(output))
                with self.subTest(case=name):
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("invalid evidence record", result.stderr)
                    self.assertEqual(output.read_text(encoding="utf-8"), "preserve me\n")

            absent = tmp_path / "absent.json"
            result = self.run_cli(
                *base, "--uri", "http://example.invalid/doc", "--output", str(absent)
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertFalse(absent.exists())

        invalid_source = self.run_cli(*base, "--source-type", "marketing-page")
        self.assertEqual(invalid_source.returncode, 2)
        self.assertIn("invalid choice", invalid_source.stderr)

    def test_dev_evidence_create_api_requires_all_api_arguments_together(self) -> None:
        base = (
            "dev", "evidence-create",
            "--source-type", "first-party-read-api",
            "--uri", "https://example.invalid/api",
            "--observed-at", "2026-09-01T00:00:00Z",
            "--projection", '{"modelName": "API Model"}',
            "--provider", "aws",
            "--service", "bedrock",
            "--operation", "GetFoundationModel",
            "--partition", "aws",
            "--region", "us-east-1",
            "--sanitised-parameters", '{}',
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            for option in (
                "--provider", "--service", "--operation", "--partition", "--region",
                "--sanitised-parameters",
            ):
                arguments = list(base)
                position = arguments.index(option)
                del arguments[position:position + 2]
                name = option.removeprefix("--")
                output = Path(tmp_dir) / f"missing-{name}.json"
                output.write_text("preserve me\n", encoding="utf-8")
                result = self.run_cli(*arguments, "--output", str(output))
                with self.subTest(missing=name):
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("requires API arguments together", result.stderr)
                    self.assertIn(option, result.stderr)
                    self.assertEqual(output.read_text(encoding="utf-8"), "preserve me\n")

    def test_dev_evidence_create_documentation_rejects_each_api_argument(self) -> None:
        base = (
            "dev", "evidence-create",
            "--source-type", "official-provider-documentation",
            "--uri", "https://example.invalid/doc",
            "--observed-at", "2026-09-01T00:00:00Z",
            "--projection", '{}',
        )
        for option, value in (
            ("--provider", "aws"),
            ("--service", "bedrock"),
            ("--operation", "GetFoundationModel"),
            ("--partition", "aws"),
            ("--region", "us-east-1"),
            ("--sanitised-parameters", "{}"),
        ):
            result = self.run_cli(*base, option, value)
            with self.subTest(option=option):
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn(
                    "documentation sources do not accept API-only arguments",
                    result.stderr,
                )
                self.assertIn(option, result.stderr)

    def test_dev_evidence_create_choices_are_exact(self) -> None:
        base = (
            "dev", "evidence-create",
            "--source-type", "first-party-read-api",
            "--uri", "https://example.invalid/api",
            "--observed-at", "2026-09-01T00:00:00Z",
            "--projection", '{}',
        )
        for option, value in (
            ("--source-type", "provider-docs"),
            ("--provider", "gcp"),
            ("--service", "vertex"),
        ):
            arguments = list(base)
            if option in arguments:
                arguments[arguments.index(option) + 1] = value
            else:
                arguments.extend((option, value))
            result = self.run_cli(*arguments)
            with self.subTest(option=option):
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid choice", result.stderr)

    def test_dev_evidence_create_rejects_sensitive_parameters_without_output(self) -> None:
        base = (
            "dev", "evidence-create",
            "--source-type", "first-party-read-api",
            "--uri", "https://example.invalid/api",
            "--observed-at", "2026-09-01T00:00:00Z",
            "--projection", '{}',
            "--provider", "aws",
            "--service", "bedrock",
            "--operation", "GetFoundationModel",
            "--partition", "aws",
            "--region", "us-east-1",
        )
        cases = (
            ({"offerToken": "secret"}, "offerToken"),
            ({"auth": {"credentials": "secret"}}, "credentials"),
            ({"items": [{"OFFER_TOKEN": "secret"}]}, "offerToken"),
            ({"items": [{"CrE_Den-TiAls": "secret"}]}, "credentials"),
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for index, (parameters, key) in enumerate(cases):
                for existing in (False, True):
                    output = tmp_path / f"sensitive-{index}-{existing}.json"
                    if existing:
                        output.write_text("preserve me\n", encoding="utf-8")
                    result = self.run_cli(
                        *base,
                        "--sanitised-parameters", json.dumps(parameters),
                        "--output", str(output),
                    )
                    with self.subTest(parameters=parameters, existing=existing):
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stdout, "")
                        self.assertIn(
                            f"prohibited sensitive key {key}", result.stderr
                        )
                        self.assertNotIn("secret", result.stderr)
                        if existing:
                            self.assertEqual(
                                output.read_text(encoding="utf-8"), "preserve me\n"
                            )
                        else:
                            self.assertFalse(output.exists())

            allowed = self.run_cli(
                *base,
                "--sanitised-parameters", '{"maxTokens": 256}',
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertEqual(
                json.loads(allowed.stdout)["source"]["sanitised_parameters"],
                {"maxTokens": 256},
            )

    def test_dev_json_arguments_have_explicit_precedence_and_clear_errors(self) -> None:
        base = (
            "dev", "evidence-create",
            "--source-type", "official-vendor-documentation",
            "--uri", "https://example.invalid/doc",
            "--observed-at", "2026-09-01T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            legacy = tmp_path / "legacy.json"
            legacy.write_text('{"mode": "legacy"}', encoding="utf-8")

            legacy_result = self.run_cli(*base, "--projection", str(legacy))
            self.assertEqual(legacy_result.returncode, 0, legacy_result.stderr)
            self.assertEqual(
                json.loads(legacy_result.stdout)["projection"], {"mode": "legacy"}
            )

            at_result = self.run_cli(*base, "--projection", f"@{legacy}")
            self.assertEqual(at_result.returncode, 0, at_result.stderr)
            self.assertEqual(
                json.loads(at_result.stdout)["projection"], {"mode": "legacy"}
            )

            inline_path_string = self.run_cli(
                *base, "--projection", json.dumps(str(legacy))
            )
            self.assertEqual(inline_path_string.returncode, 0, inline_path_string.stderr)
            self.assertEqual(
                json.loads(inline_path_string.stdout)["projection"], str(legacy)
            )

            for value, message in (
                (
                    f"@{tmp_path / 'missing.json'}",
                    "does not exist or is not a regular file",
                ),
                ("@", "@path must name a JSON file"),
                (
                    "not-json-or-a-file",
                    "must be inline JSON, @path, or an existing JSON file",
                ),
            ):
                result = self.run_cli(*base, "--projection", value)
                with self.subTest(value=value):
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(message, result.stderr)

            invalid = tmp_path / "invalid.json"
            invalid.write_text("{bad", encoding="utf-8")
            invalid_result = self.run_cli(*base, "--projection", f"@{invalid}")
            self.assertEqual(invalid_result.returncode, 2)
            self.assertIn("JSON file", invalid_result.stderr)
            self.assertIn("is invalid", invalid_result.stderr)

    def test_dev_optional_json_rejects_explicit_empty_values_without_output(self) -> None:
        digest = "sha256-" + "a" * 64
        cases = (
            (
                (
                    "dev", "evidence-create",
                    "--source-type", "official-provider-documentation",
                    "--uri", "https://example.invalid/doc",
                    "--observed-at", "2026-09-01T00:00:00Z",
                    "--projection", '{}',
                    "--scope", "",
                ),
                "--scope",
            ),
            (
                (
                    "dev", "mac-init",
                    "--operation", "add",
                    "--purpose", "Add test record",
                    "--subjects", '[{"kind":"model","identity":"test-model"}]',
                    "--requested-outcome", "Add record",
                    "--reason", "New record available",
                    "--candidate-evidence", json.dumps([{
                        "uri": "https://example.invalid/doc",
                        "observed_at": "2026-09-01T00:00:00Z",
                        "digest": digest,
                    }]),
                    "--acceptance", '["criterion 1"]',
                    "--batch-scope", "",
                ),
                "--batch-scope",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            for index, (arguments, option) in enumerate(cases):
                output = Path(tmp_dir) / f"existing-{index}.json"
                output.write_text("preserve me\n", encoding="utf-8")
                result = self.run_cli(*arguments, "--output", str(output))
                with self.subTest(option=option):
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(option, result.stderr)
                    self.assertIn("inline JSON is invalid", result.stderr)
                    self.assertEqual(
                        output.read_text(encoding="utf-8"), "preserve me\n"
                    )

    def test_dev_json_output_is_shared_pretty_and_preserved_on_input_failure(self) -> None:
        digest = "sha256-" + "a" * 64
        candidate_evidence = json.dumps([{
            "uri": "https://example.invalid/doc",
            "observed_at": "2026-09-01T00:00:00Z",
            "digest": digest,
        }])
        common = (
            "dev", "mac-init",
            "--operation", "add",
            "--purpose", "Add test record",
            "--subjects", '[{"kind":"model","identity":"test-model"}]',
            "--requested-outcome", "Add record",
            "--reason", "New record available",
            "--candidate-evidence", candidate_evidence,
            "--acceptance", '["criterion 1"]',
        )
        stdout_result = self.run_cli(*common)
        self.assertEqual(stdout_result.returncode, 0, stdout_result.stderr)
        self.assertTrue(stdout_result.stdout.endswith("\n"))
        self.assertEqual(
            stdout_result.stdout,
            json.dumps(
                json.loads(stdout_result.stdout),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "payload.json"
            output.write_text("preserve me\n", encoding="utf-8")
            bad = self.run_cli(
                *common, "--subjects", "@missing.json", "--output", str(output)
            )
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "preserve me\n")

            good = self.run_cli(*common, "--output", str(output))
            self.assertEqual(good.returncode, 0, good.stderr)
            written = output.read_text(encoding="utf-8")
            self.assertEqual(
                written,
                json.dumps(
                    json.loads(written), ensure_ascii=False, indent=2, sort_keys=True
                ) + "\n",
            )

    def test_dev_evidence_create_uses_schema_from_configured_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for name in ("modelo.yaml", "VERSION", ".python-version", "pyproject.toml", "uv.lock"):
                shutil.copy2(ROOT / name, root / name)
            shutil.copytree(ROOT / "schemas", root / "schemas")
            schema_path = root / "schemas/evidence.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["properties"]["retrieved_by"]["enum"] = ["manual"]
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            result = self.run_cli(
                "--root", str(root), "dev", "evidence-create",
                "--source-type", "official-provider-documentation",
                "--uri", "https://example.invalid/doc",
                "--observed-at", "2026-09-01T00:00:00Z",
                "--projection", '{}',
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("invalid evidence record", result.stderr)

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

    def test_dev_propose_scaffolds_evidence_and_issue_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for name in ("modelo.yaml", "VERSION", ".python-version", "pyproject.toml", "uv.lock"):
                shutil.copy2(ROOT / name, root / name)
            shutil.copytree(ROOT / "schemas", root / "schemas")
            result = self.run_cli(
                "--root", str(root),
                "dev", "propose",
                "--operation", "add",
                "--kind", "offering",
                "--identity", "test-offering-propose",
                "--purpose", "Test propose command purpose",
                "--reason", "Test propose command reason",
                "--uri", "https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("### Request type\n\nadd", result.stdout)
            self.assertIn("<!-- modelo:intake-generated-start -->", result.stdout)
            self.assertIn("test-offering-propose", result.stdout)
            evidence_files = list((root / "catalogue" / "evidence").glob("sha256-*.yaml"))
            self.assertEqual(len(evidence_files), 1)


if __name__ == "__main__":
    unittest.main()
