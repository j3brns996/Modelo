# AWS Bedrock discovery contract

This document defines what the AWS adapter may discover and what those results
mean. It is configuration and evidence guidance, not catalogue data.

## First principles

AWS Bedrock is both Region scoped and, for some operations, account scoped.
Provider availability is therefore an observation about the credentials,
account and Region used for the read. It is never Modelo approval.

The adapter records a repository-internal opaque `scope_ref`, partition, Region,
operation, sanitised request parameters and observation timestamp. `scope_ref`
is non-secret and non-reversible; account aliases, IDs and fingerprints,
credentials and ephemeral tokens are never retained.

## Read operations

| Operation | Retainable facts | Boundary |
|---|---|---|
| [`ListFoundationModels`](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModels.html) | `modelId`, `modelArn`, `modelName`, `providerName`, input/output modalities, streaming, customisation types, inference types and lifecycle | Does not establish internal approval, context limits, licence, generic capability labels or residency suitability |
| [`GetFoundationModel`](https://docs.aws.amazon.com/cli/latest/reference/bedrock/get-foundation-model.html) | The same first-party model summary for one AWS model ID | Does not prove that a workload can invoke the model |
| [`GetFoundationModelAvailability`](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GetFoundationModelAvailability.html) | Discovery-only agreement, authorisation, entitlement and Region-availability status | Not admissible retained catalogue evidence in v0.1; does not establish approval or effective IAM permission |
| [`ListInferenceProfiles`](https://docs.aws.amazon.com/cli/latest/reference/bedrock/list-inference-profiles.html) | Inference-profile ID/ARN, type, status and referenced model ARNs | Profile identity is a route, not canonical model identity |
| [`GetInferenceProfile`](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GetInferenceProfile.html) | One profile's ID/ARN, type, status and model destinations | The profile remains an opaque route; account-owned application profiles are deferred in v0.1 |
| [`ListFoundationModelAgreementOffers`](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModelAgreementOffers.html) | Official legal-term links and returned rate-card dimensions when safe to retain | Never retain or publish `offerToken`; private terms never enter a public Pages artefact |

The Bedrock model-access guide explains provider access differences and why
access should be tested in the intended account and Region:
[Access Amazon Bedrock foundation models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html).

AWS documents the Region and geography topology separately:
[Supported Regions and models for inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html).
`eu-west-2` is the London Region. `uk` is not an AWS inference geography.

## Illustrative read sequence

The values below are placeholders. Commands are read-only.

```bash
aws bedrock list-foundation-models --region <region>
aws bedrock get-foundation-model \
  --region <region> \
  --model-identifier <foundation-model-id>
aws bedrock get-foundation-model-availability \
  --region <region> \
  --model-id <foundation-model-id>
aws bedrock list-inference-profiles --region <region>
aws bedrock get-inference-profile \
  --region <region> \
  --inference-profile-identifier <profile-id-or-arn>
```

The adapter stores a durable redacted canonical projection beneath the globally
configured evidence path, computes its digest, extracts only schema-supported
facts, and attaches fact-level JSON Pointers to that evidence record. Raw
responses may be short-lived private artefacts, but are not the only retained
proof. Discovery opens or updates a MAC issue; it cannot edit an approved
catalogue record.

For first-party API evidence the operation name and request scope are required.
The evidence ID is content-addressed from the full canonical envelope, excluding
the ID itself. Once merged, an evidence record is immutable; refreshes create a
new record and migrate references through MAC review.

Canonicalisation uses the JSON data model produced by the restricted YAML
loader and RFC 8785 JCS. The root `id` is omitted, the canonical UTF-8 bytes are
hashed with SHA-256, and the lowercase digest is prefixed with `sha256-`.

## AWS route types

- `foundation-model`: a direct Bedrock foundation-model ID or ARN, generally
  invoked in one Region.
- `system-inference-profile`: an AWS-owned geography or global system profile
  used as the invocation route. A geography profile may route among several
  Regions.
- Provisioned, custom and imported model resources require their own adapter
  values and first-party fixtures before they are admitted.
- Account-owned application profiles are deferred with those route types.

Regions and AWS-owned model or system-profile references may appear in routes.
Account IDs and account-owned ARNs may exist only in short-lived discovery
configuration or raw private artefacts and are not retained in v0.1 catalogue
evidence. None belongs in canonical filenames.

## Route-to-model binding

A direct foundation-model route retains evidenced `modelId`/`modelArn`,
`modelName` and `providerName` and binds them by exact equality to the canonical
model's evidenced identity facts. A system inference profile retains every
destination model ARN. Each destination must resolve through evidenced
`GetFoundationModel` facts to that same canonical model. If equality would need
normalisation, aliasing or another transformation, the mapping is deferred.

## Cross-cloud path comparison

| Concern | AWS Bedrock | GCP Vertex AI | Azure AI Foundry |
|---|---|---|---|
| Model coordinate | AWS model ID and foundation-model ARN | Publisher/model/version | Publisher/format/name/version |
| Invocation coordinate | Direct model ID/ARN or inference-profile ID/ARN | Publisher route or project/location endpoint | Account-child deployment name |
| Administrative scope | Partition, account and Region | Organisation/project and location | Tenant/subscription/resource group/account and location |
| Mutable alias risk | Application profile or provisioned resource | Endpoint/deployed-model binding | Deployment name and account |

Only the common semantics are core: an opaque inference-service reference, its resource
type, scope, consumption mode and evidence. GCP and Azure syntax must come from
first-party response fixtures before their adapter schemas are implemented.

## Documentation MCP

`.codex/config.toml` pins the official
[`awslabs.aws-documentation-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/aws-documentation-mcp-server)
to `1.2.0` and exposes read-only documentation tools. The dependency is
optional so a clean clone can still validate without network access. A missing
MCP blocks fresh documentation discovery, not deterministic validation of
already captured evidence.
