# Modelo

Modelo is a Git-backed approval ledger and static publication system for an
enterprise AI model catalogue. Git provider issues initiate move/add/change
(MAC) work; pull or merge requests and trusted CI arbitrate acceptance. Modelo
does not expose an application API.

> **Implementation status:** T1, T2, T3, T4 and T7 are implemented and
> independently gated. The accepted T4 head is
> `76b6fe8f3e74a34299851b6bae9411c719154e9d`. Change-aware `modelo check`,
> schemas and MAC templates exist. Build/receipt tooling, the static site,
> trusted CI adapters, Agent Skills, Pages and release/restore rehearsal remain
> unimplemented. Agent approval is disabled.
> Do not add real catalogue data before T10 passes.

## Repository planes

| Plane | Location | Purpose |
|---|---|---|
| Governed solution | `catalogue/`, `schemas/`, `modelo.yaml` | Reviewed source of truth |
| Build tooling | `tooling/modelo/`, `pyproject.toml`, `uv.lock` | Deterministic validation and generation |
| Static presentation | `site/` | Templates, content and local assets |
| Publication | `dist/` | Generated, tested and never committed |

Agent Skills under `.agents/skills/` will guide authorship and review. They are
not executable build inputs: an agent uses a skill before invoking the ordinary
locked CLI. Required CI contains no Node, npm or `npx` step and produces the
same bytes when no skills are installed.

`uv build --offline --no-cache` packages the Python tooling. `uv.lock` governs
runtime dependency sync and `uv run --locked`; it is not a `uv build` flag.
PEP 517 build requirements are exactly pinned in `pyproject.toml`, which also
requires the bootstrapped `uv 0.11.33`. The future `modelo build`
compiles the catalogue/static publication and deliberately has no ambient
defaults:

```bash
uv run --locked modelo build --kind candidate \
  --base-commit BASE_SHA --source-commit HEAD_SHA --source-tree HEAD_TREE_SHA \
  --as-of YYYY-MM-DD --source-date-epoch AUTHOR_UNIX_SECONDS \
  --mac-metadata /path/to/validated-mac.json --profile synthetic \
  --no-base-url --base-path /Modelo/ --output dist/candidate
```

Exactly one of `--base-url` or `--no-base-url` is required. T5 accepts only
`--kind candidate`; `--kind final` and its future `--merge-commit`/
`--merge-tree` inputs fail closed until T6 supplies the static publication.
Tool packages and solution publications are different outputs; neither creates
a service.

The candidate output is exactly `site/data/catalogue.json`,
`site/data/change-delta.json` and `site/data/manifest.json` below the selected
output. The manifest hashes exactly the first two files and never itself. T8,
not T5, writes detached `dist/receipts/check.json`.

`--mac-metadata` is an explicit path to one closed `schemas/mac-metadata.schema.json`
JSON envelope, not the JSON value and not a second schema argument. The file is
read once as a regular non-symlink, is limited to 262144 bytes, and rejects
invalid UTF-8, YAML, duplicate keys, floating-point or non-finite numbers. CI
fails closed if stable no-follow and before/after file identity checks cannot
be enforced. The envelope is created only by T8 from the same repository. It binds the open issue, exact
base/head/tree, complete neutral MAC payload and digest, and expected Git delta;
T5 performs no provider read or enrichment.

## Clean-clone smoke test

Prerequisites are Git, Python `3.12.13` and `uv 0.11.33`.

```bash
uv sync --locked
uv build --offline --no-cache
uv run --locked modelo --version
uv run --locked modelo --help
uv run --locked modelo check --help
uv run --locked modelo build --help
```

`modelo check` is implemented. `modelo build` still exits with status 2 until
T5/T6 land. The static site and its templates are specified under `site/` but
not implemented or deployed; `site.base_url` remains unset.

Read [SPEC.md](SPEC.md), [the machine contract](docs/contract.yaml),
[the implementation plan](docs/implementation-plan.md),
[the MAC contract](docs/mac-contract.md), [the site contract](docs/site-contract.md),
[the security contract](docs/security-contract.md) and
[CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
