"""Checksummed Git/provider recovery exports and offline verification."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import tempfile
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import urlopen

from modelo.build import BuildError, _git, _safe_inventory_path, _strict_json_bytes
from modelo.github_release import _api, _items, _repository, _response, github_capabilities
from modelo.quality import UBS_REPOSITORY, UBS_REVISION, command
from modelo.receipt import canonical_bytes, sha256_bytes


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def _wheel_sources(lock: bytes) -> dict[str, dict]:
    # packaging is already in the locked development toolchain used by recovery.
    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename

    tags = set(sys_tags())
    result = {}
    for package in tomllib.loads(lock.decode("utf-8"))["package"]:
        if "editable" in package.get("source", {}):
            continue
        selected = next(
            (
                wheel
                for wheel in package.get("wheels", [])
                if parse_wheel_filename(PurePosixPath(urlsplit(wheel["url"]).path).name)[3] & tags
            ),
            None,
        )
        if selected is None:
            raise BuildError("no locked wheel for recovery platform: " + package["name"])
        url = urlsplit(selected["url"])
        if (
            url.scheme != "https"
            or url.hostname != "files.pythonhosted.org"
            or url.username
            or url.query
            or url.fragment
        ):
            raise BuildError("locked recovery wheel URL is outside the supported package host")
        if not 0 < selected["size"] <= 134_217_728:
            raise BuildError("locked recovery wheel exceeds the download bound")
        result[PurePosixPath(url.path).name] = selected
    return result


def _wheels(lock: bytes, directory: Path) -> None:
    directory.mkdir()
    for name, selected in _wheel_sources(lock).items():
        with urlopen(selected["url"], timeout=60) as response:
            raw = response.read(selected["size"] + 1)
        if len(raw) != selected["size"] or sha256_bytes(raw) != selected["hash"]:
            raise BuildError("downloaded recovery wheel differs from uv.lock")
        (directory / name).write_bytes(raw)


def export_recovery(root: Path, output: Path) -> dict:
    if sys.platform != "linux":
        raise BuildError("complete recovery export requires the locked Linux/WSL toolchain")
    root = root.resolve()
    output = output.resolve()
    if output.exists():
        raise BuildError("recovery output already exists")
    document, repository = _repository(root)
    if str(_git(root, "rev-parse", "--is-shallow-repository")).strip() != "false":
        raise BuildError("recovery requires complete Git history")
    if str(_git(root, "status", "--porcelain", "--untracked-files=all")).strip():
        raise BuildError("commit repository changes before recovery export")
    if command(["uv", "--version"], root).split()[:2] != ["uv", "0.11.33"]:
        raise BuildError("recovery requires pinned uv 0.11.33")
    source = str(_git(root, "rev-parse", "HEAD")).strip()
    python_pin = (
        bytes(_git(root, "show", f"{source}:.python-version", binary=True)).decode().strip()
    )
    if python_pin != ".".join(map(str, sys.version_info[:3])):
        raise BuildError("recovery interpreter differs from committed Python pin")
    prefix = f"repos/{repository}"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="modelo-recovery-") as raw:
        stage = Path(raw)
        mirror = stage / "repository.git"
        command(
            [
                "git",
                "-c",
                "credential.helper=",
                "-c",
                "credential.helper=!gh auth git-credential",
                "clone",
                "--mirror",
                f"https://github.com/{repository}.git",
                str(mirror),
            ],
            stage,
            timeout=300,
        )
        command(["git", "cat-file", "-e", f"{source}^{{commit}}"], mirror)
        command(
            ["git", "bundle", "create", str(stage / "repository.bundle"), "--all", "HEAD"], mirror
        )
        command(["git", "bundle", "verify", str(stage / "repository.bundle")], mirror)
        lock = bytes(_git(root, "show", f"{source}:uv.lock", binary=True))
        _wheels(lock, stage / "wheels")
        command(["uv", "build", "--offline", "--no-cache", "--out-dir", str(stage / "tool")], root)
        ubs = stage / "ubs.git"
        command(
            [
                "git",
                "clone",
                "--bare",
                "--single-branch",
                "--branch",
                "v5.3.13",
                UBS_REPOSITORY,
                str(ubs),
            ],
            stage,
        )
        if command(["git", "rev-parse", "HEAD"], ubs).strip() != UBS_REVISION:
            raise BuildError("UBS recovery source differs from its pin")
        command(["git", "bundle", "create", str(stage / "ubs.bundle"), "--all", "HEAD"], ubs)
        metadata = {
            "repository": _api(prefix),
            "issues": _items(f"{prefix}/issues?state=all", max_pages=100),
            "pull_requests": _items(f"{prefix}/pulls?state=all", max_pages=100),
            "rulesets": _api(f"{prefix}/rulesets?per_page=100"),
            "capabilities": github_capabilities(root),
            "releases": _items(f"{prefix}/releases", max_pages=100),
            "trusted_runs": _items(
                f"{prefix}/actions/workflows/modelo.yml/runs", "workflow_runs", max_pages=100
            ),
        }
        ci = stage / "ci"
        ci.mkdir()
        for run in metadata["trusted_runs"]:
            run_id = run["id"]
            if type(run_id) is not int or run_id < 1:
                raise BuildError("recovery CI run identity is invalid")
            run["jobs"] = _items(f"{prefix}/actions/runs/{run_id}/jobs", "jobs")
            artifacts = _items(f"{prefix}/actions/runs/{run_id}/artifacts", "artifacts")
            run["artifacts"] = artifacts
            trusted = [
                item for item in artifacts if item.get("name", "").startswith("modelo-check-")
            ]
            run["receipt_archive_status"] = "available" if trusted else "unavailable"
            for artifact in trusted:
                identity = artifact["id"]
                if type(identity) is not int or identity < 1:
                    raise BuildError(f"CI artifact identity is invalid for run {run_id}")
                if artifact.get("expired") is True:
                    run["receipt_archive_status"] = "expired"
                    continue
                if artifact.get("expired") is not False:
                    raise BuildError("CI artifact expiry state is unknown")
                if artifact.get("workflow_run", {}).get("id") != run_id:
                    raise BuildError("recovery CI artifact provenance differs")
                data = _response(f"{prefix}/actions/artifacts/{identity}/zip")
                if len(data) != artifact.get("size_in_bytes"):
                    raise BuildError("recovery CI artifact download is incomplete")
                (ci / f"{run_id}-{identity}.zip").write_bytes(data)
        if len(metadata["rulesets"]) >= 100:
            raise BuildError("recovery ruleset export is incomplete")
        metadata["rulesets"] = [
            _api(f"{prefix}/rulesets/{item['id']}") for item in metadata["rulesets"]
        ]
        for pull in metadata["pull_requests"]:
            number = pull["number"]
            pull["reviews"] = _items(f"{prefix}/pulls/{number}/reviews")
            pull["review_comments"] = _items(f"{prefix}/pulls/{number}/comments")
        for issue in metadata["issues"]:
            issue["exported_comments"] = _items(f"{prefix}/issues/{issue['number']}/comments")
        releases = stage / "releases"
        releases.mkdir()
        for release in metadata["releases"]:
            target = releases / str(release["id"])
            target.mkdir()
            assets = _items(f"{prefix}/releases/{release['id']}/assets")
            release["assets"] = assets
            for asset in assets:
                name = asset["name"]
                if not _safe_name(name) or "/" in name:
                    raise BuildError("release asset name is unsafe for recovery")
                data = _response(f"{prefix}/releases/assets/{asset['id']}", octet_stream=True)
                if len(data) != asset["size"]:
                    raise BuildError("recovery asset download is incomplete")
                (target / name).write_bytes(data)
            if release.get("tag_name", "").startswith("catalogue-") and not release.get("draft"):
                required = {
                    "check.json",
                    "release.json",
                    "mac.json",
                    "push.json",
                    "publication.zip",
                }
                if not required.issubset({asset["name"] for asset in assets}):
                    raise BuildError("published catalogue release lacks durable recovery evidence")
                check = _strict_json_bytes((target / "check.json").read_bytes(), "archived check")
                receipt = _strict_json_bytes(
                    (target / "release.json").read_bytes(), "archived release"
                )
                if (
                    receipt.get("accepted_check_receipt_digest")
                    != sha256_bytes(canonical_bytes(check))
                    or receipt.get("ci", {}).get("run_id") != check.get("ci", {}).get("run_id")
                    or receipt.get("head_sha") != check.get("head_sha")
                    or receipt.get("release") != release["tag_name"]
                ):
                    raise BuildError("durable release receipt provenance differs")
        (stage / "host.json").write_bytes(canonical_bytes(metadata))
        files = [
            path
            for path in stage.rglob("*")
            if path.is_file() and not path.is_relative_to(ubs) and not path.is_relative_to(mirror)
        ]
        inventory = {
            path.relative_to(stage).as_posix(): {
                "sha256": _file_digest(path),
                "size": path.stat().st_size,
            }
            for path in files
        }
        manifest = {
            "version": 1,
            "repository": repository,
            "source_sha": source,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "platform": sys.platform,
            "python": python_pin,
            "ubs_revision": UBS_REVISION,
            "lock_digest": sha256_bytes(lock),
            "files": inventory,
        }
        with output.open("xb") as stream:
            with zipfile.ZipFile(
                stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                for path in sorted(files):
                    archive.write(path, path.relative_to(stage).as_posix())
                archive.writestr("recovery.json", canonical_bytes(manifest))
            stream.flush()
            os.fsync(stream.fileno())
    digest = _file_digest(output)
    verify_recovery(output, digest)
    return {"path": str(output), "sha256": digest, "source_sha": source}


def _safe_name(name: str) -> bool:
    return (
        _safe_inventory_path(name)
        and "\\" not in name
        and ":" not in name
        and not any(ord(char) < 32 or ord(char) == 127 for char in name)
    )


def verify_recovery(bundle: Path, expected_digest: str) -> dict:
    if _file_digest(bundle) != expected_digest:
        raise BuildError("recovery bundle checksum differs")
    try:
        with zipfile.ZipFile(bundle) as archive:
            infos = archive.infolist()
            names = [item.orig_filename for item in infos]
            if (
                len(names) != len(set(names))
                or len(names) > 100_000
                or sum(item.file_size for item in infos) > 2_147_483_648
            ):
                raise BuildError("recovery inventory is duplicate or oversized")
            for item in infos:
                if (
                    not _safe_name(item.orig_filename)
                    or item.file_size > 134_217_728
                    or (item.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise BuildError("recovery archive contains unsafe entries")
            manifest = _strict_json_bytes(archive.read("recovery.json"), "recovery manifest")
            if (
                set(manifest)
                != {
                    "version",
                    "repository",
                    "source_sha",
                    "retrieved_at",
                    "platform",
                    "python",
                    "ubs_revision",
                    "lock_digest",
                    "files",
                }
                or type(manifest["version"]) is not int
                or manifest["version"] != 1
            ):
                raise BuildError("recovery manifest has an unsupported shape")
            if (
                not isinstance(manifest["source_sha"], str)
                or not re.fullmatch(r"[0-9a-f]{40}", manifest["source_sha"])
                or not isinstance(manifest["lock_digest"], str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest["lock_digest"])
                or manifest["ubs_revision"] != UBS_REVISION
            ):
                raise BuildError("recovery source or dependency identity is invalid")
            files = manifest["files"]
            if not isinstance(files, dict) or set(files) != set(names) - {"recovery.json"}:
                raise BuildError("recovery manifest inventory differs from archive")
            if (
                not {"repository.bundle", "ubs.bundle", "host.json"}.issubset(files)
                or not any(name.startswith("wheels/") for name in files)
                or len(
                    [name for name in files if name.startswith("tool/") and name.endswith(".whl")]
                )
                != 1
            ):
                raise BuildError("recovery bundle lacks required components")
            for name, entry in files.items():
                data = archive.read(name)
                if (
                    not isinstance(entry, dict)
                    or type(entry.get("size")) is not int
                    or entry != {"sha256": sha256_bytes(data), "size": len(data)}
                ):
                    raise BuildError("recovery file checksum differs: " + name)
            return manifest
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise BuildError("recovery bundle is incomplete or invalid") from exc


def restore_recovery(bundle: Path, expected_digest: str, output: Path) -> dict:
    if sys.platform != "linux":
        raise BuildError("offline recovery requires Linux/WSL with pinned Python and uv installed")
    # Verify and consume a private snapshot, even if the supplied path is replaced.
    with tempfile.TemporaryDirectory(prefix="modelo-restore-") as temporary:
        snapshot = Path(temporary) / "recovery.zip"
        shutil.copyfile(bundle, snapshot)
        return _restore_snapshot(snapshot, expected_digest, output)


def _restore_snapshot(bundle: Path, expected_digest: str, output: Path) -> dict:
    manifest = verify_recovery(bundle, expected_digest)
    output = output.resolve()
    if output.exists():
        raise BuildError("recovery restore requires a new empty destination path")
    output.mkdir(parents=True)
    with zipfile.ZipFile(bundle) as archive:
        for name in archive.namelist():
            target = output.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(archive.read(name))
    command(
        [
            "git",
            "clone",
            "--mirror",
            str(output / "repository.bundle"),
            str(output / "repository.git"),
        ],
        output,
    )
    command(["git", "fsck", "--full", "--strict"], output / "repository.git")
    source = command(
        ["git", "rev-parse", f"{manifest['source_sha']}^{{commit}}"], output / "repository.git"
    ).strip()
    if source != manifest["source_sha"]:
        raise BuildError("restored Git source differs from recovery manifest")
    lock = bytes(_git(output / "repository.git", "show", f"{source}:uv.lock", binary=True))
    python_pin = (
        bytes(_git(output / "repository.git", "show", f"{source}:.python-version", binary=True))
        .decode()
        .strip()
    )
    if manifest["python"] != python_pin or python_pin != ".".join(map(str, sys.version_info[:3])):
        raise BuildError("restored interpreter differs from committed Python pin")
    if sha256_bytes(lock) != manifest["lock_digest"]:
        raise BuildError("restored dependency lock differs")
    wheels = _wheel_sources(lock)
    if {path.name for path in (output / "wheels").iterdir()} != set(wheels):
        raise BuildError("restored wheel inventory differs from uv.lock")
    for name, expected in wheels.items():
        wheel = output / "wheels" / name
        if wheel.stat().st_size != expected["size"] or _file_digest(wheel) != expected["hash"]:
            raise BuildError("restored wheel differs from uv.lock")
    command(["git", "clone", "--bare", str(output / "ubs.bundle"), str(output / "ubs.git")], output)
    command(["git", "fsck", "--full", "--strict"], output / "ubs.git")
    if (
        command(["git", "rev-parse", f"{UBS_REVISION}^{{commit}}"], output / "ubs.git").strip()
        != UBS_REVISION
    ):
        raise BuildError("restored UBS source differs from its pin")
    command(["git", "clone", str(output / "ubs.git"), str(output / "ubs")], output)
    command(["git", "checkout", "--detach", UBS_REVISION], output / "ubs")
    command(
        ["git", "clone", "--no-local", str(output / "repository.git"), str(output / "worktree")],
        output,
    )
    command(["git", "checkout", "--detach", source], output / "worktree")
    if command(["uv", "--version"], output).split()[:2] != ["uv", "0.11.33"]:
        raise BuildError("offline recovery requires pinned uv 0.11.33")
    command(
        ["uv", "venv", "--offline", "--python", manifest["python"], str(output / "environment")],
        output,
    )
    interpreter = output / "environment/bin/python"
    packages = [
        str(path)
        for directory in (output / "wheels", output / "tool")
        for path in sorted(directory.glob("*.whl"))
    ]
    command(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--no-index",
            "--no-deps",
            "--python",
            str(interpreter),
            *packages,
        ],
        output,
    )
    command(["uv", "pip", "check", "--python", str(interpreter)], output)
    command([str(interpreter), "-m", "modelo", "--version"], output)
    return manifest
