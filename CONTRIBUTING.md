# Contributing to Modelo

## Requester

- Open a linked MAC issue before any catalogue move, add, change, revoke, or batch change.
- Open the linked control issue before any product or documentation change.
- Use a topic branch and submit a change request instead of writing directly to the protected default branch.

## Author or contributor

- Read `AGENTS.md`, `modelo.yaml`, `docs/contract.yaml`, and the owning specification or schema before editing.
- Keep one writer per branch or worktree.
- Treat GitHub and GitLab as adapters. Do not put host-specific fields in core records, schemas, or validation.
- Do not create a Modelo application API. Workflow writes use the selected Git
  provider API; cloud-provider APIs, CLIs and MCP tools are read-only evidence
  sources. Local `modelo dev ... --output` may write only an explicitly
  requested, author-controlled draft file.
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

Use Ubuntu 24.04 or Ubuntu 24.04 under WSL for the complete checks, matching CI.
Bash, Git, jq and GNU coreutils are system prerequisites. The locked environment
supplies Ruff, yamllint, ast-grep and Linux ripgrep. The first UBS run fetches its
pinned source into the user tool cache; subsequent runs verify that checkout.
No installer, hooks, agent configuration changes or automatic updates run.

Run the quality tools directly:

```bash
uv run --locked modelo-local-ci lint
```

Ruff lint/format and yamllint are blocking. UBS scan failures, empty scans and
inventory mismatches also block. Completed heuristic findings are retained in
`dist/quality/ubs.json` with stderr and the scanned inventory for independent
review. They are not automatically waived or described as clean. Resolve real
defects and explain false positives in the PR; never weaken sound code to
satisfy a heuristic. See [the decision](docs/adr/0004-v1-simplification.md).

The complete Python test inventory includes this same quality entry point and
real failing/corrected input checks, so the protected CI runner executes the
local tools rather than merely checking configuration text. Raw reports can be
reproduced with the command above at the reviewed commit.

Local-ci:

```bash
uv run --locked modelo-local-ci run \
  --base <base-sha> --head <head-sha> --as-of YYYY-MM-DD --jobs 3
```

- Treat local success as advisory only; the remote exact-head `modelo/check`
  required check is the acceptance gate.
- Control changes run the complete Python test inventory and offline package build.
- Catalogue-only changes run validation and execute no proposed tooling in trusted CI.

## Authoring helpers

- Read [docs/authoring.md](docs/authoring.md) before using the browser or CLI
  drafting helpers.
- The static proposal chooser covers add, change, revoke, move and batch. The
  interactive helper is intentionally limited to add and change.
- `modelo dev evidence-create` and `modelo dev mac-init` print a draft to
  standard output by default. Use `--output` only when you explicitly want a
  local file.
- Treat every result as a drafting aid. It is not approval, accepted evidence
  or canonical intake output; the linked issue and trusted compiler remain
  authoritative.

## Non-negotiables

- Start every move, add, change, revoke, or batch operation from a linked MAC issue.
- Keep one writer per branch or worktree.
- CI is the technical acceptance arbiter. Only the trusted final check for the exact current head is accepting; missing, skipped, neutral, cancelled, stale, or failed results are not.
- Do not commit `dist/`.
- Do not weaken validation to make data pass.
- Do not introduce technical debt without a linked issue that names an owner, rationale, removal criterion, target release or date, and test reference.
