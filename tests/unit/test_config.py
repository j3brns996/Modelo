from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from modelo.config import ConfigError, load_config


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FILES = ("modelo.yaml", "VERSION", ".python-version", "pyproject.toml", "uv.lock")


class ConfigTests(unittest.TestCase):
    def clone_bootstrap(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        target = Path(directory.name)
        for relative in BOOTSTRAP_FILES:
            shutil.copyfile(ROOT / relative, target / relative)
        return target

    def assert_code(self, root: Path, code: str) -> None:
        with self.assertRaises(ConfigError) as caught:
            load_config(root)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.exit_code, 2)

    def test_checked_in_config_loads_as_frozen_bootstrap(self) -> None:
        config = load_config(ROOT)
        self.assertEqual(config.project_id, "modelo")
        self.assertEqual(config.project_version, "0.1.0")
        self.assertEqual(config.python_version, "3.12.13")
        self.assertEqual(config.uv_version, "0.11.33")
        self.assertEqual(config.repository_path("site_templates"), ROOT / "site/templates")
        for key in ("readme", "contributing", "codeowners", "gitignore", "gitattributes"):
            self.assertTrue(config.repository_path(key).is_file())
        with self.assertRaises(TypeError):
            config.paths["bad"] = Path("bad")  # type: ignore[index,assignment]

    def test_default_root_is_current_directory_not_parent_search(self) -> None:
        child = ROOT / "tests"
        previous = Path.cwd()
        self.addCleanup(lambda: __import__("os").chdir(previous))
        __import__("os").chdir(child)
        self.assert_code(child, "FILE_OR_PATH_ERROR")

    def test_missing_and_symlink_config_fail(self) -> None:
        root = self.clone_bootstrap()
        (root / "modelo.yaml").unlink()
        self.assert_code(root, "FILE_OR_PATH_ERROR")
        (root / "real.yaml").write_text("config_version: '0.1.0'\n", encoding="utf-8")
        (root / "modelo.yaml").symlink_to("real.yaml")
        self.assert_code(root, "FILE_OR_PATH_ERROR")

    def test_invalid_utf8_fails(self) -> None:
        root = self.clone_bootstrap()
        (root / "modelo.yaml").write_bytes(b"\xff")
        self.assert_code(root, "FILE_OR_PATH_ERROR")

    def test_invalid_utf8_in_companion_files_fails(self) -> None:
        for relative in ("VERSION", ".python-version"):
            with self.subTest(relative=relative):
                root = self.clone_bootstrap()
                (root / relative).write_bytes(b"\xff")
                self.assert_code(root, "FILE_OR_PATH_ERROR")

    def test_restricted_yaml_constructs_fail(self) -> None:
        cases = {
            "duplicate": ("config_version: '0.1.0'\nconfig_version: '0.1.0'\n", "YAML_DUPLICATE_KEY"),
            "anchor": ("value: &x 1\n", "YAML_ALIAS_OR_ANCHOR"),
            "alias": ("value: &x 1\ncopy: *x\n", "YAML_ALIAS_OR_ANCHOR"),
            "tag": ("value: !thing 1\n", "YAML_CUSTOM_TAG"),
            "multi": ("value: 1\n---\nvalue: 2\n", "YAML_MULTI_DOCUMENT"),
            "scalar": ("value\n", "YAML_INVALID_ROOT"),
        }
        for name, (content, code) in cases.items():
            with self.subTest(name=name):
                root = self.clone_bootstrap()
                (root / "modelo.yaml").write_text(content, encoding="utf-8")
                self.assert_code(root, code)

    def test_unsupported_version_and_environment_interpolation_fail(self) -> None:
        for old, new in (("config_version: \"0.1.0\"", "config_version: \"9.0.0\""),
                         ("title: Modelo", "title: ${TITLE}")):
            root = self.clone_bootstrap()
            path = root / "modelo.yaml"
            path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
            self.assert_code(root, "SCHEMA_VIOLATION")

    def test_unsafe_configured_paths_fail(self) -> None:
        for unsafe in ("/tmp/models", "../models", "bad\\models", ".", "bad//models"):
            with self.subTest(path=unsafe):
                root = self.clone_bootstrap()
                path = root / "modelo.yaml"
                text = path.read_text(encoding="utf-8").replace("catalogue/models", unsafe, 1)
                path.write_text(text, encoding="utf-8")
                self.assert_code(root, "FILE_OR_PATH_ERROR")

    def test_symlinked_parent_cannot_escape_repository(self) -> None:
        root = self.clone_bootstrap()
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        Path(outside.name, "VERSION").write_text("0.1.0\n", encoding="utf-8")
        (root / "escape").symlink_to(outside.name, target_is_directory=True)
        path = root / "modelo.yaml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("version_file: VERSION", "version_file: escape/VERSION"),
            encoding="utf-8",
        )
        self.assert_code(root, "FILE_OR_PATH_ERROR")

    def test_depth_node_and_byte_limits_fail_before_construction(self) -> None:
        cases = (
            ("deep", "value: " + "[" * 500 + "0" + "]" * 500, "YAML_LIMIT_EXCEEDED"),
            ("nodes", "values:\n" + "".join("  - value\n" for _ in range(2_001)), "YAML_LIMIT_EXCEEDED"),
        )
        for name, content, code in cases:
            with self.subTest(name=name):
                root = self.clone_bootstrap()
                (root / "modelo.yaml").write_text(content, encoding="utf-8")
                self.assert_code(root, code)
        root = self.clone_bootstrap()
        (root / "modelo.yaml").write_bytes(b"a" * 131_073)
        self.assert_code(root, "YAML_LIMIT_EXCEEDED")

    def test_bootstrap_limit_drift_and_wrong_section_type_fail(self) -> None:
        for old, new in (
            ("max_depth: 20", "max_depth: 21"),
            ("project:\n  id: modelo", "project: invalid\nignored:\n  id: modelo"),
        ):
            root = self.clone_bootstrap()
            path = root / "modelo.yaml"
            path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
            self.assert_code(root, "SCHEMA_VIOLATION")

    def test_adapter_and_web_base_mismatch_fail(self) -> None:
        for old, new in (("adapter: github", "adapter: unknown"),
                         ("web_base: https://github.com/j3brns996/Modelo", "web_base: https://example.invalid/repo")):
            root = self.clone_bootstrap()
            path = root / "modelo.yaml"
            path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
            self.assert_code(root, "SCHEMA_VIOLATION")

    def test_pin_and_required_file_drift_fail(self) -> None:
        root = self.clone_bootstrap()
        (root / ".python-version").write_text("3.13.0\n", encoding="utf-8")
        self.assert_code(root, "SCHEMA_VIOLATION")
        root = self.clone_bootstrap()
        (root / "uv.lock").unlink()
        self.assert_code(root, "FILE_OR_PATH_ERROR")

    def test_repository_ignore_and_attribute_contract(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        shutil.copyfile(ROOT / ".gitignore", root / ".gitignore")
        shutil.copyfile(ROOT / ".gitattributes", root / ".gitattributes")
        for relative in ("dist/probe", "site/probe.html", "schemas/probe.json", "tests/fixtures/probe.yaml", "uv.lock"):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        ignored = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", "dist/probe"], check=False
        )
        self.assertEqual(ignored.returncode, 0)
        for relative in ("site/probe.html", "schemas/probe.json", "tests/fixtures/probe.yaml", "uv.lock"):
            result = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "-q", relative], check=False
            )
            self.assertEqual(result.returncode, 1, relative)
        attributes = subprocess.run(
            ["git", "-C", str(root), "check-attr", "text", "eol", "--", "site/probe.html", "uv.lock"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertNotIn("unspecified", attributes)
        self.assertEqual((ROOT / "CODEOWNERS").read_text(encoding="utf-8").splitlines()[-1], "* @j3brns")


if __name__ == "__main__":
    unittest.main()
