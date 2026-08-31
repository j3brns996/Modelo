from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
VALID = ROOT / "tests/fixtures/semantic/valid"


class Repository:
    def __init__(self) -> None:
        self.temporary = TemporaryDirectory(prefix="modelo-test-repo-")
        self.root = Path(self.temporary.name)
        shutil.copytree(
            ROOT,
            self.root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", ".venv", "dist", "__pycache__"),
        )
        shutil.copytree(VALID / "catalogue", self.root / "catalogue", dirs_exist_ok=True)
        self.git("init", "-q")
        self.git("config", "user.name", "Modelo Tests")
        self.git("config", "user.email", "modelo@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments], cwd=self.root, text=True, capture_output=True, check=True
        ).stdout

    def commit(self, message: str = "candidate") -> str:
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip()

    def close(self) -> None:
        self.temporary.cleanup()
