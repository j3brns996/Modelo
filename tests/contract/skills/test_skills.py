from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import yaml

from modelo.build import _layout


ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / ".agents/skills"
NAMES = {"modelo-change", "modelo-review", "modelo-discover"}
HEADINGS = {
    "## Authority",
    "## Use and do not use",
    "## Preconditions",
    "## Procedure",
    "## Stop conditions",
    "## Handoff evidence",
}


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    value = {}
    for key_node, item_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in value:
            raise AssertionError(f"duplicate frontmatter key: {key}")
        value[key] = loader.construct_object(item_node, deep=deep)
    return value


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse_skill(path: Path) -> tuple[dict[str, object], str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise AssertionError(f"{path} must be UTF-8 without BOM and LF terminated")
    text = raw.decode("utf-8", "strict")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path} lacks frontmatter")
    frontmatter, separator, body = text[4:].partition("\n---\n")
    if not separator:
        raise AssertionError(f"{path} has unterminated frontmatter")
    if any(token in frontmatter for token in ("&", "*", "!")):
        raise AssertionError(f"{path} uses unsupported YAML features")
    metadata = yaml.load(frontmatter, Loader=_UniqueLoader)
    if not isinstance(metadata, dict):
        raise AssertionError(f"{path} frontmatter is not a mapping")
    return metadata, body


class SkillContractTests(unittest.TestCase):
    def test_exact_native_skill_tree_and_frontmatter(self) -> None:
        self.assertFalse((ROOT / ".agents").is_symlink())
        self.assertFalse(SKILLS.is_symlink())
        self.assertFalse(any(path.is_symlink() for path in SKILLS.rglob("*")))
        self.assertEqual({path.name for path in SKILLS.iterdir() if path.is_dir()}, NAMES)
        self.assertEqual(
            {path.relative_to(SKILLS).as_posix() for path in SKILLS.rglob("*") if path.is_file()},
            {f"{name}/SKILL.md" for name in NAMES},
        )
        for name in NAMES:
            path = SKILLS / name / "SKILL.md"
            self.assertFalse(path.is_symlink())
            metadata, body = parse_skill(path)
            self.assertEqual(
                set(metadata), {"name", "description", "compatibility", "metadata"}
            )
            self.assertEqual(metadata["name"], name)
            self.assertRegex(name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
            self.assertLessEqual(len(name), 64)
            description = metadata["description"]
            self.assertIsInstance(description, str)
            self.assertTrue(str(description).startswith("Use when "))
            self.assertLessEqual(len(str(description)), 1024)
            self.assertLessEqual(len(str(metadata["compatibility"])), 500)
            self.assertEqual(
                metadata["metadata"],
                {"modelo-contract-version": "0.1.0", "modelo-origin": "native"},
            )
            self.assertTrue(HEADINGS.issubset(set(re.findall(r"^## .+$", body, re.MULTILINE))))

    def test_skills_contain_no_installers_hooks_or_unsafe_commands(self) -> None:
        forbidden = (
            "npx", "npm ", "pip install", "pipx", "curl ", "wget ",
            "git push", "git merge", "git reset", "--force", "rm -rf",
            "workflow_dispatch", "pull_request_target", "allowed-tools",
            "addyosmani", "github.com/addyosmani",
        )
        for path in SKILLS.rglob("SKILL.md"):
            text = path.read_text(encoding="utf-8").lower()
            for value in forbidden:
                self.assertNotIn(value, text, (path, value))

    def test_referenced_config_paths_and_cli_flags_exist(self) -> None:
        document = yaml.safe_load((ROOT / "modelo.yaml").read_text(encoding="utf-8"))
        configured = set(document["paths"])
        referenced: set[str] = set()
        for path in SKILLS.rglob("SKILL.md"):
            referenced.update(re.findall(r"`paths\.([a-z_]+)`", path.read_text(encoding="utf-8")))
        self.assertTrue(referenced)
        self.assertEqual(referenced - configured, set())
        help_text = subprocess.run(
            [sys.executable, "-m", "modelo", "check", "--help"],
            cwd=ROOT, text=True, capture_output=True, check=True,
        ).stdout
        for flag in ("--base", "--head", "--as-of"):
            self.assertIn(flag, help_text)

    def test_skills_are_outside_runtime_build_and_wheel(self) -> None:
        layout = _layout(ROOT)
        skills_path = Path(yaml.safe_load((ROOT / "modelo.yaml").read_text())["paths"]["open_skills"])
        self.assertNotIn(skills_path.as_posix(), {path.as_posix() for path in layout.input_roots})
        for path in (ROOT / "tooling/modelo/src").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(".agents", source)
            self.assertNotIn("open_skills", source)
        with tempfile.TemporaryDirectory(prefix="modelo-skill-wheel-") as raw:
            subprocess.run(
                ["uv", "build", "--offline", "--no-cache", "--wheel", "--out-dir", raw],
                cwd=ROOT, text=True, capture_output=True, check=True,
            )
            wheels = list(Path(raw).glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            with zipfile.ZipFile(wheels[0]) as archive:
                self.assertFalse(any(name.startswith(".agents/") for name in archive.namelist()))

    def test_wheel_is_identical_without_skills_in_same_source_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="modelo-skill-absence-") as raw:
            temporary = Path(raw)
            copies = []
            for name in ("with", "without"):
                target = temporary / name
                shutil.copytree(
                    ROOT, target,
                    ignore=shutil.ignore_patterns(".git", ".venv", "dist", "__pycache__", "*.pyc"),
                )
                copies.append(target)
            shutil.rmtree(copies[1] / ".agents/skills")
            wheels = []
            for target in copies:
                output = target / "wheel-output"
                subprocess.run(
                    ["uv", "build", "--offline", "--no-cache", "--wheel", "--out-dir", str(output)],
                    cwd=target, text=True, capture_output=True, check=True,
                )
                wheel = next(output.glob("*.whl"))
                wheels.append(wheel.read_bytes())
            self.assertEqual(wheels[0], wheels[1])


if __name__ == "__main__":
    unittest.main()
