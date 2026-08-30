"""Modelo command-line bootstrap."""

from __future__ import annotations

import argparse
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Sequence

from modelo.config import ConfigError, load_config
from modelo.diagnostics import Diagnostic, diagnostics_json
from modelo.freshness import parse_as_of
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

    build = subparsers.add_parser("build", help="build static artefacts (unavailable in T1)")
    build.add_argument("--as-of", required=True)
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
    try:
        load_config(arguments.root)
    except ConfigError as exc:
        parser.exit(exc.exit_code, f"{exc.render()}\n")
    parser.exit(2, f"{UNAVAILABLE.format(command=arguments.command)}\n")
    return 2


def _render_text(diagnostic: Diagnostic) -> str:
    pointer = diagnostic.json_pointer
    return (
        f"{diagnostic.code} [{diagnostic.severity.value}] "
        f"{diagnostic.path}{pointer}: {diagnostic.message} "
        f"Remediation: {diagnostic.remediation}"
    )
