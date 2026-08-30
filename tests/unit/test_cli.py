from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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
        self.assertEqual(result.stdout, "modelo 0.1.0\n")
        self.assertEqual(result.stderr, "")

    def test_help_and_future_command_help_succeed(self) -> None:
        for arguments in ((), ("check", "--help"), ("build", "--help")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)

    def test_future_commands_fail_closed(self) -> None:
        cases = (
            ("check", "--base", "base", "--head", "head", "--as-of", "2026-08-30"),
            ("build", "--as-of", "2026-08-30"),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("is not implemented in the current repository slice", result.stderr)
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


if __name__ == "__main__":
    unittest.main()
