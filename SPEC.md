# Model Catalogue v0.1.0 — Specification

> Status: draft implementation contract for version `0.1.0`.
>
> This document explains the system's intent and operating model. JSON Schema,
> the validator and the CI pipeline determine whether a change is accepted.
> A disagreement between them and this document is a defect that must be fixed
> in the same pull request.
>
> **Agent entry point:** load [`docs/contract.yaml`](docs/contract.yaml) first.

---

## Quick reference

```bash
python scripts/ci_local.py                     # Run all 11 CI gates
python scripts/validate.py                     # Validate the catalogue
python scripts/validate.py --format json       # Emit structured diagnostics
python scripts/validate.py --as-of 2026-08-28  # Fix the date for tests only
python scripts/build.py                        # Development build
python scripts/build.py --release              # Release build
```

After a successful build, open `public-docs/index.html` to inspect the site.

## Objective and scope

The catalogue is a Git-backed registry of AI model offerings approved for
enterprise consumption. It answers four questions:

1. Which model is being offered?
2. Which operator supplies it, and where?
3. What does it cost?
4. Which conditions constrain its use?

A **model** records facts about a named, versioned model. An **offering** records
an operator's provision of that model in a geographical market. A model record
alone does not grant permission to consume anything; an approved offering is
required.

Version `0.1.0` supports token-priced inference. A model may be multimodal, but
an offering whose price cannot be represented as input and output tokens per
million is outside this version's scope.

## Authority

| Concern | Authority |
|---|---|
| Data shape, required fields, patterns, enums and formats | `schemas/*.schema.json` |
| Paths, references, uniqueness and freshness | Python validators |
| Gate order and release acceptance | `scripts/ci_local.py` |
| Approval, ownership and audit history | GitHub branch protection, reviews and `CODEOWNERS` |
| Human explanation | `SPEC.md` |
| Compact agent navigation | `docs/contract.yaml` |

The contract is a checked summary, not an independent source of catalogue
rules. Changes to schemas, paths, diagnostic codes or CI gates must update the
contract in the same pull request.

## Invariants

### 1. Protected-main presence is approval

Approval applies only to records beneath these paths:

```text
catalogue/models/
catalogue/offerings/
catalogue/governance/
```

A record at one of those paths on protected `main` has passed CI and review.
The pull request, reviews and resulting commit form the governance receipt.
Files elsewhere on `main`, including proposals and generated artefacts, are not
approved catalogue entries.

There are no approval flags or workflow-state fields. `lifecycle` is descriptive
vendor metadata; it is not an approval state.

### 2. Paths encode identity

```text
catalogue/models/{model_id}.yaml
catalogue/offerings/{operator_id}/{model_id}.{geo}.yaml
```

The model key is `model_id`. The offering key is
`(operator_id, model_id, geo)`. Identifiers and filename components must match.

`model_id` must identify a named model version, not a mutable family alias. If
two operators expose materially different model capabilities or context limits,
they are not silently treated as the same model.

### 3. Consumption requires an offering

A vendor, operator or model entry permits referential use only. It does not
grant consumption approval. An offering on protected `main` is the consumable
unit, subject to its recorded conditions.

Revocation removes the offering in a pull request. Git history retains the
reason, reviewer and former content while current consumers see only the live
set.

### 4. Every enforced fact is testable

Schema-enforced files contain facts that CI can check structurally or against a
defined reference. Assertions such as `dpa_agreed: true` are excluded unless the
system also defines evidence, ownership and validation semantics for them.

Free-form conditions in `0.1.0` are human-readable constraints, not executable
policy. `docs/conditions.yaml` is guidance and is deliberately outside the
authoritative catalogue-data boundary.

### 5. One fact has one owner

| Fact | Owner |
|---|---|
| Vendor identity and domicile | `catalogue/governance/vendors.yaml` |
| Operator identity and service name | `catalogue/governance/operators.yaml` |
| Freshness thresholds | `catalogue/governance/freshness.yaml` |
| Model capabilities and context window | Model file |
| Price, market and operator regions | Offering file |
| Structural rules and enums | JSON Schema |
| Path and reference rules | Python validators |

Summaries in this specification and the agent contract must not become competing
authorities.

### 6. Geography is not a residency claim

`geo` identifies the offering's catalogue market: `uk`, `eu`, `us` or `global`.
`available_regions` contains operator deployment-region identifiers. Neither
field, by itself, proves data residency, processing location or regulatory
compliance. Those claims require separately modelled evidence.

