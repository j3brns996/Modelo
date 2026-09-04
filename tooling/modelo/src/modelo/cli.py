"""Modelo command-line bootstrap."""

from __future__ import annotations

import argparse
from datetime import date
from importlib.metadata import version
import json
from pathlib import Path
from pathlib import PurePosixPath
from typing import Sequence

from modelo.config import ConfigError, load_config
from modelo.loader import load_yaml_mapping
from modelo.build import BuildError, BuildRequest, build_candidate, recover_candidate
from modelo.diagnostics import Diagnostic, diagnostics_json
from modelo.freshness import parse_as_of
from modelo.site import DemoBuildRequest, FinalBuildRequest, build_demo_site, build_final_site
from modelo.platform import (
    TrustedCheckRequest, TrustedControlCheckRequest, run_trusted_check,
    run_trusted_control_check,
)
from modelo.github_adapter import (
    _intake_issue_body, write_github_intake_outputs,
    github_control_issue_reference, github_issue_reference, prepare_github,
    prepare_github_control,
)
from modelo.gitlab_adapter import (
    write_gitlab_intake_outputs,
    gitlab_control_issue_reference, gitlab_issue_reference, prepare_gitlab,
    prepare_gitlab_control,
)
from modelo.evidence import create_evidence_record
from modelo.mac import MacError, init_mac_payload
from modelo.schemas import SchemaSet
from modelo.validators import CheckSystemError, check_repository


UNAVAILABLE = "modelo: {command} is not implemented in the current repository slice"


def _read_json_file(path: Path, option: str) -> Any:
    try:
        if not path.is_file():
            raise ValueError(
                f"{option} JSON file does not exist or is not a regular file: {path}"
            )
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read {option} JSON file {path}: {exc}") from exc
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{option} JSON file {path} is invalid: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc


def _parse_json_arg(value: str, option: str) -> Any:
    if value.startswith("@"):
        path_value = value[1:]
        if not path_value:
            raise ValueError(f"{option} @path must name a JSON file")
        return _read_json_file(Path(path_value), option)

    try:
        return json.loads(value)
    except json.JSONDecodeError as inline_error:
        candidate = Path(value)
        try:
            is_file = candidate.is_file()
        except OSError:
            is_file = False
        if is_file:
            return _read_json_file(candidate, option)
        raise ValueError(
            f"{option} must be inline JSON, @path, or an existing JSON file; "
            f"inline JSON is invalid: {inline_error.msg} "
            f"(line {inline_error.lineno}, column {inline_error.colno})"
        ) from inline_error


