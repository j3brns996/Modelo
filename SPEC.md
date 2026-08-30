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
2. Which inference-service offering is approved for enterprise consumption?
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

An enterprise-approved inference-service/model relationship. The offering has a stable
internal ID and contains one or more approved provider routes.

### Route

An invocable provider reference plus provider-owned invocation coordinates and
consumption mode. The inference-service registry is the sole owner of the
adapter; routes never repeat it. Provider references are opaque to the core.
The first implemented provider schema is AWS Bedrock.

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
  offerings/{inference_service_id}/
    {offering_id}.yaml               Stable approved offerings and routes
  evidence/{evidence_id}.yaml        Durable redacted evidence projections
  governance/
    vendors.yaml                     Vendor identities
    inference-services.yaml          Inference-service identities and adapters
    freshness.yaml                   Evidence freshness policy
    actors.yaml                       Eligible agent actors; empty means disabled
  policies/conditions/
    {condition_id}/{version}.yaml    Immutable condition versions
schemas/                             Core and provider-adapter schemas
tooling/modelo/                      Locked platform-neutral Python package
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
Generated site data belongs in the configured candidate/final `dist/` roots
and is published as a CI artefact; it is never committed to the source branch.

`uv.lock` governs runtime dependency sync and `uv run --locked`; it is not a
package-build option. The tooling distribution uses
`uv build --offline --no-cache`. `pyproject.toml` pins the PEP 517 backend to
`uv_build==0.11.33` and requires bootstrap `uv==0.11.33`. Catalogue and site
publication remains `uv run --locked modelo build ...` and is a separate output.

## Invariants

### 1. Protected-default-branch presence is approval

Accepted catalogue records beneath `catalogue/` require a linked MAC issue, a
reviewed change request, required checks and merge to the protected default
branch. Only a current offering grants consumption; accepted evidence,
conditions, models and governance records grant no consumption by themselves.

The issue is intake. The merged files and commit are the approved state.

### 2. Stable paths use internal identities

```text
catalogue/models/{model_id}.yaml
catalogue/offerings/{inference_service_id}/{offering_id}.yaml
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

Schemas classify leaves with `x-modelo-provenance` (`external`, `internal` or
`policy`) and, where applicable, `x-modelo-freshness-class`. Every external leaf
must link to an evidence record and projection pointer. CI resolves both
pointers and requires canonical deep equality. Transformed claims are deferred.

Internal IDs and references are validated against repository structure.
Enterprise-authored conditions are approved policy, not claims about an
external source. Evidence envelopes are terminal provenance and do not require
evidence about themselves.

Each evidence record contains:

- for documentation, an official HTTPS URI;
- for first-party API evidence, provider, service, exact operation, partition,
  Region, sanitised parameters and an official documentation URI;
- source type;
- observation date and time;
- retrieval method and scope;
- a redacted canonical projection.

If a fact cannot be evidenced and tested, omit it. Do not infer context windows,
reasoning support, licensing or approval from model names.

### 5. One fact has one owner

| Fact | Owner |
|---|---|
| Paths and relative site routes | `modelo.yaml` |
| Model identity and evidenced intrinsic facts | Model record |
| Inference-service route, availability scope and price | Offering record |
| Redacted observation projection and provenance | Evidence record |
| Vendor and inference-service identity | Governance registry |
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

The portable release receipt contains base, source and merge commits; explicit
`as_of`; contract, tool and lock versions; catalogue, site and manifest digests;
the exact CI result; linked issue and request; and change delta. Approval
evidence includes reviewer platform identity, approved head SHA, approval time,
actors-registry digest, independence/eligibility result and provider
approval/check reference; stale-head, self-authored or ineligible approval is
invalid. The
portable release is a protected annotated `catalogue-YYYYMMDD.N` tag at the
exact merge commit. Optional signatures may strengthen it.

### 8. Deterministic input produces deterministic output

The same source tree, exact source-commit author timestamp, explicit `as_of`,
effective site base URL/path, runtime version and locked dependencies must
produce byte-identical catalogue and site artefacts.

The exact source commit and its tree are inputs. The required explicit source
epoch must equal that commit's author timestamp expressed as non-negative whole
Unix seconds; arbitrary overrides, environment reads, filesystem mtimes and
committer time are forbidden. T5 resolves the explicit source commit locally
and rejects any epoch mismatch. For final, the source commit remains the
accepted head; T8 may record the merge timestamp separately in the release
receipt, but it is not a build epoch. T5 receives the
commit, tree, `as_of`, epoch,
validated MAC metadata, publication profile, base URL and base path explicitly;
it performs no provider or Git-host API reads.

For a local candidate build, the explicit base URL may be `null` and links are
resolved from `base_path`. Trusted CI and every final build must supply and
receipt-bind an absolute HTTPS base URL; the adapter may not infer it from an
untrusted change.

A non-null base URL is canonical: lowercase DNS host, implicit HTTPS port 443
(no explicit port), no userinfo/query/fragment, normalised path segments, and a
required trailing slash. Its URL path must equal the normalised `base_path`
exactly: `/` pairs with `https://host/`, and `/Modelo/` pairs only with
`https://host/Modelo/`. T8 enforces this cross-field equality after schema
validation.

