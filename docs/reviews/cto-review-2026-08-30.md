# CTO review - 2026-08-30

## Verdict

Proceed with Git for the v0.1.0 approval ledger. At 10–20 approved changes per
working day, evidence review and reviewer availability are the material risks;
Git storage and merge mechanics are not. Keep cloud discovery outside approved
state and measure explicit exit criteria.

Codex Work is appropriate for planning, research coordination and preparing a
reviewable branch. It is not the system of record, an enforcement boundary or
an approval authority. Issues hold intent, one root agent owns writes, CI owns
acceptance and humans approve the change request.

## Required corrections to the original draft

1. Describe the repository as a target contract until executable schemas,
   fixtures and `modelo check` exist. Do not call design claims “as-built”.
2. Require evidence for every non-identity assertion. Optional evidence would
   contradict the catalogue objective.
3. Separate canonical models, approved offerings and provider routes.
   `(operator_id, model_id, geo)` is too lossy for AWS inference profiles and
   Azure or GCP deployments.
4. Replace free-form conditions with versioned condition references.
5. Use dimensional pricing from v0.1.0 rather than promising token-only fields
   that cannot faithfully represent image, cache, batch or provisioned prices.
6. Centralise paths and relative routes in `modelo.yaml`; keep host URL
   construction inside the GitHub or GitLab adapter.
7. Replace eleven public CI gates with one acceptance command and four visible
   outcomes. Internal stages may remain detailed.
8. Use `AGENTS.md` and open Agent Skills as the portable agent layer. Kiro and
   Codex configuration remain optional adapters.
9. State that Git is tamper-evident, not WORM-immutable, and verify remote host
   controls independently.
10. Initiate MAC through an issue and use only the change request as the
    approval unit; do not maintain a duplicate `proposals/` state tree.
11. Expose no Modelo application API. Use the selected Git provider API for all
    workflow writes and static artefacts for consumers.
12. Retain a redacted canonical evidence projection in Git. A digest of an
    expiring CI artefact is insufficient to reproduce factual validation.

## Repository comparison

| Repository | Strength to reuse | Limitation for Modelo |
|---|---|---|
| [models.dev](https://github.com/anomalyco/models.dev) | Separates laboratory model facts from provider serving details; strict data maintenance | Community discovery database, not enterprise approval; evidence semantics are insufficient |
| [truefoundry/models](https://github.com/truefoundry/models) | YAML catalogue, CUE validation and region-aware pricing | Provider-centred data and a visible PR queue increase review and conflict pressure |
| [Portkey-AI/models](https://github.com/Portkey-AI/models) | Broad pricing dimensions and provider coverage | Large provider-oriented records are harder to own and review as approval units |
| [ferro-labs/model-catalog](https://github.com/ferro-labs/model-catalog) | Static source/build/release shape is close to the target | Young project; external-source and enterprise-governance contracts are not yet strong enough |
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | Extensive provider edge-case coverage | A large shared pricing JSON file is a conflict and review anti-pattern for this use case |
| [Kubeflow Hub](https://github.com/kubeflow/hub) | Strong service/API patterns for a genuinely operational catalogue | Introduces service complexity that Modelo does not currently need |

These repositories are references, not authorities. Modelo accepts only facts
that its schemas, first-party evidence and validation can test.

## Platform portability

Use neutral kernel concepts and two thin mappings:

| Kernel capability | GitHub | GitLab |
|---|---|---|
| Intake | Issue Forms | Issue templates |
| Change request | Pull request | Merge request |
| Validation | Actions | GitLab CI |
| Serialisation | Merge queue | Merge train |
| Ownership | CODEOWNERS and rulesets | CODEOWNERS and approval rules |
| Static publication | Pages | Pages |

The clone baseline is host-neutral: clone, install locked dependencies, run
`modelo check`, then build. Codespaces, Workspaces, Kiro and IDE configuration
are accelerators, never prerequisites.

## Go/no-go controls for the next slice

Do not merge catalogue data until the next implementation slice supplies:

- JSON Schemas for models, offerings, evidence, routes and conditions;
- AWS provider-reference schema and captured first-party fixtures;
- one deterministic `modelo check` command;
- valid and invalid fixtures for every invariant;
- GitHub adapter workflows and a remote `modelo platform check`;
- a Pages build that publishes no private terms;
- a GitLab adapter conformance fixture proving core data is unchanged.
