# Modelo

Modelo is a Git-backed approval ledger and static publisher for an enterprise
AI model catalogue. Models record facts; offerings carry consumption approval.
Issues start work, while change requests and trusted CI decide it. There is no
application API; host concerns stay in Git adapters, not core records or schemas.

## Start Here

- Live synthetic demo: [j3brns996.github.io/Modelo/](https://j3brns996.github.io/Modelo/)
- Guided issue chooser: [Open a Modelo MAC request](https://github.com/j3brns996/Modelo/issues/new/choose)
  for add, change, revoke, move or batch requests.
- Repository rules and contracts: [SPEC.md](SPEC.md) and [docs/contract.yaml](docs/contract.yaml)

Demo records are synthetic, not enterprise approval. Catalogue work starts in
the issue chooser, capturing the intent and subjects a change must preserve.

## Product tour

These synthetic-demo captures are not approval, launch or T10 evidence and
contain no production data.

![Modelo synthetic-demo home showing navigation, synthetic status and catalogue totals](docs/img/modelo-home.png)

![Modelo synthetic catalogue showing filters and model result cards](docs/img/modelo-catalogue.png)

## Why Facts And Approval Are Separate

A model describes a named release; it does not permit enterprise use. An
offering is the approval unit, joining it to provider routes, policy rationale
and evidenced conditions. Provider availability, documentation and demos are
observations, not approval. Enterprise use follows the approved offering and
route.

## Current Status

T8 pre-merge CI, T9 and the public synthetic Pages demo are implemented.
Production post-merge release and receipt automation and the T10 remote gate
remain blocked. No production catalogue data is published; agent approval is
disabled. The site demonstrates static publication, not launch completion.

Do not add real production catalogue data before T10 passes remotely.

## Choose Your Path

| If you want to... | Start here |
|---|---|
| Browse the live site | [Synthetic demo](https://j3brns996.github.io/Modelo/) |
| Start a proposed change | [Guided issue chooser](https://github.com/j3brns996/Modelo/issues/new/choose) |
| Draft an add or change | [Interactive proposal helper](https://j3brns996.github.io/Modelo/propose/#builder) |
| Use the local authoring commands | [Authoring guide](docs/authoring.md) |
| Learn how to contribute safely | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Read the docs index | [docs/README.md](docs/README.md) |
| Understand the product rules | [SPEC.md](SPEC.md) |
| Inspect the machine contract | [docs/contract.yaml](docs/contract.yaml) |

## How A Change Is Decided

A proposal starts with a linked issue and continues on a one-writer topic
branch. The change request binds its operation to the reviewed base, head and
tree. Trusted CI validates that exact head; missing, stale, skipped or failed
results cannot accept it. Catalogue facts need admissible evidence. Human
CODEOWNER approval remains required for control and documentation paths. A new
commit invalidates earlier checks and reviews.

## Five-Minute Setup

```bash
uv sync --locked
uv run --locked modelo --version
uv build --offline --no-cache
uv run --locked modelo-local-ci run --base <base-sha> --head <head-sha> --as-of YYYY-MM-DD --jobs 3
```

`modelo-local-ci` is advisory; `modelo/check` remains the acceptance gate. Use
the change request's exact base and head SHAs so preflight matches review.

Builds take explicit provenance inputs. `--base-commit` names the baseline;
source and tree values bind output to reviewed Git content. See
[docs/contract.yaml](docs/contract.yaml) for the required set.

Authoring helpers prepare drafts only; the linked issue and trusted compiler
remain authoritative.

Work from a clean worktree after reading repository rules and relevant schemas.
Run narrow tests before local CI. Never commit generated `dist/` output.

## Four Planes

| Plane | Location | Purpose |
|---|---|---|
| Governed solution | `catalogue/`, `schemas/`, `modelo.yaml` | Reviewed source of truth |
| Build tooling | `tooling/modelo/`, `pyproject.toml`, `uv.lock` | Deterministic validation and generation |
| Static presentation | `site/` | Templates, content and local assets |
| Publication | `dist/` | Generated output, never committed |

## Configuration and validation authority

[`modelo.yaml`](modelo.yaml) owns configured repository paths, site and issue
routes, publication profiles, GitHub or GitLab adapter selection, platform
controls, toolchain pins and build inputs. The tooling loads those values.

Validation has separate, explicit owners. JSON schemas define record shapes
and provenance annotations. The Python validator enforces cross-record,
evidence and change semantics. [docs/contract.yaml](docs/contract.yaml) records
the compact machine contract, while [SPEC.md](SPEC.md) explains its rationale.
Configuration does not replace those shape or semantic authorities.

## Documentation Map

- [CONTRIBUTING.md](CONTRIBUTING.md) covers governed contribution and preflight.
- [docs/README.md](docs/README.md) is the repository docs index.
- [docs/authoring.md](docs/authoring.md) explains drafting helpers and authority.
- [SPEC.md](SPEC.md) explains the product rationale, scope and invariants.
- [docs/contract.yaml](docs/contract.yaml) is the compact machine contract.

## Security And Reuse

- [SECURITY.md](SECURITY.md) is the security and recovery guidance.
- There is no root repository licence file yet.
- Reuse terms are undecided.
- Public visibility does not grant reuse rights.
- Do not post secrets, tokens or private evidence in issues, pull requests or
  public comments.
  If something belongs in the ledger, capture it through the governed
  workflow instead of copying it into chat or an ad hoc note.