### Build and receipt wire contract

T8 is the sole producer of the bounded same-repository adapter envelope
validated by `schemas/mac-metadata.schema.json`. The `--mac-metadata` value is
an explicit file path, not JSON text or another schema input. T5 reads one
regular non-symlink file once, with a 262144-byte ceiling, strict UTF-8 JSON
object parsing, duplicate-key/float/non-finite/YAML rejection and stable
before/after device, inode, size and nanosecond-mtime checks. Trusted CI fails
closed if no-follow or stable identity checks over device, inode, mode/type,
size, nanosecond mtime and nanosecond ctime cannot be enforced; a local
candidate cannot produce accepting durability without them. T8 may stage
the file outside the repository but never behind a network read. The envelope contains canonical repository and open issue
identity, exact base/head/head-tree SHAs, the complete neutral MAC payload, its
SHA-256 over RFC 8785 UTF-8 bytes plus one LF, and canonical expected change
delta. T5 validates the envelope and payload, URL/repository binding, the three
explicit Git flags, affected identities and exact computed Git paths and blob
digests. It performs no provider read, supplies no missing fact and rejects all
mismatches. Vendor and inference-service identities are the exact changed keys
from canonical base/head registry-map comparison, so one registry-file delta
may bind a homogeneous batch while missing or extra subjects fail. Other kinds
retain per-record path identity. Revoke/move `reason` and `effective_at` come
only from expected delta. Move replacement is required and equals its
destination path; standalone revoke replacement is optional but, when present,
is a distinct offering path existing in the exact head. Nothing is inferred
from deletion, prose or the clock.

`schemas/catalogue-output.schema.json` defines the sole JSON serialisation of
validated catalogue state. T5 emits RFC 8785 UTF-8 bytes followed by exactly
one LF. SHA-256 always covers those exact emitted bytes, including the LF.
Object members use RFC 8785 ordering. Before serialisation T5 sorts models by
`id`; offerings by `(inference_service_id, id)`; evidence by `id`; conditions
by `(id, version)`; model capabilities and modalities by ASCII ID; offering
routes by `id`; route destinations by `destination_pointer`; pricing by
`(dimension, unit, quantity, amount, currency, joined sorted route_ids)`;
`route_ids` by ID; and condition references by `(id, version)`. Every object
array then uses its RFC 8785 canonical JSON bytes as the final bytewise
tie-breaker; ID arrays and `route_ids` are schema-unique. Thus every key is
total even before semantic duplicate-identity validation. When routes or
pricing move, T5 deterministically rewrites the corresponding JSON Pointer keys
in `evidence_refs` before RFC 8785 orders that object. Evidence projection
arrays retain source order because provider order can be meaningful; that order
is therefore part of the evidence fact, not an unordered set.

