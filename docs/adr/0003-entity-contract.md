# Canonical entity acceptance

Engineering issue: [#89](https://github.com/j3brns996/Modelo/issues/89).
Entity acceptance profile: 0.3.0. Publication envelope version remains 0.1.0.

An accepted source entity satisfies four checks: configured filename and path,
its closed JSON Schema, semantic relationships and evidence, and Git change
rules. JSON Schema alone does not enforce filenames, foreign keys or approval.
YAML linting is a separate style check.

The publication entry point is `schemas/catalogue-output.schema.json`. It
references the same source schemas; it is not a second set of entity fields.
Its `x-modelo-entity-profile` identifies entity compatibility. The inventory's
`contract_version` describes its envelope; `source_commit` pins the actual schema
bundle. Do not validate an old snapshot against a newer bundle.
`model-release.schema.json` defines reusable release metadata inside
`model.schema.json`, not another stored entity. `mac.schema.json` describes a
proposal, not a model or publication. `docs/contract.yaml` identifies the rules
and acceptance profile. Load all schemas from the same source commit. Their
absolute `$id` values are logical identifiers, not URLs to fetch from the network.
Duplicate schema IDs or JSON keys fail loading.

| Record | Configured path | Key |
|---|---|---|
| Model | `{paths.models}/{id}.yaml` | `id` |
| Offering | `{paths.offerings}/{inference_service_id}/{id}.yaml` | Global `id`; service directory is checked but is not part of the key |
| Evidence | `{paths.evidence}/{id}.yaml` | Content digest `id` |
| Condition | `{paths.conditions}/{id}/{version}.yaml` | `(id, version)` |
| Vendor | `{paths.governance}/vendors.yaml` | Registry key equals `id` |
| Inference service | `{paths.governance}/inference-services.yaml` | Registry key equals `id` |
| Route | Embedded in its offering | `(offering_id, route.id)` |

Entity directories accept exact lowercase `.yaml` filenames and `README.md`.
Wrong extensions and undeclared YAML record paths fail. Supporting documents
belong outside entity directories. Keys are stable internal identities; a
provider selector, display name, account or Region does not become a key.
`family_id` is a grouping label, not a foreign key. URNs are derived from IDs.
Supersession is acyclic, may cross a family grouping after review, and never
transfers approval. All route-eligible external identity claims must be
unambiguous across models; disputed claims can be retained but cannot bind a route.

## Minimum decision information

Keep the existing entity split. Do not add a generic metadata map, organisation
hierarchy, country service, workflow state machine or application-use registry.

- A vendor identifies a producer or organisation. Optional `legal_name` and
  `domicile` require evidence. Domicile requires a legal name; a brand name is
  insufficient. Store the evidenced jurisdiction name, not an inferred country
  from a cloud Region.
- A model may reference `rights_owner_vendor_id`; a service may reference
  `operator_vendor_id`. The target must exist and have an evidenced legal name.
  These are independently reviewed internal bindings. Evidence of a legal name
  alone does not prove ownership or an operating relationship. The reviewer must
  establish that relationship in the linked change and its supporting evidence.
- An offering requires `approval_owner`, `approved_use` and `approval_rationale`.
  The owner is an accountable team or role, not a duplicate of the Git approver.
  The use states task, data boundary and oversight. Application-specific purpose,
  deployment and risk acceptance remain in the external use inventory.
- Empty conditions require `no_conditions_rationale`. Do not create a dummy
  condition. The rationale is forbidden when conditions are present.
- Optional `review_by` is an inclusive date. Omitting it means event-triggered
  review on changes to scope, routes, rights, conditions or material evidence.
  An overdue date fails the next full check and blocks a new publication until
  reviewed or revoked. It does not remove an existing published offering.
  Offering review is distinct from the system's capacity and NFR assessment.
- Optional `licence_uri` identifies an evidenced licence or terms document.
  `licensing` is a display category and grants no permission by itself.

Omission of an optional external fact means unknown. Never fill missing fields
with plausible values or treat a blank request checkbox as a negative fact.
Known processing Regions remain in provider route evidence. Rights-owner
domicile, operator domicile and processing location are separate concepts.

## Migration and publication

This profile adds mandatory approval scope and accountability to offerings.
Existing production records must receive a reviewed migration before use with
the new schema; the repository currently has no production catalogue. Synthetic
fixtures explicitly declare test-only use. Never rewrite merged evidence or
condition versions to make a migration pass. Optional legal facts stay absent
until evidence exists. The agent guide and schema ZIP are built from repository
source at publication time and explain the acceptance boundary.

Azure and Google route schemas describe future adapter structures. They are
schema-reachable but not semantically accepted by this release. The machine
contract lists AWS Bedrock as the only supported acceptance adapter. A schema-only
agent must report `not_run` for semantic, path and history checks it cannot execute.

## Verification and capacity

`tests/unit/test_entity_contract.py` covers identity, cycle, policy, provenance
and schema ambiguity cases. `tests/unit/test_discovery.py` covers extensions;
existing validator tests cover filename/key correspondence and immutable history.
`tests/scale/test_entity_scale.py` creates exactly 5,000 mixed entities, loads
real files, runs a Git-backed check, and validates and serialises the publication.
It reports timings rather than asserting a machine-specific runtime SLA.
The deep-chain regression exercises 5,000 predecessor edges without recursion.

Measured on 2026-09-06 with locked Python 3.12.13 and uv 0.11.33, Ubuntu under
WSL while other checks ran: 1,667 models, 1,664 offerings, 1,666 evidence records,
one condition, one vendor and one service (5,000 total). File loading, schema and
semantic validation took 28.591 s; a Git-backed audit took 47.895 s; a bulk policy
change to all 1,664 offerings took 92.780 s; publication validation and
serialisation took 14.512 s for 3,568,875 bytes. These are observed timings, not
an SLA or a controlled comparison across operating systems. Reproduce with
`uv run --locked pytest -q -s tests/scale/test_entity_scale.py`.

The tested capacity is this mixture, not any distribution of 5,000 records.
Existing per-file limits remain 128 KiB and 2,000 nodes. Aggregate vendor and
service registries share those limits; 5,000 vendors in one registry would fail.
Do not remove resource bounds or invent a registry sharding system without a
workload that requires it. This change adds no dependency or deferred shortcut.

Use dictionaries for identity lookups and one iterative walk for supersession.
Reuse validators within a schema set. Add no runtime dependencies or persistent
cache. Capacity measurements do not establish browser performance, long-history
cost or production operating readiness. Those require their own measured checks.

The design follows [JSON Schema's modular reference model](https://json-schema.org/understanding-json-schema/structuring)
and [W3C guidance on provenance, licence information and structural metadata](https://www.w3.org/TR/dwbp/).
The predecessor [filename validator](https://gitlab.com/julianburns/models/-/blob/main/scripts/validate.py)
confirms path enforcement. [OpenModels](https://github.com/openmodelsrun/openmodels)
offers a useful model/provider/mapping separation; its weaker filename and
duplicate-YAML-key checks are not adopted.
