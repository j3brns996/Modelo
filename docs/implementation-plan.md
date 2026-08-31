# Modelo v0.1 implementation and verification plan

Status: T8 pre-merge CI, T9 and a public synthetic Pages demo workflow are
implemented. The accepted T6 head is `8694053c3366e162e0da6991ad08729aa8c95ad5`.
Production post-merge release/receipt automation and the T10 remote sentinel,
release/receipt and mirror-restore rehearsal remain launch gates, so no
production catalogue record may merge.

## Outcome

Implement a Git-backed approval and static-publication ledger with one locked
Python toolchain. GitHub and GitLab are adapters. Modelo exposes no application
API. `npx`, Agent Skills, cloud CLIs and MCP tools are not build dependencies.

## Required clean-clone commands

```bash
uv sync --locked
uv build --offline --no-cache
uv run --locked modelo check --base <protected-base-sha> --head <head-sha> --as-of <YYYY-MM-DD>
uv run --locked modelo build --kind candidate --base-commit <BASE> --source-commit <HEAD> --source-tree <TREE> --as-of <DATE> --source-date-epoch <EPOCH> --mac-metadata <MAC_JSON_PATH> --profile synthetic --no-base-url --base-path /Modelo/ --output dist/candidate
uv run --locked modelo build --kind demo --base-commit <SOURCE> --source-commit <SOURCE> --source-tree <TREE> --as-of <DATE> --source-date-epoch <SOURCE_AUTHOR_EPOCH> --profile synthetic --base-url https://pages.example/Modelo/ --base-path /Modelo/ --output dist/pages
uv run --locked modelo build --kind final --base-commit <BASE> --source-commit <ACCEPTED_HEAD> --source-tree <ACCEPTED_TREE> --merge-commit <MERGE> --merge-tree <ACCEPTED_TREE> --as-of <DATE> --source-date-epoch <ACCEPTED_HEAD_AUTHOR_EPOCH> --mac-metadata <MAC_JSON_PATH> --profile synthetic --base-url https://pages.example/Modelo/ --base-path /Modelo/ --output dist/final
```

`uv.lock` controls runtime sync and `uv run --locked`. Tool-package creation is
the separate supported command `uv build --offline --no-cache`; its PEP 517
backend is exactly pinned as `uv_build==0.11.33` in `pyproject.toml`, alongside
the required bootstrap `uv==0.11.33`. Solution publication continues to use
`uv run --locked modelo build ...`.

The build is split logically, not into services:

| Plane | Source | Rule |
|---|---|---|
| Governed solution | `catalogue/`, `schemas/`, `modelo.yaml`, specification | Reviewed source of truth |
| Deterministic tooling | `tooling/modelo/`, `pyproject.toml`, `uv.lock` | Core validation/build has no network; a bounded adapter pre-step may read same-repository MAC metadata |
| Presentation | `site/` | Templates, content and local assets only |
| Publication | `dist/` | Generated once, tested and deployed unchanged; never committed |
| Host adapters | `.github/`, `.gitlab/` | Map platform variables and call the same CLI; contain no catalogue rules |
| Agent workflows | `.agents/skills/` | Authoring guidance only; CI may lint but never execute skill prose |

## Task graph