Canonical change-delta order is operation rank `add`, `change`, `revoke`,
`move`, then primary path (ordinary `path`, or move source path), move
destination path, `before`, then `after`, and finally the complete delta's RFC
8785 canonical JSON bytes, all compared bytewise with a missing component equal
to the empty string. These rules apply before both
receipt serialisation and digesting; two otherwise-valid permutations cannot
produce different canonical bytes. T6 consumes that projection and adds HTML, local
assets and schema copies; it must not independently serialise raw or private
catalogue state.

T5 candidate output targets `dist/candidate/` and contains exactly
`site/data/catalogue.json`, `site/data/change-delta.json` and
`site/data/manifest.json`. Change delta is the RFC 8785 canonical expected
delta array plus one LF; its SHA-256 covers those exact bytes. The candidate
manifest excludes itself and lists exactly catalogue and change delta. Receipt
primitives remain library values; T8 alone writes detached
`dist/receipts/check.json`. T5 rejects final builds. T6 later extends the same
projection into `dist/final/`; it may not create a second raw serialisation.

Each invocation exclusively creates `dist/.modelo-build.lock` or fails fast;
it never waits. The lock contains a bounded, fsynced phase journal. Staging is
a same-filesystem sibling under target parent `dist`: candidate uses
`dist/candidate.<128-bit-CSPRNG-hex>.staging` and
`dist/candidate.<same-id>.backup`; final uses the corresponding `final` names.
Each path is created exclusively; collision retries create a fresh ID. After every
file is closed, eligible builds fsync files and directories, validate the
complete staged tree, rename an existing target to an invocation-specific
backup, rename staging to target, fsync the parent, verify the promoted target,
remove the backup, fsync the parent and release the lock. A handled failure
restores the backup before cleanup. A crash leaves the journal and lock; the
next build fails closed until an explicit recovery verifies recorded digests
and performs the single unambiguous restore/cleanup action. Ambiguous states
require manual recovery and never delete either complete candidate.

Two renames are not a global atomic transaction. The observable contract is
therefore precise: a reader may see the complete old target, the complete new
target or a temporarily absent target, but never a partially written target.
Pages/release deployment reads only after successful promotion. Final and CI
acceptance builds require file and directory fsync support; an incapable
filesystem/platform fails closed. A local candidate may record
`process-atomic-only`, but cannot produce an accepting check receipt.

`schemas/build-manifest.schema.json` defines the complete publication manifest.
Its `files` map hashes every emitted publication file except the manifest
itself. File digests are SHA-256 of exact bytes. `publication_digest` is
SHA-256 of the concatenation, in UTF-8 bytewise path order, of one record per
file: path, NUL, lowercase `sha256:<hex>`, NUL, base-10 byte size, LF. The
manifest digest is SHA-256 of its RFC 8785 UTF-8 bytes plus one LF. This removes
recursive and archive-metadata ambiguity.

T6's executable completeness check requires `files` keys to equal, not merely
contain, the fixed inventory in `docs/contract.yaml` (base routes, local assets,
canonical catalogue, canonical change delta and every schema file beneath the
configured schema root at the exact source commit) union one model detail page
per projected model and one offering detail page per projected offering. The
manifest itself is excluded. Missing required files, missing projection-derived
pages and undeclared extra files all fail; schema validation alone is not the
completeness arbiter.

`schemas/check-receipt.schema.json` is the detached pre-merge envelope. T8,
not T5, supplies trusted Git-provider workflow identity, run and exact-head
result and assembles it. Its digest is SHA-256 of the RFC 8785 serialisation of
the complete receipt plus exactly one LF. T8 validates equality between the
receipt and trusted inputs for repository identity, current base/head/head-tree,
`as_of`, source epoch, profile, canonical base URL/path, validated MAC issue and
payload, canonical delta, named artefact paths/digests, tool/lock and actor
registry digests, plus CI provider, workflow identity, run ID, check name and
successful result. It also requires `ci.head_sha == head_sha` and
`ci.provider == repository.provider`. Missing or unequal input is an error; there is no
field-by-field fallback.