### 7. Deterministic input produces deterministic output

Given the same source tree, `SOURCE_DATE_EPOCH`, Python version and locked
dependencies, the build must be byte-identical. File discovery is sorted and
output serialisation is canonical.

## Repository layout

```text
catalogue/                         Authoritative source data
  models/                          One YAML file per named model version
  offerings/
    {operator_id}/                 One operator directory
      {model_id}.{geo}.yaml
  governance/
    vendors.yaml                   Schema-enforced vendor registry
    operators.yaml                 Schema-enforced operator registry
    freshness.yaml                 Schema-enforced freshness policy
schemas/                           JSON Schema 2020-12 documents
scripts/
  ci_local.py                      Authoritative CI gate sequence
  validate.py                      Validator CLI
  build.py                         Build CLI
  loader.py                        Restricted YAML loader
  discovery.py                     Deterministic discovery
  validators.py                    Cross-file validation
  diagnostics.py                   Structured diagnostics
tests/
  fixtures/valid/                  Miniature repositories that must pass
  fixtures/invalid/                Miniature repositories that must fail
public-docs/                       Static catalogue site
  assets/base.css
  index.html
  browse.html
  process.html
  propose.html                     Download or GitHub issue hand-off only
docs/
  contract.yaml                    Compact agent reference
  conditions.yaml                  Non-normative condition guidance
  adr/                             Architecture decision records
config/model-discovery/            Source configuration for Kiro skills
.kiro/                             Agent configuration and skills
.github/
  workflows/ci.yml                 Calls `scripts/ci_local.py`
  CODEOWNERS                       Review ownership
  ISSUE_TEMPLATE/                  Proposal issue forms
VERSION                            Plain-text semantic version
pyproject.toml                     Python project configuration
requirements.lock                  Locked CI dependencies
.yamllint.yml                      YAML lint configuration
.secrets.baseline                  Secret-scanning baseline
```

Top-level `models/`, `offerings/`, `governance/`, `data/`, `registries/` and
`operators/` are forbidden. The `catalogue/` prefix provides one review,
ownership, validation and change-detection boundary. Generated site data remains
under `public-docs/data/` and cannot be mistaken for source.

`scripts/ci_local.py` is authoritative. Convenience wrappers may call it but
must not redefine the pipeline.

## Entity contracts

The tables below are summaries. The JSON Schemas own the exact constraints.

### Model

Path: `catalogue/models/{model_id}.yaml`

| Field | Type | Required | Summary |
|---|---|---:|---|
| `id` | string | yes | Kebab-case; equals filename stem |
| `vendor` | string | yes | Key in the vendor registry |
| `name` | string | yes | Non-empty display name |
| `description` | string | yes | Non-empty description |
| `capabilities` | array | yes | Unique schema-enumerated values |
| `modalities` | array | yes | Unique schema-enumerated values |
| `context_window` | integer | yes | Minimum `1` |
| `licensing` | string | yes | Schema-enumerated value |
| `lifecycle` | string | no | `active`, `legacy` or `eol`; not approval |
| `evidence` | object | no | Capability evidence required when present |

### Offering

Path: `catalogue/offerings/{operator_id}/{model_id}.{geo}.yaml`

| Field | Type | Required | Summary |
|---|---|---:|---|
| `model_id` | string | yes | References an existing model |
| `operator_id` | string | yes | Key in the operator registry |
| `provider_model_name` | string | yes | Operator's exact model identifier |
| `geo` | string | yes | `uk`, `eu`, `us` or `global` |
| `pricing` | object | yes | Token price and evidence |
| `available_regions` | array | yes | At least one operator region identifier |
| `conditions` | array | no | Free-form strings in `0.1.0` |

### Pricing

| Field | Type | Required | Summary |
|---|---|---:|---|
| `input_per_million` | number | yes | Minimum `0`; zero is valid |
| `output_per_million` | number | yes | Minimum `0`; zero is valid |
| `currency` | string | yes | Three-letter uppercase ISO 4217 code |
| `source_url` | string | yes | Valid absolute URI |
| `checked_at` | string | yes | ISO 8601 calendar date |

### Governance registries

`catalogue/governance/vendors.yaml` contains a top-level `vendors` mapping. Each
key is a kebab-case vendor ID with a non-empty `name` and two-letter lowercase
ISO 3166-1 alpha-2 `domicile`.

