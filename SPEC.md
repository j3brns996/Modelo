# Modelo v0.1.0 — Model Catalogue Specification

> Status: target contract, not yet an as-built description.
>
> Modelo is a Git-backed approval and publication ledger for AI model
> offerings. It is not a live cloud inventory and it does not replace provider
> APIs, IAM, procurement, Legal review or runtime policy enforcement.
>
> Agents should load `modelo.yaml`, then `docs/contract.yaml`.

## Decision

Use Git for v0.1.0.

Ten to twenty approved changes per working day is comfortably within Git's
mechanical capacity when records are split by identity. The likely constraint
is evidence review, not storage or merging. Live provider discovery may run
more frequently, but its output is an observation: it can open or update an
issue and supply evidence; it cannot approve, revoke or directly rewrite the
catalogue.

No database, application API, bespoke authentication service, audit service or
message bus is justified for v0.1.0. The Git platform supplies identity,
change requests, review, protected branches, CI, static Pages and releases.

Modelo exposes no HTTP or service API. Workflow writes and control-plane
automation use only the selected Git provider API. Cloud provider APIs, CLIs
and MCP tools are read-only evidence sources. Consumers read versioned static
artefacts from Pages, a release or a clone.

## Objective

The catalogue answers:

1. Which named model is being described?
2. Which operator offering is approved for enterprise consumption?
3. Through which provider route can it be consumed?
4. What factual price and capability evidence supports the record?
5. Which versioned enterprise conditions apply?

An approved model record is not, by itself, consumable. Consumption approval
exists only through an approved offering.

## Non-goals

Version `0.1.0` does not:

- represent real-time account entitlements or deployment health;
- infer approval from provider availability;
- provide transactional or row-level access;
- store prompts, usage telemetry or model artefacts;
- normalise every AWS, GCP and Azure resource hierarchy into one invented path;
- make Git history legally immutable or WORM-compliant.

## Authority

| Concern | Executable owner |
|---|---|
| Repository paths, relative public routes and selected host adapter | `modelo.yaml` |
| Entity structure and allowed values | `schemas/` |
| Path, reference, evidence and change rules | Validator |
| Acceptance command | `modelo check` |
| Remote branch, review and publication controls | Platform adapter and host settings |
| Human rationale | `SPEC.md` and ADRs |
| Compact agent context | `docs/contract.yaml` |

`SPEC.md` and `docs/contract.yaml` are checked explanations, not competing
sources of executable truth. A conflict is a defect. It must not be excused by
silently saying that code wins.

## Core concepts

### Model

A canonical, named model release produced by a model vendor or laboratory.
Its identity is independent of the cloud or API host that serves it.

### Offering

An enterprise-approved operator/model relationship. The offering has a stable
internal ID and contains one or more approved provider routes.

### Route

An invocable provider reference plus its scope and consumption mode. Provider
references are opaque to the core schema. AWS, GCP and Azure adapters validate
their syntax and obtain them from first-party read APIs.

### Observation

A time-bounded result from a provider CLI, API, MCP tool or official document.
An observation is evidence, never approval. Failed or missing discovery must
never revoke an offering automatically.

### Condition

A versioned enterprise policy identifier referenced by offerings. Conditions
are structured records, not free-form strings. A reference contains both `id`
and positive integer `version`. A version is immutable once it has ever been
merged or referenced on the protected default branch; changed meaning adds the
next version and migrates offerings through MAC review.

## Source layout

`modelo.yaml` owns these paths. They are shown here for orientation only.

```text
modelo.yaml                          Global bootstrap configuration
AGENTS.md                            Repository-wide agent rules
catalogue/
  models/{model_id}.yaml             Canonical model records
  offerings/{operator_id}/
    {offering_id}.yaml               Stable approved offerings and routes
  evidence/{evidence_id}.yaml        Durable redacted evidence projections
  governance/
    vendors.yaml                     Vendor identities
    operators.yaml                   Operator identities and adapters
    freshness.yaml                   Evidence freshness policy
  policies/conditions/
    {condition_id}/{version}.yaml    Immutable condition versions
schemas/                             Core and provider-adapter schemas
scripts/                             Platform-neutral implementation
tests/                               Unit, fixture and contract tests
site/                                Static HTML, CSS and JavaScript source
dist/                                Untracked deterministic output
docs/
  contract.yaml                      Compact agent context
  adr/                               Architecture decisions
  providers/                         Provider discovery facts
  reviews/                           Dated design reviews
.agents/skills/                      Open Agent Skills workflows
.codex/                              Optional Codex adapter
.kiro/                               Optional Kiro adapter
.github/                             GitHub-only workflow adapter
.gitlab/                             GitLab-only workflow adapter
```

