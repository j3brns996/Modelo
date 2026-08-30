# AWS Bedrock discovery contract

This document defines what the AWS adapter may discover and what those results
mean. It is configuration and evidence guidance, not catalogue data.

## First principles

AWS Bedrock is both Region scoped and, for some operations, account scoped.
Provider availability is therefore an observation about the credentials,
account and Region used for the read. It is never Modelo approval.

The adapter must record the AWS account alias or safe account fingerprint,
partition, Region, operation, request parameters and observation timestamp.
Credentials and ephemeral tokens must never be retained.

## Read operations

| Operation | Retainable facts | Boundary |
|---|---|---|
| [`ListFoundationModels`](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModels.html) | `modelId`, `modelArn`, `modelName`, `providerName`, input/output modalities, streaming, customisation types, inference types and lifecycle | Does not establish internal approval, context limits, licence, generic capability labels or residency suitability |
| [`GetFoundationModel`](https://docs.aws.amazon.com/cli/latest/reference/bedrock/get-foundation-model.html) | The same first-party model summary for one AWS model ID | Does not prove that a workload can invoke the model |
| [`GetFoundationModelAvailability`](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GetFoundationModelAvailability.html) | Agreement, authorisation, entitlement and Region-availability status for the observed account and Region | Does not establish enterprise approval or effective IAM permission for a workload |
| [`ListInferenceProfiles`](https://docs.aws.amazon.com/cli/latest/reference/bedrock/list-inference-profiles.html) | Inference-profile ID/ARN, type, status and referenced model ARNs | Profile identity is a route, not canonical model identity |
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
```

The adapter stores a short-lived private response artefact when policy allows,
computes a digest, extracts only schema-supported facts, and attaches fact-level
JSON Pointers to the evidence record. Discovery opens or updates a MAC issue;
it cannot edit an approved catalogue record.

## AWS route types

- `foundation-model`: a direct Bedrock foundation-model ID or ARN, generally
  invoked in one Region.
- `inference-profile`: an AWS geography, global or application profile used as
  the invocation route. A geography profile may route among several Regions.
- Provisioned, custom and imported model resources require their own adapter
  values and first-party fixtures before they are admitted.

Account IDs, ARNs, Regions and inference-profile references belong in route or
protected discovery configuration. They do not belong in canonical filenames.

## Cross-cloud path comparison

| Concern | AWS Bedrock | GCP Vertex AI | Azure AI Foundry |
|---|---|---|---|
| Model coordinate | AWS model ID and foundation-model ARN | Publisher/model/version | Publisher/format/name/version |
| Invocation coordinate | Direct model ID/ARN or inference-profile ID/ARN | Publisher route or project/location endpoint | Account-child deployment name |
| Administrative scope | Partition, account and Region | Organisation/project and location | Tenant/subscription/resource group/account and location |
| Mutable alias risk | Application profile or provisioned resource | Endpoint/deployed-model binding | Deployment name and account |

Only the common semantics are core: an opaque operator reference, its resource
type, scope, consumption mode and evidence. GCP and Azure syntax must come from
first-party response fixtures before their adapter schemas are implemented.

## Documentation MCP

`.codex/config.toml` pins the official
[`awslabs.aws-documentation-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/aws-documentation-mcp-server)
to `1.2.0` and exposes read-only documentation tools. The dependency is
optional so a clean clone can still validate without network access. A missing
MCP blocks fresh documentation discovery, not deterministic validation of
already captured evidence.
