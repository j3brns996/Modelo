# ADR 0001: Git is the approval ledger, not live inventory

- Status: proposed
- Date: 2026-08-30
- Decision issue: GitHub issue 1

## Context

Modelo expects roughly 10–20 approved catalogue changes per working day. It
needs evidence, review, a durable change receipt and static publication, but it
does not require live transactional queries or automatic runtime enforcement.
Cloud APIs change independently and may be queried much more frequently.

## Decision

Use the Git protected default branch as the v0.1.0 approval ledger. Use issues
for MAC intake, change requests for review, CI for validation, Pages for static
publication and protected releases for portable receipts.

The selected Git provider API is the only workflow and control-plane API.
Modelo exposes no application API. Consumers use static Pages, release
artefacts or a clone.

Provider APIs, CLIs and read-only MCP tools form an observation plane. Their
output may supply evidence and initiate an issue, but cannot directly approve,
change or revoke catalogue state.

Keep the kernel platform-neutral. GitHub and GitLab integrations are thin
adapters. `modelo.yaml` owns global paths, relative routes and the selected
adapter.

## Consequences

- No database, bespoke API, authentication service, audit service or message
  bus is introduced in v0.1.0.
- Git history is described as tamper-evident, not absolutely immutable or WORM.
- Remote protections must be verified separately by `modelo platform check`.
- A GitHub plan that cannot provide private Pages must use synthetic/public data
  or a private CI artefact; it does not justify an authentication proxy.
- Approval throughput is measured so review capacity, not Git mechanics, can be
  identified as the actual bottleneck.

## Alternatives considered

### Operational database first

Rejected for v0.1.0. It adds identity, API, audit, deployment and backup
responsibilities before transactional or live-state requirements exist.

### Git as live provider inventory

Rejected. Rapid and account-scoped cloud observations would create noise,
conflicts and false revocations in the approval ledger.

### Provider availability as approval

Rejected. Availability cannot establish enterprise Legal, security, policy,
IAM or workload approval.

## Review and exit

Review after 90 days. Reconsider the operational store when any two measured
exit criteria in `SPEC.md` persist for four weeks. Approved release snapshots
remain in Git even if live state later moves elsewhere.
