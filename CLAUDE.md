# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Modelo is a Git-backed approval ledger and static publication system for an
enterprise AI model catalogue. It has **no application API**: every change is
proposed as a Git-provider issue (a move/add/change/revoke, "MAC"), submitted
as a pull/merge request on a topic branch, and arbitrated by CI. The
repository builds a deterministic static site from validated catalogue
records; it does not run a service.

Implementation status matters here: only pre-merge CI (T8/T9) and the public
synthetic Pages workflow exist. Post-merge release/receipt automation and the
T10 remote sentinel/restore rehearsal are not implemented, and there is no
`catalogue/` directory yet — do not add real catalogue records or assume
production release automation exists.

## Commands

Toolchain is pinned: Python `3.12.13`, `uv 0.11.33` (enforced by
`pyproject.toml`'s `[tool.uv] required-version`).

```bash
uv sync --locked                                   # install locked deps
uv run --locked pytest -q                          # full test suite
uv run --locked pytest tests/unit/test_build.py -q                       # one file
uv run --locked pytest tests/unit/test_build.py::ClassName::test_method  # one test
uv run --locked python -m unittest discover -s tests/unit -v             # unittest runner (CONTRIBUTING.md's baseline)
uv build --offline --no-cache                      # package tooling (must stay network-free)
uv run --locked modelo --version
uv run --locked modelo --help
```

Tests are written as `unittest.TestCase` classes under `tests/unit/`,
`tests/contract/` and `tests/site/`, and both `pytest` and `unittest discover`
run them. There is no separate lint command wired up beyond the schema/test
gates below.

`modelo check` validates a committed change (schema + semantic rules) for an
exact base/head pair:

```bash
uv run --locked modelo check --base BASE_SHA --head HEAD_SHA --as-of YYYY-MM-DD
```

`modelo build` compiles the catalogue/static site and has no ambient
defaults — every coordinate is explicit:

```bash
uv run --locked modelo build --kind candidate \
  --base-commit BASE_SHA --source-commit HEAD_SHA --source-tree HEAD_TREE_SHA \
  --as-of YYYY-MM-DD --source-date-epoch AUTHOR_UNIX_SECONDS \
  --mac-metadata /path/to/validated-mac.json --profile synthetic \
  --no-base-url --base-path /Modelo/ --output dist/candidate
```

`--kind` is one of `candidate` (pre-merge), `demo` (public synthetic Pages,
`--profile synthetic` only, requires `--base-commit == --source-commit`, no
`--mac-metadata`) or `final` (post-merge, requires `--merge-commit`,
`--merge-tree`, `--mac-metadata` and `--publication-capability`). Exactly one
of `--base-url`/`--no-base-url` is required.

Optional supplementary JS behaviour test (only runs if a host Node is
present, not a build dependency): `node tests/site/catalogue-explorer.behavior.js`.

Never commit `dist/` — it is generated, disposable output.

## Architecture

### Repository planes (from README.md)

| Plane | Location | Purpose |
|---|---|---|
| Governed solution | `catalogue/`, `schemas/`, `modelo.yaml` | Reviewed source of truth |
| Build tooling | `tooling/modelo/`, `pyproject.toml`, `uv.lock` | Deterministic validation and generation |
| Static presentation | `site/` | Templates, content and local assets |
| Publication | `dist/` | Generated, tested and never committed |

`modelo.yaml` is the single source of truth for every repository path
(`paths.*`) and repository-adapter config; resolve paths from it rather than
hardcoding directory names — this is enforced by the `modelo-change` skill's
own procedure.

### The `tooling/modelo/src/modelo/` package

- `cli.py` — argparse entry point (`check`, `build`, `recover`, `config site`,
  `platform check|control-check|github-issue|github-control-issue|github-prepare|github-prepare-control`).
  Business logic is never in the CLI module itself.
- `config.py` / `loader.py` — load and validate `modelo.yaml` and YAML
  documents against the JSON Schemas in `schemas/`.
- `schemas.py` — `SchemaSet`, the compiled-schema registry used by validators
  and builders.
- `mac.py` — validates a MAC neutral payload (schema in
  `schemas/mac.schema.json`; see `docs/mac-contract.md`).
- `change.py` — Git plumbing: resolving commits, computing changed paths,
  requiring ancestor relationships, snapshotting a tree.
- `validators.py` — `check_repository`: the full schema + semantic gate run by
  `modelo check` and reused inside builds before publication.
- `evidence.py` — canonical JSON serialisation and content-addressed evidence
  IDs; evidence records are terminal/immutable once merged (a refresh creates
  a new record, it never edits proof behind an existing evidence ID).
- `receipt.py` — canonical byte serialisation, the catalogue projection, the
  change delta, and manifest-entry hashing used by both candidate and final
  builds.
- `build.py` — `build_candidate` / `recover_candidate`: the deterministic,
  atomic, single-writer publisher (temp-dir build + rename, with crash
  recovery). Candidate output is exactly `data/catalogue.json`,
  `data/change-delta.json` and `data/manifest.json` (which hashes only those
  two files, never itself).
- `site.py` — `build_demo_site` / `build_final_site`: static HTML generation
  over `site/templates` + `site/assets` + `site/content`.
- `platform.py` — trusted Git-provider adapter operations: assembling the
  detached `check.json` / `control-check.json` receipts for the exact CI head.
- `github_adapter.py` — extracts the linked MAC/control issue reference from a
  GitHub webhook event and prepares trusted build inputs from it. This is the
  only place GitHub-specific shapes are allowed to leak into the tool; core
  records/schemas/validation stay host-agnostic (GitHub and GitLab are both
  adapters, see `.gitlab-ci.yml` vs `.github/workflows/modelo.yml`).
- `discovery.py`, `freshness.py` — provider read/discovery helpers and
  freshness-policy date handling (`--as-of` parsing).
- `diagnostics.py` — the `Diagnostic` type and JSON/text rendering shared by
  `modelo check`'s two output formats.

### Trust boundary in CI (`.github/workflows/modelo.yml`)

The pre-merge check is split to keep untrusted PR content from running with
trusted credentials or producing the accepted receipt:

1. **classify** — fetches the PR diff with an ephemeral read token, rejects a
   PR that mixes `catalogue/*` changes with control-plane changes (they must
   be separate PRs), and labels the change `mac-data` or `control-plane`.
2. **proposed-control** — for `control-plane` changes only, checks out the
   *proposed* head and runs its tests/build in isolation (no receipt is
   produced from this job).
3. **trusted-check** — checks out the *base* commit's tooling plus a
   provider-computed test-merge ref, runs the locked tests/build from that
   trusted checkout, fetches the linked issue via the GitHub API, and (for
   `mac-data`) builds the validation site and detached
   `dist/receipts/check.json`, or (for `control-plane`) the
   `control-check.json` receipt. Only this trusted, exact-head result is
   acceptance evidence — nothing computed from the PR branch's own code is
   trusted.

### Governance model (see `AGENTS.md`, `docs/mac-contract.md`, `docs/contract.yaml`)

- Every catalogue change starts from a linked MAC issue and lands via a
  pull/merge request on a topic branch; the protected default branch is never
  written directly.
- Agent approval, where it exists, is allowlisted only to
  `catalogue/models/**`, `catalogue/offerings/**` and `catalogue/evidence/**`,
  only after trusted CI succeeds for the exact current head, and never by an
  agent that authored/committed/modified the change. Any new commit
  invalidates prior checks and approvals. Every other path requires human
  CODEOWNER review.
- A semantic move is add-new plus revoke-old — never a cosmetic rename.
- Catalogue facts must trace to admissible evidence (first-party read APIs,
  then official provider/vendor docs); provider availability is an
  observation, not enterprise approval. Never invent or infer facts from
  names or marketing.

### `.agents/skills/`

Three portable Agent Skills — `modelo-change`, `modelo-discover`,
`modelo-review` — describe the authoring/review workflow for agents. They are
guidance only, never build inputs or CI evidence; `AGENTS.md`, `modelo.yaml`
and the executable schemas/validators always override them.

### Site (`site/`)

Static HTML/CSS/JS with no build step and no Node/npm/npx requirement. The
only JavaScript dependency is a locally vendored, checksum-pinned Alpine CSP
build (`@alpinejs/csp==3.16.3`) — the standard expression-evaluating Alpine
build is forbidden by the site's CSP. See `docs/site-contract.md` for the
exact generated-output boundaries between `dist/candidate`, `dist/pages`,
`dist/final` and `dist/receipts`.

### Reading before changing a path

`docs/contract.yaml` is the machine contract; `SPEC.md` is the human
specification. Read the owning schema/contract doc before touching a path —
`docs/mac-contract.md` (MAC payloads), `docs/site-contract.md` (site
generation), `docs/security-contract.md` (trust boundary/security), and
`docs/implementation-plan.md`/`docs/launch-runbook.md` for sequencing and
launch gating (T-numbered milestones referenced throughout the docs and
commit history).
