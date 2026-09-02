## Decision requested

- Issue: <!-- modelo:mac-issue -->https://HOST/NAMESPACE/REPOSITORY/ISSUE_PATH<!-- /modelo:mac-issue -->
- Operation: <!-- add | change | revoke | move | batch -->
- Affected logical identities: <!-- exact kind/identity reservations -->

State the catalogue decision you want the reviewer to make in one sentence.

## Why this should change

Summarise the linked issue's purpose and reason. Explain the user or governance outcome, not the implementation steps.

## Evidence

- Neutral payload digest: `sha256:...`
- Accepted evidence added or refreshed: <!-- paths or none -->
- Observation scope and time: <!-- bounded source/scope/as-of -->

Candidate links in the issue are leads only. The branch must contain every admissible evidence record needed by the proposed facts.

## Expected change delta

<!-- modelo:change-delta -->
```json
[]
```
<!-- /modelo:change-delta -->

## Verification

- Tests run:
- Deterministic artefact or receipt:
- Known limitations:

## Reviewer decision

- [ ] The evidence supports every changed external fact.
- [ ] The operation and identities match the linked request.
- [ ] Conditions, routes and approval rationale are understandable.
- [ ] The trusted `modelo/check` succeeded for this exact head.
- [ ] No generated `dist/` output, secret or private commercial term is present.

<!-- Checkboxes are assertions, not evidence, CI acceptance or approval. -->