A change request has no final receipt. Post-merge CI dereferences the accepted
check receipt by its canonical-byte digest; requires release `source_sha`, CI
`head_sha` and approval `approved_head_sha` to equal the accepted head; requires
release base and head-tree to equal the accepted values; and requires
`merge_tree_sha == head_tree_sha`. Repository, `as_of`, epoch, profile, base
URL/path, MAC delta, tool/lock digest, workflow identity and catalogue artefact
name/digest must remain equal. Publication and manifest names remain fixed but
their digests may differ only because the final build adds merge-history
content; those are the only final-only digest exceptions. Post-merge CI
proves the merge tree equals the accepted head tree, validates the final
publication once, creates the detached release receipt, and deploys those exact
bytes without rebuilding.

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
  /name:
    id: <evidence-id>
    projection_pointer: /modelName
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
inference_service_id: aws-bedrock
model_id: <stable-canonical-model-id>
routes:
  - id: <stable-route-id>
    source_region: <aws-request-region>
    reference: <opaque-first-party-reference>
    model_binding:
      kind: foundation-model
      model_evidence:
        id: <evidence-id>
        id_pointer: /modelId
        arn_pointer: /modelArn
        name_pointer: /modelName
        provider_pointer: /providerName
pricing: []
condition_refs:
  - id: <condition-id>
    version: 1
evidence_refs:
  /routes/0/reference:
    id: <evidence-id>
    projection_pointer: /modelId
```

An offering must have at least one valid route to be consumable. Empty pricing
means that no price assertion is made; it does not imply zero or free usage.

### Routes

```yaml
routes:
  - id: <stable-route-id>
    reference: <opaque-first-party-reference>
    <provider-owned-invocation-coordinate>: <value>
    model_binding: <provider-owned-object>
```

The core validates structure and references. It resolves
`inference_service_id` through `governance/inference-services.yaml` and dispatches
the provider validator at runtime by that registry's `adapter`; an alias service therefore
uses the same provider rules. v0.1 has a static AWS-only route schema, not a
runtime plug-in union. Unknown services and unsupported adapters fail closed.
Route IDs are internal and stable; provider references may change through an
evidenced MAC change.

For an AWS system inference profile, the adapter-owned object contains the
profile evidence reference and one entry per destination:

```yaml
model_binding:
  kind: system-inference-profile
  profile_evidence:
    id: <profile-evidence-id>
    projection_pointer: /profileId
    type_pointer: /type
    status_pointer: /status
    destinations_pointer: /models
  destinations:
    - destination_pointer: /models/0/modelArn
      model_evidence:
        id: <foundation-model-evidence-id>
        arn_pointer: /modelArn
        name_pointer: /modelName
        provider_pointer: /providerName
```

CI requires `SYSTEM_DEFINED`, `ACTIVE`, and a complete one-to-one binding of
every reported profile destination. Each destination ARN equals its explicit
model `arn_pointer`; that ARN's partition and Region equal the destination's
`GetFoundationModel` evidence source. The reported model and provider names
equal the canonical model name and governed vendor name. All references are
explicit; the validator never searches globally for plausible evidence.

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
  /pricing/0:
    id: <evidence-id>
    projection_pointer: /price
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
visibility: internal
```

Entity `evidence_refs` map fact JSON Pointers to an evidence ID and a projection
JSON Pointer. One evidence record may support several facts. CI uses schema
provenance annotations to check coverage, verifies both pointers, requires
canonical deep equality and verifies that filename and `id` equal the SHA-256
of the canonical evidence envelope with `id` omitted.

