"""Fail-closed bootstrap reader for the repository-level Modelo configuration."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, Mapping

import yaml


CONFIG_VERSION = "0.1.0"
MAX_BYTES = 131_072
MAX_DEPTH = 20
MAX_NODES = 2_000


class ConfigError(Exception):
    """A deterministic bootstrap configuration failure."""

    exit_code = 2

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str = "modelo.yaml",
        json_pointer: str = "",
        remediation: str = "Correct the repository bootstrap configuration.",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.json_pointer = json_pointer
        self.remediation = remediation

    def render(self) -> str:
        return f"{self.code}: {self.path}{self.json_pointer}: {self}"


class _RestrictedLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _RestrictedLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConfigError(
                "YAML_DUPLICATE_KEY",
                f"duplicate mapping key {key!r}",
                remediation="Remove the duplicate key; each fact has one owner.",
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_RestrictedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


@dataclass(frozen=True)
class ModeloConfig:
    root: Path
    config_version: str
    project_id: str
    project_version: str
    default_branch: str
    adapter: Literal["github", "gitlab"]
    paths: Mapping[str, PurePosixPath]
    python_version: str
    uv_version: str

    def repository_path(self, key: str) -> Path:
        try:
            relative = self.paths[key]
        except KeyError as exc:
            raise ConfigError(
                "FILE_OR_PATH_ERROR",
                f"unknown configured path key {key!r}",
                json_pointer=f"/paths/{key}",
            ) from exc
        return self.root.joinpath(*relative.parts)


def _mapping(value: Any, pointer: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigError(
            "SCHEMA_VIOLATION",
            "expected a string-keyed mapping",
            json_pointer=pointer,
        )
    return value


def _string(mapping: Mapping[str, Any], key: str, pointer: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(
            "SCHEMA_VIOLATION",
            "expected a non-empty string",
            json_pointer=f"{pointer}/{key}",
        )
    return value


def _safe_relative_path(raw: str, pointer: str) -> PurePosixPath:
    if not raw or raw == "." or "\\" in raw or any(ord(char) < 32 for char in raw):
        raise ConfigError(
            "FILE_OR_PATH_ERROR", "path is not a safe POSIX relative path", json_pointer=pointer
        )
    value = PurePosixPath(raw)
    if (
        value.is_absolute()
        or value.as_posix() != raw
        or any(part in {"", ".", ".."} for part in value.parts)
    ):
        raise ConfigError(
            "FILE_OR_PATH_ERROR", "path is not a safe POSIX relative path", json_pointer=pointer
        )
    return value


def _measure(value: Any, depth: int = 1) -> tuple[int, int]:
    if isinstance(value, dict):
        measurements = [_measure(item, depth + 1) for pair in value.items() for item in pair]
    elif isinstance(value, list):
        measurements = [_measure(item, depth + 1) for item in value]
    else:
        measurements = []
    return (
        max([depth, *(child_depth for child_depth, _ in measurements)]),
        1 + sum(child_nodes for _, child_nodes in measurements),
    )


def _reject_interpolation(value: Any, pointer: str = "") -> None:
    if isinstance(value, str) and "${" in value:
        raise ConfigError(
            "SCHEMA_VIOLATION",
            "environment interpolation is forbidden",
            json_pointer=pointer,
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_interpolation(item, f"{pointer}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_interpolation(item, f"{pointer}/{index}")


def _parse(path: Path) -> Mapping[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ConfigError("FILE_OR_PATH_ERROR", str(exc), path=str(path)) from exc
    if size > MAX_BYTES:
        raise ConfigError("YAML_LIMIT_EXCEEDED", f"configuration exceeds {MAX_BYTES} bytes")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError("FILE_OR_PATH_ERROR", str(exc), path=str(path)) from exc
    try:
        for token in yaml.scan(text):
            if isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)):
                raise ConfigError(
                    "YAML_ALIAS_OR_ANCHOR", "YAML aliases and anchors are forbidden"
                )
            if isinstance(token, yaml.tokens.TagToken):
                raise ConfigError("YAML_CUSTOM_TAG", "explicit YAML tags are forbidden")
        documents = list(yaml.load_all(text, Loader=_RestrictedLoader))
    except ConfigError:
        raise
    except yaml.YAMLError as exc:
        raise ConfigError("YAML_PARSE_ERROR", str(exc)) from exc
    if len(documents) != 1:
        raise ConfigError("YAML_MULTI_DOCUMENT", "exactly one YAML document is required")
    document = documents[0]
    if not isinstance(document, dict):
        raise ConfigError("YAML_INVALID_ROOT", "configuration root must be a mapping")
    depth, nodes = _measure(document)
    if depth > MAX_DEPTH or nodes > MAX_NODES:
        raise ConfigError(
            "YAML_LIMIT_EXCEEDED",
            f"configuration exceeds depth {MAX_DEPTH} or node count {MAX_NODES}",
        )
    _reject_interpolation(document)
    return _mapping(document, "")


def _require_regular_file(root: Path, relative: PurePosixPath, pointer: str) -> Path:
    target = root.joinpath(*relative.parts)
    if target.is_symlink() or not target.is_file():
        raise ConfigError(
            "FILE_OR_PATH_ERROR",
            "required bootstrap file is missing, not regular, or a symlink",
            path=str(target),
            json_pointer=pointer,
        )
    return target


def load_config(root: Path | None = None) -> ModeloConfig:
    repository_root = (root if root is not None else Path.cwd()).resolve()
    config_path = repository_root / "modelo.yaml"
    if config_path.is_symlink() or not config_path.is_file():
        raise ConfigError(
            "FILE_OR_PATH_ERROR",
            "modelo.yaml is missing, not regular, or a symlink",
            path=str(config_path),
        )
    document = _parse(config_path)
    if document.get("config_version") != CONFIG_VERSION:
        raise ConfigError(
            "SCHEMA_VIOLATION",
            f"unsupported config_version; expected {CONFIG_VERSION}",
            json_pointer="/config_version",
        )
    project = _mapping(document.get("project"), "/project")
    repository = _mapping(document.get("repository"), "/repository")
    raw_paths = _mapping(document.get("paths"), "/paths")
    toolchain = _mapping(document.get("toolchain"), "/toolchain")
    limits = _mapping(toolchain.get("bootstrap_config_limits"), "/toolchain/bootstrap_config_limits")
    expected_limits = {"max_bytes": MAX_BYTES, "max_depth": MAX_DEPTH, "max_nodes": MAX_NODES}
    if dict(limits) != expected_limits:
        raise ConfigError(
            "SCHEMA_VIOLATION",
            f"bootstrap limits must equal {expected_limits}",
            json_pointer="/toolchain/bootstrap_config_limits",
        )

    paths = {
        key: _safe_relative_path(value, f"/paths/{key}")
        for key, value in raw_paths.items()
        if isinstance(value, str)
    }
    if len(paths) != len(raw_paths):
        raise ConfigError("SCHEMA_VIOLATION", "all path values must be strings", json_pointer="/paths")

    version_file = _safe_relative_path(
        _string(project, "version_file", "/project"), "/project/version_file"
    )
    python_version_file = _safe_relative_path(
        _string(toolchain, "python_version_file", "/toolchain"),
        "/toolchain/python_version_file",
    )
    package_config = _safe_relative_path(
        _string(toolchain, "package_config", "/toolchain"), "/toolchain/package_config"
    )
    lock_file = _safe_relative_path(
        _string(toolchain, "lock_file", "/toolchain"), "/toolchain/lock_file"
    )
    version_path = _require_regular_file(repository_root, version_file, "/project/version_file")
    python_path = _require_regular_file(
        repository_root, python_version_file, "/toolchain/python_version_file"
    )
    _require_regular_file(repository_root, package_config, "/toolchain/package_config")
    _require_regular_file(repository_root, lock_file, "/toolchain/lock_file")

    python_version = _string(toolchain, "python_version", "/toolchain")
    uv_version = _string(toolchain, "uv_version", "/toolchain")
    if python_path.read_text(encoding="utf-8").strip() != python_version:
        raise ConfigError(
            "SCHEMA_VIOLATION",
            ".python-version and toolchain.python_version differ",
            json_pointer="/toolchain/python_version",
        )
    try:
        installed_version = version("modelo-tooling")
    except PackageNotFoundError as exc:
        raise ConfigError(
            "FILE_OR_PATH_ERROR", "modelo-tooling is not installed", path="pyproject.toml"
        ) from exc
    project_version = version_path.read_text(encoding="utf-8").strip()
    if project_version != installed_version:
        raise ConfigError(
            "SCHEMA_VIOLATION",
            "VERSION and installed package metadata differ",
            path=str(version_path),
        )

    adapter = _string(repository, "adapter", "/repository")
    if adapter not in {"github", "gitlab"}:
        raise ConfigError("SCHEMA_VIOLATION", "unsupported repository adapter", json_pointer="/repository/adapter")
    host = _string(repository, "host", "/repository")
    namespace = _string(repository, "namespace", "/repository")
    name = _string(repository, "name", "/repository")
    expected_web_base = f"https://{host}/{namespace}/{name}"
    if repository.get("web_base") != expected_web_base:
        raise ConfigError(
            "SCHEMA_VIOLATION",
            f"web_base must equal {expected_web_base}",
            json_pointer="/repository/web_base",
        )

    return ModeloConfig(
        root=repository_root,
        config_version=CONFIG_VERSION,
        project_id=_string(project, "id", "/project"),
        project_version=project_version,
        default_branch=_string(project, "default_branch", "/project"),
        adapter=adapter,
        paths=MappingProxyType(paths),
        python_version=python_version,
        uv_version=uv_version,
    )
