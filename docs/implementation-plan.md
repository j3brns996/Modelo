# Modelo v0.1 implementation and verification plan

Status: Slice 0 contract reconciliation. No catalogue record may merge yet.

## Outcome

Implement a Git-backed approval and static-publication ledger with one locked
Python toolchain. GitHub and GitLab are adapters. Modelo exposes no application
API. `npx`, Agent Skills, cloud CLIs and MCP tools are not build dependencies.

## Required clean-clone commands

```bash
uv sync --locked
uv run --locked modelo check --base <protected-base-sha> --head <head-sha> --as-of <YYYY-MM-DD>
uv run --locked modelo build --as-of <YYYY-MM-DD>
```

The build is split logically, not into services:

| Plane | Source | Rule |
|---|---|---|
| Governed solution | `catalogue/`, `schemas/`, `modelo.yaml`, specification | Reviewed source of truth |
| Deterministic tooling | `tooling/modelo/`, `pyproject.toml`, `uv.lock` | Implements the contract; no network during required checks |
| Presentation | `site/` | Templates, content and local assets only |
| Publication | `dist/` | Generated once, tested and deployed unchanged; never committed |
| Host adapters | `.github/`, `.gitlab/` | Map platform variables and call the same CLI; contain no catalogue rules |
| Agent workflows | `.agents/skills/` | Authoring guidance only; CI may lint but never execute skill prose |

## Task graph

| ID | Deliverable and owned paths | Depends on | Acceptance evidence |
|---|---|---|---|
| T0 | Reconciled target contract, site/MAC/security contracts and repository review under `docs/`; freeze `modelo.yaml` | — | Structured files parse; contradiction checklist is closed; independent review |
| T1 | Root metadata and Python/uv CLI skeleton: `README.md`, `CONTRIBUTING.md`, `CODEOWNERS`, `.gitignore`, `.gitattributes`, `.python-version`, `pyproject.toml`, `uv.lock`, `tooling/modelo/` | T0 | Clean clone runs locked commands offline after dependency sync; CLI smoke tests |
| T2 | Restricted loader, configuration, discovery and stable diagnostics in `tooling/modelo/`; unit tests | T1 | Malicious YAML/path corpus and diagnostic snapshot tests pass |
| T3 | Core and AWS schemas plus synthetic valid/invalid fixtures in `schemas/`, `tests/fixtures/` | T1 | Every invariant has at least one passing and failing fixture |
| T4 | Path/reference/evidence/freshness/change-aware validation | T2, T3 | Base/head, equality, immutability, move and revoke tests pass |
| T5 | Deterministic catalogue, manifest and release-receipt builder | T4 | Double build is byte-identical; digests and delta receipt verify |
| T6 | Static templates/assets/generator and site tests in `site/`, `tests/site/` | T5 | Route, base-path, XSS, leakage, accessibility and reproducibility gates pass |
| T7 | Neutral MAC schema/examples and GitHub/GitLab issue/change-request templates | T1, T0 | Adapter fixtures round-trip to identical canonical MAC objects |
| T8 | GitHub and GitLab CI adapters plus parity fixtures | T4, T6, T7 | Exact-head trusted final check; skipped/failed/stale checks fail closed |
| T9 | `.agents/skills/{modelo-change,modelo-review,modelo-discover}/` and static skill lint | T7, T8 | Skill commands and paths resolve; no skill is a build/runtime input |
| T10 | Remote platform check, synthetic Pages deployment, release and mirror-restore rehearsal | T1–T9 | Protection/capability report, exact artefact deployment, verified receipt and restore log |

T2 and T3 may run concurrently. T7 may start after T0/T1. All other edges are
hard dependencies. Each task uses a separate branch/worktree and one writer.
Review agents are read-only. The integration writer alone updates the target
branch after validating each task's exact head.

## CI is the arbiter

Pre-merge technical acceptance is one trusted final check named
`modelo/check`. It runs with `always()`-equivalent semantics and fails if any
mandatory input is missing, skipped, neutral, cancelled, stale or failed. Its
receipt binds base SHA, exact head SHA, workflow/pipeline identity, tool and lock
digests, test result and build artefact digests.

Governance approval is separate. An independent eligible agent may approve a
data-only MAC only after verifying the trusted receipt for the exact current
head. It cannot have authored, committed or modified the change. Control-plane
changes—CI, tooling, schemas, locks, `modelo.yaml`, governance, publication or
skills—require a human CODEOWNER. Any new commit invalidates checks and review.

Post-merge publication generates the neutral release receipt and deploys the
already checked artefact. A pull request cannot be required to possess a
post-merge receipt.

## Launch gates

### Implementation swarm

The swarm may start only when T0 is committed and independently verified:

- the exact tree and path owners are frozen in `modelo.yaml`;
- site routes, templates, publication profile and private-site fallback agree;
- the neutral MAC payload, hashes, revocation and adapter mappings agree;
- evidence equality, freshness, versioning, diagnostics and receipt rules agree;
- `openmodels.run` and other repositories have a dated adopt/adapt/reject review;
- Python + `uv` and the no-required-`npx` decision are explicit;
- every task above has disjoint path ownership and acceptance tests.

### Catalogue launch

No real catalogue data may merge until T10 passes. In particular, the actual
required check, protected branch, independent approval reset, synthetic Pages
and release/restore rehearsal must be verified remotely. Prose and local tests
cannot substitute for host controls.

## Current status

| Gate | Status |
|---|---|
| Six independent read-only architecture reviews | Complete |
| T0 contract reconciliation | In progress |
| Implementation swarm | Paused |
| Executable validator and CI | Missing |
| Static site and platform templates | Missing |
| Production catalogue launch | Blocked through T10 |

