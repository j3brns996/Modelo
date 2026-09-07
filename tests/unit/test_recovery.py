import io
import zipfile

import pytest
from modelo.build import BuildError
from modelo.quality import UBS_REVISION
from modelo.receipt import canonical_bytes, sha256_bytes
from modelo.recovery import verify_recovery


def test_restore_consumes_private_snapshot_when_original_path_changes(tmp_path, monkeypatch):
    from modelo import recovery

    source = tmp_path / "input.zip"
    source.write_bytes(b"verified input")
    monkeypatch.setattr(recovery.sys, "platform", "linux")

    def restore(snapshot, digest, output):
        source.write_bytes(b"replacement")
        assert snapshot != source
        assert snapshot.read_bytes() == b"verified input"
        assert digest == sha256_bytes(snapshot.read_bytes())
        return {"verified": True}

    monkeypatch.setattr(recovery, "_restore_snapshot", restore)
    assert recovery.restore_recovery(
        source, sha256_bytes(source.read_bytes()), tmp_path / "out"
    ) == {"verified": True}


def test_recovery_checks_complete_inventory_bytes_and_paths(tmp_path):
    files = {
        "repository.bundle": b"git fixture",
        "ubs.bundle": b"UBS fixture",
        "host.json": b"{}\n",
        "wheels/example-1-py3-none-any.whl": b"wheel fixture",
        "tool/modelo_tooling-0.2.0-py3-none-any.whl": b"tool fixture",
    }

    def write(selected, changed=None):
        manifest = {
            "version": 1,
            "repository": "example/Modelo",
            "source_sha": "a" * 40,
            "retrieved_at": "2026-09-07T12:00:00+00:00",
            "platform": "linux",
            "python": "3.12.13",
            "ubs_revision": UBS_REVISION,
            "lock_digest": "sha256:" + "b" * 64,
            "files": {
                name: {"sha256": sha256_bytes(data), "size": len(data)}
                for name, data in selected.items()
            },
        }
        if changed:
            manifest.update(changed)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in selected.items():
                entry = zipfile.ZipInfo("placeholder")
                entry.filename = name
                archive.writestr(entry, data)
            archive.writestr("recovery.json", canonical_bytes(manifest))
        path = tmp_path / "backup.zip"
        raw = stream.getvalue()
        path.write_bytes(raw)
        return path, sha256_bytes(raw)

    path, digest = write(files)
    assert verify_recovery(path, digest)["source_sha"] == "a" * 40
    with pytest.raises(BuildError, match="checksum differs"):
        verify_recovery(path, "sha256:" + "0" * 64)
    for name in ("../escape", "/absolute", "C:/outside", "bad\\path"):
        path, digest = write(files | {name: b"unsafe"})
        with pytest.raises(BuildError, match="unsafe"):
            verify_recovery(path, digest)
    for missing in (
        "repository.bundle",
        "ubs.bundle",
        "host.json",
        "wheels/example-1-py3-none-any.whl",
        "tool/modelo_tooling-0.2.0-py3-none-any.whl",
    ):
        path, digest = write({name: data for name, data in files.items() if name != missing})
        with pytest.raises(BuildError, match="required components"):
            verify_recovery(path, digest)
    path, digest = write(files, {"source_sha": "--output=outside"})
    with pytest.raises(BuildError, match="identity is invalid"):
        verify_recovery(path, digest)
    path, digest = write(files, {"files": {}})
    with pytest.raises(BuildError, match="inventory differs"):
        verify_recovery(path, digest)
