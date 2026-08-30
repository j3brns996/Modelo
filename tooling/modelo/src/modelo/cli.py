"""Modelo command-line bootstrap."""

from __future__ import annotations

import argparse
from importlib.metadata import version
from pathlib import Path
from typing import Sequence

from modelo.config import ConfigError, load_config


UNAVAILABLE = "modelo: {command} is not implemented in the current repository slice"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="modelo", description="Modelo repository tooling")
    parser.add_argument("--version", action="version", version=f"modelo {version('modelo-tooling')}")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="validate a candidate change (unavailable in T1)")
    check.add_argument("--base", required=True)
    check.add_argument("--head", required=True)
    check.add_argument("--as-of", required=True)

    build = subparsers.add_parser("build", help="build static artefacts (unavailable in T1)")
    build.add_argument("--as-of", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.command is None:
        parser.print_help()
        return 0
    try:
        load_config(arguments.root)
    except ConfigError as exc:
        parser.exit(exc.exit_code, f"{exc.render()}\n")
    parser.exit(2, f"{UNAVAILABLE.format(command=arguments.command)}\n")
    return 2