Canonical means: parse the restricted YAML into the JSON data model, omit the
root `id`, serialise with the
[JSON Canonicalization Scheme (RFC 8785)](https://www.rfc-editor.org/rfc/rfc8785),
hash the UTF-8 bytes with SHA-256, and prefix the lowercase digest with
`sha256-`.

A referenced evidence record is immutable once it has ever been merged to the
protected default branch. A correction or refreshed observation creates a new
content-addressed evidence ID and migrates fact references through MAC review.

The redacted projection is durable Git source, not an expiring CI artefact. It
contains only the first-party response fields needed to reproduce validation.
Credentials, tokens, private prices, account identifiers and unrelated response
fields are excluded. v0.1 builds the public synthetic profile only from
`tests/fixtures/build/synthetic` and the private profile only from `catalogue`.
The former belongs to T5; missing future T6 publication fixture paths are never
substituted. Production field-level
redaction is deferred because removing facts can silently change meaning.

YAML date and timestamp scalars remain strings. Evidence projections admit only
signed 64-bit integers or decimal strings for numbers; binary floating point and
non-finite values are forbidden so RFC 8785 hashes remain portable.

### Freshness

`as_of` is an explicit UTC date recorded in every check and receipt. A fact is
stale only when `as_of - date(observed_at in UTC)` is greater than its class
threshold: availability 30 days, pricing 90 days and intrinsic model facts 365
days. Equality is fresh; a future observation is an error. Staleness fails the
next change check or scheduled main audit but never auto-revokes an offering.
The scheduled audit checks `base=head=main` with the current explicit UTC date.

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

`GetFoundationModelAvailability` is discovery-only in v0.1 and is not retained
as catalogue evidence. Other account-scoped observations use a non-secret,
non-reversible opaque `scope_ref`; account aliases, IDs and fingerprints are not
stored.

AWS routes must also bind to the offering's canonical `model_id`. A direct route
requires its reference to equal the evidenced model ID/ARN, then requires the
reported model name and provider name to equal the canonical model name and
governed vendor name. Every route carries one internal `source_region`: the AWS
request Region, not a geography label or a profile destination. It is also the
processing Region only for a direct route; a profile is processed in its
explicit evidenced destination Regions. `source_region`
must equal the Region of explicit AWS Bedrock `Get`/`List` evidence for that
route. ARN forms must also agree with the evidence partition and Region. A
system inference profile retains every destination model ARN; CI resolves each
through evidenced `GetFoundationModel`/`ListFoundationModels` facts in the
destination Region and requires a complete one-to-one set bound to that same
canonical model. This proves the observed route shape, not entitlement, quota,
health or effective workload permission. Mappings needing transformation are
deferred.

The generic `/routes/{index}/reference` fact link must be the same explicit
binding evidence: direct routes use the matching model ID/ARN pointer and
profiles use the profile reference pointer. A newer documentation record cannot
mask stale or mismatched first-party route-binding evidence.

### Illustrative AWS configuration

The following contains placeholders, not catalogue facts:

```yaml
inference_service_id: aws-bedrock
model_id: <canonical-model-id>
routes:
  - id: london-direct
    source_region: eu-west-2
    reference: <bedrock-foundation-model-id>
    model_binding:
      kind: foundation-model
      model_evidence: <explicit-evidence-binding>
  - id: eu-cross-region
    source_region: eu-west-2
    reference: <bedrock-system-inference-profile-id>
    model_binding:
      kind: system-inference-profile
      profile_evidence: <explicit-profile-evidence-binding>
      destinations: [<complete-explicit-destination-bindings>]
```

`uk` is not an AWS inference geography. London is `eu-west-2`. AWS geography
and global inference profiles are distinct routes, not suffixes on canonical
model identity. The same profile invoked from two source Regions is represented
by two route IDs, so pricing and evidence remain bound to the callable regional
coordinates. Duplicate `(source_region, kind, reference)` routes are invalid.

## Cross-cloud configuration boundary

| Inference service | External model coordinate | Deployment or route coordinate |
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

The neutral operations are `add`, `change`, `revoke`, `move` and `batch`.
`change` preserves identity. In v0.1, move and revoke apply only to offerings;
move compiles to atomic add-destination and revoke-source. A batch declares one
homogeneous `item_operation` (`add`, `change` or `revoke`). The issue contains a
schema-valid neutral payload whose canonical
digest is bound into the change request and release receipt.

A dedupe key hashes a typed sorted identity reservation set, effective
operation and purpose. An idempotency key hashes the full canonical intent.
Both use RFC 8785 with hash fields omitted; idempotency also omits random
`request_id`. Exact retries
return the existing issue; a conflicting open reservation fails closed. Move
reserves source and destination. A batch reserves at most 25 identities and has
one source, observation scope, inference service and purpose. Candidate issue
evidence is never accepted catalogue evidence. See `docs/mac-contract.md`.

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
The current personal GitHub repository cannot satisfy the private Pages
capability. It therefore publishes only the synthetic fixture profile to public
Pages, or stops at a restricted CI/release artefact for the private catalogue.
It must not acquire an
authentication proxy merely to compensate for a hosting-plan limitation.

The site route resolver receives the configured repository web base, neutral
commit/issue/change-request/tag/release route templates, MAC intake routes, and
effective `base_url`/`base_path`. CI may override local repository coordinates
only through the selected adapter; the effective values are receipt-bound.
`/changes/` is generated without network access from local Git first-parent
history plus validated base/head deltas. Release receipts are detached release
assets, not recursive site inputs.

`modelo platform check` will verify the remote control profile: protected
default branch, no direct or force pushes, trusted exact-head validation,
independent approval, stale-review dismissal, resolved conversations, protected
tags and appropriate Pages visibility. Human CODEOWNER approval is mandatory
for every path except the positive agent-approval allowlist
(`catalogue/models/**`, `catalogue/offerings/**`, `catalogue/evidence/**`);
agent approval is disabled by default. It can be enabled only when
`catalogue/governance/actors.yaml` registers an enabled actor with a distinct
platform identity and data-only scope, the reviewer is independent of author,
committer and last pusher, and the current exact head has a successful trusted
check receipt whose repository/base/head and actor-registry digest still match.
T8 computes the complete base/head changed-path set and permits agent approval
only when every path matches one of those three data allowlist patterns; one
schema, tooling, lock, configuration, governance, publication, workflow,
template, skill or documentation path makes the entire change human-only.
Control-plane changes always require a human CODEOWNER. The
topic branch must be up to date
with the protected base, and a merge queue/train is deferred until it has a
candidate-tree contract. Repository
files alone cannot prove those remote settings are active.

GitLab must enforce the trusted pipeline through a Pipeline Execution Policy or
an equivalent control outside change-request authors' control. If that cannot
be proved, `modelo platform check` reports the repository incapable rather than
accepting project-local CI.

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
uv sync --locked
uv run --locked modelo check --base <protected-base-sha> --head <head-sha> --as-of <YYYY-MM-DD>
uv run --locked modelo build --kind candidate \
  --base-commit <base-sha> --source-commit <head-sha> --source-tree <head-tree-sha> \
  --as-of <YYYY-MM-DD> --source-date-epoch <author-unix-seconds> \
  --mac-metadata <validated-mac.json> --profile synthetic \
  --no-base-url --base-path /Modelo/ --output dist/candidate
```

T5 implements exactly those build inputs. `--kind`, `--base-commit`, `--source-commit`,
`--source-tree`, `--as-of`, `--source-date-epoch`, `--mac-metadata`,
`--profile`, `--base-path` and `--output` are required. Exactly one of
`--base-url <canonical-https-url>` or candidate-only `--no-base-url` is
required. T5 accepts only `--kind candidate`; final fails closed until T6. The CLI validates that the
explicit base is the comparison base and the source commit resolves to the explicit tree and timestamp; it never
infers HEAD, environment values, output, MAC metadata or publication settings.
The explicit output is not freely selectable: candidate must equal the
configured repository-relative `candidate_root` (`dist/candidate`) after safe
resolution. T6 will require final to equal `final_root` (`dist/final`). An
absolute, traversing or symlinked path, any alternative directory, or an output
inside catalogue, schema, fixture, template, asset or other input roots fails.
T8 supplies the exact configured value for the requested kind.
T6 will add final builds with explicit `--merge-commit` and `--merge-tree`,
merge-tree equality and the accepted source epoch unchanged.

T8 invokes the candidate build with the trusted provider's base/head/tree,
the explicit path to validated bounded MAC metadata, explicit epoch/profile/base URL/path and a
fresh candidate output path, then hashes that exact result. T5 does not perform
the post-merge final build; that interface remains deferred to T6.

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
the open Agent Skills format. They guide authors and reviewers; CI may lint
their metadata but never executes skill prose or treats agent output as
acceptance. `.codex/` and `.kiro/` are optional adapters and must not redefine
catalogue rules. `npx` may be an optional skill-import convenience, never a
required build or CI runtime.

Skills participate before the build: an author or reviewer invokes a skill to
prepare or inspect repository source, then the ordinary locked `modelo check`
validates that source. CI never executes skill prose, and build output must be
identical when `.agents/skills/` is absent.

The project-scoped Codex configuration declares the official AWS Documentation
MCP server as a pinned, read-only dependency. Hosted ChatGPT Work does not load
local MCP configuration; it needs an installed plugin. Either route may gather
evidence, but neither is a source of approval.

## Validation contract

One change-aware command, `modelo check --base BASE --head HEAD --as-of DATE`,
owns pre-merge technical acceptance. Its externally visible outcomes are:

1. `schema-and-facts`: schema, path, reference and evidence validation;
2. `tests`: unit and fixture tests;
3. `build-and-site`: deterministic catalogue and static-site build with smoke tests;
4. `receipt-and-clean-tree`: release-contract simulation and clean-tree verification.

The trusted final `modelo/check` job runs even when dependencies fail and
explicitly rejects missing, skipped, neutral, cancelled, stale or failed
prerequisites. Its receipt binds the exact base/head, trusted workflow identity,
tool/lock digests, test results and built artefacts. Post-merge publication then
proves the merge tree equals the accepted, up-to-date head tree, builds the final
merge-aware site/release artefact once, validates that exact artefact, creates a
detached receipt that hashes it, and deploys without another build. The receipt
is not inside the artefact whose digest it records. Pre-merge and post-merge
artefacts are not claimed to be byte-identical.

T6 owns static no-JavaScript navigation, link integrity, inert-XSS fixtures,
publication non-leakage and accessibility-structure tests. T8 owns pinned
Python-controlled browser execution outside the deterministic core build
runtime. T10 records human keyboard and screen-reader launch evidence. None
requires Node, npm or `npx`.

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
- **Batch:** one source, time, inference service and semantic purpose.
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

## Implementation and verification

The detailed static-site, MAC, security and staged implementation contracts are
`docs/site-contract.md`, `docs/mac-contract.md`,
`docs/security-contract.md` and `docs/implementation-plan.md`. The dated
repository comparison is
`docs/reviews/catalogue-repositories-2026-08-30.md`; the pinned Addy Osmani
skills decision is `docs/reviews/agent-skills-2026-08-30.md`.

No implementation swarm starts until those contracts and `modelo.yaml` agree.
No production catalogue launches until the executable validator, schemas,
fixtures, templates, GitHub/GitLab adapters, synthetic Pages build, protected
host controls, release receipt and mirror-restore rehearsal all pass.

Implementation status at this contract revision: T1, T2, T3, T4 and T7 are
implemented and independently gated. The accepted T4 head is
`76b6fe8f3e74a34299851b6bae9411c719154e9d`. T5, T6, T8, T9 and T10 remain
unimplemented; no static site or trusted CI is deployed and agent approval is
disabled.
