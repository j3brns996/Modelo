from __future__ import annotations

import tempfile
import unittest
from pathlib import Path, PurePosixPath

from modelo.discovery import DiscoveryError, discover_yaml_files


class DiscoveryTests(unittest.TestCase):
    def repository(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def test_recursive_discovery_is_sorted_relative_and_yaml_only(self) -> None:
        root = self.repository()
        for relative in (
            "catalogue/z.yaml",
            "catalogue/a.yaml",
            "catalogue/nested/b.yaml",
            "catalogue/nested/ignored.yml",
            "catalogue/README.md",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("id: value\n", encoding="utf-8")
        self.assertEqual(
            discover_yaml_files(root, "catalogue"),
            (
                PurePosixPath("catalogue/a.yaml"),
                PurePosixPath("catalogue/nested/b.yaml"),
                PurePosixPath("catalogue/z.yaml"),
            ),
        )

    def test_empty_directory_is_valid_and_missing_directory_fails(self) -> None:
        root = self.repository()
        (root / "catalogue").mkdir()
        self.assertEqual(discover_yaml_files(root, "catalogue"), ())
        with self.assertRaises(DiscoveryError) as caught:
            discover_yaml_files(root, "missing")
        self.assertEqual(caught.exception.diagnostic.code, "FILE_OR_PATH_ERROR")

    def test_unsafe_roots_fail(self) -> None:
        root = self.repository()
        for relative in ("/tmp", "../catalogue", "bad\\path", "bad//path", "."):
            with self.subTest(relative=relative):
                with self.assertRaises(DiscoveryError):
                    discover_yaml_files(root, relative)

    def test_file_as_discovery_root_fails(self) -> None:
        root = self.repository()
        (root / "catalogue").write_text("not a directory\n", encoding="utf-8")
        with self.assertRaises(DiscoveryError):
            discover_yaml_files(root, "catalogue")

    def test_root_and_nested_symlinks_fail_without_following(self) -> None:
        outside = self.repository()
        (outside / "external.yaml").write_text("id: external\n", encoding="utf-8")

        root = self.repository()
        (root / "catalogue").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(DiscoveryError) as caught:
            discover_yaml_files(root, "catalogue")
        self.assertEqual(caught.exception.diagnostic.path, "catalogue")

        nested_root = self.repository()
        (nested_root / "catalogue").mkdir()
        (nested_root / "catalogue/external").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(DiscoveryError) as nested:
            discover_yaml_files(nested_root, "catalogue")
        self.assertEqual(nested.exception.diagnostic.path, "catalogue/external")

    def test_results_are_identical_across_creation_order(self) -> None:
        expected = (
            PurePosixPath("catalogue/a.yaml"),
            PurePosixPath("catalogue/b.yaml"),
            PurePosixPath("catalogue/c.yaml"),
        )
        for order in (("c", "a", "b"), ("b", "c", "a")):
            with self.subTest(order=order):
                root = self.repository()
                (root / "catalogue").mkdir()
                for name in order:
                    (root / f"catalogue/{name}.yaml").write_text("id: value\n", encoding="utf-8")
                self.assertEqual(discover_yaml_files(root, "catalogue"), expected)


if __name__ == "__main__":
    unittest.main()
