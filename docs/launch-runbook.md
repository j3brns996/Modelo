# Modelo v0.1 launch runbook

This runbook separates approval of the bootstrap control plane from approval to
launch a production catalogue. The release-candidate PR may be human-approved
and merged as a bootstrap exception; it is not evidence that T10 passed.

## Gate A — bootstrap PR

The PR must contain no production model or offering records. Before merge:

1. Record the issue, PR, reviewed head SHA and head tree.
2. Run the complete locked test suite and offline package build on that head.
3. Obtain an independent read-only review of T6, T8 and T9.
4. Human CODEOWNER reviews every control-plane path.
5. Squash merge only after confirming the resulting tree will equal the reviewed
   head tree. Record that CI could not arbitrate the workflow which introduces
   CI; this is the one bootstrap exception.

After merge, verify the main tree equals the reviewed head tree. Do not yet add
`modelo/check` as a required check unless a positive sentinel can run.

## Gate B — repository controls

Apply and read back: PR required; one independent approval; stale approvals
dismissed; last pusher cannot supply the accepting approval; branch current;
conversations resolved; force push and deletion denied; Actions default token
read-only; action SHAs pinned; Pages source set to Actions; `catalogue-*` tags
protected. The required check name is exactly `modelo/check`.

GitHub Free cannot provide every paid organisation control. Any unavailable
control is recorded as an explicit capability failure, never treated as
present. GitLab's checked-in job is deliberately fail-closed until a protected
pipeline policy or equivalent is configured and rehearsed.

## Gate C — disposable rehearsal repository

Create `j3brns996/Modelo-rehearsal` from the exact bootstrap tree. Override only
the globally owned repository and Pages coordinates in `modelo.yaml`. Use this
repository for sentinel records and destructive protection tests; never pollute
the production approval ledger with disposable data.

Run one factual synthetic condition-add MAC through issue, PR, exact-head check,
independent approval and squash merge. Retain `check.json` and the validation
site. Then prove separate negative cases for invalid data, failed tests, stale
head, stale base, spoofed check, ineligible approval, unresolved conversation,
direct/force push, branch deletion and skipped/cancelled check.

## Gate D — remaining executable launch slice

Production launch remains blocked until a further human-approved PR implements
and tests all of the following:

- consume the accepted exact-head check receipt after merge;
- prove merge tree equals accepted head tree;
- build the final site once and deploy those exact bytes to Pages;
- write and validate the detached release receipt;
- create and verify a protected `catalogue-YYYYMMDD.N` release;
- export a checksummed recovery bundle and restore it offline;
- restore to an isolated GitLab project and record capability differences;
- record keyboard and screen-reader evidence.
- record the owner's explicit repository licence decision; public visibility
  alone does not grant reuse rights.

This deferral is an explicit launch contract, not accepted technical debt. No
production catalogue data, agent approval or launch claim is permitted before
Gate D and the full T10 evidence set pass.

## Human approval prerequisite

The repository currently has no enabled agent actor. A data-only agent approval
is impossible until a distinct platform identity is registered and enabled.
The author, committer and last pusher cannot supply the independent approval.
If no second eligible identity exists, stop: do not lower the approval rule.
