# ADR 0004: Simplify v1 without adding entities

Issue: [#91](https://github.com/j3brns996/Modelo/issues/91).
Status: proposed for the authorised v1 change workflow.

Keep the existing entity structure and acceptance layers. Schemas define shape,
configuration defines paths, validators check relationships and history, and
the Git host enforces workflow authority. Documentation explains these rules
without maintaining a second field catalogue.

## Correlation without a reservation service

Retire the unimplemented promise of cross-issue reservations and exactly-once
issue creation. The existing MAC hash fields remain wire-compatible advisory
correlation values; computing a digest is not acquiring a lock. Reprocessing one
issue remains idempotent, but equivalent separate issues can require triage.

Keep payload/head binding, current-base checks, schema and semantic validation,
immutable history, independent review and serialised acceptance. Competing
changes must be revalidated against the current base. This removes an
unsupported promise; it does not remove an implemented acceptance safeguard.
No registry, lock service or new workflow entity replaces it.

## Quality tools and scanner limits

Locked Ruff and yamllint checks block on findings. UBS v5.3.13 is pinned to
`0af10c926d6fbb14a1f589326d75c03f610207f0`; ast-grep is locked at 0.40.1.
Use the same Linux/WSL commands locally and in CI. Bootstrap fetches only that
UBS source revision; it does not install hooks or modify agent configuration.
Unpinned UBS uv analyzers and automatic updates are disabled.

UBS must execute the selected Python and JavaScript scans and report matching
file counts and totals. Environment errors, empty scans and inconsistent output
fail verification. Preserve raw findings for independent review. A completed
scan with findings is not labelled clean, and no suppression baseline is added.
Zero heuristic findings is not the acceptance criterion: UBS mistakes Path
composition for division and public integrity hashes for authentication secrets.
Resolve real defects, record false-positive reasoning, and retain correct
Boolean/type checks. This release cannot attest that every optional upstream
analyzer ran; the reported scope is its Python/JS modules with prerequisites.

## Retained publication protections

Keep detached receipts, one publication manifest and the existing local output
recovery contract. Native CI artifact metadata does not represent Modelo's
approval semantics or replace its local filesystem durability guarantees.
There is no demonstrated replacement justifying deletion of those controls.
GitLab activation remains explicitly unavailable until a protected adapter and
remote rehearsal exist. No runnable-looking deployment scaffold is retained.

## Verification

Existing MAC tests cover stable keys and repeated handling; platform tests
reject stale accepted-base evidence. New quality tests run the actual tools,
exercise failing/corrected lint input and reject incomplete scan summaries.
Documentation tests compare the current profile/policy fields to source schemas
and exercise configured proposal links. The full suite and mixed 5,000-entity
test remain required. Production release/T10 evidence remains separate from
this engineering milestone; do not bump a release merely to declare completion.