| ID | Deliverable and owned paths | Depends on | Acceptance evidence |
|---|---|---|---|
| T0 | Reconciled target contract, site/MAC/security contracts and repository review under `docs/`; freeze `modelo.yaml` | — | Structured files parse; contradiction checklist is closed; independent review |
| T1 | Repository/CLI foundation: `README.md`, `CONTRIBUTING.md`, `CODEOWNERS`, `.gitignore`, `.gitattributes`, `.python-version`, `pyproject.toml`, `uv.lock`, `tooling/modelo/src/modelo/{__init__,__main__,cli,config}.py` and `tests/unit/test_{cli,config}.py` | T0 | Locked sync, package/build and CLI/config smoke tests pass; `check`/`build` expose target syntax but fail closed as unavailable |
| T2 | `tooling/modelo/src/modelo/{loader,discovery,diagnostics}.py` and `tests/unit/{test_loader,test_discovery,test_diagnostics}.py` | T1 | Malicious YAML/path corpus and diagnostic snapshot tests pass |
| T3 | Core/AWS/entity/receipt schemas and schema-only fixtures under `schemas/` and `tests/fixtures/schema/` | T1 | Every structural invariant has passing and failing fixtures |
| T4 | `tooling/modelo/src/modelo/{schemas,evidence,freshness,change,validators}.py`, `tests/fixtures/semantic/` and matching `tests/unit/test_{schemas,evidence,freshness,change,validators}.py` | T2, T3, T7 | Base/head, model binding, equality, immutability, move and revoke tests pass |
| T5 | `tooling/modelo/src/modelo/{build,receipt}.py`, `tests/fixtures/build/synthetic`, build/receipt fixtures and tests | T4 | Candidate-only exact three-file output; validated MAC envelope/base-head-tree correlations; deterministic catalogue/delta bytes and receipt primitives; no provider reads |
| T6 | `tooling/modelo/src/modelo/site.py`, `site/`, `tests/fixtures/publication/` and `tests/site/` | T5, T7 | Exact manifest keys equal fixed routes/assets/data/schema inventory plus every projection-derived model/offering page; AWS Source/Destination Region view is derived from validated route/evidence bindings without browser ARN parsing; missing/extra, base-path, XSS, leakage, accessibility, history and reproducibility gates pass |
| T7 | `tooling/modelo/src/modelo/mac.py`, MAC schema/examples, GitHub/GitLab issue and change-request template directories, MAC tests | T1, T0 | Adapter fixtures round-trip to identical canonical MAC objects |
| T8 | `tooling/modelo/src/modelo/platform.py`, `.github/workflows/`, fail-closed `paths.gitlab_ci` capability probe, and `tests/contract/platform/` | T4, T6, T7 | Correlate every trusted provider input with the receipt, including current base/head/tree, provider/workflow/run/check/result and internal head/provider equalities; skipped/failed/stale or drifted checks fail closed |
| T9 | `.agents/skills/{modelo-change,modelo-review,modelo-discover}/` and static skill lint | T7, T8 | Skill commands and paths resolve; no skill is a build/runtime input |
| T10 | Remote `modelo platform capabilities`, synthetic Pages deployment, release and mirror-restore rehearsal | T1–T9 | Protection/capability report, exact artefact deployment, verified receipt and restore log |

T2, T3 and T7 may run concurrently because the table gives them disjoint paths.
All other edges are hard dependencies and later tasks run sequentially where
they extend the same package. Each task uses a separate branch/worktree and one
writer. Review agents are read-only. The integration writer alone updates the
target branch after validating each task's exact head.

`tooling/modelo/src/modelo/cli.py` and `tests/unit/test_cli.py` are narrow shared
integration paths for T5, T6 and T8. A task may change them only to expose its
already-tested command surface and must run the combined earlier-slice suite.
They contain orchestration only, never duplicate build, site or platform rules.

T1 owns the bootstrap reader for `modelo.yaml`; it validates only fields needed
to locate and run the locked tool. T2 owns the restricted loader for catalogue
and policy documents. Both enforce the common YAML safety rules, but they are
separate trust boundaries and neither may silently broaden the other. T3 owns
the complete `modelo.yaml` schema and drift fixtures.

## CI is the arbiter

Pre-merge technical acceptance is one trusted final check named
`modelo/check`. It runs with `always()`-equivalent semantics and fails if any
mandatory input is missing, skipped, neutral, cancelled, stale or failed. Its
receipt binds base SHA, exact head SHA, workflow/pipeline identity, tool and lock
digests, test result and build artefact digests.

Governance approval is separate. Agent approval is disabled until a
post-bootstrap MAC seeds the actors registry with a distinct enabled platform identity and the platform control
is explicitly enabled. An independently eligible agent may then approve a
data-only MAC only after verifying the successful trusted receipt for the exact
current base and head. It cannot be author, committer, last pusher or change
writer. Control-plane
changes—CI, tooling, schemas, locks, `modelo.yaml`, governance, publication or
skills—require a human CODEOWNER. Any new commit invalidates checks and review.

Pre-merge CI validates a deterministic candidate content artefact and records
the current base, exact head and head-tree SHA. The protected branch must remain
up to date; immediately before merge, the adapter requires the current base SHA
to equal the accepted receipt base SHA. Post-merge CI proves that the merge tree equals the accepted head
tree, builds the final merge-aware artefact once, validates it, creates a
detached receipt that hashes it, then deploys that exact final artefact without
another build. A pull request cannot possess a post-merge receipt.

