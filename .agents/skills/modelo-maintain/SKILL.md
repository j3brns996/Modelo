---
name: modelo-maintain
description: Use when a Modelo maintainer asks an agent to triage a model request, improve the repository, or assess system requirements and capacity.
compatibility: Modelo contract 0.1.0; GitHub or GitLab; locked Python and uv.
metadata:
  modelo-contract-version: "0.1.0"
  modelo-origin: native
---

# Modelo maintain

## Authority

Read `AGENTS.md`, `modelo.yaml`, `docs/contract.yaml`, and the relevant schema.
This skill guides maintenance; it is not an approval or build input. Keep
existing user authorization and scope. Human CODEOWNER review applies to
maintenance changes. Agent approval is disabled; agents do not merge.

## Use and do not use

Use for request triage, code, site, documentation, tests, and uplift reviews.
Use [modelo-change](../modelo-change/SKILL.md) for catalogue authorship and
[modelo-discover](../modelo-discover/SKILL.md) for read-only provider evidence.
Do not treat a model-card URL or provider selector as canonical model identity.
Do not add production records before remote T10 passes.

## Preconditions

Read the linked request and current branch status. Establish whether the work
is triage, a catalogue MAC, or a system change. Keep one writer per topic branch.
Preserve unrelated edits. Do not require a requester to supply record IDs,
evidence digests, or schema fields that the agent can establish from sources.
Ask only for missing purpose, scope, or authority that changes the decision.

## Procedure

1. For a model request, establish who needs it, the business outcome and reason,
   intended task and data, human oversight, and known service, region,
   environment, and timing. Keep vendor, model, and offering distinct. Do not
   require all deployment details at intake; flag gaps that affect the decision.
   Check existing records and open requests. Gather only
   the needed official evidence, recording retrieval time and scope. Preserve
   unknowns. Route supported catalogue work through a linked MAC before writes.
2. For maintenance, use a linked engineering issue. Make the smallest complete
   change and keep code, configuration, schemas, prose, and tests consistent.
   Follow the site's Microsoft writing style for prose and diagram labels.
3. Parse changed structured files and read back the branch contents. Run narrow
   tests, then `uv run --locked modelo check --base <base-sha> --head <head-sha> --as-of <YYYY-MM-DD>`.
   Separate baseline failures from new failures. Do not weaken validation.
4. Prepare the change request and inspect trusted CI at its exact current head.
   Fix failures within scope and rerun the affected checks. Every new commit
   invalidates previous check and review evidence.
5. Assess system requirements and capacity when accepted changes reach the
   5-10 per working day range,
   or a consumer needs an API contract. Keep this separate from offering and
   record approval; it creates no extra record approval steps. Above 10 per day, reassess approval and
   publication capacity promptly. Use the system assessment section of `SPEC.md`.
   Assess performance, availability, security, recovery, and cost as NFRs.
   Define consumers, data and operations, identity/versioning, access controls,
   errors, and service expectations. First assess whether existing static JSON
   and release snapshots meet the contract. Propose an API or store change only
   through a separate human-reviewed system change; never add one by default.

## Stop conditions

Do not advance an unsupported fact, unapproved scope expansion, failed required
check, or stale head to acceptance. Continue independent work where possible;
report the precise blocker. Provider API, CLI, and MCP operations stay read-only.
Do not change cloud resources, approvals, or protected-branch controls.

## Handoff evidence

Provide the issue and change request, base/head/tree SHAs, changed scope,
test results, exact trusted CI reference, and outstanding human decisions.
For uplift, include observed change volume or the consumer's API requirement,
options, recommendation, and acceptance criteria. Distinguish observations
from targets. Remove only task-owned temporary files and processes.