`catalogue/governance/operators.yaml` contains a top-level `operators` mapping.
Each entry has `id`, `name` and `service_name`; `id` must equal its mapping key.

`catalogue/governance/freshness.yaml` contains positive integer
`pricing_days` and `capabilities_days` thresholds. All three registries reject
unknown properties.

## Restricted YAML loading

`scripts/loader.py` treats catalogue YAML as untrusted input and accepts a
deliberately small YAML subset.

| Rejected input | Diagnostic | Reason |
|---|---|---|
| Duplicate mapping key | `DUPLICATE_KEY` | Prevent silent replacement |
| Alias | `ALIAS_FOUND` | Prevent expansion and hidden sharing |
| Anchor | `ANCHOR_FOUND` | Keep documents explicit |
| Custom tag | `CUSTOM_TAG` | Exclude loader-specific object semantics |
| Multiple documents | `MULTI_DOCUMENT` | Require one record per file |
| Non-mapping root | `INVALID_ROOT` | Preserve the entity shape |
| Nesting beyond 10 levels | `EXCESSIVE_NESTING` | Bound parser work |
| Invalid YAML | `YAML_PARSE_ERROR` | Reject malformed data |
| Unreadable UTF-8 file | `FILE_READ_ERROR` | Require portable source text |

Implicit timestamp resolution is disabled, so `2026-08-28` remains a string.
Boolean resolution follows YAML 1.2 (`true` and `false` only). All file I/O uses
UTF-8 and LF line endings.

JSON Schema uses `Draft202012Validator` with `FormatChecker()` enabled. Without
the format checker, `date` and `uri` would be annotations rather than enforced
constraints.

## Validation and CI

`python scripts/ci_local.py` runs these gates sequentially and fails fast:

| # | Gate | Failure detected |
|---:|---|---|
| 1 | `lock-check` | Dependency drift |
| 2 | `lint` | Python or YAML style failure |
| 3 | `validate` | Invalid catalogue or contract drift |
| 4 | `test` | Broken validation logic |
| 5 | `site-test` | Broken static pages |
| 6 | `skill-test` | Invalid agent or skill configuration |
| 7 | `build` | Output generation failure |
| 8 | `scan` | Secrets; advisory only when tooling is unavailable |
| 9 | `reproducibility-check` | Non-deterministic output |
| 10 | `generated-output-check` | Invalid generated JSON |
| 11 | `clean-tree-check` | Build changed tracked source |

The pipeline exits `0` only when every blocking gate passes. It exits `1` for a
gate failure. `validate.py` exits `0` for success, `1` for invalid catalogue data
and `2` for invocation or repository-layout errors.

CI evaluates freshness against the current UTC date. `--as-of` exists for
reproducible tests and diagnostics; release CI must not supply a fixed date.

The scan requires both `detect-secrets` and `.secrets.baseline`. Their absence is
reported prominently but is non-blocking in `0.1.0`; repositories requiring a
hard security gate must install both.

### Dependent-check suppression

When a prerequisite cannot be loaded, validators suppress only checks that
depend on it:

- vendor references when the vendor registry is invalid;
- operator references when the operator registry is invalid;
- model references when no model records load successfully.

The prerequisite diagnostic remains an error, so validation cannot pass. This
reduces noise without failing open.

## Diagnostic contract

Every diagnostic contains `code`, `severity`, `path`, `json_pointer`, `message`
and `remediation`. Codes are stable API values; consumers must not parse message
text.

| Layer | Codes |
|---|---|
| YAML | `DUPLICATE_KEY`, `ALIAS_FOUND`, `ANCHOR_FOUND`, `CUSTOM_TAG`, `MULTI_DOCUMENT`, `INVALID_ROOT`, `EXCESSIVE_NESTING`, `YAML_PARSE_ERROR`, `FILE_READ_ERROR` |
| Schema | `SCHEMA_VIOLATION` |
| Path | `MODEL_PATH_MISMATCH`, `OFFERING_OPERATOR_MISMATCH`, `OFFERING_PATH_MISMATCH`, `OFFERING_GEO_MISMATCH`, `DUPLICATE_IDENTITY` |
| Reference | `UNKNOWN_VENDOR`, `UNKNOWN_OPERATOR`, `UNKNOWN_MODEL` |
| Evidence | `STALE_PRICING`, `STALE_EVIDENCE`, `FUTURE_DATE` |
| Build | `DIRTY_TREE`, `UNKNOWN_COMMIT` |
| System | `MISSING_SCHEMAS` |

