# Modelo v1 implementation plan and execution log

Engineering issue: [#91](https://github.com/j3brns996/Modelo/issues/91).
Working branch: `v1-simplification`, initially based on PR #90 at `ae5962a`.
Status: implementation in progress. This section is the current execution plan;
the bootstrap record below is historical evidence, not a second work queue.

Completion here means the scoped v1 engineering work is verified and merged.
It does not mean a 1.0 release or production launch: those require the remaining
remote capability, publication and human T10 evidence. Keep the current version
until its release criteria are demonstrated.

## Execution prompt

Plan and implement a pragmatic simplification through v1. Do the work, use
independent agents and continue through tests, review, PRs and trusted CI.
Preserve existing entity types and filename-enforced identities. No new entity
types, generic metadata maps, speculative wrappers or compatibility machinery.
Apply Ponytail: question the need, reuse existing code, prefer the standard
library and native host facilities, then write the minimum complete solution.

No technical debt: no deferred defects, temporary workarounds, placeholder
implementations, disabled checks or symptom-only patches. Trace every affected
caller and fix the root cause. Keep necessary validation, security,
accessibility, evidence integrity and approval controls. Exclude optional future
capabilities without scaffolding them. Keep host-specific concerns in adapters;
requesters submit through Git-host issues/forms, not a Modelo application API.

Before each change, identify its radius: code, callers, paths, schemas, records,
commands, documentation, generated artifacts, CI and consumers. State acceptance
criteria, compatibility and rollback. Define proof before implementation; show
defects failing first, then run focused and required broader checks. Parse
structured edits, read back the exact diff and test affected documentation.

Assess every specification for necessary and testable requirements, one
authoritative definition, consistent identities and boundaries, implementation
traceability, explicit failure behaviour and claims supported by evidence.
Separate executable tests from architectural judgment. NIST mapping describes
supported outcomes; it does not mandate Modelo's implementation mechanisms.

Use one writer per branch/worktree. Delegate bounded read-only research and
independent architecture, correctness and documentation reviews. Fix blocking
findings and repeat affected verification. Record exact tested commits and
distinguish assumptions, observations and external dependencies. Preserve
unrelated work and clean task-owned resources. Do not claim completion while
required work or blocking conflicts remain.

## Authority and conflict register

On 2026-09-07 the user explicitly authorised merging test-passing PRs through
v1. This session instruction overrides the general agent no-merge instruction
for this work. It does not authorise bypassing required host controls, fabricating
approvals or accepting stale CI. Production catalogue records remain prohibited
until remote T10 passes. A blocked host approval remains an external blocker.

| Conflict | Sources | Resolution |
|---|---|---|
| Merge authority | AGENTS.md and maintainer skill prohibit agent merges; user grants merges through v1 | Follow explicit session authority after current-head checks and independent review; no bypass |
| Deliberate shortcuts | Ponytail permits marked shortcuts; user forbids technical debt | User's zero-debt rule wins; no shortcut exceptions introduced |
| Existing plan filename | Config references lowercase historical plan; user requests IMPLEMENTATION-PLAN.MD | Case-rename one file and update references; retain bootstrap evidence below |
| Lint acceptance | Original checkout has advisory, unpinned local lint instructions; user requires functioning local/CI tools | Preserve original edits; implement pinned blocking gates in this worktree |
| UBS name | User calls it ultimate bug squasher; official repository is Ultimate Bug Scanner | Integrate Dicklesworthstone/ultimate_bug_scanner at a verified fixed revision |
| Apparent GitLab readiness | Pipeline scaffold looks runnable; launch documents say activation is unavailable | Replace misleading behaviour with an explicit activation boundary and regression tests |
| Specification promises | Reservation, scanning and command claims exceed inspected implementation | Reconcile each claim with executable proof; no silent weakening |

## Work breakdown and acceptance

| Package | Work and change radius | Dependencies | Required proof | Status |
|---|---|---|---|---|
| W0: authority and plan | Instructions, this plan, configuration path and documentation links | None | Conflict dispositions; exact-case links resolve | Implemented; focused docs checks pass |
| W1: baseline | Main and PR #90 state, existing tests, schemas, CLI and publication flow | W0 | Baseline failures distinguished from regressions; source commit recorded | In progress |
| W2: architecture | All specifications, config contracts, schemas, agent rules and workflow claims | W1 | Every document assessed; findings classified retain/clarify/consolidate/remove/implement/decision | Coverage recorded below; final integrated tests pending |
| W3: canonical contract | Schema guide, entity ledger, decision links, source schemas and published bundle | W2 | Keys/paths/profile agree; negative filename/reference/history tests; no entity additions | Pending |
| W4: quality tools | pyproject.toml, uv.lock, local_ci.py, CI, lint configuration and contributor commands | W1 | Pinned yamllint, Ruff and UBS run locally and remotely; real failure and clean controls; incomplete summaries rejected | Local Linux tool and control tests pass; remote pending |
| W5: workflow | Git-host adapters, MAC documentation, CI acceptance and request templates | W2 | Stale head, invalid input, failed/missing checks and unsupported host activation rejected | Pending |
| W6: publication | Build/receipt code, configuration, security/site contracts and launch runbook | W2, W5 | Named purpose for retained mechanisms; failure tests before any removal; no false production-readiness claim | Assessing retained guarantees |
| W7: documentation | README, docs index, schema guide, site templates, published agent/form/schema artifacts | W3-W6 | Commands, links, positive/negative examples and nondefault base paths exercised | Pending |
| W8: integration | Full tests, 5,000-entity workload, package/site builds and independent reviews | W3-W7 | Results tied to exact commit; trusted CI; no blocking findings | Pending |

Deliver small PRs by dependency: plan/contract reconciliation; blocking quality
toolchain; workflow/publication corrections and final integration. Adjust the
split only when shared-file or trusted-runner dependencies require it, and log
the reason. Do not merge mixed catalogue and control-plane changes.

Implementation uses one control-plane PR for quality gates and specification
corrections because the new executable documentation checks must land with the
corrected sources, and the first formatter baseline touches the same Python
files. Formatting is mechanical; substantive changes are the shared Git timeout,
quality gate, configured proposal link and explicit inactive GitLab pipeline.

For each package use a step card: problem, intended behaviour, affected paths
and callers, smallest solution, acceptance tests, compatibility and rollback.
Then implement rather than stopping at the card. Roll back code/config changes
through a reviewed revert; never rewrite merged evidence or approvals.

## Local and CI toolchain acceptance

Use locked Python/uv dependencies for yamllint and Ruff. Pin UBS and its required
scanner dependencies; inspect the official source before installation. Do not
run a floating curl-to-shell installer, enable automatic updates, edit user
agent configuration or install hooks as a side effect.

Local and CI commands must invoke the same gates. Demonstrate each tool detects
an appropriate harmless failing fixture and accepts its corrected counterpart.
For UBS, prove the intended language scanners executed, covered the selected
files and completed. Exit zero alone is insufficient for an empty or partial
scan. Distinguish real defects, scanner failures and false positives; do not
hide findings with blanket exclusions or suppressions. Use Linux/WSL where
required and document the actual supported execution environment.

## Initial architecture findings and disposition

- Consolidate stale profile 0.2 guidance with the 0.3 source schemas and required
  offering scope/accountability. Keep diagrams about keys and relationships.
- Correct evidence wording: externally sourced facts need evidence; policy
  fields and internal references follow their declared rules.
- Replace the escaped Markdown proposal link with an existing template link
  using the configured route; test a nondefault base path.
- Reconcile local-font behaviour, obsolete demo counts and ambiguous ADR
  numbering without breaking existing published links.
- Distinguish a computed idempotency key from cross-request reservation; test
  the actual boundary. Clarify which stages belong to modelo check, local
  verification and trusted remote acceptance.
- Do not represent the absent capabilities command or incomplete GitLab
  publication pipeline as an available operational control.
- Retain evidence hashes and detached receipts unless a concrete replacement
  preserves their approval/source/artifact binding. Native artifact metadata
  alone does not prove business approval.
- Assess local crash recovery against its actual filesystem contract. Native
  deployment is not a substitute until that contract and failure tests change.

## Evidence and progress log

| Date | Work | Evidence and limits |
|---|---|---|
| 2026-09-07 | Baseline branch and isolation | PR #90 remains open at ae5962a; prior trusted run 34064099254 passed 438 tests. New worktree Modelo-v1 preserves original CONTRIBUTING.md/uv.lock/advisory yamllint edits. These are prior results, not acceptance of new changes. |
| 2026-09-07 | Independent architecture review | CTO reviewed ae5962a read-only; findings above include misleading GitLab readiness, duplicate contract prose and unsupported reservation/scanning claims. No approval issued. |
| 2026-09-07 | Independent documentation review | Reviewer found stale schema guide, policy-evidence wording and escaped proposal link. Existing selected-host template/schema bundling was consistent on inspected source. No new tests run by reviewer. |
| 2026-09-07 | UBS identification | Official GitHub repository identified; fixed revision, dependencies and failure semantics under investigation. Not installed or accepted yet. |
| 2026-09-07 | PR #90 merged | Exact previously tested head ae5962a was squash-merged as f5fda188 under explicit user authority. GitHub rejected merge-commit mode; squash used without bypass. |
| 2026-09-07 | Failure reproduction | New tests failed on profile 0.2 guidance, runnable-looking GitLab Pages and missing root-deployment proposal link before corrections. |
| 2026-09-07 | Local verification | 21 documentation tests pass; 11 workflow/site/timeout tests pass on Linux; 4 actual quality-tool and bad/corrected-input tests pass on Linux. Windows broader baseline has old system uv and lacks O_NOFOLLOW, so full verification uses locked Ubuntu/WSL. |
| 2026-09-07 | UBS disposition | Initial 24 Python/2 JS scan returned 19 critical and 162 warning heuristic counts. Independent category/source review found static-template, public-digest, denylist-key and configured-URL false positives; Path division and exact bool/int checks remain correct. Missing local subprocess deadlines were corrected in shared helpers with error-propagation tests. Raw reports remain visible; not a clean-scan claim. |
| 2026-09-07 | Toolchain pins | Ruff 0.16.6, yamllint 1.38.0, ast-grep 0.40.1 and Linux ripgrep 15.1.0 are locked. UBS source is pinned at 0af10c926d6fbb14a1f589326d75c03f610207f0. System Bash/Git/jq/coreutils are prerequisites. No hooks or agent configuration changed. |

## Specification coverage and retained boundaries

| Family | Assessed sources | Disposition and proof |
|---|---|---|
| Authority | AGENTS.md, CONTRIBUTING.md, CODEOWNERS, SECURITY.md, four portable skills | Retain authority boundaries; session merge exception recorded; contributor commands tested |
| Global configuration | SPEC.md, modelo.yaml, docs/contract.yaml, modelo.schema.json | Clarify command ownership and paths; existing config/schema fixtures plus documentation checks |
| Entity schemas | common, model, model-release, offering, vendor/service registries, evidence, condition, freshness-policy | Retain acceptance checks; consolidate guidance; profile, identity/history and 5,000-entity regressions |
| Provider contracts | Three provider schemas and docs/providers files | AWS semantic support retained; Azure/GCP remain explicitly unsupported; no inferred provider facts |
| Proposals | MAC schemas, mac-contract.md, selected-host templates | Retain payload/head correlation; retire unsupported cross-issue reservation promise; existing round-trip/idempotency/stale-base tests |
| Publication | catalogue-output/build-manifest schemas, site-contract.md | Retain same-source bundle and manifest; output/link/CSP/fixture tests |
| Receipts and trust | Check/control/release receipts and trusted contexts | Retain approval/source/artifact bindings and existing negative fixtures; no production orchestration claim |
| Host workflows | Three GitHub workflows, GitLab pipeline | Protected runner retained; inactive GitLab script is executed by a negative test; remote settings still need T10 |
| Toolchain | pyproject.toml, uv.lock, Python pin, gitattributes | Real tools run in the shared test inventory; bad/corrected controls; no machine-level Ruff inheritance |
| Decisions and explanations | All ADRs, schema guide, entity ledger, ELI21 | Remove duplicate field table; distinguish offering policy from external application-use context; preserve existing decision URLs |
| Operating status | This plan, launch-runbook.md, maturity profile | Distinguish engineering completion, synthetic evidence and production launch; retain launch gates |
| NIST | Mapping schema/YAML, method-equivalence and embedded-AI guidance | Retain bounded contribution/non-certification claims; no new technical mandate or catalogue entity |
| Human and agent surfaces | README, docs index, authoring, quickstart, site content/templates | Configured link regression and existing same-source host-form/schema-bundle checks |
| Historical reviews | docs/reviews files and bootstrap section below | Preserve as dated evidence, not new normative requirements |

The inventory covers all 24 schema files and the normative document families.
Executable fixtures validate machine rules; independent review assesses purpose
and proportionality. Neither substitutes for remote or operating evidence.

## Historical bootstrap record

The following v0.1 record is retained for traceability. Its task statuses and
commands describe the bootstrap context; current execution is governed above.

Status: historical bootstrap delivery record and current control posture. T8
pre-merge CI, T9 and the public synthetic Pages demo workflow are implemented.
The accepted T6 head is `8694053c3366e162e0da6991ad08729aa8c95ad5`.
Production post-merge release/receipt automation and the T10 remote sentinel,
release/receipt and mirror-restore rehearsal remain launch gates, so no
production catalogue record may merge.

This document records completed delivery history and the current launch posture.
It is not execution authority for new work. For current changes, follow
`docs/contract.yaml` and the linked issue(s) instead of this plan.

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
uv run --locked modelo build --kind demo --base-commit <SOURCE> --source-commit <SOURCE> --source-tree <TREE> --as-of <CONFIGURED_SYNTHETIC_AS_OF> --source-date-epoch <SOURCE_AUTHOR_EPOCH> --profile synthetic --base-url https://pages.example/Modelo/ --base-path /Modelo/ --output dist/pages
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
| T6 | `tooling/modelo/src/modelo/site.py`, `site/` and `tests/site/` | T5, T7 | Exact manifest keys equal fixed routes/assets/data/schema inventory plus every projection-derived model/offering page; AWS Source/Destination Region view is derived from validated route/evidence bindings without browser ARN parsing; missing/extra, base-path, XSS, leakage, accessibility, history and reproducibility gates pass |
| T6-UX | Local Alpine CSP runtime, catalogue explorer and a second synthetic model under `site/`, `tooling/modelo/src/modelo/site.py` and `tests/fixtures/build/synthetic/` | T6, synthetic Pages demo | Locked tests prove runtime/licence integrity, emitted bounds and no-JavaScript completeness; the repeatable zero-package Node harness executes controller logic; controlled-browser and human evidence remain T10 |
| T6-UX2 | Responsive product shell, guided landing journey, card-first explorer, structured entity/reference components, allowlisted font CDN and richer content-addressed synthetic facts | T6-UX, public synthetic demo | Shared-shell/static gates, complete facets, comparison/context behavior, CSP font allowlist, deterministic rebuilds and desktop/mobile visual QA pass |
| T7 | `tooling/modelo/src/modelo/mac.py`, MAC schema/examples, GitHub/GitLab issue and change-request template directories, MAC tests | T1, T0 | Adapter fixtures round-trip to identical canonical MAC objects |
| T8 | `tooling/modelo/src/modelo/{platform,local_ci}.py`, `.github/workflows/`, fail-closed `paths.gitlab_ci` capability probe, and `tests/contract/platform/` | T4, T6, T7 | Correlate every trusted provider input with the receipt; share fixed advisory/local gates through protected tooling; run protected-base and proposed-head control verification in parallel; skipped/failed/stale or drifted checks fail closed |
| T9 | `.agents/skills/{modelo-change,modelo-review,modelo-discover,modelo-maintain}/` and static skill lint | T7, T8 | Skill commands and paths resolve; no skill is a build/runtime input |
| T10 | Remote `modelo platform capabilities`, synthetic Pages deployment, release and mirror-restore rehearsal | T1–T9 | Protection/capability report, exact artefact deployment, verified receipt and restore log |

T2, T3 and T7 may run concurrently because the table gives them disjoint paths.
All other edges are hard dependencies and later tasks run sequentially where
they extend the same package. Each task uses a separate branch/worktree and one
writer. Review agents are read-only. The integration writer alone updates the
target branch after validating each task's exact head.

The task graph is retained as delivery evidence. It describes the bootstrap
work that was completed, not permission to start new changes.

Later maintenance added local `mac-init` and `evidence-create` authoring
conveniences and an interactive proposal draft. Issue #58 reconciles their
documentation and runtime boundaries: the catalogue owns Alpine-backed
exploration, while the proposal page owns a small independent vanilla script.
These additions do not create a new accepting authority or complete T10.

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

T6-UX uses the exact locally published `@alpinejs/csp==3.16.3` bytes, not the
standard Alpine build, because the site forbids `unsafe-eval`. Alpine's and the
bundled Vue reactivity dependency's MIT notices are published beside the runtime.
Explorer state is bounded and allowlisted before
it reaches search, filters, URL state or canonical-model comparison.
Only the catalogue route loads the explorer and Alpine runtime. The proposal
route loads only its dedicated vanilla script for an add/change issue-field
draft; all five configured operation links remain static and no-JavaScript
usable. Every other route loads no runtime.
The locked suite proves structure and bounds. The supplementary command
`node tests/site/catalogue-explorer.behavior.js` executes controller logic when
Node already exists, but remains outside the locked build and cannot replace
T10 browser, keyboard or screen-reader evidence.

Every CI checkout that runs the test suite or generates change history fetches
complete reachable history. A shallow checkout is an explicit failure because
the tests create repository fixtures from that checkout and immutable-condition
and `/changes/` validation require first-parent history.

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
| Implementation swarm | T1–T7 accepted; T8 trusted pre-merge checks and T9 portable skills are part of the bootstrap delivery history |
| Executable validator and CI | Validator and GitHub trusted pre-merge adapter implemented; remote host-control rehearsal remains T10 |
| Static site and platform templates | Synthetic Pages demo and functional explorer are live; the product-quality site experience v2 was delivered in the closed issue #37 history; production final publication remains T10 evidence |
| Local authoring conveniences | Neutral MAC and evidence-envelope drafting plus configured proposal links are implemented; outputs remain author-controlled and non-accepting |
| Production catalogue launch | Blocked through T10 |

## Backlog: embedded AI in vertical products

[Issue 78](https://github.com/j3brns996/Modelo/issues/78) tracks external inventory
coverage and links for embedded AI. Owner: j3brns. Target: post-T10 scope review
by 2026-12-05. Completion requires reviewed coverage criteria, a minimal reference
contract, and tests for known, unknown, stale, and revoked bindings. Modelo does
not acquire an application inventory. NIST scope is not an exemption from review.
