# Modelo

Modelo is a Git-backed approval ledger and static publication system for an
enterprise AI model catalogue. Git provider issues initiate move/add/change
(MAC) work; pull or merge requests and trusted CI arbitrate acceptance. Modelo
does not expose an application API.

> **Bootstrap status:** T1 provides the locked Python package and fail-closed
> CLI foundation only. The validator, CI adapters, catalogue, static site and
> site templates, Pages deployment, issue and change-request templates, and
> Agent Skills are not implemented yet.
> Do not add real catalogue data before T10 passes.

## Repository planes

| Plane | Location | Purpose |
|---|---|---|
| Governed solution | `catalogue/`, `schemas/`, `modelo.yaml` | Reviewed source of truth |
| Build tooling | `tooling/modelo/`, `pyproject.toml`, `uv.lock` | Deterministic validation and generation |
| Static presentation | `site/` | Templates, content and local assets |
| Publication | `dist/` | Generated, tested and never committed |

Agent Skills under `.agents/skills/` will guide authorship and review. They are
not executable build inputs. Required CI contains no Node, npm or `npx` step.

## T1 clean-clone smoke test

Prerequisites are Git, Python `3.12.13` and `uv 0.11.33`.

```bash
uv sync --locked
uv run --locked modelo --version
uv run --locked modelo --help
uv run --locked modelo check --help
uv run --locked modelo build --help
```

Running `modelo check` or `modelo build` currently exits with status 2 because
their implementation slices have not landed. The static site has no deployed
URL while `site.base_url` is unset.

Read [SPEC.md](SPEC.md), [the machine contract](docs/contract.yaml),
[the implementation plan](docs/implementation-plan.md),
[the MAC contract](docs/mac-contract.md), [the site contract](docs/site-contract.md),
[the security contract](docs/security-contract.md) and
[CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
