# Modelo

Modelo is a Git-backed approval ledger and static publication system for an
enterprise AI model catalogue. Git provider issues initiate move/add/change
(MAC) work; pull or merge requests and trusted CI arbitrate acceptance. Modelo
does not expose an application API.

> **Implementation status:** T8 pre-merge CI, T9 and the public synthetic Pages
> workflow are implemented. The static generator, detached trusted-check
> receipt, GitHub adapter and three portable Agent Skills exist. The Pages
> workflow is a labelled demo, not a production-catalogue approval path.
> Post-merge production release/receipt automation and T10 remote
> sentinel/restore evidence remain explicit launch blockers. Agent approval is disabled.
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
requires the bootstrapped `uv 0.11.33`. `modelo build`
compiles the catalogue/static publication and deliberately has no ambient
defaults:

```bash
uv run --locked modelo build --kind candidate \
  --base-commit BASE_SHA --source-commit HEAD_SHA --source-tree HEAD_TREE_SHA \
  --as-of YYYY-MM-DD --source-date-epoch AUTHOR_UNIX_SECONDS \
  --mac-metadata /path/to/validated-mac.json --profile synthetic \
  --no-base-url --base-path /Modelo/ --output dist/candidate
```

Exactly one of `--base-url` or `--no-base-url` is required. Candidate, demo and
final builds are implemented; the trusted `modelo platform check` builds the distinct
validation site for the Git provider's exact test-merge commit.
Tool packages and solution publications are different outputs; neither creates
a service.

The Pages workflow runs the locked tests and offline package build, reads the
single global URL and synthetic snapshot-date owner with `modelo config site`,
builds `--kind demo` once to
`dist/pages/site`, archives those exact bytes and uploads them with the directly
pinned GitHub artifact action before deploying without rebuilding.
Demo builds accept only the synthetic profile, use an empty MAC delta and make
no approval, merge or release-receipt claim.

The catalogue is progressively enhanced with the locally vendored Alpine CSP
build `@alpinejs/csp==3.16.3`; standard Alpine's expression evaluator, CDNs,
npm and `npx` are not used. Search, multi-select facets, deterministic sorting,
result counts, table/grid views, shareable URL state and comparison of two to
four canonical models remain browser-only views over server-rendered records.
Only the table/grid preference is stored locally, explicit URL state wins, and
storage failure safely falls back to table view. Scripts load only on the
catalogue page.

The locked Python suite proves emitted structure, bounds, integrity and the
no-JavaScript baseline. When a host Node executable is available,
`node tests/site/catalogue-explorer.behavior.js` additionally executes the real
controller's search, facet, sort, result, URL/local-view and comparison logic
without npm or `npx`. This supplementary harness is not a build dependency and
does not replace the pinned Python-controlled browser evidence reserved for the
remote launch slice.
Every record link and the complete catalogue remain usable without JavaScript.

The candidate output is exactly `site/data/catalogue.json`,
`site/data/change-delta.json` and `site/data/manifest.json` below the selected
output. The manifest hashes exactly the first two files and never itself. T8,
not T5, writes detached `dist/receipts/check.json`.

`--mac-metadata` is an explicit path to one closed `schemas/mac-metadata.schema.json`
JSON envelope, not the JSON value and not a second schema argument. The file is
read once as a regular non-symlink, is limited to 262144 bytes, and rejects
invalid UTF-8, YAML, duplicate keys, floating-point or non-finite numbers. CI
fails closed if stable no-follow and before/after device, inode, mode/type,
size, nanosecond mtime and nanosecond ctime checks cannot be enforced; such a
local candidate cannot produce accepting durability. The envelope is created only by T8 from the same repository. It binds the open issue, exact
base/head/tree, complete neutral MAC payload and digest, and expected Git delta;
T5 performs no provider read or enrichment.

The explicit `--source-date-epoch` must equal the exact source commit's author
Unix timestamp. The build rejects mismatch and never reads an environment
override. Final continues to use the accepted head author time; merge time is
receipt metadata only.

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

`modelo check`, `modelo build` and `modelo platform check` are implemented. The
templates and local assets are under `site/`; generated demo, validation and
final sites are under `dist/pages`, `dist/validation` and `dist/final`. The
canonical synthetic Pages URL is `https://j3brns996.github.io/Modelo/`. A first
successful post-merge workflow run proves the demo deployment; it does not
complete the T10 production launch rehearsal.

Read [SPEC.md](SPEC.md), [the machine contract](docs/contract.yaml),
[the implementation plan](docs/implementation-plan.md),
[the MAC contract](docs/mac-contract.md), [the site contract](docs/site-contract.md),
[the security contract](docs/security-contract.md) and
[the launch runbook](docs/launch-runbook.md) and
[CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
