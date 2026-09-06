# Entity acceptance profile 0.2.0

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

Config, MAC and receipt wire families remain unchanged. Tightened entity
acceptance is versioned separately from tool releases and enterprise Conditions.
The NIST mapping schema validates assurance documentation, never catalogue
approval. Its O classification requires operating evidence and is rejected by
this non-operating repository profile even if a form is syntactically complete.