def _emit_json(document: Any, output: Path | None) -> None:
    formatted = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(formatted, encoding="utf-8")
    else:
        print(formatted, end="")



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
    build.add_argument("--kind", required=True, choices=("candidate", "demo", "final"))
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
    config = subparsers.add_parser("config", help="read validated global configuration")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    config_site = config_subparsers.add_parser(
        "site", help="print canonical site URL configuration"
    )
    config_site.add_argument("--format", choices=("json", "lines"), default="json")
    platform = subparsers.add_parser("platform", help="run a trusted Git-provider adapter operation")
    platform_subparsers = platform.add_subparsers(dest="platform_command", required=True)
    platform_check = platform_subparsers.add_parser("check", help="assemble an exact-head check receipt")
    platform_check.add_argument("--context", type=Path, required=True)
    platform_check.add_argument("--mac-metadata", type=Path, required=True)
    platform_check.add_argument("--output", type=Path, required=True)
    control_check = platform_subparsers.add_parser("control-check", help="assemble an exact-head control receipt")
    control_check.add_argument("--context", type=Path, required=True)
    control_check.add_argument("--output", type=Path, required=True)
    github_issue = platform_subparsers.add_parser("github-issue", help="extract the linked MAC issue")
    github_issue.add_argument("--event", type=Path, required=True)
    github_control_issue = platform_subparsers.add_parser("github-control-issue", help="extract the linked control issue")
    github_control_issue.add_argument("--event", type=Path, required=True)
    github_prepare = platform_subparsers.add_parser("github-prepare", help="prepare trusted GitHub inputs")
    github_prepare.add_argument("--event", type=Path, required=True)
    github_prepare.add_argument("--issue", type=Path, required=True)
    github_prepare.add_argument("--validation-sha", required=True)
    github_prepare.add_argument("--validation-tree", required=True)
    github_prepare.add_argument("--as-of", required=True)
    github_prepare.add_argument("--metadata-output", type=Path, required=True)
    github_prepare.add_argument("--context-output", type=Path, required=True)
    github_control = platform_subparsers.add_parser("github-prepare-control", help="prepare trusted GitHub control inputs")
    github_control.add_argument("--event", type=Path, required=True)
    github_control.add_argument("--issue", type=Path, required=True)
    github_control.add_argument("--validation-sha", required=True)
    github_control.add_argument("--validation-tree", required=True)
    github_control.add_argument("--as-of", required=True)
    github_control.add_argument("--context-output", type=Path, required=True)
    github_intake = platform_subparsers.add_parser(
        "github-intake", help="compile a guided GitHub issue proposal"
    )
    github_intake.add_argument("--event", type=Path, required=True)
    github_intake.add_argument("--issue-body-output", type=Path, required=True)
    github_intake.add_argument("--comment-output", type=Path, required=True)

    gitlab_issue = platform_subparsers.add_parser("gitlab-issue", help="extract the linked MAC issue from GitLab MR")
    gitlab_issue.add_argument("--event", type=Path, required=True)
    gitlab_control_issue = platform_subparsers.add_parser("gitlab-control-issue", help="extract the linked control issue from GitLab MR")
    gitlab_control_issue.add_argument("--event", type=Path, required=True)
    gitlab_prepare = platform_subparsers.add_parser("gitlab-prepare", help="prepare trusted GitLab inputs")
    gitlab_prepare.add_argument("--event", type=Path, required=True)
    gitlab_prepare.add_argument("--issue", type=Path, required=True)
    gitlab_prepare.add_argument("--validation-sha", required=True)
    gitlab_prepare.add_argument("--validation-tree", required=True)
    gitlab_prepare.add_argument("--as-of", required=True)
    gitlab_prepare.add_argument("--metadata-output", type=Path, required=True)
    gitlab_prepare.add_argument("--context-output", type=Path, required=True)
    gitlab_control = platform_subparsers.add_parser("gitlab-prepare-control", help="prepare trusted GitLab control inputs")
    gitlab_control.add_argument("--event", type=Path, required=True)
    gitlab_control.add_argument("--issue", type=Path, required=True)
    gitlab_control.add_argument("--validation-sha", required=True)
    gitlab_control.add_argument("--validation-tree", required=True)
    gitlab_control.add_argument("--as-of", required=True)
    gitlab_control.add_argument("--context-output", type=Path, required=True)
    gitlab_intake = platform_subparsers.add_parser(
        "gitlab-intake", help="compile a guided GitLab issue proposal"
    )
    gitlab_intake.add_argument("--event", type=Path, required=True)
    gitlab_intake.add_argument("--issue-body-output", type=Path, required=True)
    gitlab_intake.add_argument("--comment-output", type=Path, required=True)

    dev = subparsers.add_parser("dev", help="developer and authoring suite utilities")
    dev_subparsers = dev.add_subparsers(dest="dev_command", required=True)

    evidence_create = dev_subparsers.add_parser(
        "evidence-create", help="create a schema-valid local evidence record"
    )
    evidence_create.add_argument(
        "--source-type",
        required=True,
        choices=(
            "first-party-read-api",
            "official-provider-documentation",
            "official-vendor-documentation",
        ),
    )
    evidence_create.add_argument("--uri", required=True)
    evidence_create.add_argument("--observed-at", required=True)
    evidence_create.add_argument("--projection", required=True)
    evidence_create.add_argument("--provider", choices=("aws",))
    evidence_create.add_argument("--service", choices=("bedrock",))
    evidence_create.add_argument("--operation")
    evidence_create.add_argument("--partition")
    evidence_create.add_argument("--region")
    evidence_create.add_argument("--sanitised-parameters")
    evidence_create.add_argument("--retrieved-by", default="cli")
    evidence_create.add_argument("--scope")
    evidence_create.add_argument("--visibility", default="internal")
    evidence_create.add_argument("--output", type=Path)

    mac_init = dev_subparsers.add_parser(
        "mac-init", help="initialize a MAC payload"
    )
    mac_init.add_argument("--operation", required=True)
    mac_init.add_argument("--purpose", required=True)
    mac_init.add_argument("--subjects", required=True)
    mac_init.add_argument("--requested-outcome", required=True)
    mac_init.add_argument("--reason", required=True)
    mac_init.add_argument("--candidate-evidence", required=True)
    mac_init.add_argument("--acceptance", required=True)
    mac_init.add_argument("--item-operation")
    mac_init.add_argument("--batch-scope")
    mac_init.add_argument("--output", type=Path)

    dev_propose = dev_subparsers.add_parser(
        "propose", help="propose a candidate catalogue change in a single command"
    )
    dev_propose.add_argument("--operation", default="add", choices=("add", "change", "revoke", "move", "batch"))
    dev_propose.add_argument("--kind", default="offering", choices=("offering", "model", "vendor", "inference-service", "condition"))
    dev_propose.add_argument("--identity", required=True, help="logical identity (e.g. aws-bedrock-nova-lite)")
    dev_propose.add_argument("--purpose", required=True, help="business/technical purpose of the proposal")
    dev_propose.add_argument("--reason", required=True, help="rationale explaining why this change is needed")
    dev_propose.add_argument("--uri", required=True, help="HTTPS documentation or discovery observation URL")
    dev_propose.add_argument("--outcome", help="requested outcome summary")
    dev_propose.add_argument("--acceptance", help="acceptance check description")
    dev_propose.add_argument("--observed-at", help="UTC ISO timestamp of observation")
    dev_propose.add_argument("--output", type=Path, help="output path for the generated issue body markdown")

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
    if arguments.command == "config" and arguments.config_command == "site":
        try:
            root = arguments.root.resolve()
            load_config(root)
            document = load_yaml_mapping(root, PurePosixPath("modelo.yaml"))
            site = document["site"]
            synthetic_as_of = document["publication"]["profiles"]["synthetic"]["as_of"]
            if arguments.format == "lines":
                print(site["base_url"])
                print(site["base_path"])
                print(synthetic_as_of)
            else:
                print(json.dumps(
                    {"base_path": site["base_path"], "base_url": site["base_url"], "synthetic_as_of": synthetic_as_of},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ))
            return 0
        except (ConfigError, KeyError, TypeError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "check":
        try:
            run_trusted_check(TrustedCheckRequest(
                root=arguments.root, context=arguments.context,
                mac_metadata=arguments.mac_metadata, output=arguments.output,
            ))
            return 0
        except (ValueError, ConfigError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "control-check":
        try:
            run_trusted_control_check(TrustedControlCheckRequest(
                root=arguments.root, context=arguments.context, output=arguments.output,
            ))
            return 0
        except (ValueError, ConfigError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "github-issue":
        try:
            print(github_issue_reference(arguments.event))
            return 0
        except BuildError as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "github-control-issue":
        try:
            print(github_control_issue_reference(arguments.event))
            return 0
        except BuildError as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "github-prepare":
        try:
            prepare_github(
                root=arguments.root, event_path=arguments.event, issue_path=arguments.issue,
                validation_sha=arguments.validation_sha, validation_tree=arguments.validation_tree,
                as_of=parse_as_of(arguments.as_of), metadata_output=arguments.metadata_output,
                context_output=arguments.context_output,
            )
            return 0
        except (ValueError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "github-prepare-control":
        try:
            prepare_github_control(
                root=arguments.root, event_path=arguments.event, issue_path=arguments.issue,
                validation_sha=arguments.validation_sha, validation_tree=arguments.validation_tree,
                as_of=parse_as_of(arguments.as_of), context_output=arguments.context_output,
            )
            return 0
        except (ValueError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "github-intake":
        try:
            write_github_intake_outputs(
                event_path=arguments.event,
                issue_body_output=arguments.issue_body_output,
                comment_output=arguments.comment_output,
            )
            return 0
        except (ValueError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "gitlab-issue":
        try:
            reference = gitlab_issue_reference(arguments.event)
            print(reference)
            return 0
        except BuildError as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "gitlab-control-issue":
        try:
            reference = gitlab_control_issue_reference(arguments.event)
            print(reference)
            return 0
        except BuildError as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "gitlab-prepare":
        try:
            prepare_gitlab(
                root=arguments.root, event_path=arguments.event, issue_path=arguments.issue,
                validation_sha=arguments.validation_sha, validation_tree=arguments.validation_tree,
                as_of=parse_as_of(arguments.as_of), metadata_output=arguments.metadata_output,
                context_output=arguments.context_output,
            )
            return 0
        except (ValueError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "gitlab-prepare-control":
        try:
            prepare_gitlab_control(
                root=arguments.root, event_path=arguments.event, issue_path=arguments.issue,
                validation_sha=arguments.validation_sha, validation_tree=arguments.validation_tree,
                as_of=parse_as_of(arguments.as_of), context_output=arguments.context_output,
            )
            return 0
        except (ValueError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "platform" and arguments.platform_command == "gitlab-intake":
        try:
            write_gitlab_intake_outputs(
                event_path=arguments.event,
                issue_body_output=arguments.issue_body_output,
                comment_output=arguments.comment_output,
            )
            return 0
        except (ValueError, BuildError) as exc:
            parser.exit(2, f"modelo: {exc}\n")
    if arguments.command == "build":
        try:
            as_of = parse_as_of(arguments.as_of)
            if arguments.kind == "demo":
                if arguments.no_base_url or not arguments.base_url:
                    raise BuildError("demo build requires --base-url")
                if arguments.base_commit != arguments.source_commit:
                    raise BuildError("demo build requires base commit to equal source commit")
                if arguments.mac_metadata is not None:
                    raise BuildError("demo build does not accept --mac-metadata")
                if arguments.merge_commit or arguments.merge_tree:
                    raise BuildError("demo build does not accept merge coordinates")
                if arguments.publication_capability is not None:
                    raise BuildError("demo build fixes publication capability to public Pages")
                if arguments.profile != "synthetic":
                    raise BuildError("demo build fixes publication profile to synthetic")
                build_demo_site(DemoBuildRequest(
                    root=arguments.root, source_commit=arguments.source_commit,
                    source_tree=arguments.source_tree, as_of=as_of,
                    source_date_epoch=arguments.source_date_epoch,
                    base_url=arguments.base_url, base_path=arguments.base_path,
                    output=arguments.output,
                ))
                return 0
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
    if arguments.command == "dev":
        if arguments.dev_command == "evidence-create":
            try:
                api_options = {
                    "--provider": arguments.provider,
                    "--service": arguments.service,
                    "--operation": arguments.operation,
                    "--partition": arguments.partition,
                    "--region": arguments.region,
                    "--sanitised-parameters": arguments.sanitised_parameters,
                }
                if arguments.source_type == "first-party-read-api":
                    missing = [
                        name for name, value in api_options.items() if value is None
                    ]
                    if missing:
                        raise ValueError(
                            "first-party-read-api requires API arguments together: "
                            + ", ".join(missing)
                        )
                else:
                    supplied = [
                        name for name, value in api_options.items() if value is not None
                    ]
                    if supplied:
                        raise ValueError(
                            "documentation sources do not accept API-only arguments: "
                            + ", ".join(supplied)
                        )
                config = load_config(arguments.root.resolve())
                schemas = SchemaSet(config.root, config.paths["schemas"])
                projection = _parse_json_arg(arguments.projection, "--projection")
                scope = (
                    _parse_json_arg(arguments.scope, "--scope")
                    if arguments.scope
                    else None
                )
                sanitised_parameters = (
                    _parse_json_arg(
                        arguments.sanitised_parameters, "--sanitised-parameters"
                    )
                    if arguments.sanitised_parameters is not None
                    else None
                )
                record_arguments = dict(
                    source_type=arguments.source_type,
                    uri=arguments.uri,
                    observed_at=arguments.observed_at,
                    projection=projection,
                    schemas=schemas,
                    provider=arguments.provider,
                    service=arguments.service,
                    operation=arguments.operation,
                    partition=arguments.partition,
                    region=arguments.region,
                    retrieved_by=arguments.retrieved_by,
                    scope=scope,
                    visibility=arguments.visibility,
                )
                if arguments.sanitised_parameters is not None:
                    record_arguments["sanitised_parameters"] = sanitised_parameters
                record = create_evidence_record(**record_arguments)
                _emit_json(record, arguments.output)
                return 0
            except (ConfigError, ValueError, json.JSONDecodeError, OSError) as exc:
                parser.exit(2, f"modelo: {exc}\n")
        if arguments.dev_command == "mac-init":
            try:
                subjects = _parse_json_arg(arguments.subjects, "--subjects")
                candidate_evidence = _parse_json_arg(
                    arguments.candidate_evidence, "--candidate-evidence"
                )
                acceptance = _parse_json_arg(arguments.acceptance, "--acceptance")
                batch_scope = (
                    _parse_json_arg(arguments.batch_scope, "--batch-scope")
                    if arguments.batch_scope
                    else None
                )
                payload = init_mac_payload(
                    operation=arguments.operation,
                    purpose=arguments.purpose,
                    subjects=subjects,
                    requested_outcome=arguments.requested_outcome,
                    reason=arguments.reason,
                    candidate_evidence=candidate_evidence,
                    acceptance=acceptance,
                    item_operation=arguments.item_operation,
                    batch_scope=batch_scope,
                )
                _emit_json(payload, arguments.output)
                return 0
            except (ValueError, MacError, json.JSONDecodeError, OSError) as exc:
                parser.exit(2, f"modelo: {exc}\n")
        if arguments.dev_command == "propose":
            try:
                from datetime import datetime, timezone
                config = load_config(arguments.root.resolve())
                schemas = SchemaSet(config.root, config.paths["schemas"])
                observed_at = arguments.observed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                projection = {"identity": arguments.identity, "purpose": arguments.purpose}
                evidence_record = create_evidence_record(
                    source_type="official-provider-documentation",
                    uri=arguments.uri,
                    observed_at=observed_at,
                    projection=projection,
                    schemas=schemas,
                )
                evidence_id = evidence_record["id"]
                evidence_dir = config.root / "catalogue" / "evidence"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                evidence_path = evidence_dir / f"{evidence_id}.yaml"
                import yaml
                evidence_path.write_text(
                    yaml.dump(evidence_record, sort_keys=True, allow_unicode=True),
                    encoding="utf-8",
                )

                subjects = [{"kind": arguments.kind, "identity": arguments.identity}]
                candidate_evidence = [{"uri": arguments.uri, "observed_at": observed_at, "digest": evidence_id}]
                outcome = arguments.outcome or f"{arguments.operation.title()} candidate {arguments.kind} record"
                acceptance = [arguments.acceptance or "Record passes modelo check validation."]
                payload = init_mac_payload(
                    operation=arguments.operation,
                    purpose=arguments.purpose,
                    subjects=subjects,
                    requested_outcome=outcome,
                    reason=arguments.reason,
                    candidate_evidence=candidate_evidence,
                    acceptance=acceptance,
                )
                source_text = (
                    f"### Request type\n\n{arguments.operation}\n\n"
                    f"### Subject type\n\n{arguments.kind}\n\n"
                    f"### Subject identity\n\n{arguments.identity}\n\n"
                    f"### Purpose\n\n{arguments.purpose}\n\n"
                    f"### Requested outcome\n\n{outcome}\n\n"
                    f"### Why is this needed?\n\n{arguments.reason}\n\n"
                    f"### Supporting observations\n\n{arguments.uri} | {observed_at} | {evidence_id}\n\n"
                    f"### Acceptance checks\n\n{acceptance[0]}\n"
                )
                issue_body = _intake_issue_body(source_text, payload)
                if arguments.output is not None:
                    arguments.output.write_text(issue_body, encoding="utf-8")
                else:
                    print(issue_body, end="")
                return 0
            except (ConfigError, ValueError, MacError, OSError) as exc:
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
