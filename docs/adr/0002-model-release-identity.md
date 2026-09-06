# ADR 0002: Canonical ModelRelease identity and one approval proposal

Status: proposed for human CODEOWNER review. Issue: #70. Owner: j3brns.
Entity acceptance profile: 0.2.0. Config and receipt wire remain 0.1.0.

## Decision

The physical `model` entity is a canonical named ModelRelease, not a family,
deployment, floating alias or marketing category. Keep its immutable internal
`id` and readable path. Derive `urn:modelo:model-release:<id>`; an optional
stored `canonical_urn` must equal that derivation. Offering URNs similarly
derive as `urn:modelo:offering:<id>`. They identify records, not permissions
outside a current accepted revision. IDs are never reused after retirement.
Models remain in history/current records; consumption retirement revokes the
Offering. External universal canonical identity is neither required nor assumed.

Optional `family_id` is internal grouping, not a separate family registry or an
evidenced assertion about vendor taxonomy. `release.vendor_label` and optional
`released_at` are external facts with ordinary exact `evidence_refs` pointers.
Omit unknown dates rather than adding a new null-fact convention. Precision is
a reviewed classification; absent metadata retains only the existing
named-release baseline. Do not infer weights, version immutability or dates.
Floating/unresolved descriptions cannot support consumption.

`identity_claims` uses namespace/value/relation/status. Values require the same
canonical evidence equality and freshness as other model facts. Status is a
reviewed assertion, not an automated confidence score. Probable, conflicting
and unresolved claims cannot establish route binding. Verified namespace
conflicts fail closed. Display names remain consistency checks, not identity.

AWS retains its provider-owned `reference`, source Region and complete explicit
`model_binding` evidence. `selector_type` supplies the classification; namespace
comes from the provider binding kind and value remains `reference`, avoiding
duplicate coordinate fields. The enclosing Offering's model_id is the single
binding target. Each direct model ID and every profile destination must match
an evidenced Model identity claim in `aws.bedrock.foundation-model`.
The relation is serves-release; eligible claims explicitly record their status.
Existing same-release relocation between inference-service aliases remains
supported; this is not a semantic release move. Changing the release requires
a new Offering ID even when the path also changes.

The example selector enum omitted an honest category for existing observations:
`provider-model-id` reports a provider identifier **without asserting immutable
weights**. `inference-profile` identifies routing indirection. Immutable,
floating-alias, deployment and provisioned selectors remain fail-closed in the
AWS semantic adapter until evidence and implementation establish their meaning.
Never infer immutability from spelling such as `-v1`. Other adapters remain
intentionally fail-closed; this is not a provider-parity change.

## Four independent version dimensions

| Dimension | Owner |
|---|---|
| Model-release version/precision | Model release metadata and evidenced identity claims |
| Provider selector/route version | Provider reference, selector classification and binding evidence |
| Modelo record/schema revision | Exact Git revision and entity acceptance profile; config/receipt wire version separately |
| Enterprise policy version | Immutable Condition `(id, version)` |

## Offering and review

An Offering is an enterprise-approved set of governance-equivalent provider
routes through which one identified ModelRelease may be consumed. All material
binding, routing/processing, residency, contractual/data-handling, controls,
Conditions and permitted-use properties must be interchangeable. Direct
single-Region, cross-Region, Azure-hosted and vendor API paths normally require
separate Offerings. Mechanical checks cannot decide legal equivalence: the
authorised reviewer owns the complete decision and approval rationale.

Existing homogeneous batch-add can introduce a Model, first Offering and
Evidence with existing Condition references: one issue, branch, candidate,
exact-head validation, relevant review, merge and target release receipt.
Reuse versioned Conditions across Offerings. ConditionSet/AssuranceProfile and
new review entities lack independent lifecycle benefit here and are rejected.

Domain-specific review digests might reduce later reapproval, but would need
proved dependency closure and exact-head binding. Decision: do not implement
partial-review acceptance. Every new commit invalidates review and check evidence.

## Compatibility, migration and rollback

Metadata is structurally additive. Required AWS selector classification and
provider-ID claim linkage are a **breaking acceptance change**, explicitly
profiled as 0.2.0. Old route-only records fail new semantic acceptance rather
than silently acquiring stronger identity. No config/receipt wire shape changes.

`modelo.identity.migrate_bound_model` deterministically returns a local draft
from an explicit reviewed model ID and API evidence projection pointer. It
never searches display names, reads a provider, writes history or edits evidence.
The migration script accepts explicit files/pointer and prints this draft.
For example, from the repository root:

```text
uv run --locked python tooling/modelo/scripts/migrate-model-release.py --model MODEL.yaml --evidence EVIDENCE.yaml --id-pointer /modelId --reviewed-model-id MODEL_ID
uv run --locked python tooling/modelo/scripts/migrate-model-release.py --offering OFFERING.yaml
```

Both commands print only non-accepting drafts, leaving all input files intact.
The Offering helper deterministically classifies explicit binding kinds and
rejects attempts to overwrite a different selector assertion. Apply reviewed
output on the MAC branch, then run normal exact-head validation.
Classify direct routes as provider-model-id and profiles as inference-profile;
validate all destinations and review governance equivalence before MAC acceptance.
Only the two synthetic/semantic bound models need claims; the other 21 synthetic
models retain stable IDs and no unsupported external identity. Evidence bytes
and hashes are unchanged. Unknown metadata stays absent.

Rollback before adoption is a reviewed revert of code, schemas and fixtures.
After adoption, coordinate consumers and preserve accepted history/evidence;
do not downgrade an approval silently. No production records are migrated here.