T5 accepts exact base/head/tree, `as_of`, source epoch and an explicit path to
validated MAC metadata as arguments and writes exactly candidate
`site/data/{catalogue,change-delta,manifest}.json`;
the manifest hashes exactly catalogue and change delta. Receipt primitives are
library values and T8 writes the detached check receipt. T6 rebuilds that single
projection from the accepted commit and validated MAC metadata, without trusting
mutable candidate output, and writes the complete static
publication and non-recursive manifest. Its executable completeness check
requires the fixed routes/assets, `data/catalogue.json`,
`data/change-delta.json`, every schema beneath the configured schema root at
the exact source commit, and every projection-derived model/offering detail
page; missing or extra entries fail. T8 supplies trusted provider metadata
and creates the detached check receipt. Post-merge publication creates the
final receipt only after exact-tree verification. Core T5/T6 code performs no
provider read.

The T5 CLI has no ambient defaults: common required flags are `--kind`,
`--base-commit`, `--source-commit`, `--source-tree`, `--as-of`, `--source-date-epoch`,
`--mac-metadata`, `--profile`, `--base-path` and `--output`, plus exactly one of
`--base-url` or `--no-base-url`. T5 implements candidate only. T6 implements
final with required `--merge-commit`, `--merge-tree`, `--base-url`,
`--mac-metadata` and `--publication-capability`; it reconstructs the exact
candidate bytes. T8 supplies every value from trusted inputs and rejects any
receipt correlation mismatch.

`--output` is not a caller-selected alternative directory. For candidate it
must equal the configured `candidate_root` (`dist/candidate`) after safe
repository-relative resolution; T6 will require final to equal `final_root`
(`dist/final`). Traversal, absolute or symlinked paths and any output inside a
source/input tree fail. T8 passes the exact configured value for the kind.

The metadata path names one regular non-symlink strict-UTF-8 JSON object of at
most 262144 bytes. T5 reads it once from one no-follow descriptor, rejects
duplicate keys, floats, non-finite values and YAML, and compares device, inode,
mode/type, size, nanosecond mtime and nanosecond ctime before and after the
read. Trusted CI fails closed if those controls are unavailable, and a local
candidate cannot produce accepting durability without them. The metadata schema validates this one input;
it is not another CLI input.

The required explicit source epoch must equal the exact source commit author
timestamp. T5 compares and rejects mismatch; it never reads a source-epoch
environment variable or permits an arbitrary override. Final continues to use
the accepted head's author timestamp; T8 may separately record merge time only
in the release receipt.

T5 defines the shared single-writer publication state machine and exercises it
only for candidate output: exclusive fail-fast lock, same-filesystem sibling
`dist/candidate.<id>.staging` and matching `.backup`, fsynced staged validation, old-target
backup, promoted-target verification and explicit journal recovery. The two
renames are not claimed as one transaction; the target can be complete-old,
complete-new or temporarily absent, never partial. Final builds fail closed
in T5; T6 later reuses the state machine for `dist/final` and fails closed
without file/directory fsync support.

T6 owns no-JavaScript navigation, link/XSS/non-leakage and accessibility
structure. Its generator emits AWS Source Region from the route and Destination
Regions from explicit destination evidence metadata; templates and browser code
never parse ARNs. T10 owns pinned Python-controlled browser execution outside
the core build runtime and records human keyboard and screen-reader evidence.
Node, npm and `npx` are not required.

## Launch gates

### Implementation swarm

The swarm may start only when T0 is committed and independently verified:

- the exact tree and path owners are frozen in `modelo.yaml`;
- site routes, templates, publication profile and private-site fallback agree;
- the neutral MAC payload, hashes, revocation and adapter mappings agree;
- evidence equality, freshness, versioning, diagnostics and receipt rules agree;
- `openmodels.run` and other repositories have a dated adopt/adapt/reject review;
- Addy Osmani/open skill candidates have a dated trust and fit review;
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
| T0 contract reconciliation | Complete; four independent exact-head gates returned READY |
| Implementation swarm | T1–T7 accepted; T8 trusted pre-merge checks and T9 portable skills implemented in the bootstrap candidate |
| Executable validator and CI | Validator and GitHub trusted pre-merge adapter implemented; remote host-control rehearsal remains T10 |
| Static site and platform templates | Static site, issue templates, PR/MR templates and synthetic demo Pages workflow implemented; live deploy and production final publication remain T10 evidence |
| Production catalogue launch | Blocked through T10 |
