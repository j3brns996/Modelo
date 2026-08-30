# Move, add, change and revoke contract

MAC starts as a Git-provider issue and is approved only through its linked pull
or merge request. Platform templates are conveniences; the neutral payload and
CI validation are authoritative.

## Neutral payload

```yaml
schema_version: "0.1"
request_id: <uuid>
operation: add | change | revoke | move | batch
item_operation: add | change | revoke  # required only for batch
purpose: <short-stable-purpose>
subjects:
  - kind: model | offering | evidence | vendor | inference-service | condition
    identity: <logical-identity>
requested_outcome: <testable-outcome>
reason: <reason>
candidate_evidence:
  - uri: <official-https-uri>
    observed_at: <rfc3339>
    digest: sha256-<digest>
acceptance:
  - <observable-criterion>
dedupe_key: sha256-<canonical-reservation-set>
idempotency_key: sha256-<canonical-complete-intent>
```

Candidate issue evidence never becomes accepted catalogue evidence. The branch
must contain admissible evidence records.

`change` preserves identity. In v0.1, `move` and `revoke` apply only to
offerings. A move changes offering identity and compiles to atomic
add-destination plus revoke-source; a Git rename is insufficient. Revoke
deletes the current offering after reference checks, while the post-merge
release delta permanently records prior identity/digest, reason, effective
time, replacement if any, issue, change request and merge commit. No parallel
status or tombstone source tree exists. A batch has one homogeneous
`item_operation`, source, observation scope, inference service and purpose and
reserves at most 25 subjects. Evidence and condition versions are immutable and
cannot be revoke/move subjects.

## Idempotency

Both hashes use RFC 8785 canonical JSON. Their input omits `dedupe_key` and
`idempotency_key`. The idempotency input also omits the random `request_id`.
`dedupe_key` hashes a typed object containing the sorted `{kind, identity}`
reservation set, effective operation (`item_operation` for a batch) and purpose.
`idempotency_key` hashes the remaining complete canonical intent including
candidate evidence digests. Exact retries return the existing open issue;
different intent colliding with an open reservation fails closed. Move reserves
source and destination; batch reserves every subject. CI rechecks reservations.

The canonical payload digest is embedded as a stable marker in the issue and
declared by the change request. A least-privilege host-adapter pre-step reads
only the same repository's issue metadata and emits a bounded canonical MAC
input bound to the head SHA. The networkless core check verifies repository,
immutable platform issue identifier, open state, payload, digest and affected
identities from that input. Labels are routing hints only.

## Adapter assets

The canonical examples/schema render to:

- GitHub `.github/ISSUE_TEMPLATE/{mac-add,mac-change,mac-revoke,mac-move,mac-batch}.yml`
  and `.github/PULL_REQUEST_TEMPLATE/mac.md`;
- GitLab `.gitlab/issue_templates/{MAC-Add,MAC-Change,MAC-Revoke,MAC-Move,MAC-Batch}.md`
  and `.gitlab/merge_request_templates/MAC.md`.

Adapter conformance tests must recover identical neutral objects. Checkboxes and
labels are assertions, not evidence.

## Acceptance and approval

The trusted final job rejects missing, skipped, neutral, cancelled, stale or
failed prerequisites and any unexpected check producer. Pre-merge acceptance
binds the exact base/head and built artefacts. Post-merge publication binds the
issue, request digest, accepted head, merge commit, independent reviewer,
checks, change delta and artefact hashes in the release receipt.

An agent approver must be a distinct eligible platform identity and not an
author, committer or modifier. Agent approval is restricted to data-only MACs.
Control-plane changes require a human CODEOWNER. A new commit invalidates both
CI and approval.
