## Linked MAC

- Issue: <!-- modelo:mac-issue -->https://HOST/NAMESPACE/REPOSITORY/ISSUE_PATH<!-- /modelo:mac-issue -->
- Neutral payload digest: `sha256:...`
- Operation: <!-- add | change | revoke | move | batch -->
- Affected logical identities: <!-- exact kind/identity reservations -->

## Expected change delta

<!-- modelo:change-delta -->
```json
[]
```
<!-- /modelo:change-delta -->

## Acceptance

- [ ] The branch contains the admissible evidence records; issue evidence is only a candidate.
- [ ] The declared payload digest matches the linked issue payload.
- [ ] The change is limited to the linked MAC reservation set.
- [ ] No generated `dist/` output, secrets or private commercial terms are present.
- [ ] The trusted final check is required for the exact current head; a new commit invalidates it.

<!-- Checkboxes are assertions, not evidence, CI acceptance or approval. -->
