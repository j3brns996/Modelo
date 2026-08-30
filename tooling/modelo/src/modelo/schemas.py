"""Offline JSON Schema loading and deterministic validation."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from modelo.diagnostics import Diagnostic, Severity


def _pointer(parts: object) -> str:
    return "".join(
        f"/{str(part).replace('~', '~0').replace('/', '~1')}" for part in parts  # type: ignore[arg-type]
    )


class SchemaSet:
    """A repository-confined Draft 2020-12 schema registry."""

    def __init__(self, root: Path, schemas_path: PurePosixPath) -> None:
        directory = root.joinpath(*schemas_path.parts)
        self.documents: dict[str, Mapping[str, Any]] = {}
        registry: Registry[Any] = Registry()
        try:
            paths = sorted(directory.rglob("*.schema.json"))
        except OSError as exc:
            raise ValueError(f"cannot enumerate schemas: {exc}") from exc
        if not paths:
            raise ValueError("no schema files were found")
        for path in paths:
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"schema is not a regular file: {path}")
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(document)
                identifier = document["$id"]
                resource = Resource.from_contents(document)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"cannot load schema {path}: {exc}") from exc
            name = path.relative_to(directory).as_posix()
            self.documents[name] = document
            registry = registry.with_resource(identifier, resource)
        identifiers = {document["$id"] for document in self.documents.values()}
        for name, document in self.documents.items():
            for reference in self._references(document):
                target = urljoin(document["$id"], reference).split("#", 1)[0]
                if target not in identifiers:
                    raise ValueError(f"schema {name} has unresolved local reference {reference}")
        self.registry = registry

    @staticmethod
    def _references(value: Any):
        if isinstance(value, dict):
            if isinstance(value.get("$ref"), str):
                yield value["$ref"]
            for child in value.values():
                yield from SchemaSet._references(child)
        elif isinstance(value, list):
            for child in value:
                yield from SchemaSet._references(child)

    def validator(self, name: str) -> Draft202012Validator:
        try:
            schema = self.documents[name]
        except KeyError as exc:
            raise ValueError(f"required schema is missing: {name}") from exc
        checker = FormatChecker()

        @checker.checks("date")
        def valid_date(value: object) -> bool:
            if not isinstance(value, str):
                return True
            try:
                return date.fromisoformat(value).isoformat() == value
            except ValueError:
                return False

        @checker.checks("date-time")
        def valid_datetime(value: object) -> bool:
            if not isinstance(value, str):
                return True
            candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed.tzinfo is not None
            except ValueError:
                return False

        @checker.checks("uri")
        def valid_uri(value: object) -> bool:
            if not isinstance(value, str):
                return True
            try:
                parsed = urlsplit(value)
                return bool(parsed.scheme and parsed.netloc and parsed.hostname)
            except ValueError:
                return False

        return Draft202012Validator(schema, registry=self.registry, format_checker=checker)

    def validate(self, name: str, instance: Any, path: str) -> tuple[Diagnostic, ...]:
        errors = sorted(
            self.validator(name).iter_errors(instance),
            key=lambda error: (
                tuple(str(item) for item in error.absolute_path),
                str(error.validator),
                error.message,
            ),
        )
        return tuple(
            Diagnostic(
                code="SCHEMA_VIOLATION",
                severity=Severity.ERROR,
                path=path,
                json_pointer=_pointer(error.absolute_path),
                message=f"{error.validator}: {error.message}",
                remediation=f"Conform the document to {name}.",
            )
            for error in errors
        )

    def schema(self, name: str) -> Mapping[str, Any]:
        try:
            return self.documents[name]
        except KeyError as exc:
            raise ValueError(f"required schema is missing: {name}") from exc

    def resolve(
        self, schema: Mapping[str, Any], base: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        reference = schema.get("$ref")
        if not isinstance(reference, str):
            return schema, base
        resource_name, _, fragment = reference.partition("#")
        target = base
        if resource_name:
            resource_basename = PurePosixPath(resource_name).name
            matches = [
                document
                for name, document in self.documents.items()
                if name == resource_name
                or (".." in PurePosixPath(resource_name).parts and PurePosixPath(name).name == resource_basename)
            ]
            if len(matches) != 1:
                raise ValueError(f"schema reference is not uniquely local: {reference}")
            target = matches[0]
        resolved: Any = target
        if fragment:
            if not fragment.startswith("/"):
                raise ValueError(f"unsupported schema fragment: {reference}")
            for raw in fragment[1:].split("/"):
                token = raw.replace("~1", "/").replace("~0", "~")
                resolved = resolved[token]
        if not isinstance(resolved, Mapping):
            raise ValueError(f"schema reference does not resolve to a mapping: {reference}")
        return resolved, target
