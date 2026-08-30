# Modelo agent rules

These rules apply to every agent and every repository path. More specific
`AGENTS.md` files may add constraints but may not weaken these rules.

## Current state

This repository is in contract design. `SPEC.md` describes the target, not an
implemented system. Until schemas, fixtures and the `modelo check` command are
present and passing, do not add or merge catalogue records.

## Authority and workflow

- Read `modelo.yaml`, `docs/contract.yaml` and the relevant schema before work.
- Start every move, add, change or revoke operation from a linked MAC issue.
- Work on a topic branch and submit a change request. Never write directly to
  the protected default branch.
- Treat GitHub and GitLab as adapters. Do not put host-specific fields in core
  records, schemas or validation.
- Do not create a Modelo application API. All workflow writes use the selected
  Git provider API; cloud provider APIs and MCP tools are read-only evidence
  sources.
- One root agent owns writes. Research and review agents are read-only unless a
  human explicitly grants a narrower write scope.
- Agents may prepare commits and change requests. They may not approve, merge,
  bypass a required check or push to a protected branch.

## Facts

- Never invent, extrapolate or infer catalogue facts from names or marketing.
- Provider availability is an observation, not enterprise approval.
- Every externally sourced assertion requires admissible evidence and a fact
  link. Internal references and enterprise-authored policy are validated by the
  repository contract; evidence envelopes terminate the evidence chain.
- Evidence records are terminal, content-addressed and immutable once merged.
  Refreshes create new records and migrate references; never edit proof behind
  an existing evidence ID.
- Prefer first-party read APIs, then official provider or vendor documentation.
- Record retrieval scope and time. Do not store credentials, tokens, private
  commercial terms or AWS agreement `offerToken` values.
- Missing discovery results never revoke an approved offering automatically.

## Changes and quality

- Keep stable internal identities out of provider account, project,
  subscription, region and mutable deployment paths.
- A semantic move is add-new plus revoke-old, never a cosmetic rename.
- Do not commit generated output from `dist/`.
- Do not weaken validation to make data pass.
- Do not introduce technical debt without a linked issue containing an owner,
  rationale, removal criterion, target release or date, and test reference.
- After every write, parse the changed structured files and read back the exact
  branch contents. Run the narrow tests first, then `modelo check` when it
  exists.

## Tooling

Use open Agent Skills under `.agents/skills/` for portable workflows. `.codex/`
and `.kiro/` may provide thin adapters, but must not contain the only copy of a
rule. Modelo cloud adapters, CLI commands and MCP access are always read-only.
A separately governed cloud change is outside Modelo and cannot be performed by
its agents or adapters.
