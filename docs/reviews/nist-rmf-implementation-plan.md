# Model-release and RMF refinement — issue #70

Base: `3ebcfdb` (remote main, 2026-09-06). Branch: `nist-rmf` in a
separate worktree. Existing user site edits are excluded.

## Conditions and scope

Git and exact-head CI/review remain authoritative; only Offerings grant
consumption. Named ModelRelease IDs and evidence bytes remain stable. No core
AI-use inventory, new approval entities, provider parity or production data.
External identity must be evidenced, not inferred from display names. One
homogeneous batch-add already permits Model, initial Offering and Evidence.

## Inventory and defects

There are no production catalogue records or governance registries at this
base. Synthetic build fixtures contain 22 Models and one AWS Offering;
semantic fixtures contain the small `test-model`/`test-offering` repository.
Schema cases and dynamically constructed tests also exercise these entities.
References flow through offering.model_id, route.model_binding API projection
pointers, evidence_refs, build projections and MAC subjects.

Existing AWS validation compares model/provider display names: insufficient
identity proof. Offering model_id is not change-immutable. SPEC's tool version
is stale (0.1.1 versus 0.1.2), and its claim that GCP/Azure schemas are still
absent contradicts reachable, intentionally fail-closed schemas. Its combined
direct/cross-region Offering example needs separation.

Baseline `modelo check --base HEAD --head HEAD --as-of 2026-09-06` fails on
three absent production governance registries. Do not invent production data
to make that command pass. Control-plane acceptance uses the complete test
and package gates; synthetic fixtures exercise catalogue validation.

## Reviewed implementation plan

1. Extend the existing Model with optional release/claim metadata and derived
   canonical URNs. Keep absent release metadata at the existing named-release
   baseline, never upgrade it to a verified immutable snapshot.
2. Tighten AWS consumption validation: explicit selector classification and
   provider-ID claims for direct routes and every profile destination. Freeze
   Offering model binding and model identity precision across changes.
3. Version the tightened **entity acceptance profile** separately from the
   unchanged 0.1.0 config/receipt wire. Provide deterministic local migration
   primitives which copy only explicitly bound evidence, preserve hashes,
   and require review; migrate synthetic fixtures, never accepted history.
4. Add a deterministic schema-validated NIST mapping, reverse artefact index,
   assessment rules and drift tests; document external inventory/coverage,
   ELI21, diagrams, identity ADR and inventory-boundary ADR. Extend only the
   existing site documentation page.
5. Run narrow and complete tests, local control CI, package and repeat demo
   builds; independently verify original conditions; push draft PR, no merge.

## Architecture challenge and decisions

Independent read-only CTO review supports the plan subject to honest selector
classification, explicit versioning, preserved AWS scope/destination checks,
and no operating-maturity overclaim. Accepted: `provider-model-id` does not
assert immutability; the requested example enum lacked that honest category.
Reject Family registry, ConditionSet, AssuranceProfile and review entities:
existing internal grouping, versioned Conditions and MAC provenance suffice.
Do not implement domain-specific partial approval; keep an ADR decision only.

Current NIST equivalence is P/S, never O. M1 is a product target with substantial
local implementation, not proven production operation. T8 postmerge and T10
remain absent. Mapping categories and maturity levels are organisation-defined.

## Risks, migration and rollback

Tighter binding checks reject legacy consumable records: this is intentionally
breaking acceptance, even though metadata fields are structurally additive.
Old evidence cannot prove immutable weights. No external identity is generated
from names or filenames. External inventory examples are non-authoritative.
Rollback is a reviewed code/schema/fixture revert before adopting the profile;
after adoption, review each consumer and preserve accepted evidence/history.
Owner: j3brns. Target: issue #70 draft PR. Tests and independent findings must
be recorded before claiming completion; production launch is not this issue.

## Adversarial follow-up: record maintenance

Scope: validator transitions, synthetic tests and aligned contract documentation.
No operational records, schema shape, workflow adapter or approval changes.
Permit reviewed status transitions while retaining every accepted claim tuple;
keep route eligibility fail-closed. Permit evidenced date enrichment/correction
and optional date withdrawal while freezing actual release identity.
Tests exercise full base/head validation for revoke-then-downgrade, active-route
rejection, downgrade-then-delete/replacement rejection, evidence failures and
date maintenance. Review also checks claim addition/reordering and unchanged
identity-substitution protections. Run focused tests, locked full local CI,
deterministic demo comparison and trusted remote exact-head CI; loop on findings.
Rollback is a reviewed revert of this system-only follow-up.

## Consumer-reference closure

Repair migration tuple matching, then render existing identity metadata through
the current model detail layout. Tests cover all six pre-existing claim statuses,
duplicate rejection, retained evidence, idempotency, escaped HTML, missing values
and full demo HTML/JSON agreement. Update the existing AWS guide and schema ledger
with links to the schema guide/ADR rather than creating another specification.
No schema shape changes, operational records, new styles or generated assets.
Repeat independent review, locked acceptance, deterministic builds and exact-head
CI after fixes. Scope cleanup means consolidating PR documentation references;
unrelated user worktrees, files and history are preserved.
