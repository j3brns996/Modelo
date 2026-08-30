"""Restricted YAML-to-JSON loader for governed Modelo source files."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path, PurePosixPath
from typing import Any, TypeAlias

import yaml

from modelo.diagnostics import Diagnostic, Severity


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class YamlLimits:
    """Explicit resource limits for one governed YAML document."""

    max_bytes: int = 131_072
    max_depth: int = 20
    max_nodes: int = 2_000

    def __post_init__(self) -> None:
        for name in ("max_bytes", "max_depth", "max_nodes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_LIMITS = YamlLimits()


class LoadError(Exception):
    """A restricted-loading failure represented by a stable diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class _RestrictedLoader(yaml.SafeLoader):
    pass


# Keep dates and timestamps as strings. Copy before editing so importing this
# module cannot change PyYAML's process-global SafeLoader behaviour.
_RestrictedLoader.yaml_implicit_resolvers = deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for _initial, _resolvers in list(_RestrictedLoader.yaml_implicit_resolvers.items()):
    _RestrictedLoader.yaml_implicit_resolvers[_initial] = [
        resolver for resolver in _resolvers if resolver[0] != "tag:yaml.org,2002:timestamp"
    ]


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
                "mapping keys must be scalar strings",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise LoadError(
                _diagnostic(
                    "YAML_DUPLICATE_KEY",
                    "duplicate mapping key",
                    "Remove the duplicate key; each fact must have one value.",
                )
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_RestrictedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _diagnostic(
    code: str,
    message: str,
    remediation: str,
    *,
    path: str = "<yaml>",
    json_pointer: str = "",
) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=Severity.ERROR,
        path=path,
        json_pointer=json_pointer,
        message=message,
        remediation=remediation,
    )


def _error(
    code: str,
    message: str,
    remediation: str,
    *,
    path: str,
    json_pointer: str = "",
) -> LoadError:
    return LoadError(
        _diagnostic(
            code,
            message,
            remediation,
            path=path,
            json_pointer=json_pointer,
        )
    )


def _safe_relative_path(value: str | PurePosixPath) -> PurePosixPath:
    raw = str(value)
    candidate = PurePosixPath(raw)
    if (
        not raw
        or raw == "."
        or "\\" in raw
        or any(ord(character) < 32 for character in raw)
        or candidate.is_absolute()
        or candidate.as_posix() != raw
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise _error(
            "FILE_OR_PATH_ERROR",
            "YAML path is not a safe repository-relative POSIX path",
            "Use a configured relative path without traversal or platform separators.",
            path=raw or "<empty>",
        )
    return candidate


def _confined_file(repository_root: Path, relative: PurePosixPath) -> Path:
    try:
        root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise _error(
            "FILE_OR_PATH_ERROR",
            f"cannot resolve repository root: {exc}",
            "Provide the checked-out repository root.",
            path=str(repository_root),
        ) from exc
    if not root.is_dir():
        raise _error(
            "FILE_OR_PATH_ERROR",
            "repository root is not a directory",
            "Provide the checked-out repository root.",
            path=str(repository_root),
        )
    current = root
    target = root.joinpath(*relative.parts)
    try:
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise _error(
                    "FILE_OR_PATH_ERROR",
                    "symlinks are forbidden in governed YAML paths",
                    "Replace the symlink with a regular repository file or directory.",
                    path=relative.as_posix(),
                )
        resolved = target.resolve(strict=True)
    except LoadError:
        raise
    except OSError as exc:
        raise _error(
            "FILE_OR_PATH_ERROR",
            f"cannot resolve YAML path: {exc}",
            "Create a readable regular file beneath the configured repository root.",
            path=relative.as_posix(),
        ) from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise _error(
            "FILE_OR_PATH_ERROR",
            "YAML path is outside the repository or is not a regular file",
            "Use a readable regular file beneath the configured repository root.",
            path=relative.as_posix(),
        )
    return target


def _scan(text: str, *, limits: YamlLimits, path: str) -> None:
    nesting = 0
    nodes = 0
    try:
        for token in yaml.scan(text):
            if isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)):
                raise _error(
                    "YAML_ALIAS_OR_ANCHOR",
                    "YAML aliases and anchors are forbidden",
                    "Write each value explicitly without aliases or anchors.",
                    path=path,
                )
            if isinstance(token, yaml.tokens.TagToken):
                raise _error(
                    "YAML_CUSTOM_TAG",
                    "explicit YAML tags are forbidden",
                    "Remove the tag and use JSON-compatible scalar, sequence and mapping values.",
                    path=path,
                )
            if isinstance(
                token,
                (
                    yaml.tokens.BlockMappingStartToken,
                    yaml.tokens.BlockSequenceStartToken,
                    yaml.tokens.FlowMappingStartToken,
                    yaml.tokens.FlowSequenceStartToken,
                ),
            ):
                nesting += 1
                nodes += 1
            elif isinstance(
                token,
                (
                    yaml.tokens.BlockEndToken,
                    yaml.tokens.FlowMappingEndToken,
                    yaml.tokens.FlowSequenceEndToken,
                ),
            ):
                nesting = max(0, nesting - 1)
            elif isinstance(token, yaml.tokens.ScalarToken):
                nodes += 1
            if nesting > limits.max_depth or nodes > limits.max_nodes:
                raise _error(
                    "YAML_LIMIT_EXCEEDED",
                    "YAML exceeds its configured depth or node limit",
                    "Reduce document nesting or item count.",
                    path=path,
                )
    except LoadError:
        raise
    except RecursionError as exc:
        raise _error(
            "YAML_LIMIT_EXCEEDED",
            "YAML nesting is excessive",
            "Reduce document nesting.",
            path=path,
        ) from exc
    except yaml.YAMLError as exc:
        raise _error(
            "YAML_PARSE_ERROR",
            f"cannot scan YAML: {exc}",
            "Correct the YAML syntax.",
            path=path,
        ) from exc


