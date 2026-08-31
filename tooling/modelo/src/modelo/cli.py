"""Modelo command-line bootstrap."""

from __future__ import annotations

import argparse
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Sequence

from modelo.config import ConfigError, load_config
from modelo.build import BuildError, BuildRequest, build_candidate, recover_candidate
from modelo.diagnostics import Diagnostic, diagnostics_json
from modelo.freshness import parse_as_of
from modelo.site import FinalBuildRequest, build_final_site
from modelo.validators import CheckSystemError, check_repository


UNAVAILABLE = "modelo: {command} is not implemented in the current repository slice"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="modelo", description="Modelo repository tooling")
    parser.add_argument("--version", action="version", version=f"modelo {version('modelo-tooling')}")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="validate a committed candidate change")
    check.add_argument("--base", required=True)
    check.add_argument("--head", required=True)
    check.add_argument("--as-of", required=True)
    check.add_argument("--format", choices=("text", "json"), default="text")

    build = subparsers.add_parser("build", help="build deterministic candidate artefacts")
    build.add_argument("--kind", required=True, choices=("candidate", "final"))
    build.add_argument("--base-commit", required=True)
    build.add_argument("--source-commit", required=True)
    build.add_argument("--source-tree", required=True)
    build.add_argument("--as-of", required=True)
    build.add_argument("--source-date-epoch", required=True, type=int)
    build.add_argument("--mac-metadata", type=Path)
    build.add_argument("--profile", required=True)
    choice = build.add_mutually_exclusive_group(required=True)
    choice.add_argument("--base-url")
    choice.add_argument("--no-base-url", action="store_true")
    build.add_argument("--base-path", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--merge-commit")
    build.add_argument("--merge-tree")
    build.add_argument(
        "--publication-capability",
        choices=("public-pages", "restricted-artifact", "access-controlled-pages"),
    )
    subparsers.add_parser("recover", help="recover an interrupted candidate or final publication")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.command is None:
        parser.print_help()
        return 0
    if arguments.command == "check":
        try:
            as_of: date = parse_as_of(arguments.as_of)
            diagnostics = check_repository(
                arguments.root.resolve(), arguments.base, arguments.head, as_of
            )
        except (ValueError, CheckSystemError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
        if diagnostics:
            if arguments.format == "json":
                print(diagnostics_json(diagnostics), end="")
            else:
                for diagnostic in diagnostics:
                    print(_render_text(diagnostic))
            return 1
        return 0
    if arguments.command == "recover":
        try:
            recover_candidate(arguments.root.resolve())
            return 0
        except (ConfigError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "build":
        try:
            as_of = parse_as_of(arguments.as_of)
            if arguments.kind == "final":
                if arguments.no_base_url or not arguments.base_url:
                    raise BuildError("final build requires --base-url")
                if not arguments.merge_commit or not arguments.merge_tree:
                    raise BuildError("final build requires --merge-commit and --merge-tree")
                if arguments.mac_metadata is None:
                    raise BuildError("final build requires --mac-metadata to rebuild trusted candidate inputs")
                if arguments.publication_capability is None:
                    raise BuildError("final build requires --publication-capability")
                build_final_site(FinalBuildRequest(
                    root=arguments.root,
                    base_commit=arguments.base_commit,
                    source_commit=arguments.source_commit,
                    source_tree=arguments.source_tree,
                    merge_commit=arguments.merge_commit,
                    merge_tree=arguments.merge_tree,
                    as_of=as_of,
                    source_date_epoch=arguments.source_date_epoch,
                    profile=arguments.profile,
                    base_url=arguments.base_url,
                    base_path=arguments.base_path,
                    output=arguments.output,
                    mac_metadata=arguments.mac_metadata,
                    publication_capability=arguments.publication_capability,
                ))
                return 0
            if arguments.merge_commit or arguments.merge_tree:
                raise BuildError("candidate build does not accept merge coordinates")
            if arguments.publication_capability is not None:
                raise BuildError("candidate build does not accept --publication-capability")
            if arguments.mac_metadata is None:
                raise BuildError("candidate build requires --mac-metadata")
            build_candidate(BuildRequest(
                root=arguments.root,
                kind=arguments.kind,
                base_commit=arguments.base_commit,
                source_commit=arguments.source_commit,
                source_tree=arguments.source_tree,
                as_of=as_of,
                source_date_epoch=arguments.source_date_epoch,
                mac_metadata=arguments.mac_metadata,
                profile=arguments.profile,
                base_url=None if arguments.no_base_url else arguments.base_url,
                base_path=arguments.base_path,
                output=arguments.output,
            ))
            return 0
        except (ValueError, ConfigError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    parser.exit(2, f"{UNAVAILABLE.format(command=arguments.command)}\n")
    return 2


def _render_text(diagnostic: Diagnostic) -> str:
    pointer = diagnostic.json_pointer
    return (
        f"{diagnostic.code} [{diagnostic.severity.value}] "
        f"{diagnostic.path}{pointer}: {diagnostic.message} "
        f"Remediation: {diagnostic.remediation}"
    )
