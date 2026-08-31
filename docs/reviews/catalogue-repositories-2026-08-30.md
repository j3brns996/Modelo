# Catalogue repository review — 2026-08-30

## Verdict

`openmodels.run` is the closest conceptual and UX reference, but it is not a
reproducible or sufficiently governed implementation reference for Modelo. The
best small design combines its model/provider/mapping split with stronger
evidence, a locked Python build, deterministic static Pages and neutral Git-host
adapters.

All observations below are pinned to a commit on 30 August 2026. Repositories
are references, not fact authorities, and no unlicensed data or code is copied.

## Primary reference: OpenModels

Pinned source: [`openmodelsrun/openmodels@7201e945`](https://github.com/openmodelsrun/openmodels/tree/7201e9452323461862f16394497a8a64313d35fb),
version `1.10.0`, commit dated 27 August 2026.

| Concern | Finding | Modelo decision |
|---|---|---|
| Entities | One YAML per canonical model, provider and provider/model mapping, with three JSON Schemas | Adopt granular separation; adapt mapping into an approved offering with provider routes |
| Validation | YAML, Draft 7 Schema, duplicate/reference/path checks in a GitHub PR gate | Add restricted loading, stable diagnostics, exact-head trusted CI and base/head checks |
| Pricing | Mapping-owned token/cache/image/audio/reasoning fields | Use explicit dimensional components; pricing may be absent rather than invented |
| Provenance | No `source`/`sources` field was found in the 400 registry YAML records reviewed | Reject as an evidence model; Modelo binds external facts to immutable evidence projections |
| Freshness | Mapping `updated_at` is used as a price-review proxy | Reject; modification and observation are different events |
| Runtime | Merge ingests records into a platform database serving a site/API and telemetry | Reject API, database, accounts and live services |
| Reproducibility | No root licence, dependency lock, release artefact, manifest or receipt | Do not copy; require locked tools and deterministic receipts |
| CI security | Mutable action tags and unfrozen Python dependencies | Use full action SHAs, image digests, least permissions and `uv.lock` |

Primary evidence: [README](https://github.com/openmodelsrun/openmodels/blob/7201e9452323461862f16394497a8a64313d35fb/README.md),
[validator](https://github.com/openmodelsrun/openmodels/blob/7201e9452323461862f16394497a8a64313d35fb/validate_registry.py),
[mapping schema](https://github.com/openmodelsrun/openmodels/blob/7201e9452323461862f16394497a8a64313d35fb/schemas/mapping.schema.json),
[freshness script](https://github.com/openmodelsrun/openmodels/blob/7201e9452323461862f16394497a8a64313d35fb/check_pricing_freshness.py) and
[validation workflow](https://github.com/openmodelsrun/openmodels/blob/7201e9452323461862f16394497a8a64313d35fb/.github/workflows/validate-registry.yml).

### Site-to-source gap

The public site is a useful UX reference but not a verified static-build source:

- [openmodels.run](https://www.openmodels.run/) reported 136 models, 52
  providers and 209 mappings;
- the pinned registry README reported 138, 52 and 209;
- [the documentation](https://docs.openmodels.run/) reported 117, 51 and 185;
- the public organisation exposed registry, docs, CLI, skills and MCP
  repositories, but no verifiable website application source;
- the README says merged data is ingested into a platform database.

Modelo adopts immediate search, model/provider separation, faceted browse,
detail/provider comparison and stable routes. It does not claim OpenModels'
site implementation is reproducible, and does not adopt live telemetry,
ranking, quick-start inference, accounts, API or service stack.

## Comparative matrix

| Repository | Licence | Strength to adapt | Weakness to avoid | Decision |
|---|---|---|---|---|
| [models.dev `5b087ae`](https://github.com/anomalyco/models.dev/tree/5b087ae043b7de0ef823c916ac96595c9bbd1365) | MIT | Model/provider separation, per-model TOML, isolated provider sync PRs and source-authority rules | Bun/SST/Cloudflare app, dynamic API, secondary sources and absence-driven deletion | Adapt automation/source authority only |
| [TrueFoundry Models `16b6718`](https://github.com/truefoundry/models/tree/16b67189217bd720050ba4e9c4f0b6ed92004b8f) | MIT | Per-provider/model YAML, regional price rows, source URLs and CUE validation | No canonical model/provider split, S3 delivery and GitHub-specific bots | Adapt price/source/schema ideas |
| [Portkey Models `cfa78cd`](https://github.com/Portkey-AI/models/tree/cfa78cd5357c33ae8b247dbe6cf5a2f7d42e1127) | MIT | Rich pricing vocabulary and provider coverage | Large provider JSON, weak CI, source URLs outside data and S3/gateway coupling | Reject structure; consult vocabulary |
| [Ferro Model Catalog `9650b3d`](https://github.com/ferro-labs/model-catalog/tree/9650b3d384582516e4dc801bf8080ec4c20f2618) | Apache-2.0 | Hashes, Sigstore manifest, immutable release URLs, provider slices and deployment verification | Complex Go stack, secondary scrapers and a second generated-output PR queue | Adapt receipt/release; simplify |
| [LiteLLM `5e4b383`](https://github.com/BerriAI/litellm/tree/5e4b3838aabf00d135be800404d03728c8afa506) | MIT outside `enterprise/` | Broad price/capability vocabulary and many source URLs | 55,039-line shared JSON, duplicated backup and gateway-product coupling | Cross-check/vocabulary only |
| [Kubeflow Hub `ba769e1`](https://github.com/kubeflow/hub/tree/ba769e15afdc6faf34e4aa13e273c87c99c351e1) | Apache-2.0 | Configured read-only source descriptors and discovery boundaries | REST/BFF/React/Kubernetes service runtime for a different problem | Adapt source descriptors only |

## Sustainability and portability

Per-identity files used by OpenModels, models.dev, TrueFoundry and Ferro suit
10–20 approved daily changes because unrelated records rarely conflict. Avoid
Portkey/LiteLLM shared files, a shared automation branch and Ferro's mandatory
second generated-output PR. One provider/discovery proposal stream per logical
scope may update an open unapproved branch; after approval, every new commit
invalidates CI and review.

All reviewed projects are operationally GitHub-coupled. Modelo therefore keeps
one platform-neutral CLI and confines host differences to CI, Pages,
issue/change-request templates and release publication. It uses no S3,
Cloudflare, ingestion database or application API.

No reviewed project supplies the complete required site. OpenModels has the
best UX but an unverifiable site build; models.dev has a same-repo application
but non-portable hosting; Ferro verifies publication but exposes JSON rather
than a human catalogue. Modelo must implement and test its own deterministic
`site/` contract.

## Composite decision

Adopt per-record canonical models, inference services, offerings and provider
routes; provider-attached pricing; strong schema/reference checks; provider
slices; a hash receipt; post-publication verification; and isolated observation
proposals.

Reject application APIs, telemetry and ingestion services, shared monolithic
JSON, absence-driven revocation, secondary-source consensus as approval,
mutable tool versions, unlicensed reuse, committed generated output and hidden
provider assumptions.