Adding a code is additive for tolerant consumers. Renaming, removing or changing
the meaning of a code requires a format-version change and migration note.

## Evidence and freshness

Freshness thresholds come only from
`catalogue/governance/freshness.yaml`. Pricing evidence uses `pricing_days`;
capability evidence uses `capabilities_days`. Future `checked_at` values are
errors because verification cannot occur in the future.

Preferred source order is operator pricing API, official pricing page, vendor or
operator documentation, then secondary sources. This ordering guides review; it
is not machine proof of truth. Conflicting authoritative sources block a human
approval until resolved.

## Build and release

```bash
python scripts/build.py                  # Validate, then build
python scripts/build.py --skip-validation # Development output; non-releasable
python scripts/build.py --release         # Strict release build
```

| Output | Purpose | Tracked |
|---|---|---:|
| `dist/catalogue.json` | Merged catalogue | no |
| `dist/manifest.json` | Provenance and catalogue digest | no |
| `public-docs/data/catalogue.json` | Byte-copy for the site | no |
| `public-docs/data/schemas-bundle.json` | Client-side schema bundle | no |

`catalogue.json` contains `catalogue_revision`, `generated_at`, sorted `models`
and `offerings`, `project_version`, and the full `source_commit`. The manifest
records the catalogue SHA-256 but never hashes itself.

The builder serialises catalogue data once and uses `shutil.copy2()` for the site
copy. It writes `public-docs/data/` only when using the default `dist/` output,
so temporary reproducibility builds cannot alter the site tree.

Release mode requires a clean tree, a known source commit, valid data,
`SOURCE_DATE_EPOCH`, and `CATALOGUE_RELEASE_SEQ`; it rejects
`--skip-validation`. Release revisions use `YYYYMMDD.N`, while development
revisions use `dev+{seven-character-commit}`. An unknown commit produces
`dev+unknown` and is never releasable.

## GitHub proposal and approval workflow

### Issue-form path

```text
GitHub issue form -> structured proposal -> discussion -> catalogue pull request
```

The public site's `propose.html` may validate and preview YAML locally, then
download it or open a pre-filled GitHub issue. It must not hold a personal access
token or claim that a GitHub browser session authorises API calls.

### Pull-request path

```text
Branch proposal/{id} -> edit catalogue YAML -> local CI -> pull request ->
required GitHub Actions check -> CODEOWNERS review -> merge to protected main
```

Neither an issue nor a pull request grants approval. Only a qualifying merge to
protected `main` does.

## Fixture contract

Each fixture is a miniature repository using the same `catalogue/` boundary and
an `expected_diagnostics.json` file. `tests/test_fixtures.py` discovers fixture
directories automatically.

| Prefix | Layer |
|---|---|
| `yaml--` | Restricted YAML loader |
| `schema--` | JSON Schema |
| `path--` | Path and identity |
| `ref--` | Referential integrity |
| `evidence--` | Freshness and dates |

Fixtures use synthetic identifiers and `example.invalid` URLs. Real catalogue
records appear only below `catalogue/`.

## Agent boundary

The contract describes expected agent behaviour; enforcement belongs to the
runtime sandbox, GitHub permissions and branch protection. A prose deny-list is
not a security boundary.

Agents may write proposal artefacts and tests beneath `proposals/**`,
`artifacts/**` and `tests/fixtures/**`. They may inspect catalogue source and run
the documented validation, build, test and read-only Git commands. They must not
modify protected catalogue data, schemas, validators or agent policy unless a
human explicitly scopes that work.

Agents cannot approve or merge pull requests, push to protected branches,
weaken validation, invent catalogue facts, or infer revocation from the absence
of discovery evidence.

## Compatibility and deferred work

While the project is below `1.0.0`, incompatible format changes increment the
minor version. Patch releases correct behaviour without changing accepted data
shape.

Adding an optional schema field is safe only until producers begin emitting it;
older validators reject unknown properties. Adding an enum value similarly
requires consumer coordination. The release notes must describe both changes.

Targeted for `0.2.0`, not `0.1.x`:

- unit-based pricing beyond input and output tokens;
- referentially validated condition identifiers;
- structured modality and context representations;
- deletion-aware validation against base and head commits.

