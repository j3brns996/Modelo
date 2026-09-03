# GCP Vertex AI discovery contract

This is a stub. `schemas/providers/gcp-vertex.schema.json` defines the route
shape and `inference-services-registry.schema.json`'s `adapter` enum
includes `gcp-vertex` (Phase 1, issue #56), so a `gcp-vertex` route and
inference service are both schema-reachable today. **No semantic dispatch
exists for this adapter.** `tooling/modelo/src/modelo/validators.py` has no
`_gcp_offering_checks`: an offering resolved to a `gcp-vertex` service — or
an `aws-bedrock`-resolved offering whose route is GCP-shaped instead —
currently fails closed with `UNKNOWN_REFERENCE` ("adapter has no implemented
validator" or "route is not shaped for this offering's resolved adapter"),
the same safe fail-closed behaviour any adapter without an implemented
validator gets. See `docs/catalogue-schema-ledger.md` and
`docs/providers/aws-bedrock.md`'s cross-cloud comparison table for how this
fits alongside the implemented AWS Bedrock adapter.

## Why semantic dispatch isn't implemented yet

Full AWS-parity semantic validation (evidence correlation, malformed-reference
rejection, freshness) needs real first-party GCP evidence fixtures to
validate any coherence rule against — `docs/providers/aws-bedrock.md:143-145`
states this precondition for both deferred providers, and
`docs/contract.yaml`'s `provider_boundary.gcp_vertex_ai` and top-level
`deferred: gcp_and_azure_adapters` name it as contract. Writing GCP resource-
name coherence rules without a first-party fixture to validate them against
would mean inventing catalogue facts, which `AGENTS.md` forbids.

`schemas/evidence.schema.json`'s `apiSource` definition is also currently
AWS-only (`partition` is an AWS-partition enum, `region` matches the AWS
region pattern), so no GCP route can have valid first-party-API evidence
today regardless of adapter dispatch. Generalising it is part of the same
deferred, evidence-fixture-gated follow-on.

## Route shape

A GCP Vertex AI route (`schemas/providers/gcp-vertex.schema.json`) requires
`id`, `location` (the discriminator field that distinguishes this route shape
from AWS's `source_region` and Azure's `region` in `offering.schema.json`'s
route `oneOf`), `reference` and `model_binding`. `model_binding.kind` is
either `publisher-model` (a `publishers/<publisher>/models/<model>` reference)
or `endpoint-model` (a `projects/.../locations/.../endpoints/...` or
`projects/.../locations/.../publishers/.../models/...` reference), each with
its own `model_evidence` pointer set. See the schema file and its fixtures in
`tests/fixtures/schema/cases.json` for the exact shape.

## What comes next (Phase 2, not this document's scope)

Implementing semantic dispatch for this adapter requires: real first-party
`aiplatform.googleapis.com` response fixtures; a `_gcp_offering_checks`
validator function analogous to `_aws_offering_checks`; a
`schemas/evidence.schema.json` `apiSource` generalisation that can represent
GCP evidence without weakening AWS's existing shape; a
`docs/contract.yaml` `provider_boundary.gcp_vertex_ai` section with real
AWS-equivalent rules, replacing today's `schema_reachable_semantic_dispatch_deferred_until_first_party_fixtures`
marker; and removal of `gcp_and_azure_adapters` from `docs/contract.yaml`'s
`deferred:` list once both providers are done, with the version bump that
implies. None of that is in scope for this document or for the change that
introduced it.
