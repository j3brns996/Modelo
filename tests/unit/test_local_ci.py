from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from modelo.local_ci import (
    ChangeMode, LocalCIError, advisory_run, classify_change_mode,
    discover_test_files, verification_shards, verify,
)


ROOT = Path(__file__).resolve().parents[2]


def test_change_mode_is_separate_from_agent_approval_scope() -> None:
    assert classify_change_mode(["catalogue/models/a.yaml"]) is ChangeMode.MAC_DATA
    assert classify_change_mode(["catalogue/governance/actors.yaml"]) is ChangeMode.MAC_DATA
    assert classify_change_mode(["catalogue/policies/conditions/x/1.yaml"]) is ChangeMode.MAC_DATA
    assert classify_change_mode(["docs/contract.yaml"]) is ChangeMode.CONTROL_PLANE
    with pytest.raises(LocalCIError, match="separate pull requests"):
        classify_change_mode(["catalogue/models/a.yaml", "docs/contract.yaml"])
    with pytest.raises(LocalCIError, match="no changed paths"):
        classify_change_mode([])
    for unsafe in ("../outside", "/absolute", "bad\x00path"):
        with pytest.raises(LocalCIError, match="unsafe"):
            classify_change_mode([unsafe])


def test_parallel_shards_are_disjoint_and_cover_the_exact_python_test_inventory() -> None:
    discovered = discover_test_files(ROOT)
    shards = verification_shards(ROOT, jobs=3)
    flattened = [path for shard in shards for path in shard]
    assert len(flattened) == len(set(flattened))
    assert set(flattened) == set(discovered)
    assert any(shard == ("tests/site/test_site.py",) for shard in shards)
    assert any(shard == ("tests/unit/test_build.py",) for shard in shards)


def test_single_job_uses_one_complete_inventory_and_jobs_are_bounded() -> None:
    discovered = discover_test_files(ROOT)
    assert verification_shards(ROOT, jobs=1) == (discovered,)
    for invalid in (0, 4, True):
        with pytest.raises(LocalCIError, match="between 1 and 3"):
            verification_shards(ROOT, jobs=invalid)


def test_test_discovery_rejects_an_empty_or_unsafe_root(tmp_path: Path) -> None:
    with pytest.raises(LocalCIError, match="no Python tests"):
        discover_test_files(tmp_path)


def test_verify_owns_sync_complete_tests_and_offline_package_gate(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_one.py").write_text("def test_one(): pass\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='1'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    passed = subprocess.CompletedProcess([], 0, "", "")
    with patch("modelo.local_ci._run", return_value=passed) as run:
        verify(tmp_path, jobs=1)
    commands = [call.args[0] for call in run.call_args_list]
    assert commands[0][:3] == ("uv", "sync", "--project")
    assert commands[1][-2:] == ("-q", "tests/test_one.py")
    assert commands[2] == ("uv", "build", "--offline", "--no-cache")


def test_advisory_data_mode_never_runs_the_control_verifier(tmp_path: Path) -> None:
    with (
        patch("modelo.local_ci.repository_change_mode", return_value=ChangeMode.MAC_DATA),
        patch("modelo.local_ci.check_repository", return_value=()),
        patch("modelo.local_ci.verify") as control_verify,
    ):
        advisory_run(tmp_path, "base", "head", "2026-09-02", jobs=3)
    control_verify.assert_not_called()


def test_advisory_control_mode_runs_the_fixed_verifier(tmp_path: Path) -> None:
    with (
        patch("modelo.local_ci.repository_change_mode", return_value=ChangeMode.CONTROL_PLANE),
        patch("modelo.local_ci.verify") as control_verify,
    ):
        advisory_run(tmp_path, "base", "head", None, jobs=2)
    control_verify.assert_called_once_with(tmp_path, 2)
