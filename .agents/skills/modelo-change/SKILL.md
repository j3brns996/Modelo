---
name: modelo-change
description: Use when proposing a Modelo catalogue move, add, change, revoke or batch change through its governed MAC workflow.
compatibility: Modelo contract 0.1.0; GitHub or GitLab; Python and uv.
metadata:
  modelo-contract-version: "0.1.0"
  modelo-origin: native
---

# Modelo change

## Authority

`AGENTS.md`, `modelo.yaml`, the executable schemas and validators override this
skill. This skill guides authorship; it is never build input or acceptance
evidence.

## Use and do not use

Use for catalogue records beneath `paths.models`, `paths.offerings` and
`paths.evidence`, or for their governed supporting records. Do not use it for
platform controls, production cloud changes or facts that lack admissible
evidence.

## Preconditions

- Read the applicable schema and machine contract.
- Require an open linked MAC issue whose scope covers every changed path.
- Work on a topic branch from the issue's exact current base.
- Confirm that the Git-provider repository coordinates equal `modelo.yaml`.

## Procedure

1. Resolve every path from `modelo.yaml`; do not reconstruct directory names.
2. Make the smallest complete semantic change. A move is add-new plus
   revoke-old, never a cosmetic rename.
3. Bind each external assertion to immutable evidence. Treat provider
   availability as observation, not approval.
4. Run the narrow schema and semantic tests.
5. Run `uv run --locked modelo check --base <base-sha> --head <head-sha> --as-of <YYYY-MM-DD>` against the exact committed head.
6. Read back the committed diff and record its head SHA, tree SHA, diagnostics
   and trusted check reference.

## Stop conditions

Stop on an invented fact, missing evidence, scope drift, stale base, dirty tree,
unavailable required check or any non-success result. Do not weaken validation,
approve the change or merge it.

## Handoff evidence

Provide the MAC issue, base/head/tree SHAs, changed paths, evidence IDs, test
results and exact trusted-check reference. A new commit invalidates the handoff.
