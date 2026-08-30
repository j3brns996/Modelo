from __future__ import annotations

from datetime import date
import tempfile
import unittest
from pathlib import Path

from modelo.loader import LoadError, YamlLimits, load_yaml_mapping


class LoaderTests(unittest.TestCase):
    def repository(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def write(
        self, root: Path, content: str | bytes, relative: str = "catalogue/item.yaml"
    ) -> None:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")

    def assert_error(
        self,
        root: Path,
        code: str,
        *,
        relative: str = "catalogue/item.yaml",
        limits: YamlLimits = YamlLimits(),
    ) -> LoadError:
        with self.assertRaises(LoadError) as caught:
            load_yaml_mapping(root, relative, limits=limits)
        self.assertEqual(caught.exception.diagnostic.code, code)
        self.assertEqual(caught.exception.diagnostic.path, relative)
        return caught.exception

    def test_valid_mapping_loads_as_json_data_and_dates_stay_strings(self) -> None:
        root = self.repository()
        self.write(
            root,
            "id: test-model\nobserved_at: 2026-08-30\nenabled: true\nitems: [one, 2, null]\n",
        )
        document = load_yaml_mapping(root, "catalogue/item.yaml")
        self.assertEqual(document["observed_at"], "2026-08-30")
        self.assertNotIsInstance(document["observed_at"], date)
        self.assertEqual(document["items"], ["one", 2, None])

    def test_duplicate_alias_anchor_tag_and_multiple_documents_fail(self) -> None:
        cases = {
            "YAML_DUPLICATE_KEY": "id: one\nid: two\n",
            "YAML_ALIAS_OR_ANCHOR": "id: &identity one\n",
            "alias": "id: &identity one\ncopy: *identity\n",
            "YAML_CUSTOM_TAG": "id: !python one\n",
            "YAML_MULTI_DOCUMENT": "id: one\n---\nid: two\n",
        }
        for label, content in cases.items():
            with self.subTest(label=label):
                root = self.repository()
                self.write(root, content)
                expected = "YAML_ALIAS_OR_ANCHOR" if label == "alias" else label
                self.assert_error(root, expected)

    def test_invalid_syntax_root_key_and_nonfinite_number_fail(self) -> None:
        cases = (
            ("[unterminated", "YAML_PARSE_ERROR"),
            ("- item\n", "YAML_INVALID_ROOT"),
            ("1: value\n", "YAML_PARSE_ERROR"),
            ("value: .inf\n", "YAML_PARSE_ERROR"),
        )
        for content, code in cases:
            with self.subTest(content=content):
                root = self.repository()
                self.write(root, content)
                self.assert_error(root, code)

    def test_invalid_utf8_and_missing_file_fail(self) -> None:
        root = self.repository()
        self.write(root, b"\xff")
        self.assert_error(root, "FILE_OR_PATH_ERROR")
        missing = self.repository()
        self.assert_error(missing, "FILE_OR_PATH_ERROR")

    def test_absolute_traversal_and_platform_paths_fail(self) -> None:
        root = self.repository()
        for relative in ("/tmp/item.yaml", "../item.yaml", "bad\\item.yaml", "bad//item.yaml", "."):
            with self.subTest(relative=relative):
                with self.assertRaises(LoadError) as caught:
                    load_yaml_mapping(root, relative)
                self.assertEqual(caught.exception.diagnostic.code, "FILE_OR_PATH_ERROR")

    def test_file_and_parent_symlinks_fail(self) -> None:
        root = self.repository()
        outside = self.repository()
        self.write(outside, "id: outside\n", "item.yaml")
        (root / "catalogue").mkdir()
        (root / "catalogue/item.yaml").symlink_to(outside / "item.yaml")
        self.assert_error(root, "FILE_OR_PATH_ERROR")

        parent_root = self.repository()
        (parent_root / "catalogue").symlink_to(outside, target_is_directory=True)
        self.assert_error(parent_root, "FILE_OR_PATH_ERROR")

    def test_byte_depth_and_node_limits_fail_closed(self) -> None:
        root = self.repository()
        self.write(root, b"a" * 17)
        self.assert_error(root, "YAML_LIMIT_EXCEEDED", limits=YamlLimits(max_bytes=16))

        for count in (21, 500, 1_500):
            with self.subTest(depth=count):
                root = self.repository()
                self.write(root, "value: " + "[" * count + "0" + "]" * count + "\n")
                self.assert_error(root, "YAML_LIMIT_EXCEEDED")

        root = self.repository()
        self.write(root, "values:\n" + "".join("  - item\n" for _ in range(30)))
        self.assert_error(root, "YAML_LIMIT_EXCEEDED", limits=YamlLimits(max_nodes=20))

    def test_limits_must_be_positive_integers(self) -> None:
        for field in ("max_bytes", "max_depth", "max_nodes"):
            with self.subTest(field=field):
                values = {"max_bytes": 1, "max_depth": 1, "max_nodes": 1, field: 0}
                with self.assertRaises(ValueError):
                    YamlLimits(**values)

    def test_loading_does_not_mutate_source(self) -> None:
        root = self.repository()
        self.write(root, "id: immutable\n")
        target = root / "catalogue/item.yaml"
        before = target.read_bytes()
        load_yaml_mapping(root, "catalogue/item.yaml")
        self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