def _validate_json_value(document: Any, *, path: str, limits: YamlLimits) -> None:
    stack: list[tuple[Any, int, str]] = [(document, 1, "")]
    nodes = 0
    while stack:
        value, depth, pointer = stack.pop()
        nodes += 1
        if depth > limits.max_depth or nodes > limits.max_nodes:
            raise _error(
                "YAML_LIMIT_EXCEEDED",
                "constructed YAML exceeds its configured depth or node limit",
                "Reduce document nesting or item count.",
                path=path,
                json_pointer=pointer,
            )
        if value is None or isinstance(value, (bool, int, str)):
            continue
        if isinstance(value, float):
            if not math.isfinite(value):
                raise _error(
                    "YAML_PARSE_ERROR",
                    "non-finite numbers are not JSON-compatible",
                    "Use a finite number or a decimal string.",
                    path=path,
                    json_pointer=pointer,
                )
            continue
        if isinstance(value, list):
            stack.extend(
                (item, depth + 1, f"{pointer}/{index}")
                for index, item in reversed(tuple(enumerate(value)))
            )
            continue
        if isinstance(value, dict):
            for key in value:
                if not isinstance(key, str):
                    raise _error(
                        "YAML_PARSE_ERROR",
                        "mapping keys must be strings",
                        "Use string keys so the document has a portable JSON data model.",
                        path=path,
                        json_pointer=pointer,
                    )
            stack.extend(
                (item, depth + 1, f"{pointer}/{_escape_pointer(key)}")
                for key, item in reversed(tuple(value.items()))
            )
            continue
        raise _error(
            "YAML_PARSE_ERROR",
            f"value of type {type(value).__name__} is not JSON-compatible",
            "Use null, boolean, number, string, sequence or string-keyed mapping values.",
            path=path,
            json_pointer=pointer,
        )


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def load_yaml_mapping(
    repository_root: Path,
    relative_path: str | PurePosixPath,
    *,
    limits: YamlLimits = DEFAULT_LIMITS,
) -> dict[str, JsonValue]:
    """Load one confined YAML file into a JSON-compatible root mapping."""

    relative = _safe_relative_path(relative_path)
    path_text = relative.as_posix()
    try:
        target = _confined_file(repository_root, relative)
        raw = target.read_bytes()
    except LoadError:
        raise
    except OSError as exc:
        raise _error(
            "FILE_OR_PATH_ERROR",
            f"cannot read YAML file: {exc}",
            "Ensure the governed file is readable.",
            path=path_text,
        ) from exc
    if len(raw) > limits.max_bytes:
        raise _error(
            "YAML_LIMIT_EXCEEDED",
            f"YAML exceeds {limits.max_bytes} bytes",
            "Reduce the document size.",
            path=path_text,
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error(
            "FILE_OR_PATH_ERROR",
            f"YAML is not valid UTF-8: {exc}",
            "Encode the file as UTF-8.",
            path=path_text,
        ) from exc
    _scan(text, limits=limits, path=path_text)
    try:
        documents = list(yaml.load_all(text, Loader=_RestrictedLoader))
    except LoadError as exc:
        if exc.diagnostic.path == "<yaml>":
            raise LoadError(
                Diagnostic(
                    code=exc.diagnostic.code,
                    severity=exc.diagnostic.severity,
                    path=path_text,
                    json_pointer=exc.diagnostic.json_pointer,
                    message=exc.diagnostic.message,
                    remediation=exc.diagnostic.remediation,
                )
            ) from exc
        raise
    except RecursionError as exc:
        raise _error(
            "YAML_LIMIT_EXCEEDED",
            "YAML nesting is excessive",
            "Reduce document nesting.",
            path=path_text,
        ) from exc
    except yaml.YAMLError as exc:
        raise _error(
            "YAML_PARSE_ERROR",
            f"cannot parse YAML: {exc}",
            "Correct the YAML syntax.",
            path=path_text,
        ) from exc
    if len(documents) != 1:
        raise _error(
            "YAML_MULTI_DOCUMENT",
            "exactly one YAML document is required",
            "Keep one root mapping in each governed YAML file.",
            path=path_text,
        )
    document = documents[0]
    if not isinstance(document, dict):
        raise _error(
            "YAML_INVALID_ROOT",
            "YAML root must be a mapping",
            "Use a mapping at the document root.",
            path=path_text,
        )
    _validate_json_value(document, path=path_text, limits=limits)
    return document
