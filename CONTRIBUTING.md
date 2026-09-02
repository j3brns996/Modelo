# Contributing to Modelo

## Requester

- Open a linked MAC issue before any catalogue move, add, change, revoke, or batch change.
- Open the linked control issue before any product or documentation change.
- Use a topic branch and submit a change request instead of writing directly to the protected default branch.

## Author or contributor

- Read `AGENTS.md`, `modelo.yaml`, `docs/contract.yaml`, and the owning specification or schema before editing.
- Keep one writer per branch or worktree.
- Treat GitHub and GitLab as adapters. Do not put host-specific fields in core records, schemas, or validation.
- Do not create a Modelo application API. Workflow writes use the selected Git provider API; cloud provider APIs and MCP tools are read-only evidence sources.
- Do not add production catalogue records before T10 passes remotely.

## Reviewer

- Review agents are read-only.
- For data-only MAC work, an independent eligible agent may approve only after trusted CI succeeds for the exact current head and the evidence is recorded.
- The approving agent must not be the author, committer, or modifier of the change.

## Approver

- Control paths require a human CODEOWNER.
- Agent approval is disabled except for the current narrow allowlist: `catalogue/models/**`, `catalogue/offerings/**`, and `catalogue/evidence/**`.
- Any new commit invalidates trusted CI evidence and any prior approval.
- Agents may not merge, bypass controls, or push to the protected branch.

## Local verification

Setup:

```bash
uv sync --locked
```

Local-ci:

```bash
uv run --locked modelo-local-ci run \
  --base <base-sha> --head <head-sha> --as-of YYYY-MM-DD --jobs 3
```

- Treat local success as advisory only; `modelo check` remains authoritative when it exists.
- Control changes run the complete Python test inventory and offline package build.
- Catalogue-only changes run validation and execute no proposed tooling in trusted CI.

## Non-negotiables

- Start every move, add, change, revoke, or batch operation from a linked MAC issue.
- Keep one writer per branch or worktree.
- CI is the technical acceptance arbiter. Only the trusted final check for the exact current head is accepting; missing, skipped, neutral, cancelled, stale, or failed results are not.
- Do not commit `dist/`.
- Do not weaken validation to make data pass.
- Do not introduce technical debt without a linked issue that names an owner, rationale, removal criterion, target release or date, and test reference.