Top-level `models/`, `offerings/`, `governance/` and `data/` are forbidden.
Generated site data belongs in `dist/site/` and is published as a CI artefact;
it is never committed back to the source branch.

## Invariants

### 1. Protected-default-branch presence is approval

Approval applies only to valid records beneath `catalogue/`. It requires a
linked MAC issue, a reviewed change request, required checks and merge to the
protected default branch.

The issue is intake. The merged files and commit are the approved state.

### 2. Stable paths use internal identities

```text
catalogue/models/{model_id}.yaml
catalogue/offerings/{operator_id}/{offering_id}.yaml
```

The offering path does not contain geography, cloud region, account, project,
subscription or a provider's mutable deployment alias. Those values belong in
routes or discovery configuration.

A move that changes identity is an atomic add-new and revoke-old operation. It
is never treated as a cosmetic Git rename.

### 3. Availability is not approval

AWS `AVAILABLE`, a visible Vertex publisher model or an Azure account model
means the provider reports availability in a particular scope. It does not
prove enterprise approval, effective IAM permission, legal acceptance, data
residency suitability or suitability for a workload.

### 4. Every externally sourced assertion has evidence

Every externally sourced leaf in a model, offering or external governance
record must be linked by JSON Pointer to an evidence record. A pointer may name
an ancestor object or array only when every externally sourced leaf beneath it
came from the same evidence record.

Internal IDs and references are validated against repository structure.
Enterprise-authored conditions are approved policy, not claims about an
external source. Evidence envelopes are terminal provenance and do not require
evidence about themselves.

Each evidence record contains:

- an official source URI;
- for first-party API evidence, the exact operation as an additional required field;
- source type;
- observation date and time;
- retrieval method and scope;
- a required digest of its redacted canonical projection.

If a fact cannot be evidenced and tested, omit it. Do not infer context windows,
reasoning support, licensing or approval from model names.

### 5. One fact has one owner

| Fact | Owner |
|---|---|
| Paths and relative site routes | `modelo.yaml` |
| Model identity and evidenced intrinsic facts | Model record |
| Operator route, availability scope and price | Offering record |
| Redacted observation projection and provenance | Evidence record |
| Vendor and operator identity | Governance registry |
| Enterprise condition text and owner | Condition record |
| Field shape and allowed values | Schema |
| Provider resource syntax | Provider adapter schema |
| Approval receipt | Git platform change request and commit |

### 6. Platform semantics stay outside the kernel

The catalogue, schemas, validator, builder and tests use neutral terms:

- issue;
- change request;
- protected default branch;
- required check;
- code-owner review;
- static-site publication;
- protected release.

GitHub pull requests, Actions, Issue Forms and Pages live in `.github/` and the
GitHub adapter. GitLab merge requests, CI, issue templates and Pages live in
`.gitlab/` and the GitLab adapter. Switching host must not require catalogue or
core-schema changes.

### 7. Git is tamper-evident, not absolutely immutable

The portable release receipt contains the source commit, catalogue revision,
manifest digest, validation result, linked issue and change request, and a
protected signed or annotated tag. Host-native immutable releases may strengthen
this on GitHub; they are not a portable WORM guarantee.

### 8. Deterministic input produces deterministic output

The same source tree, source-date epoch, runtime version and locked dependencies
must produce byte-identical catalogue and site artefacts.

### 9. The Git provider is the only workflow API

Modelo has no application API or API gateway. Issues, branches, change
requests, checks, releases and publication are created through the selected Git
provider API. Provider adapters may call cloud APIs only for read-only evidence
collection. Pages and release artefacts are read-only distribution surfaces.

## Model contract

The exact shape belongs to `schemas/model.schema.json`. The minimum record is:

```yaml
id: <stable-canonical-model-id>
vendor_id: <vendor-id>
name: <official-name>
evidence_refs:
  /vendor_id: <evidence-id>
  /name: <evidence-id>
```

Capabilities, modalities, context limits, licence, lifecycle and descriptions
are optional until supported by admissible evidence. A canonical model ID must
identify a named version, not a mutable `latest` alias.

The design follows the strongest idea in
[models.dev](https://github.com/anomalyco/models.dev): separate laboratory model
facts from host-specific serving details. Modelo adds evidence and enterprise
approval semantics that community discovery catalogues do not provide.

## Offering contract

The exact shape belongs to `schemas/offering.schema.json`. The minimum shape is:

```yaml
id: <stable-offering-id>
operator_id: aws
model_id: <stable-canonical-model-id>
routes:
  - id: <stable-route-id>
    operator_reference: <opaque-first-party-reference>
    resource_type: <provider-adapter-value>
    scope:
      kind: region
      values: [<provider-region>]
    consumption: <provider-adapter-value>
pricing: []
condition_refs:
  - id: <condition-id>
    version: 1
evidence_refs:
  /routes/0: <evidence-id>
```

An offering must have at least one valid route to be consumable. Empty pricing
means that no price assertion is made; it does not imply zero or free usage.

### Routes

```yaml
routes:
  - id: <stable-route-id>
    operator_reference: <opaque-first-party-reference>
    resource_type: <provider-adapter-value>
    scope:
      kind: region | geography | global
      values: []
    consumption: <provider-adapter-value>
```

The core validates structure and references. The operator adapter validates
provider-specific values. Route IDs are internal and stable; provider references
may change through an evidenced MAC change.

### Dimensional pricing

Pricing is dimensional from v0.1.0. Two mandatory token-price fields would
either exclude Bedrock image, cache, batch and provisioned prices or encourage
fabrication.

```yaml
pricing:
  - dimension: input
    unit: token
    quantity: 1000000
    amount: "3.00"
    currency: USD
    route_ids: [<route-id>]
evidence_refs:
  /pricing/0: <evidence-id>
```

The schema admits only explicit units and dimensions. Unsupported commercial
terms are omitted and diagnosed; they are never squeezed into an approximate
token price.

### Evidence coverage

```yaml
# catalogue/evidence/{evidence_id}.yaml
id: sha256-<digest-of-canonical-envelope-without-id>
source:
  type: first-party-read-api | official-provider-documentation | official-vendor-documentation
  uri: <official-source-uri>
  operation: <required-for-first-party-read-api>
retrieved_by: cli | mcp | manual
observed_at: <RFC-3339-timestamp>
scope: {}
projection: {}
content_sha256: <lowercase-hex-of-canonical-projection>
visibility: internal
```

Entity `evidence_refs` map JSON Pointers to evidence IDs. One evidence record may
support several facts. CI expands ancestor pointers, checks that every externally
sourced leaf is covered, verifies that pointers resolve, checks the projection
digest, and verifies that the filename and `id` equal the SHA-256 of the
canonical evidence envelope with `id` omitted.

Canonical means: parse the restricted YAML into the JSON data model, omit the
root `id`, serialise with the
[JSON Canonicalization Scheme (RFC 8785)](https://www.rfc-editor.org/rfc/rfc8785),
hash the UTF-8 bytes with SHA-256, and prefix the lowercase digest with
`sha256-`. `content_sha256` applies the same process to `projection` alone.

A referenced evidence record is immutable once it has ever been merged to the
protected default branch. A correction or refreshed observation creates a new
content-addressed evidence ID and migrates fact references through MAC review.

The redacted projection is durable Git source, not an expiring CI artefact. It
contains only the first-party response fields needed to reproduce validation.
Credentials, tokens, private prices, account identifiers and unrelated response
fields are excluded. Private Pages may include redacted internal evidence. A
public or synthetic build may include a fact only if it also includes admissible
public evidence and the reference. Otherwise the builder removes the fact and
its reference together; dangling or unsupported published facts are errors.

## AWS-first provider reasoning

AWS is the first adapter to be implemented because its topology exposes the
mistakes a falsely universal model would make.

| AWS read operation | Facts it can establish | Facts it cannot establish |
|---|---|---|
| `ListFoundationModels` / `GetFoundationModel` | AWS model ID/ARN, provider name, AWS modalities, streaming, customisation types, inference types and lifecycle | Internal approval, context limits, generic reasoning, licence or residency suitability |
| `GetFoundationModelAvailability` | Account/Region agreement, authorisation, entitlement and regional availability observations | Enterprise approval or effective workload permission |
| `ListInferenceProfiles` / `GetInferenceProfile` | Profile identity, type, status and constituent model ARNs | Canonical model identity or enterprise approval |
| `ListFoundationModelAgreementOffers` | Legal-term URL and rate-card dimensions | Internal Legal approval; offer tokens must never be published |
| AWS Price List API | Public price products and dimensions | Private negotiated price unless deliberately queried and protected |

The exact commands and evidence boundaries are documented in
`docs/providers/aws-bedrock.md`.

### Illustrative AWS configuration

The following contains placeholders, not catalogue facts:

```yaml
operator_id: aws
model_id: <canonical-model-id>
routes:
  - id: london-direct
    operator_reference: <bedrock-foundation-model-id>
    resource_type: foundation-model
    scope:
      kind: region
      values: [eu-west-2]
    consumption: managed-on-demand
  - id: eu-cross-region
    operator_reference: <bedrock-inference-profile-id>
    resource_type: inference-profile
    scope:
      kind: geography
      values: [eu]
    consumption: managed-on-demand
```

`uk` is not an AWS inference geography. London is `eu-west-2`. AWS geography
and global inference profiles are distinct routes, not suffixes on canonical
model identity.

## Cross-cloud configuration boundary

| Operator | External model coordinate | Deployment or route coordinate |
|---|---|---|
| AWS Bedrock | `modelId` and AWS-owned foundation-model ARN | Base model ID or inference-profile ID/ARN; discovery is Region and sometimes account scoped |
| GCP Vertex | Publisher/model/version | Managed publisher route or project/location endpoint |
| Azure Foundry | Publisher/format/name/version | Account-child deployment name plus deployment type and region/data zone |

The common model stores an exact opaque external reference, scope, consumption
mode and evidence. Provider adapters define syntax and API mappings. Account,
project, subscription and resource-group coordinates belong in discovery
configuration or protected observations, not canonical paths.

GCP and Azure adapter schemas will be added only from captured first-party API
fixtures. Their differences are documented now; they are not speculated into
the v0.1.0 core.

## Discovery and MAC workflow

```text
Scheduled native CI
  -> read configured provider APIs
  -> retain a redacted canonical evidence projection and digest
  -> compare factual fields with approved state
  -> open or update one MAC issue
  -> human or agent prepares a branch and change request
  -> modelo check
  -> code-owner review
  -> protected-default-branch merge
  -> deterministic Pages artefact and protected release
```

The neutral catalogue operations are `add`, `change` and `revoke`. `move` is an
intake convenience compiled to atomic `add + revoke` in one change request. The
issue captures target identity,
requested outcome, official evidence, observation time, reason and acceptance
criteria. Its mutable body is not authoritative data.

One open MAC is permitted per logical identity. Ordinary changes affect one
identity or one model plus its initial offerings. A batch is allowed only for
one source, observation time, operator and semantic purpose, with a default
limit of 25 identities.

## Git-platform implementation

| Capability | GitHub adapter | GitLab adapter |
|---|---|---|
| Structured intake | Issue Forms | Issue/description templates |
| Change review | Pull request | Merge request |
| Validation | Actions | GitLab CI |
| Concurrency | Merge queue | Merge train |
| Ownership | CODEOWNERS and ruleset | CODEOWNERS and approval rules |
| Publication | Pages Actions artefact | Pages CI artefact |
| Release | Protected tag and release | Protected tag and release |

Pages serves static HTML and JSON only. It has no write API and no custom auth.
If the selected GitHub plan cannot publish a private Pages site, v0.1.0 must use
synthetic/public data or stop at a private CI artefact. It must not acquire an
authentication proxy merely to compensate for a hosting-plan limitation.

`modelo platform check` will verify the remote control profile: protected
default branch, no direct or force pushes, required validation, code-owner
approval, stale-review dismissal, resolved conversations, protected tags and
appropriate Pages visibility. Repository files alone cannot prove those remote
settings are active.

There is no Modelo service endpoint to port. Switching from GitHub to GitLab
changes the platform adapter and `modelo.yaml`; it does not change the core
catalogue, schemas or consumer artefact contract.

## Global bootstrap and clone contract

`modelo.yaml` is the only owner of paths, relative public routes, selected host
adapter and local repository coordinates. CI host variables override local
repository coordinates through the adapter; the YAML contains no `${ENV}`
interpolation and no provider URL templates.

Target clone acceptance, once the executable slice is present:

```bash
git clone <repository-url>
cd Modelo
uv sync --frozen
uv run modelo check
uv run modelo build
```

Codespaces, GitLab Workspaces, Kiro and IDE settings are optional conveniences.
They cannot be required for a clean clone.

## Codex, agents and plugins

Codex Work is suitable as the planner and coordinating implementation agent,
not as the planning system of record or an approval authority.

- The MAC issue records intent and acceptance criteria.
- Read-only specialist agents may research independent questions in parallel.
- One root agent owns writes.
- Every write receives targeted validation; `modelo check` runs before hand-off.
- The platform change request exposes the diff for human review.

`AGENTS.md` and `.agents/skills/` are the portable workflow layer. Skills follow
the open Agent Skills format. `.codex/` and `.kiro/` are optional adapters and
must not redefine catalogue rules.

The project-scoped Codex configuration declares the official AWS Documentation
MCP server as a pinned, read-only dependency. Hosted ChatGPT Work does not load
local MCP configuration; it needs an installed plugin. Either route may gather
evidence, but neither is a source of approval.

## Validation contract

One command, `modelo check`, owns acceptance. Its externally visible outcomes
are:

1. `schema-and-facts`: schema, path, reference and evidence validation;
2. `tests`: unit and fixture tests;
3. `build-and-site`: deterministic catalogue and static-site build with smoke tests;
4. `release-and-clean-tree`: release-contract and clean-tree verification.

Lint, dependency lock, secret scanning and document-drift checks are internal
stages of those outcomes, not eleven independently promised products. A control
is blocking or it is explicitly outside the baseline; an advisory security gate
must not be advertised as enforcement.

The implementation must distinguish root errors from suppressed dependent
checks. If a vendor registry is invalid, vendor-reference checks may be skipped
to reduce noise, but the original error still fails the run.

## No-technical-debt contracts

No workaround, compatibility shim, duplicate rule, placeholder field or
deferred control enters `main` without an issue or ADR containing owner,
rationale, removal condition, target version and a test that exposes its
continued presence.

The initial explicit contracts are:

- **Fact:** every external assertion has evidence or is omitted.
- **Observation:** discovery cannot write approved state.
- **Change:** every catalogue diff links to one MAC issue and reviewed change request.
- **Identity:** identity changes are migrations, not silent moves.
- **Batch:** one source, time, operator and semantic purpose.
- **Generated output:** reproducible, uneditable and tied to a source commit.
- **Automation:** issue conversion is idempotent.
- **Platform:** core code contains no GitHub or GitLab URL logic.
- **Schema:** shape changes include compatibility, migration and rollback.
- **Audit:** claim tamper evidence, not WORM immutability.
- **Exit:** measure when Git stops fitting.

## Sustainability exit criteria

Review the architecture after 90 days. Move live operational state to an event
or database service, while retaining Git for approved releases, if any two of
these persist for four weeks:

- more than 50 accepted changes per working day;
- repeated peaks above 10 changes per hour with a sub-hour publication SLA;
- more than 10% of catalogue changes require conflict resolution;
- p95 issue-to-publication exceeds one business day while review utilisation is below 70%;
- p95 validation exceeds five minutes or publication exceeds ten minutes;
- more than 5% of changes bypass the standard workflow;
- the same logical identity normally changes more than once per day;
- consumers require transactional queries, row-level access or live state;
- the supported baseline clone exceeds 60 seconds because of retained data.

Until those conditions exist, adding services would be anticipatory complexity,
not architecture.
