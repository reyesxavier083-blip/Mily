"""Unit tests for MILY workspace path validation."""

import tempfile
import unittest
from pathlib import Path

from mily_core.security import PathSecurityError, resolve_workspace_path


class ResolveWorkspacePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_accepts_path_inside_workspace(self) -> None:
        self.assertEqual(resolve_workspace_path(self.root, "data/note.txt"), self.root / "data/note.txt")

    def test_rejects_parent_traversal(self) -> None:
        with self.assertRaises(PathSecurityError):
            resolve_workspace_path(self.root, "../outside.txt")

    def test_rejects_absolute_path(self) -> None:
        with self.assertRaises(PathSecurityError):
            resolve_workspace_path(self.root, self.root / "note.txt")

    def test_rejects_empty_path(self) -> None:
        with self.assertRaises(PathSecurityError):
            resolve_workspace_path(self.root, "")

    def test_rejects_null_byte(self) -> None:
        with self.assertRaises(PathSecurityError):
            resolve_workspace_path(self.root, "bad\x00name")

    def test_rejects_symlink_escape(self) -> None:
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir(exist_ok=True)
        link = self.root / "escape"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are not supported in this environment")
        try:
            with self.assertRaises(PathSecurityError):
                resolve_workspace_path(self.root, "escape/file.txt")
        finally:
            link.unlink(missing_ok=True)
            try:
                outside.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
