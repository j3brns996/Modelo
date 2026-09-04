# CTO Review - GitLab Host Adapter Migration (2026-09-04)

> Status: Approved for implementation and remote host rehearsal.

## Verdict

Proceed with the implementation and verification of the **GitLab Host Adapter**. 

Switching the host adapter from GitHub to GitLab is a zero-breakage platform configuration change that adheres strictly to **Invariant 6** (*"Platform semantics stay outside the kernel"*). The core catalogue records, JSON Schemas, content-addressed evidence envelopes, and deterministic static-site generator remain 100% untouched.

---

## Documented External Conditions & Constraints

Before the GitLab adapter can arbitrate merges or publish static Pages in production, the following remote external conditions must be satisfied and verified:

### 1. External Pipeline Security (Protected Pipeline Execution)
* **Condition**: The remote GitLab repository or group MUST enforce CI pipeline execution via a **GitLab Pipeline Execution Policy** (or protected branch policy).
* **Rationale**: Change request authors must be strictly prevented from modifying or overriding `.gitlab-ci.yml` in their merge request branches to bypass technical acceptance checks.
* **Fail-Closed Rule**: If remote pipeline execution cannot be independently verified, `modelo platform capabilities` must report the repository incapable.

### 2. Exact-Head Pre-Merge Validation (`modelo/check`)
* **Condition**: Pre-merge technical acceptance MUST execute `modelo check` against the exact `CI_MERGE_REQUEST_DIFF_BASE_SHA` and `CI_COMMIT_SHA`.
* **Rationale**: Any uncommitted changes, stale base SHAs, or commit head drift invalidate the validation receipt.

### 3. Independent Approval & Review Reset
* **Condition**: GitLab project settings MUST enforce approval reset on push (`stale_review_dismissal: true`).
* **Rationale**: Any new commit pushed to an open Merge Request invalidates prior approvals and requires fresh CI execution.

### 4. Zero Core Schema & Invariant Drift
* **Condition**: Core schemas under `schemas/` MUST NOT be altered for platform-specific reasons.
* **Verification**: All schemas (`mac.schema.json`, `check-receipt.schema.json`, `release-receipt.schema.json`, `modelo.schema.json`) already carry valid `"provider": {"enum": ["github", "gitlab"]}` definitions.

---

## Implementation Scope & Deliverables

| Deliverable | File Path | Responsibilities |
|---|---|---|
| **GitLab Adapter** | `tooling/modelo/src/modelo/gitlab_adapter.py` | MR description parsing, guided issue payload compilation (`compile_gitlab_guided_issue`), and context assembly (`prepare_gitlab`, `prepare_gitlab_control`). |
| **CLI Subcommands** | `tooling/modelo/src/modelo/cli.py` | Expose `platform gitlab-issue`, `platform gitlab-control-issue`, `platform gitlab-prepare`, and `platform gitlab-prepare-control`. |
| **GitLab CI Pipeline** | `.gitlab-ci.yml` | Replace `exit 1` probe with active `modelo/check` validation and `pages` static site deployment. |
| **Unit Tests** | `tests/unit/test_gitlab_intake.py` | Complete unit test suite covering GitLab URL regex matching, guided issue compilation, and context assembly. |
| **Contract Tests** | `tests/contract/platform/test_workflows.py` | Contract tests asserting `.gitlab-ci.yml` rules, pin integrity, and offline packaging. |

---

## Verification Strategy

1. **Unit & Contract Suite**: Execute `uv run pytest` across all unit, site, and contract tests.
2. **Schema & Config Integrity**: Execute `uv run --locked modelo check --base BASE --head HEAD --as-of DATE`.
3. **Determinism Verification**: Confirm that identical MAC issue inputs produce byte-identical candidate outputs under both GitHub and GitLab adapters.
