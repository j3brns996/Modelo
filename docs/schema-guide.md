# Entity acceptance profile 0.3.0

An accepted record passes configured path and filename checks, its closed JSON
Schema, semantic references and evidence checks, and Git history rules.
The [canonical entity contract](adr/0003-entity-contract.md) identifies the
source schemas, keys and migration rules. `catalogue-output.schema.json` is the
publication entry point and references those same schemas. Use the bundle from
the publication's source commit; envelope and tool versions are separate.

Offerings require `approval_owner`, `approved_use` and `approval_rationale`.
They describe accountable role, permitted task/data/oversight and the policy
reason for approval. Empty conditions require `no_conditions_rationale`.
Optional `review_by` sets an inclusive review deadline; omission means
event-triggered review. Application-specific ownership and use remain external.
Policy fields do not require external fact evidence. Optional external facts
remain unknown until evidenced; do not infer legal ownership from a brand name.

Model means a canonical named ModelRelease. Existing internal IDs remain
canonical; optional canonical_urn must equal the derived namespace and ID.
Release metadata and identity claims are defined in model-release.schema.json.
External leaf values use ordinary evidence_refs with exact projection equality.
Accepted claim tuples (namespace/value/relation) remain present regardless of
status; review may change status or append claims, but not erase prior assertions.
Each tuple has exactly one status; duplicate tuples are rejected semantically.
An ineligible claim cannot support a remaining Offering. Release dates may be
added, corrected with evidence, or withdrawn; effective release label, vendor
identity and precision remain fixed.
There is no required universal external identity, family registry or AI-use entity.

AWS route selector_type is structurally additive but mandatory in semantic
acceptance. Only provider-model-id and inference-profile are currently supported.
Every explicit binding must match a Model's evidenced provider-ID claim.
Offering remains the only consumption unit, and cannot change model_id in place.
See [migration and compatibility ADR](adr/0002-model-release-identity.md).
Migration matches existing claim tuples without changing their status or evidence;
ambiguous duplicates fail rather than being silently resolved. Evidence refresh
and status review remain explicit governed changes, not migration side effects.

Config, MAC and receipt wire families remain unchanged. Tightened entity
acceptance is versioned separately from tool releases and enterprise Conditions.
The NIST mapping schema validates assurance documentation, never catalogue
approval. Its O classification requires operating evidence and is rejected by
this non-operating repository profile even if a form is syntactically complete.
