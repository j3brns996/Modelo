from __future__ import annotations

import json
import unittest

from modelo.diagnostics import Diagnostic, Severity, diagnostics_json, sort_diagnostics


class DiagnosticTests(unittest.TestCase):
    def diagnostic(self, *, code: str = "SCHEMA_VIOLATION", path: str = "b.yaml") -> Diagnostic:
        return Diagnostic(
            code=code,
            severity=Severity.ERROR,
            path=path,
            json_pointer="/id",
            message="invalid value",
            remediation="Correct the value.",
        )

    def test_exact_public_fields_and_snapshot(self) -> None:
        rendered = diagnostics_json([self.diagnostic()])
        self.assertEqual(
            rendered,
            "[\n"
            "  {\n"
            '    "code": "SCHEMA_VIOLATION",\n'
            '    "severity": "error",\n'
            '    "path": "b.yaml",\n'
            '    "json_pointer": "/id",\n'
            '    "message": "invalid value",\n'
            '    "remediation": "Correct the value."\n'
            "  }\n"
            "]\n",
        )
        self.assertEqual(
            json.loads(rendered),
            [
                {
                    "code": "SCHEMA_VIOLATION",
                    "severity": "error",
                    "path": "b.yaml",
                    "json_pointer": "/id",
                    "message": "invalid value",
                    "remediation": "Correct the value.",
                }
            ],
        )

    def test_sort_is_deterministic_and_does_not_mutate_input(self) -> None:
        source = [self.diagnostic(path="z.yaml"), self.diagnostic(path="a.yaml")]
        ordered = sort_diagnostics(reversed(source))
        self.assertEqual([item.path for item in ordered], ["a.yaml", "z.yaml"])
        self.assertEqual([item.path for item in source], ["z.yaml", "a.yaml"])

    def test_unknown_code_and_invalid_pointer_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            self.diagnostic(code="NEW_UNCONTRACTED_CODE")
        with self.assertRaises(ValueError):
            Diagnostic(
                code="SCHEMA_VIOLATION",
                severity=Severity.ERROR,
                path="model.yaml",
                json_pointer="not-a-pointer",
                message="invalid",
                remediation="Correct it.",
            )

    def test_diagnostic_is_immutable(self) -> None:
        diagnostic = self.diagnostic()
        with self.assertRaises((AttributeError, TypeError)):
            diagnostic.code = "FILE_OR_PATH_ERROR"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
